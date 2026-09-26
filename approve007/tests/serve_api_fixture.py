# -*- coding: utf-8 -*-
"""เปิด API ตัวจริง (approve_api.handle) บนเครื่อง ด้วย Supabase จำลอง + ข้อมูลจาก All_on_Cloud จำลอง
ใช้กับ test_app.mjs โหมดออนไลน์ · พิมพ์บรรทัดแรกเป็น URL ของ API แล้วค้างไว้จนถูก kill"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import make_fixture                              # noqa: E402
from test_api import A, FakeSB, TOKEN, add_person  # noqa: E402


def main():
    aoc = make_fixture.make(tempfile.mkdtemp())
    sb = FakeSB()
    add_person(sb, "tok-sale", "e1", "พนักงานขาย", "PPS")
    add_person(sb, "tok-gem", "e3", "ผู้บริหาร", "SKN", admin=True)
    env = {"SUPABASE_URL": "x", "SUPABASE_SERVICE_ROLE_KEY": "x", "APPROVE007_PUSH_TOKEN": TOKEN}

    class H(http.server.BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")           # เฉพาะเทส (production เป็น same-origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Approve-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def _go(self, method):
            u = urllib.parse.urlparse(self.path)
            n = int(self.headers.get("content-length") or 0)
            status, out = A.handle(u.path.rstrip("/").rsplit("/", 1)[-1], method, dict(self.headers.items()),
                                   self.rfile.read(n) if n else b"", urllib.parse.parse_qs(u.query), env=env, sb=sb)
            data = json.dumps(out, ensure_ascii=False).encode()
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    base = f"http://127.0.0.1:{srv.server_port}/api/approve"
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "engine", "build.py"), "push"], capture_output=True, text=True,
                       env=dict(os.environ, APPROVE007_ALL_ON_CLOUD=aoc, APPROVE007_API=base, APPROVE007_PUSH_TOKEN=TOKEN))
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        sys.exit(1)
    print(base, flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
