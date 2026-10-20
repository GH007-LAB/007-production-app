# -*- coding: utf-8 -*-
"""เซิร์ฟเวอร์ทดสอบหน้าเว็บ Fleet007: /fleet007 = app/fleet007.html · /api/fleet/* = handler ตัวจริง + FakeSB (อีเมลจำลอง)
usage: python3 serve_fixture.py <port>   ·  GET /__mail → อีเมลที่ "ส่ง" แล้ว"""
import datetime
import http.server
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_fleet as T      # noqa: E402  (FakeSB + fleet_api)

F = T.F
SB = T.FakeSB()
SB.add_staff(1, "tok-hr", "", "แอน", position="เจ้าหน้าที่ฝ่ายบุคคล (HR)", app_id=12)
SB.add_staff(4, "tok-sales", "SKN", "นิด", position="พนักงานขาย", app_id=12)
MAIL = []
F.send_email = lambda env, to, subject, html, text: MAIL.append({"to": to, "subject": subject, "text": text}) or "fake"
NOW = datetime.datetime(2026, 10, 20, 1, 0, tzinfo=datetime.timezone.utc)


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, status, data, ctype="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _go(self, method):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        if u.path == "/fleet007":
            with open(os.path.join(os.path.dirname(HERE), "app", "fleet007.html"), "rb") as f:
                html = f.read().replace(b"<head>", b"<head><script>window.__F7_TOKEN__=localStorage.t;</script>", 1)
            return self._send(200, html, "text/html; charset=utf-8")
        if u.path == "/__mail":
            return self._send(200, json.dumps(MAIL, ensure_ascii=False).encode())
        if u.path.startswith("/api/fleet/"):
            SB.clock = NOW
            st, out = F.handle(u.path.rsplit("/", 1)[1], method, dict(self.headers.items()), body, {},
                               env=T.ENV, sb=SB, now=NOW)
            return self._send(st, json.dumps(out, ensure_ascii=False, default=str).encode())
        self._send(404, b"{}")

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
