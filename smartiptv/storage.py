"""Account-isolated favorites and checkpoints, plus user-scoped Windows DPAPI."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from .client import Credentials
from .models import Content


def data_directory():
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "SmartIPTV" if base else Path.home() / ".local" / "share" / "SmartIPTV"


def account_key(credentials):
    value = credentials.server.rstrip("/").lower() + "\0" + credentials.username
    return hashlib.sha256(value.encode()).hexdigest()


def _dpapi(raw, decrypt=False):
    if os.name != "nt":
        raise OSError("A sessão persistente requer o Windows.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("O Windows não conseguiu proteger ou recuperar a sessão.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class SessionStore:
    def __init__(self, directory=None):
        self.path = Path(directory or data_directory()) / "session.bin"

    def save(self, credentials):
        raw = json.dumps({"server": credentials.server, "username": credentials.username, "password": credentials.password}).encode()
        encrypted = _dpapi(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_bytes(encrypted)
        temp.replace(self.path)

    def load(self):
        if not self.path.exists():
            return None
        try:
            data = json.loads(_dpapi(self.path.read_bytes(), decrypt=True))
            return Credentials(str(data["server"]), str(data["username"]), str(data["password"]))
        except (OSError, ValueError, KeyError, TypeError):
            raise OSError("Não foi possível recuperar a sessão salva. Entre novamente.") from None

    def clear(self):
        self.path.unlink(missing_ok=True)


class Library:
    def __init__(self, directory=None):
        directory = Path(directory or data_directory())
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "library.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS favorites (account TEXT, uid TEXT, item TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(account,uid))")
        self.db.execute("CREATE TABLE IF NOT EXISTS progress (account TEXT, uid TEXT, item TEXT NOT NULL, position INTEGER NOT NULL, duration INTEGER NOT NULL, finished INTEGER NOT NULL, updated REAL NOT NULL, PRIMARY KEY(account,uid))")
        self.db.commit()
        self.account = ""
        self.favorites = {}
        self.progress = {}

    @property
    def auto_next_enabled(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='auto_next'").fetchone()
        return bool(row and row[0] == "true")

    def set_auto_next(self, enabled):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('auto_next', ?)", ("true" if enabled else "false",))

    def select_account(self, credentials):
        self.account = account_key(credentials)
        self.favorites = {}
        self.progress = {}
        for uid, raw in self.db.execute("SELECT uid,item FROM favorites WHERE account=? ORDER BY updated DESC", (self.account,)):
            try:
                self.favorites[uid] = Content.from_dict(json.loads(raw))
            except (ValueError, TypeError, KeyError):
                pass
        for uid, raw, position, duration, finished, updated in self.db.execute("SELECT uid,item,position,duration,finished,updated FROM progress WHERE account=?", (self.account,)):
            try:
                self.progress[uid] = {"item": Content.from_dict(json.loads(raw)), "position": position, "duration": duration, "finished": bool(finished), "updated": updated}
            except (ValueError, TypeError, KeyError):
                pass

    def is_favorite(self, item):
        return item.uid in self.favorites

    def toggle_favorite(self, item):
        if self.is_favorite(item):
            self.db.execute("DELETE FROM favorites WHERE account=? AND uid=?", (self.account, item.uid))
            del self.favorites[item.uid]
            value = False
        else:
            self.db.execute("INSERT OR REPLACE INTO favorites VALUES (?,?,?,?)", (self.account, item.uid, json.dumps(item.to_dict()), time.time()))
            self.favorites[item.uid] = item
            value = True
        self.db.commit()
        return value

    def record_progress(self, item, position, duration, finished=False):
        if item.kind not in ("movie", "episode") or (position < 1000 and not finished):
            return
        position, duration = max(0, int(position)), max(0, int(duration))
        if duration and position >= duration * .98 and duration - position <= 60000:
            finished = True
        updated = time.time()
        self.db.execute("INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?)", (self.account, item.uid, json.dumps(item.to_dict()), position, duration, int(finished), updated))
        self.db.commit()
        self.progress[item.uid] = {"item": item, "position": position, "duration": duration, "finished": bool(finished), "updated": updated}

    def checkpoint(self, item):
        if item.kind == "series":
            candidates = [p for p in self.progress.values() if p["item"].series_id == item.id and not p["finished"]]
            return max(candidates, key=lambda p: p["updated"], default=None)
        entry = self.progress.get(item.uid)
        return entry if entry and not entry["finished"] else None

    def continuing(self):
        return [p["item"] for p in sorted(self.progress.values(), key=lambda p: p["updated"], reverse=True) if not p["finished"] and p["position"] >= 1000]

    def remove_progress(self, item):
        self.db.execute("DELETE FROM progress WHERE account=? AND uid=?", (self.account, item.uid))
        self.db.commit()
        self.progress.pop(item.uid, None)

    def close(self):
        self.db.close()
