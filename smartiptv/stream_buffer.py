"""Bounded VOD read-ahead on loopback; one upstream media connection at a time.

Bytes are passed through unchanged, including HTTP ranges used for seeking.
No media or credentials are written to disk. Live/manifest streams bypass this.
"""
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import re
import secrets
import socket
import threading
from urllib.parse import urljoin, urlsplit


class _ReadAhead:
    CHUNK = 64 * 1024
    LIMIT = 8 * 1024 * 1024
    PREFILL = 2 * 1024 * 1024

    def __init__(self, owner, url, byte_range, head=False):
        self.owner, self.url, self.byte_range, self.head = owner, url, byte_range, head
        self.condition = threading.Condition()
        self.parts = deque()
        self.buffered = 0
        self.peak_buffered = 0
        self.cancelled = threading.Event()
        self.done = False
        self.failed = False
        self.status = None
        self.headers = {}
        self.transport = None
        threading.Thread(target=self._fill, daemon=True).start()

    def cancel(self):
        self.cancelled.set()
        with self.condition:
            transport = self.transport
            self.parts.clear()
            self.buffered = 0
            self.condition.notify_all()
        # Socket shutdown interrupts a blocked network read without waiting
        # for HTTPResponse's buffered-reader lock on the GUI thread.
        if transport:
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _fill(self):
        acquired = False
        connection = response = None
        try:
            while not self.cancelled.is_set():
                if self.owner.upstream.acquire(timeout=.1):
                    acquired = True
                    break
            if not acquired or self.cancelled.is_set():
                return
            url = self.url
            for _ in range(6):
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname:
                    raise ValueError("Unsupported media endpoint")
                cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
                connection = cls(parsed.hostname, parsed.port, timeout=10)
                connection.connect()
                with self.condition:
                    self.transport = connection.sock
                if self.cancelled.is_set():
                    return
                headers = {"User-Agent": "VLC/3.0.21 LibVLC/3.0.21", "Accept-Encoding": "identity", "Connection": "close"}
                if self.byte_range:
                    headers["Range"] = self.byte_range
                connection.request("HEAD" if self.head else "GET", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""), headers=headers)
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308) and response.getheader("Location"):
                    url = urljoin(url, response.getheader("Location"))
                    response.close(); connection.close()
                    continue
                break
            else:
                raise ValueError("Too many redirects")
            with self.condition:
                self.status = response.status
                self.headers = {name: value for name in ("Content-Length", "Content-Range", "Content-Type", "Accept-Ranges")
                                if (value := response.getheader(name)) is not None}
                self.condition.notify_all()
            if self.head or self.status not in (200, 206):
                return
            remaining = response.length
            while not self.cancelled.is_set():
                with self.condition:
                    self.condition.wait_for(lambda: self.buffered + self.CHUNK <= self.LIMIT or self.cancelled.is_set())
                if self.cancelled.is_set():
                    break
                part = response.read1(self.CHUNK)
                if not part:
                    if remaining is not None and remaining > 0:
                        raise OSError("Incomplete media response")
                    break
                if remaining is not None:
                    remaining -= len(part)
                with self.condition:
                    if self.cancelled.is_set():
                        break
                    self.parts.append(part)
                    self.buffered += len(part)
                    self.peak_buffered = max(self.peak_buffered, self.buffered)
                    self.condition.notify_all()
        except Exception:
            self.failed = not self.cancelled.is_set()
        finally:
            if response:
                response.close()
            if connection:
                connection.close()
            with self.condition:
                self.transport = None
                self.done = True
                self.condition.notify_all()
            if acquired:
                self.owner.upstream.release()

    def ready(self):
        with self.condition:
            self.condition.wait_for(lambda: self.cancelled.is_set() or self.done or self.status is not None, timeout=12)
            # Prefer a small reserve before starting playback, but bound the
            # additional wait so a slow provider cannot hang startup here.
            if self.status is not None and not self.head:
                self.condition.wait_for(lambda: self.cancelled.is_set() or self.done or self.buffered >= self.PREFILL, timeout=8)
            return self.status is not None and not self.cancelled.is_set()

    def read(self):
        with self.condition:
            self.condition.wait_for(lambda: self.parts or self.done or self.cancelled.is_set())
            if self.cancelled.is_set() or not self.parts:
                return b""
            part = self.parts.popleft()
            self.buffered -= len(part)
            self.condition.notify_all()
            return part


class StreamBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.upstream = threading.Lock()
        self.closed = False
        self.current = None
        self.url = ""
        self.token = ""
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_HEAD(self):
                self._serve(True)

            def do_GET(self):
                self._serve(False)

            def _serve(self, head):
                session = None
                try:
                    self.connection.settimeout(10)
                    byte_range = self.headers.get("Range")
                    if byte_range and not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", byte_range):
                        self.send_error(416)
                        return
                    with owner.lock:
                        if owner.closed or self.path != "/" + owner.token or not owner.url:
                            self.send_error(404)
                            return
                        if owner.current:
                            owner.current.cancel()
                        session = _ReadAhead(owner, owner.url, byte_range, head)
                        owner.current = session
                    if not session.ready():
                        self.send_error(502)
                        return
                    self.send_response(session.status)
                    for name, value in session.headers.items():
                        # Error pages are never forwarded; they may contain
                        # a provider URL. Preserve range/length only for media.
                        if session.status in (200, 206) or name == "Content-Range":
                            self.send_header(name, value)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if not head and session.status in (200, 206):
                        while part := session.read():
                            self.wfile.write(part)
                except (OSError, ValueError):
                    pass
                finally:
                    self.close_connection = True
                    if session:
                        session.cancel()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .1}, daemon=True).start()

    def source(self, url):
        with self.lock:
            if self.closed:
                raise RuntimeError("Media buffer is closed")
            if self.current:
                self.current.cancel()
            self.url, self.token = url, secrets.token_urlsafe(24)
            return f"http://127.0.0.1:{self.server.server_port}/{self.token}"

    def close(self):
        with self.lock:
            self.closed = True
            self.url = self.token = ""
            if self.current:
                self.current.cancel()
        def stop():
            self.server.shutdown()
            self.server.server_close()
        threading.Thread(target=stop, daemon=True).start()
