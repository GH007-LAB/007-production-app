# -*- coding: utf-8 -*-
"""เซิร์ฟเวอร์ทดสอบหน้าเว็บ: /sales007 = app/sales007.html · /api/sales/* = handler ตัวจริง + FakeSB + นาฬิกาที่เทสตั้งได้
usage: python3 serve_fixture.py <port>   ·  POST /__clock {"at": "2026-10-05T10:00:00+07:00"}  ·  POST /__push {...}"""
import datetime
import http.server
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, HERE)

import sales_api as A       # noqa: E402
from fake_sb import FakeSB  # noqa: E402

TOKEN = "s" * 32
ENV = {"SALES007_PUSH_TOKEN": TOKEN, "SALES007_START_DATE": "2026-10-05", "SALES007_FLOAT": '{"SKN": 500}',
       "SALES007_AUDIT_IDS": "9"}
SB = FakeSB()
SB.add_staff(1, "tok-skn", "SKN", "นิด")
SB.add_staff(9, "tok-finny", "", "Finny")
NOW = [datetime.datetime(2026, 10, 5, 9, 0, tzinfo=A.TZ)]


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
        if u.path == "/sales007":
            with open(os.path.join(ROOT, "app", "sales007.html"), "rb") as f:
                html = f.read().replace(b"<head>", b"<head><script>window.__S7_TOKEN__=localStorage.t;</script>", 1)
            return self._send(200, html, "text/html; charset=utf-8")
        if u.path == "/__clock":
            NOW[0] = datetime.datetime.fromisoformat(json.loads(body)["at"])
            SB.clock = NOW[0].astimezone(datetime.timezone.utc)
            return self._send(200, b"{}")
        if u.path == "/__push":
            SB.clock = NOW[0].astimezone(datetime.timezone.utc)
            st, out = A.handle("push", "POST", {"X-Sales-Token": TOKEN}, body, {}, env=ENV, sb=SB)
            return self._send(st, json.dumps(out).encode())
        if u.path.startswith("/api/sales/"):
            SB.clock = NOW[0].astimezone(datetime.timezone.utc)
            st, out = A.handle(u.path.rsplit("/", 1)[1], method, dict(self.headers.items()), body,
                               urllib.parse.parse_qs(u.query), env=ENV, sb=SB, now=NOW[0].astimezone(datetime.timezone.utc))
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
