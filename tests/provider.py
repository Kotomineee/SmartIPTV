"""Local provider fixture. Never contacts an IPTV service."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit


class Provider:
    def __init__(self, media_file=None):
        self.media_file = Path(media_file) if media_file else None
        self.bad_catalog = False
        self.active_connections = "0"
        self.media_requests = []
        self.failed_media = set()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                path = urlsplit(self.path)
                if path.path.rsplit("/", 1)[-1] in owner.failed_media:
                    self.send_error(503)
                    return
                if owner.media_file and (path.path == "/sample.mp4" or path.path.startswith(("/movie/demo/demopass/", "/series/demo/demopass/"))):
                    owner.media_requests.append(path.path.rsplit("/", 1)[-1])
                    raw = owner.media_file.read_bytes()
                    start, end = 0, len(raw) - 1
                    range_value = self.headers.get("Range")
                    if range_value and range_value.startswith("bytes="):
                        first, _, last = range_value[6:].partition("-")
                        start, end = int(first or 0), int(last) if last else end
                    end = min(end, len(raw) - 1)
                    self.send_response(206 if range_value else 200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    if range_value:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{len(raw)}")
                    body = raw[start:end + 1]
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    try:
                        self.wfile.write(body)
                    except (ConnectionResetError, BrokenPipeError):
                        pass
                    return
                params = parse_qs(path.query)
                username = params.get("username", [""])[0]
                password = params.get("password", [""])[0]
                if password != "demopass" or username not in ("demo", "expired"):
                    payload = {"user_info": {"auth": 0}}
                elif username == "expired":
                    payload = {"user_info": {"auth": 1, "status": "Expired"}}
                else:
                    payload = owner.payload(params.get("action", [""])[0])
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def payload(self, action):
        if not action:
            return {"user_info": {"auth": 1, "status": "Active", "active_cons": self.active_connections, "max_connections": "2", "exp_date": "1893456000", "allowed_output_formats": ["ts", "m3u8"]}}
        if action.endswith("_categories"):
            names = {"get_live_categories": ("CANAIS | ABERTOS", "CANAIS | NOTÍCIAS"), "get_vod_categories": ("FILMES | LANÇAMENTOS", "FILMES | AVENTURA"), "get_series_categories": ("SÉRIES | DRAMA", "SÉRIES | DOCUMENTÁRIOS")}[action]
            return [{"category_id": str(i + 1), "category_name": name, "parent_id": 0} for i, name in enumerate(names)]
        if action == "get_live_streams":
            return [{"stream_id": i, "name": name, "category_id": str(1 if i < 3 else 2), "added": str(1700000000 + i), "stream_icon": ""} for i, name in enumerate(("Canal Cultura", "Canal Natureza", "Notícias ao vivo"), 1)]
        if action == "get_vod_streams":
            names = ("Além do horizonte", "Aurora", "Cidade em movimento", "O caminho de volta", "Oceano azul", "Uma nova estação", "Casa de vidro", "Viagem ao amanhã")
            items = [{"stream_id": i + 1, "name": names[i % len(names)] + (f" {i // 8 + 1}" if i >= 8 else ""), "category_id": str(i % 2 + 1), "category_ids": [str(i % 2 + 1)], "added": str(1700000000 + i * 100), "year": "2025", "rating": "8.2", "container_extension": "mp4", "stream_icon": ""} for i in range(80)]
            return items + [items[0]]
        if action == "get_series":
            if self.bad_catalog:
                return {"error": "invalid fixture"}
            return [{"series_id": i, "name": name, "category_id": str(i % 2 + 1), "last_modified": str(1700000000 + i), "year": "2026", "plot": "Uma história sobre descobertas e novos caminhos.", "cover": ""} for i, name in enumerate(("Novos caminhos", "Entre cidades", "Nosso planeta", "A última estação"), 1)]
        if action == "get_series_info":
            return {"seasons": [], "info": {"plot": "Uma história sobre descobertas e novos caminhos."}, "episodes": {str(s): [{"id": str(s * 100 + e), "season": s, "episode_num": e, "title": f"Episódio {e}: novos caminhos", "container_extension": "mp4", "info": {"duration_secs": 1200}} for e in (1, 2, 3)] for s in (1, 2)}}
        if action == "get_vod_info":
            return {"info": {"plot": "Uma jornada de descobertas, encontros e paisagens inesquecíveis.", "genre": "Aventura"}, "movie_data": {}}
        return []
