"""Account-isolated favorites and checkpoints, plus user-scoped Windows DPAPI."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time

from .client import Credentials
from .models import Content, content_root


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
        self.last_progress_update = 0.0

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
        # Convert legacy episode favorites once, preserving a saved series and
        # its richer metadata if both records already exist for this account.
        rows = list(self.db.execute("SELECT uid,item,updated FROM favorites WHERE account=? ORDER BY updated DESC,rowid DESC", (self.account,)))
        with self.db:
            for uid, raw, updated in rows:
                try:
                    item = Content.from_dict(json.loads(raw))
                except (ValueError, TypeError, KeyError):
                    continue
                if item.kind == "episode" and (series := content_root(item)):
                    self.db.execute("INSERT OR IGNORE INTO favorites VALUES (?,?,?,?)", (self.account, series.uid, json.dumps(series.to_dict()), updated))
                    self.db.execute("DELETE FROM favorites WHERE account=? AND uid=?", (self.account, uid))
        for uid, raw in self.db.execute("SELECT uid,item FROM favorites WHERE account=? ORDER BY updated DESC", (self.account,)):
            try:
                item = Content.from_dict(json.loads(raw))
                if item.kind != "episode":
                    self.favorites[uid] = item
            except (ValueError, TypeError, KeyError):
                pass
        for uid, raw, position, duration, finished, updated in self.db.execute("SELECT uid,item,position,duration,finished,updated FROM progress WHERE account=? ORDER BY updated DESC,rowid DESC", (self.account,)):
            try:
                self.progress[uid] = {"item": Content.from_dict(json.loads(raw)), "position": position, "duration": duration, "finished": bool(finished), "updated": updated}
            except (ValueError, TypeError, KeyError):
                pass
        self.last_progress_update = max((entry["updated"] for entry in self.progress.values()), default=0.0)

    def is_favorite(self, item):
        item = content_root(item)
        return bool(item and item.uid in self.favorites)

    def toggle_favorite(self, item):
        item = content_root(item)
        if item is None:
            return False
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
        # Windows clocks can assign the same timestamp to consecutive saves.
        # Keep writes strictly ordered, even if the system clock moves back.
        updated = max(time.time(), math.nextafter(self.last_progress_update, math.inf))
        self.db.execute("INSERT OR REPLACE INTO progress VALUES (?,?,?,?,?,?,?)", (self.account, item.uid, json.dumps(item.to_dict()), position, duration, int(finished), updated))
        self.db.commit()
        self.last_progress_update = updated
        self.progress[item.uid] = {"item": item, "position": position, "duration": duration, "finished": bool(finished), "updated": updated}

    def checkpoint(self, item):
        if item.kind == "series":
            candidates = [p for p in self.progress.values() if p["item"].kind == "episode" and p["item"].series_id == item.id]
            latest = max(candidates, key=lambda p: p["updated"], default=None)
            return latest if latest and not latest["finished"] else None
        entry = self.progress.get(item.uid)
        return entry if entry and not entry["finished"] else None

    def continuing(self):
        result, seen = [], set()
        for entry in sorted(self.progress.values(), key=lambda p: p["updated"], reverse=True):
            item = entry["item"]
            key = ("series", item.series_id) if item.kind == "episode" and item.series_id else ("item", item.uid)
            if key in seen:
                continue
            seen.add(key)
            # A completed latest episode must not resurrect an older one.
            if not entry["finished"] and entry["position"] >= 1000:
                result.append(item)
        return result

    def remove_progress(self, item):
        if item.kind == "episode" and item.series_id:
            entries = [entry["item"].uid for entry in self.progress.values()
                       if entry["item"].kind == "episode" and entry["item"].series_id == item.series_id]
        else:
            entries = [item.uid]
        self.db.executemany("DELETE FROM progress WHERE account=? AND uid=?", [(self.account, uid) for uid in entries])
        self.db.commit()
        for uid in entries:
            self.progress.pop(uid, None)

    def close(self):
        self.db.close()
