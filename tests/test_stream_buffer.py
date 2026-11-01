from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from smartiptv.stream_buffer import StreamBuffer, _ReadAhead


class StreamBufferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = bytes(range(256)) * (48 * 1024)
        cls.received = []
        cls.pause_started = threading.Event()
        cls.release = threading.Event()
        owner = cls
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302); self.send_header("Location", "/movie/demo/demopass/1.mp4"); self.end_headers(); return
                if self.path == "/error":
                    self.send_response(403); self.end_headers(); self.wfile.write(b"private-provider-url-secret"); return
                owner.received.append((self.headers.get("Range"), self.headers.get("User-Agent")))
                start, end = 0, len(owner.data) - 1
                if value := self.headers.get("Range"):
                    first, last = value[6:].split("-")
                    start, end = int(first), int(last) if last else end
                if start >= len(owner.data):
                    self.send_response(416); self.send_header("Content-Range", f"bytes */{len(owner.data)}"); self.end_headers(); return
                end = min(end, len(owner.data)-1)
                self.send_response(206 if self.headers.get("Range") else 200)
                self.send_header("Content-Length", str(end-start+1))
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                if self.headers.get("Range"): self.send_header("Content-Range", f"bytes {start}-{end}/{len(owner.data)}")
                self.end_headers()
                try:
                    for i in range(start, end+1, 32768):
                        if self.path == "/jitter" and i == 3 * 1024 * 1024:
                            owner.pause_started.set()
                            owner.release.wait(3)
                        self.wfile.write(owner.data[i:min(i+32768,end+1)])
                        if self.path == "/slow": time.sleep(.002)
                except OSError: pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        self.buffer = StreamBuffer()

    def tearDown(self):
        self.buffer.close()

    def test_passes_bytes_ranges_and_provider_headers_without_changes(self):
        url = self.buffer.source(self.origin + "/movie/demo/demopass/1.mp4")
        self.assertNotIn("demopass", url)
        with urlopen(Request(url, headers={"Range": "bytes=12345-234567"}), timeout=10) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.getheader("Content-Range"), f"bytes 12345-234567/{len(self.data)}")
            self.assertEqual(response.read(), self.data[12345:234568])
        self.assertIn(("bytes=12345-234567", "VLC/3.0.21 LibVLC/3.0.21"), self.received)

    def test_prefetch_is_bounded_and_runs_ahead_of_consumer(self):
        session = _ReadAhead(self.buffer, self.origin + "/slow", None)
        self.buffer.current = session
        self.assertTrue(session.ready())
        deadline = time.monotonic()+5
        while session.buffered < session.LIMIT and time.monotonic()<deadline: time.sleep(.01)
        self.assertGreaterEqual(session.buffered, session.PREFILL)
        self.assertLessEqual(session.peak_buffered, session.LIMIT + session.CHUNK)
        part = session.read()
        self.assertTrue(part)
        self.assertEqual(part, self.data[:len(part)])
        session.cancel()
        deadline=time.monotonic()+2
        while not session.done and time.monotonic()<deadline: time.sleep(.01)
        self.assertTrue(session.done)
        self.assertFalse(session.parts)

    def test_seek_cancels_old_request_and_preserves_new_range(self):
        url = self.buffer.source(self.origin + "/slow")
        first = urlopen(url, timeout=10)
        old = self.buffer.current
        with urlopen(Request(url, headers={"Range": "bytes=9000000-9000999"}), timeout=10) as second:
            self.assertEqual(second.read(), self.data[9000000:9001000])
            self.assertTrue(old.cancelled.is_set())
            self.assertTrue(old.done)
        first.close()

    def test_stale_and_unknown_tokens_never_contact_provider(self):
        stale = self.buffer.source(self.origin + "/slow")
        self.buffer.source(self.origin + "/redirect")
        before = len(self.received)
        with self.assertRaises(HTTPError) as result: urlopen(stale, timeout=5)
        self.assertEqual(result.exception.code, 404)
        self.assertEqual(len(self.received), before)

    def test_redirect_and_error_bodies_do_not_leak_provider_urls(self):
        url = self.buffer.source(self.origin + "/redirect")
        with urlopen(Request(url, headers={"Range":"bytes=1-1000"}),timeout=10) as response:
            self.assertEqual(response.read(), self.data[1:1001])
        url = self.buffer.source(self.origin + "/error")
        with self.assertRaises(HTTPError) as result: urlopen(url,timeout=10)
        self.assertEqual(result.exception.code, 403)
        self.assertNotIn(b"secret", result.exception.read())

    def test_close_interrupts_read_ahead_without_blocking_caller(self):
        url = self.buffer.source(self.origin + "/slow")
        with urlopen(url,timeout=10) as response:
            self.assertTrue(response.read(1))
            before=time.monotonic()
            self.buffer.close()
            self.assertLess(time.monotonic()-before, .5)
        self.assertEqual(self.buffer.url, "")

    def test_prefetched_media_remains_available_during_origin_interruption(self):
        self.pause_started.clear(); self.release.clear()
        session = _ReadAhead(self.buffer, self.origin + "/jitter", None)
        self.buffer.current = session
        try:
            self.assertTrue(session.ready())
            self.assertTrue(self.pause_started.wait(2))
            self.assertFalse(self.release.is_set())
            self.assertTrue(session.read())
            self.assertTrue(session.read())
            self.assertFalse(self.release.is_set())
        finally:
            self.release.set()
            session.cancel()


if __name__ == "__main__": unittest.main()
