"""Shared fixtures: a fake Ollama server, and a local address where nothing listens."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class FakeOllamaHandler(BaseHTTPRequestHandler):
    """Implements the Ollama endpoints the app uses: GET /api/tags, POST /api/show and streaming POST /api/chat."""

    def do_GET(self):
        self._record(None)
        if self.path == "/api/tags":
            self._send_json({"models": [{"name": name} for name in self.server.models]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self._record(json.loads(self.rfile.read(length) or b"{}"))
        if self.path == "/api/show":
            self._send_json({"capabilities": self.server.capabilities})
        elif self.path == "/api/chat":
            self._stream_chat()
        else:
            self.send_error(404)

    def _stream_chat(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for piece in self.server.thinking_pieces:
            self._write_line({"message": {"role": "assistant", "content": "", "thinking": piece}, "done": False})
        for piece in self.server.reply_pieces:
            self._write_line({"message": {"role": "assistant", "content": piece}, "done": False})
        self._write_line({"message": {"role": "assistant", "content": ""}, "done": True})

    def _record(self, body):
        self.server.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})

    def _send_json(self, data):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _write_line(self, data):
        self.wfile.write((json.dumps(data) + "\n").encode())

    def log_message(self, format, *args):  # keep test output clean
        pass


@pytest.fixture
def fake_ollama():
    """A running fake Ollama server.

    Set `.models`, `.capabilities`, `.thinking_pieces` and `.reply_pieces`. Inspect `.requests`.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
    server.models = ["qwen3:4b"]
    server.capabilities = ["completion", "thinking"]
    server.thinking_pieces = []
    server.reply_pieces = ["Hello"]
    server.requests = []
    server.url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def closed_port_url() -> str:
    """URL of a local port with no server, to simulate Ollama not running."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
