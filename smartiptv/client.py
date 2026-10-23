"""Read-only Xtream client. All requests run outside the interface thread."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import urllib.error
import urllib.parse
import urllib.request

from .models import content_from_api, episodes_from_api
from .validation import server_error


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class Credentials:
    server: str
    username: str
    password: str = field(repr=False)


class XtreamClient:
    def __init__(self, credentials):
        self.credentials = credentials
        self.account = {}

    def request(self, action=None, **extra):
        credentials = self.credentials
        params = {"username": credentials.username, "password": credentials.password}
        if action:
            params["action"] = action
        params.update(extra)
        endpoint = credentials.server.rstrip("/") + "/player_api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(endpoint, headers={
            "User-Agent": "VLC/3.0.21 LibVLC/3.0.21", "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
                if len(raw) > 64 * 1024 * 1024:
                    raise ProviderError("O catálogo recebido é maior que o limite suportado nesta versão.")
            payload = json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderError("Acesso recusado. Confira os dados e a situação da sua conta.") from None
            raise ProviderError(f"O servidor respondeu com erro {exc.code}. Confira o endereço ou tente novamente.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("Não foi possível conectar. Confira sua internet e o endereço do servidor.") from None
        except (ValueError, UnicodeError):
            raise ProviderError("O servidor não retornou uma resposta Xtream válida.") from None
        if isinstance(payload, dict) and isinstance(payload.get("user_info"), dict):
            user = payload["user_info"]
            if str(user.get("auth", "0")) != "1":
                raise ProviderError("Usuário ou senha não aceitos pelo servidor.")
            if user.get("status") and str(user["status"]).lower() != "active":
                raise ProviderError("Sua conta está inativa ou expirada. Consulte seu provedor.")
        return payload

    def authenticate(self):
        problem = server_error(self.credentials.server)
        if problem:
            raise ProviderError(problem)
        payload = self.request()
        if not isinstance(payload, dict) or not isinstance(payload.get("user_info"), dict):
            raise ProviderError("Não foi possível confirmar a autenticação Xtream.")
        self.account = {k: payload["user_info"].get(k) for k in ("status", "active_cons", "max_connections", "exp_date", "allowed_output_formats")}
        return self.account

    def _section(self, kind, categories_action, items_action):
        categories = self.request(categories_action)
        entries = self.request(items_action)
        if not isinstance(categories, list) or not isinstance(entries, list):
            raise ProviderError("O servidor enviou um catálogo em formato inesperado. Tente atualizar.")
        groups = [{"id": str(c.get("category_id", "")), "name": str(c.get("category_name") or "Sem categoria")} for c in categories if isinstance(c, dict)]
        items, seen = [], set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item = content_from_api(kind, entry)
            if item and item.uid not in seen:
                seen.add(item.uid)
                items.append(item)
        return kind, {"categories": groups, "items": items}

    def catalog(self):
        sections = [
            ("live", "get_live_categories", "get_live_streams"),
            ("movie", "get_vod_categories", "get_vod_streams"),
            ("series", "get_series_categories", "get_series"),
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            return dict(pool.map(lambda args: self._section(*args), sections))

    def series_details(self, series):
        payload = self.request("get_series_info", series_id=series.id)
        if not isinstance(payload, dict):
            raise ProviderError("Não foi possível carregar os episódios desta série.")
        return {"episodes": episodes_from_api(series, payload), "info": payload.get("info") or {}}

    def movie_details(self, movie):
        payload = self.request("get_vod_info", vod_id=movie.id)
        return payload.get("info", {}) if isinstance(payload, dict) else {}

    def playback_url(self, item):
        if item.kind not in ("live", "movie", "episode"):
            raise ProviderError("Selecione um episódio para reproduzir a série.")
        c = self.credentials
        kind = "series" if item.kind == "episode" else item.kind
        extension = "ts" if item.kind == "live" else item.extension
        if not extension or not extension.isalnum() or len(extension) > 8:
            extension = "mp4"
        parts = [kind, c.username, c.password, f"{item.id}.{extension}"]
        return c.server.rstrip("/") + "/" + "/".join(urllib.parse.quote(str(p), safe="") for p in parts)
