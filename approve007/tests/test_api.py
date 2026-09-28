# -*- coding: utf-8 -*-
"""เทส API เฟส 1 แบบครบสาย: build.py push (Mac mini) → HTTP handler ตัวจริงของ Vercel → Supabase จำลอง → /check"""
import datetime
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, HERE)

import approve_api as A  # noqa: E402
import quick as Q         # noqa: E402

TOKEN = "t" * 32


class FakeSB:
    """PostgREST จำลองเฉพาะรูปแบบ query ที่ approve_api ใช้"""

    def __init__(self):
        self.t = {"employees": [], "apps": [{"id": 7, "code": "approve007"}], "app_access": [],
                  "approve_snapshot": [], "approve_so_line": [], "approve_check_log": []}
        self.users = {}
        self.seq = 0

    def get_user(self, token):
        return self.users.get(token)

    @staticmethod
    def _ok(row, key, op, val):
        v = row.get(key)
        if op == "eq":
            return str(v).lower() == val.lower() if isinstance(v, bool) else str(v) == val
        if op == "ilike":
            return str(v or "").lower() == val.lower()
        if op in ("gte", "lt", "gt"):
            if v is None:                   # เหมือน Postgres: NULL เทียบอะไรก็ไม่จริง
                return False
            a, b = (float(v), float(val)) if re.fullmatch(r"-?\d+(\.\d+)?", str(val)) else (str(v), val)
            return a >= b if op == "gte" else a < b if op == "lt" else a > b
        if op == "in":
            return str(v) in val.strip("()").split(",")
        if op == "is":
            return (v is True) if val == "true" else (v is None)
        raise AssertionError(op)

    def _filter(self, rows, query):
        order, limit, offset = None, None, 0
        for part in query.split("&"):
            if not part:
                continue
            k, _, v = part.partition("=")
            v = urllib.parse.unquote(v)
            if k == "select":
                continue
            if k == "order":
                order = v
                continue
            if k == "limit":
                limit = int(v)
                continue
            if k == "offset":
                offset = int(v)
                continue
            if k == "or":
                conds = [c.split(".", 2) for c in v.strip("()").split(",")]
                rows = [r for r in rows if any(self._ok(r, a, b, c) for a, b, c in conds)]
                continue
            op, _, val = v.partition(".")
            rows = [r for r in rows if self._ok(r, k, op, val)]
        if order:
            for f in reversed(order.split(",")):
                name, _, d = f.partition(".")
                rows = sorted(rows, key=lambda r: (r.get(name) is None, r.get(name)), reverse=(d == "desc"))
        rows = rows[offset:]
        return rows[:limit] if limit is not None else rows

    def select(self, table, query):
        return [dict(r) for r in self._filter(list(self.t[table]), query)]

    def insert(self, table, rows, on_conflict=None):
        for r in rows:
            r = dict(r)
            if table in ("approve_snapshot", "approve_check_log"):
                self.seq += 1
                r.setdefault("id", self.seq)
                r.setdefault("ts", datetime.datetime.now(datetime.timezone.utc).isoformat())
                r.setdefault("blocked", False)
            self.t[table].append(r)

    def delete(self, table, query):
        gone = {id(r) for r in self._filter(list(self.t[table]), query)}
        self.t[table] = [r for r in self.t[table] if id(r) not in gone]


def add_person(sb, token, emp_id, position, branch, admin=False, access=True):
    sb.users[token] = {"id": "u" + emp_id, "email": f"{emp_id}@007metals.com", "user_metadata": {}}
    sb.t["employees"].append({"id": emp_id, "nickname": "คุณ" + emp_id, "branch": branch, "position": position,
                              "is_admin": admin, "active": True, "email": f"{emp_id}@007metals.com"})
    if access:
        sb.t["app_access"].append({"employee_id": emp_id, "app_id": 7})


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import make_fixture
        cls.tmp = tempfile.mkdtemp()
        cls.aoc = make_fixture.make(cls.tmp)
        cls.sb = FakeSB()
        add_person(cls.sb, "tok-sale", "e1", "พนักงานขาย", "PPS")
        add_person(cls.sb, "tok-mgr", "e2", "ผู้จัดการสาขา", "PPS")
        add_person(cls.sb, "tok-gem", "e3", "ผู้บริหาร", "SKN", admin=True)
        add_person(cls.sb, "tok-noacc", "e4", "พนักงานขาย", "BK", access=False)
        cls.env = {"SUPABASE_URL": "x", "SUPABASE_SERVICE_ROLE_KEY": "x", "APPROVE007_PUSH_TOKEN": TOKEN}
        sb, env = cls.sb, cls.env

        class H(A.vercel_handler("check")):
            def _go(self, method):          # เหมือนตัวจริง แต่เลือก action จาก path + ใช้ DB จำลอง
                action = urllib.parse.urlparse(self.path).path.rstrip("/").rsplit("/", 1)[-1]
                n = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(n) if n else b""
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                status, out = A.handle(action, method, dict(self.headers.items()), body, query, env=env, sb=sb)
                data = json.dumps(out, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}/api/approve"
        penv = dict(os.environ, APPROVE007_ALL_ON_CLOUD=cls.aoc, APPROVE007_API=cls.base,
                    APPROVE007_PUSH_TOKEN=TOKEN, APPROVE007_CHROME="/nonexistent")
        cls.push = subprocess.run([sys.executable, os.path.join(ROOT, "engine", "build.py"), "push"], env=penv,
                                  capture_output=True, text=True, timeout=120)
        cls.penv = penv

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, action, body=None, token=None, method="POST", headers=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        h.update(headers or {})
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}/{action}", data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_push_filled_server(self):
        self.assertEqual(self.push.returncode, 0, self.push.stdout + self.push.stderr)
        self.assertGreaterEqual(len(self.sb.t["approve_snapshot"]), 1)   # เทสอื่นสั่ง push --full เพิ่มได้
        self.assertNotIn("pins", json.dumps(self.sb.t["approve_snapshot"][0]["payload"]["rules"]))
        self.assertTrue(any(r["sonum"] == "SO6903141" and r["branch"] == "PPS" for r in self.sb.t["approve_so_line"]))

    def test_push_second_run_sends_only_changes(self):
        n, snaps = len(self.sb.t["approve_so_line"]), len(self.sb.t["approve_snapshot"])
        again = subprocess.run([sys.executable, os.path.join(ROOT, "engine", "build.py"), "push"], env=self.penv,
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("snapshot: ไม่เปลี่ยน", again.stdout)
        self.assertIn("PPS: ส่ง 0 บรรทัด (0 SO เปลี่ยน · ลบ 0", again.stdout)
        self.assertNotIn("รอบนี้ส่งครบ", again.stdout)
        self.assertEqual(len(self.sb.t["approve_so_line"]), n)
        self.assertEqual(len(self.sb.t["approve_snapshot"]), snaps)

    def test_push_delete_sos_removes_only_that_branch(self):
        self.sb.t["approve_so_line"] += [{"branch": "BK", "sonum": "SO9999999", "seq": 1, "sodat": "2099-01-01"},
                                         {"branch": "SKN", "sonum": "SO9999999", "seq": 1, "sodat": "2099-01-01"}]
        st, out = self.call("push", {"kind": "so_lines", "branch": "BK", "since": "2000-01-01", "rows": [],
                                     "delete_sos": ["SO9999999"]}, headers={"X-Approve-Token": TOKEN})
        self.assertEqual((st, out["deleted_sos"]), (200, 1))
        left = [r["branch"] for r in self.sb.t["approve_so_line"] if r["sonum"] == "SO9999999"]
        self.assertEqual(left, ["SKN"])
        self.sb.t["approve_so_line"] = [r for r in self.sb.t["approve_so_line"] if r["sonum"] != "SO9999999"]

    def _state(self, mutate):
        p = os.path.join(self.aoc, "AutoExport", "agent_status", "approve007_push_state.json")
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        mutate(st)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f)

    def _push(self, *extra):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "engine", "build.py"), "push", *extra], env=self.penv,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_push_deletes_vanished_so_but_guards_mass_disappearance(self):
        recent = "2099-01-01"
        fake = lambda n: {f"SO88{i:05d}": ["x", recent] for i in range(n)}
        rows = lambda n: [{"branch": "BK", "sonum": f"SO88{i:05d}", "seq": 1, "sodat": recent} for i in range(n)]
        # SO หาย 1 ใบ (ลบใน Express) → ลบบนเซิร์ฟเวอร์
        self.sb.t["approve_so_line"] += rows(1)
        self._state(lambda st: st["so"]["BK"].update(fake(1)))
        r = self._push()
        self.assertIn("ลบ 1", r.stdout)
        self.assertFalse(any(x["sonum"].startswith("SO88") for x in self.sb.t["approve_so_line"]))
        # SO หาย 500 ใบรอบเดียว (> 20% ของทั้งสาขา) → สงสัยอ่านไฟล์ไม่ครบ ไม่ลบ
        self.sb.t["approve_so_line"] += rows(500)
        self._state(lambda st: st["so"]["BK"].update(fake(500)))
        r = self._push()
        self.assertIn("ไม่ลบรอบนี้", r.stderr)
        self.assertEqual(sum(x["sonum"].startswith("SO88") for x in self.sb.t["approve_so_line"]), 500)
        # รอบเต็มแต่ยังโดน guard → ไม่ส่ง keep_sos ก็ต้องไม่ลบ
        r = self._push("--full")
        self.assertEqual(sum(x["sonum"].startswith("SO88") for x in self.sb.t["approve_so_line"]), 500)
        # ล้าง state ของ SO ปลอม แล้วรอบเต็ม → keep_sos ลบ SO ค้างที่ในเครื่องไม่รู้จัก
        self._state(lambda st: [st["so"]["BK"].pop(k) for k in list(st["so"]["BK"]) if k.startswith("SO88")])
        r = self._push("--full")
        self.assertIn("รอบนี้ส่งครบ", r.stdout)
        self.assertFalse(any(x["sonum"].startswith("SO88") for x in self.sb.t["approve_so_line"]))
        self.assertTrue(any(x["sonum"] == "SO6903141" and x["branch"] == "PPS" for x in self.sb.t["approve_so_line"]))

    def test_push_needs_token(self):
        st, out = self.call("push", {"kind": "snapshot"}, headers={"X-Approve-Token": "wrong" * 8})
        self.assertEqual((st, out["error"]), (401, "unauthorized"))

    def test_auth_and_access(self):
        self.assertEqual(self.call("check", {"so": "SO6904651"})[0], 401)
        self.assertEqual(self.call("check", {"so": "SO6904651"}, token="bogus")[0], 401)
        st, out = self.call("check", {"so": "SO6904651"}, token="tok-noacc")
        self.assertEqual((st, out["error"]), (403, "no-app-access"))

    def test_so_duplicate_across_branches_is_not_guessed(self):
        st, out = self.call("check", {"so": "so6903141"}, token="tok-sale")
        self.assertEqual(st, 200)
        self.assertEqual([a["branch"] for a in out["ambiguous"]], ["PPS", "SKN"])
        self.assertNotIn("grade", out)
        st, out = self.call("check", {"so": "SO6903141", "branch": "PPS"}, token="tok-sale")
        self.assertEqual((out["grade"], out["approval_pct"], out["branch"]), ("X", 0, "PPS"))

    def test_sales_response_has_no_cost(self):
        st, out = self.call("check", {"so": "SO6903141", "branch": "PPS"}, token="tok-sale")
        blob = json.dumps(out, ensure_ascii=False)
        for k in ('"gp_pct"', '"cost"', '"gp_band"', '"lines"', "131.6", "1.93", "72.8"):
            self.assertNotIn(k, blob)
        self.assertEqual(out["viewer"]["role"], "SALES")

    def test_manager_sees_band_only_in_own_branch_and_gem_sees_full(self):
        _, own = self.call("check", {"so": "SO6903141", "branch": "PPS"}, token="tok-mgr")
        self.assertIn("gp_band", own)
        self.assertNotIn("gp_pct", own)
        _, other = self.call("check", {"so": "SO6903141", "branch": "SKN"}, token="tok-mgr")
        self.assertNotIn("gp_band", other)
        _, gem = self.call("check", {"so": "SO6903141", "branch": "PPS"}, token="tok-gem")
        self.assertIn("gp_pct", gem)

    def test_quick_text_same_engine_as_bill(self):
        text = "ลอน 0.35 zacs cool ขาว 800 ม. 125\nสกรู 75 มม. 2000 ตัว 2.5\nPU 25 ท้องไม้ 300 ม. 100"
        st, out = self.call("check", {"branch": "PPS", "text": text}, token="tok-sale")
        self.assertEqual(st, 200, out)
        self.assertEqual(out["grade"], "X")                              # ตรงกับบิลจริง SO6903141 PPS
        self.assertTrue(all(i["matched"] for i in out["items"]))
        self.assertIn("disclaimer", out)
        # ข้อมูลที่ปุ่ม "ทำใบเสนอราคา" ส่งต่อ Quote007: ชื่อ/หน่วย/จำนวน/ราคาที่พิมพ์ — ไม่มีทุน
        sc = next(i for i in out["items"] if i["code"] == "04S-75-DOME")
        self.assertEqual((sc["desc"], sc["unit"], sc["cat_unit"], sc["qty"], sc["price"]),
                         ("สกรูปลายสว่าน 75 มม.", "ตัว", "ตัว", 2000.0, 2.5))
        self.assertEqual(next(i for i in out["items"] if i["code"].startswith("01A"))["unit"], "ม.")
        blob = json.dumps(out["items"], ensure_ascii=False)
        for k in ('"cost"', '"gp', "1.93", "131.6", "72.8"):
            self.assertNotIn(k, blob)
        st, out = self.call("check", {"branch": "PPS", "text": "ของแปลก 10 ชิ้น 99\nลอน 0.35 ขาว 100 ม. 120"}, token="tok-sale")
        self.assertIsNone(out["grade"])                                  # จับคู่ไม่ได้/กำกวม → ไม่สรุป

    def test_chase_guard_and_log_pull(self):
        body = {"branch": "BK", "text": "PU 25 ท้องไม้ 100 ม. 110"}
        results = [self.call("check", dict(body, text=f"PU 25 ท้องไม้ 100 ม. {p}"), token="tok-sale")[1]
                   for p in (119, 117, 115, 113, 111, 109)]
        self.assertNotIn("blocked", results[4])
        self.assertTrue(results[5].get("blocked"))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "engine", "build.py"), "pull-log"], env=self.penv,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = os.path.join(self.aoc, "AutoExport", "Live", "approval_requests.jsonl")
        with open(log, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f]
        self.assertTrue(any(x.get("blocked") for x in rows))
        self.assertFalse(any("cost" in x or "gp" in x for x in rows))

    def test_bands_endpoint(self):
        st, out = self.call("bands", token="tok-sale", method="GET")
        self.assertEqual(st, 200)
        self.assertIn("PPS", out["branches"])
        self.assertNotIn('"cost"', json.dumps(out))


class Quick(unittest.TestCase):
    CAT = [("01A-WA-035-ZC", "แผ่นหลังคา Zacs Cool 0.35 ขาว", "Zacs Cool/Dazzle/Natural 0.35", "ม.", 100),
           ("01A-RD-035-JJL", "แผ่นหลังคา JJL สีแดง 0.35", "JJL สี 0.35", "ม.", 40),
           ("01A-ZI-035-JJL", "แผ่นหลังคา JJL ซิงค์ 0.35", "JJL ซิงค์ 0.35", "ม.", 50),
           ("04S-75-DOME", "สกรูปลายสว่าน 75 มม.", None, "ตัว", 5), ("04S-16-HEX", "สกรูหัวหกเหลี่ยม 16 มม.", None, "ตัว", 5)]

    def test_parse(self):
        self.assertEqual(Q.parse_line("สกรู 75 มม. 2000 ตัว 2.5"), {"text": "สกรู 75 มม. 2000 ตัว 2.5", "qty": 2000.0, "unit": "ตัว", "price": 2.5})
        self.assertIsNone(Q.parse_line("PU 25 ฟอยล์ 50 ม.")["price"])

    def test_match_rules(self):
        self.assertEqual(Q.match("ลอน 0.35 jjl แดง 50 ม. 112", self.CAT)[0], "01A-RD-035-JJL")
        self.assertEqual(Q.match("JJL 0.35 ซิงค์ 100 ม. 110", self.CAT)[0], "01A-ZI-035-JJL")
        self.assertIsNone(Q.match("ลอน 0.35 ขาว 100 ม. 120", self.CAT)[0])      # ไม่ระบุยี่ห้อ → ไม่เลือกให้
        self.assertIsNone(Q.match("สกรู 1000 ตัว 2", self.CAT)[0])               # ไม่รู้ขนาด → ไม่เลือกให้
        self.assertEqual(Q.match("สกรู 75 มม. 2000 ตัว 2.5", self.CAT)[0], "04S-75-DOME")


if __name__ == "__main__":
    unittest.main()
