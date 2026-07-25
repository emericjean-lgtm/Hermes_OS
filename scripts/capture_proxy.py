"""Transparent capture proxy: 127.0.0.1:11435 -> 127.0.0.1:11434 (real Ollama).

Logs every request body Hermes Agent sends (system prompt, tools, messages)
to capture_log.jsonl, then forwards unmodified to the real Ollama server and
relays the response back byte-for-byte. Purely diagnostic - does not alter
behavior.
"""
import http.server
import json
import socketserver
import time
import urllib.request
import urllib.error

UPSTREAM = "http://127.0.0.1:11434"
LOG_PATH = r"C:\Users\emeri\hermes-ollama\scripts\capture_log.jsonl"


class Handler(http.server.BaseHTTPRequestHandler):
    def _proxy(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if body:
            try:
                parsed = json.loads(body)
                with open(LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": time.time(),
                        "path": self.path,
                        "body": parsed,
                    }) + "\n")
            except Exception as e:
                print(f"[capture] failed to log body: {e}")

        req = urllib.request.Request(
            UPSTREAM + self.path,
            data=body if body else None,
            method=self.command,
        )
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length"):
                req.add_header(k, v)

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())

    def do_POST(self):
        self._proxy()

    def do_GET(self):
        self._proxy()

    def log_message(self, fmt, *args):
        print("[capture]", fmt % args)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("127.0.0.1", 11435), Handler) as httpd:
        print("Capture proxy listening on 127.0.0.1:11435 -> " + UPSTREAM)
        httpd.serve_forever()
