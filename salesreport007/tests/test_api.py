# -*- coding: utf-8 -*-
"""python3 -m unittest discover -s salesreport007/tests -v
ไล่วันจริงของสาขา: feeder ส่ง IV/AI/SR/RE → พนักงานเลือกช่องทาง → รายจ่าย → ตัดรอบ → ส่ง → ยกมา → ตรวจ/ส่งออกให้ Finny"""
import base64
import datetime
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, HERE)

import calc                     # noqa: E402
import sales_api as A           # noqa: E402
from fake_sb import FakeSB      # noqa: E402

TOKEN = "s" * 32
ENV = {"SALES007_PUSH_TOKEN": TOKEN, "SALES007_START_DATE": "2026-10-05", "SALES007_FLOAT": '{"SKN": 500}',
       "SALES007_AUDIT_IDS": "9", "CRON_SECRET": "c" * 20}
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0fake-jpeg").decode()
D1 = datetime.date(2026, 10, 5)


def bkk(day, hm):
    h, m = map(int, hm.split(":"))
    return datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=A.TZ)


class Day(unittest.TestCase):
    def setUp(self):
        self.sb = FakeSB()
        self.sb.add_staff(1, "tok-skn", "SKN", "นิด")
        self.sb.add_staff(2, "tok-bk", "BK", "บี")
        self.sb.add_staff(9, "tok-finny", "", "Finny")

    def call(self, action, at, method="GET", body=None, query=None, token=None, headers=None):
        self.sb.clock = at.astimezone(datetime.timezone.utc)
        h = dict(headers or {})
        if token:
            h["Authorization"] = "Bearer " + token
        q = {k: [v] for k, v in (query or {}).items()}
        st, out = A.handle(action, method, h, json.dumps(body).encode() if body is not None else b"", q,
                           env=ENV, sb=self.sb, now=at.astimezone(datetime.timezone.utc))
        return st, json.loads(json.dumps(out, default=str))

    def push(self, at, br, docs, gone=()):
        st, out = self.call("push", at, "POST", {"branch": br, "docs": docs, "gone": list(gone)},
                            headers={"X-Sales-Token": TOKEN})
        self.assertEqual(st, 200, out)

    def day(self, at, token="tok-skn", **q):
        st, out = self.call("day", at, query=q, token=token)
        self.assertEqual(st, 200, out)
        return out

    def act(self, at, body, token="tok-skn", status=200):
        st, out = self.call("act", at, "POST", body, token=token)
        self.assertEqual(st, status, out)
        return out

    def test_full_day(self):
        doc = lambda no, t, total, day=D1, **k: dict({"doc_no": no, "type": t, "doc_date": day.isoformat(),
                                                      "customer": "ลูกค้า " + no, "total": total}, **k)
        # 09:00 พนักงานคีย์ IV · AI · ลดหนี้ ใน Express → ขึ้นแอปทันทีที่ feeder ส่ง
        self.push(bkk(D1, "09:00"), "SKN", [doc("IV6910001", "IV", 12000, remain=12000), doc("AI6910001", "AI", 5000),
                                            doc("SR6910001", "SR", 450), doc("AI6909999", "AI", 99, day=D1 - datetime.timedelta(days=1))])
        v = self.day(bkk(D1, "09:01"))
        self.assertEqual(v["status"], "open")
        self.assertEqual([d["doc_no"] for d in v["docs"]], ["AI6910001", "SR6910001"])     # ก่อน START_DATE ไม่ขึ้น
        self.assertEqual(v["docs"][0]["options"], {"cash": "เงินสด", "transfer": "เงินโอน", "qr": "QR Code"})
        self.assertEqual(v["docs"][1]["options"], {"deduct": "หักใน RE", "refund_cash": "คืนเงินสด"})
        self.assertEqual(v["iv"], [{"doc_no": "IV6910001", "customer": "ลูกค้า IV6910001", "total": 12000.0,
                                    "paid": False, "paid_by": []}])
        self.assertEqual(v["pending"], 2)
        for k in ("summary", "cash_expected", "diff"):
            self.assertNotIn(k, json.dumps(v))                                      # พนักงานไม่เห็นยอดรวม

        # 10:00 ลูกค้ามาจ่าย IV → ออก RE ตัดชำระ → RE ขึ้นให้เลือกช่องทาง · IV เปลี่ยนเป็นตัดชำระแล้ว
        self.push(bkk(D1, "10:00"), "SKN", [doc("RE6910001", "RE", 12000, refs=["IV6910001"])])
        v = self.day(bkk(D1, "10:01"))
        self.assertEqual(v["docs"][-1]["doc_no"], "RE6910001")
        self.assertEqual(v["iv"][0]["paid_by"], ["RE6910001"])
        self.act(bkk(D1, "10:02"), {"op": "channel", "doc_no": "RE6910001", "channel": "qr"})
        self.act(bkk(D1, "10:02"), {"op": "channel", "doc_no": "AI6910001", "channel": "cash"})
        self.act(bkk(D1, "10:03"), {"op": "channel", "doc_no": "SR6910001", "channel": "cash"}, status=400)  # SR ใช้ช่องอื่น
        self.act(bkk(D1, "10:03"), {"op": "channel", "doc_no": "SR6910001", "channel": "deduct"})
        self.act(bkk(D1, "10:04"), {"op": "channel", "doc_no": "IV6910001", "channel": "cash"}, status=404)
        self.act(bkk(D1, "10:04"), {"op": "channel", "doc_no": "AI6910001", "channel": "cash", "branch": "BK"},
                 status=403)                                                         # สาขาอื่นห้าม
        self.assertEqual(len(self.sb.t["sales_choice_log"]), 3)

        # รายจ่ายประจำวัน
        self.act(bkk(D1, "11:00"), {"op": "expense_add", "category": "น้ำมัน/ค่าเดินทาง", "item": "เติมน้ำมันรถส่งของ",
                                    "payee": "ปตท.", "amount": "120", "bill_no": "INV-889", "photo": JPEG})
        self.act(bkk(D1, "12:00"), {"op": "expense_add", "category": "อาหาร/น้ำดื่ม", "item": "ข้าวคนงาน", "amount": 60})
        self.act(bkk(D1, "12:00"), {"op": "expense_add", "category": "มั่ว", "item": "x", "amount": 1}, status=400)
        self.assertEqual(len(self.sb.files), 1)
        self.assertTrue(next(iter(self.sb.files)).startswith("SKN/691005/"))
        v = self.day(bkk(D1, "12:01"))
        self.assertEqual([e["has_receipt"] for e in v["expenses"]], [True, False])
        self.assertNotIn("receipt_url", json.dumps(v))                               # พนักงานไม่ได้ลิงก์รูป

        # ส่งก่อนตัดรอบไม่ได้
        st, out = self.call("act", bkk(D1, "16:00"), "POST", {"op": "submit", "cash_counted": 5000}, token="tok-skn")
        self.assertEqual((st, out["error"]), (409, "before-cutoff"))

        # 16:40 ออก AI หลังตัดรอบ → ไม่อยู่รอบนี้ · ขึ้นใน "ไปรายงานวันถัดไป" เลือกช่องทางไว้ได้
        self.push(bkk(D1, "16:40"), "SKN", [doc("AI6910002", "AI", 700)])
        v = self.day(bkk(D1, "16:41"))
        self.assertEqual([d["doc_no"] for d in v["docs"]], ["AI6910001", "SR6910001", "RE6910001"])
        self.assertEqual([d["doc_no"] for d in v["next"]], ["AI6910002"])
        self.act(bkk(D1, "16:42"), {"op": "channel", "doc_no": "AI6910002", "channel": "transfer"})

        # ส่ง: เงินสดควรมี = 500 + 5000 − 0 − 120 (ข้าวไม่มีบิล ไม่นับ) = 5380 · นับ 5300 → −80
        out = self.act(bkk(D1, "16:45"), {"op": "submit", "cash_counted": 5300})
        self.assertEqual(out, {"ok": True, "diff": -80.0})
        v = self.day(bkk(D1, "16:46"))
        self.assertEqual((v["status"], v["diff"], v["preparer"]), ("submitted", -80.0, "นิด"))
        self.assertNotIn("summary", v)
        self.act(bkk(D1, "16:47"), {"op": "expense_add", "category": "อาหาร/น้ำดื่ม", "item": "x", "amount": 5}, status=409)
        rep = self.sb.t["sales_report"][0]
        self.assertEqual({k: rep["summary"][k] for k in calc.MONEY_KEYS},
                         {"cash_in": 5000.0, "transfer_in": 0.0, "qr_in": 12000.0, "cash_refund": 0.0, "cash_expense": 120.0,
                          "cash_expected": 5380.0, "diff": -80.0, "deposit": 4800.0})
        self.assertEqual(rep["summary"]["expense_no_receipt"], ["ข้าวคนงาน"])
        stamped = {d["doc_no"]: d["report_date"] for d in self.sb.t["sales_doc"]}
        self.assertEqual(stamped["RE6910001"], "2026-10-05")
        self.assertIsNone(stamped["AI6910002"])

        # BK ไม่ได้ส่ง → เลย 16:55 ล็อกเองเมื่อมีคนเปิด (หรือ cron)
        self.push(bkk(D1, "10:00"), "BK", [doc("RE6910900", "RE", 100)])
        v = self.day(bkk(D1, "17:00"), token="tok-bk")
        self.assertEqual((v["status"], v["lock_reason"]), ("locked", "deadline"))
        st, out = self.call("cron", bkk(D1, "17:01"), headers={"Authorization": "Bearer " + "c" * 20})
        self.assertEqual((st, out["locked"]), (200, []))                             # ล็อกครบแล้ว ไม่ซ้ำ

        # วันถัดไป: AI ที่ออกหลังตัดรอบ = เอกสารยกมา (ช่องทางที่เลือกไว้ติดมาด้วย)
        D2 = D1 + datetime.timedelta(days=1)
        v = self.day(bkk(D2, "08:30"))
        self.assertEqual([(d["doc_no"], d["carried"], d["channel"]) for d in v["docs"]], [("AI6910002", True, "transfer")])
        self.assertEqual(v["iv"], [])

        # หลังล็อก สาขาแก้ยอด AI ใน Express → Finny เห็นในหน้าตรวจ
        self.push(bkk(D2, "09:00"), "SKN", [doc("AI6910001", "AI", 5100)])
        st, a = self.call("audit", bkk(D2, "09:05"), query={"date": "2026-10-05"}, token="tok-finny")
        self.assertEqual(st, 200, a)
        skn = next(b for b in a["branches"] if b["branch"] == "SKN")
        self.assertEqual(skn["status"], "submit")
        self.assertEqual(skn["summary"]["diff"], -80.0)
        self.assertEqual(skn["after_cutoff"], {"count": 1, "total": 700.0, "docs": ["AI6910002"]})
        self.assertEqual(skn["express_by_type"], {"IV": 12000.0, "AI": 5800.0, "SR": 450.0, "RE": 12000.0})
        self.assertIn("แก้ยอดหลังล็อก 5,000.00 → 5,100.00", skn["changed_after_lock"][0]["issue"])
        self.assertTrue(skn["expenses"][0]["receipt_url"].startswith("https://signed.example/SKN/691005/"))
        st, _ = self.call("audit", bkk(D2, "09:05"), token="tok-skn")
        self.assertEqual(st, 403)

        # ส่งออกให้ Mac mini → Drive (Finny)
        st, ex = self.call("export", bkk(D2, "09:10"), query={"branch": "SKN", "date": "2026-10-05"},
                           headers={"X-Sales-Token": TOKEN})
        self.assertEqual((st, ex["version"], ex["summary"]["diff"], ex["doc_count_at_cutoff"]), (200, 6, -80.0, 3))
        self.assertEqual({d["doc_no"]: d["channel"] for d in ex["docs"]},
                         {"AI6910001": "cash", "SR6910001": "deduct", "RE6910001": "qr"})
        st, _ = self.call("export", bkk(D2, "09:10"), query={"branch": "SKN", "date": "2026-10-05"},
                          headers={"X-Sales-Token": "wrong" * 8})
        self.assertEqual(st, 401)

    def test_submit_requires_every_channel_and_gone_docs_drop_out(self):
        doc = lambda no, t, total: {"doc_no": no, "type": t, "doc_date": D1.isoformat(), "total": total}
        self.push(bkk(D1, "09:00"), "SKN", [doc("RE1", "RE", 100), doc("RE2", "RE", 200)])
        self.act(bkk(D1, "09:05"), {"op": "channel", "doc_no": "RE1", "channel": "cash"})
        out = self.act(bkk(D1, "16:35"), {"op": "submit", "cash_counted": 600})
        self.assertEqual(out, {"ok": False, "error": "channel-missing", "docs": ["RE2"]})
        self.push(bkk(D1, "16:36"), "SKN", [], gone=["RE2"])                       # ยกเลิก RE2 ใน Express
        self.assertEqual([d["doc_no"] for d in self.day(bkk(D1, "16:37"))["docs"]], ["RE1"])
        self.assertEqual(self.act(bkk(D1, "16:38"), {"op": "submit", "cash_counted": 600})["diff"], 0.0)

    def test_push_needs_token_and_valid_rows(self):
        st, _ = self.call("push", bkk(D1, "09:00"), "POST", {"branch": "SKN", "docs": []})
        self.assertEqual(st, 401)
        st, out = self.call("push", bkk(D1, "09:00"), "POST", {"branch": "SKN", "docs": [{"doc_no": "X1", "type": "ZZ",
                            "doc_date": "2026-10-05", "total": 1}]}, headers={"X-Sales-Token": TOKEN})
        self.assertEqual((st, out["error"]), (400, "bad-doc"))

    def test_first_seen_is_kept_on_update(self):
        """เอกสารที่เห็นก่อนตัดรอบ แล้วถูกแก้หลังตัดรอบ ต้องยังอยู่รอบเดิม (first_seen_at ไม่ถูกทับ)"""
        doc = {"doc_no": "RE1", "type": "RE", "doc_date": D1.isoformat(), "total": 100}
        self.push(bkk(D1, "16:00"), "SKN", [doc])
        self.push(bkk(D1, "16:50"), "SKN", [dict(doc, total=150)])
        v = self.day(bkk(D1, "16:51"))
        self.assertEqual([(d["doc_no"], d["total"]) for d in v["docs"]], [("RE1", 150.0)])


class Calc(unittest.TestCase):
    def test_formula(self):
        docs = [{"doc_no": "RE1", "type": "RE", "total": 1000, "channel": "cash"},
                {"doc_no": "RE2", "type": "RE", "total": 2500.5, "channel": "transfer"},
                {"doc_no": "AI1", "type": "AI", "total": 300, "channel": "qr"},
                {"doc_no": "SR1", "type": "SR", "total": 200, "channel": "refund_cash"},
                {"doc_no": "SR2", "type": "SR", "total": 99, "channel": "deduct"},
                {"doc_no": "HS1", "type": "HS", "total": 50, "channel": None}]
        exp = [{"item": "น้ำมัน", "amount": 120, "receipt_path": "SKN/x.jpg"}, {"item": "ข้าว", "amount": 60}]
        s = calc.summarize(docs, exp, 1200, 500)
        self.assertEqual({k: s[k] for k in calc.MONEY_KEYS},
                         {"cash_in": 1000.0, "transfer_in": 2500.5, "qr_in": 300.0, "cash_refund": 200.0,
                          "cash_expense": 120.0, "cash_expected": 1180.0, "diff": 20.0, "deposit": 700.0})
        self.assertEqual((s["unchosen"], s["expense_no_receipt"]), (["HS1"], ["ข้าว"]))

    def test_half_satang_rounds_up(self):
        self.assertEqual(calc.satang(0.005), 1)
        self.assertEqual(calc.satang(2.675), 268)


if __name__ == "__main__":
    unittest.main()
