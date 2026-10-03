# -*- coding: utf-8 -*-
"""sales_push.py (เครื่องสาขา) อ่าน DBF รูปแบบ Express → ส่งเฉพาะที่เปลี่ยน → API รับจริง (FakeSB)"""
import datetime
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "feeder"))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "approve007", "tests"))

import sales_api as A           # noqa: E402
import sales_push as P          # noqa: E402
from fake_sb import FakeSB      # noqa: E402
from make_fixture import write_dbf  # noqa: E402

D = datetime.date(2026, 10, 5)
ARTRN_F = [("DOCNUM", "C", 12, 0), ("DOCDAT", "D", 8, 0), ("CUSCOD", "C", 10, 0), ("NETAMT", "N", 14, 2),
           ("REMAMT", "N", 14, 2), ("DOCSTAT", "C", 1, 0)]
ARRCPT_F = [("RCPNUM", "C", 12, 0), ("RCPDAT", "D", 8, 0), ("CUSCOD", "C", 10, 0), ("NETAMT", "N", 14, 2),
            ("DOCSTAT", "C", 1, 0)]
ARRCPIT_F = [("RCPNUM", "C", 12, 0), ("DOCNUM", "C", 12, 0)]
ARMAS_F = [("CUSCOD", "C", 10, 0), ("PRENAM", "C", 10, 0), ("CUSNAM", "C", 40, 0)]
TOKEN = "s" * 32


class Feeder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "skn2569")
        os.environ["LOCALAPPDATA"] = os.path.join(self.tmp.name, "local")
        write_dbf(os.path.join(self.src, "ARMAS.DBF"), ARMAS_F, [{"CUSCOD": "C001", "PRENAM": "คุณ", "CUSNAM": "สมชาย"}])
        self.trn = [
            {"DOCNUM": "IV6910001", "DOCDAT": D, "CUSCOD": "C001", "NETAMT": 12000, "REMAMT": 0, "DOCSTAT": ""},
            {"DOCNUM": "AI6910001", "DOCDAT": D, "CUSCOD": "C001", "NETAMT": 5000, "REMAMT": 0, "DOCSTAT": ""},
            {"DOCNUM": "SR6910001", "DOCDAT": D, "CUSCOD": "C001", "NETAMT": -450, "REMAMT": 0, "DOCSTAT": ""},
            {"DOCNUM": "AI6910009", "DOCDAT": D, "CUSCOD": "C001", "NETAMT": 999, "REMAMT": 0, "DOCSTAT": "C"},
            {"DOCNUM": "AI6909001", "DOCDAT": D - datetime.timedelta(days=1), "CUSCOD": "C001", "NETAMT": 1,
             "REMAMT": 0, "DOCSTAT": ""},
        ]
        self.rcp = [{"RCPNUM": "RE6910001", "RCPDAT": D, "CUSCOD": "C001", "NETAMT": 12000, "DOCSTAT": ""}]
        self.link = [{"RCPNUM": "RE6910001", "DOCNUM": "IV6910001"}]
        self.cfg = {"BRANCH": "SKN", "SRC": self.src, "API_URL": "http://x/api/sales", "PUSH_TOKEN": TOKEN,
                    "WINDOW_DAYS": "14", "START_DATE": D.isoformat()}
        self.sb, self.sent = FakeSB(), []

        def fake_post(cfg, body):                      # ส่งผ่าน handler ตัวจริงของ API
            self.sent.append(body)
            st, out = A.handle("push", "POST", {"X-Sales-Token": cfg["PUSH_TOKEN"]},
                               json.dumps(body, ensure_ascii=False).encode(), {},
                               env={"SALES007_PUSH_TOKEN": TOKEN}, sb=self.sb)
            assert st == 200, out
            return out
        self._post, P.post = P.post, fake_post

    def tearDown(self):
        P.post = self._post
        self.tmp.cleanup()

    def flush(self):
        write_dbf(os.path.join(self.src, "ARTRN.DBF"), ARTRN_F, self.trn)
        write_dbf(os.path.join(self.src, "ARRCPT.DBF"), ARRCPT_F, self.rcp)
        write_dbf(os.path.join(self.src, "ARRCPIT.DBF"), ARRCPIT_F, self.link)

    def test_push_changes_only_and_deletions(self):
        self.flush()
        P.run(self.cfg, today=D)
        docs = {d["doc_no"]: d for d in self.sb.t["sales_doc"]}
        self.assertEqual(sorted(docs), ["AI6910001", "IV6910001", "RE6910001", "SR6910001"])   # ไม่เอาใบยกเลิก/ก่อนเริ่ม
        self.assertEqual(docs["SR6910001"]["total"], 450.0)
        self.assertEqual(docs["RE6910001"]["refs"], ["IV6910001"])
        self.assertEqual(docs["AI6910001"]["customer"], "คุณ สมชาย")
        self.assertEqual(self.sb.t["sales_feed"][0]["info"]["docs"], 4)

        P.run(self.cfg, today=D)                                        # ไม่มีอะไรเปลี่ยน → heartbeat อย่างเดียว
        self.assertEqual((self.sent[-1]["docs"], self.sent[-1]["gone"]), ([], []))

        self.trn[1]["NETAMT"] = 5100                                    # แก้ยอด AI
        self.rcp.append({"RCPNUM": "RE6910002", "RCPDAT": D, "CUSCOD": "C001", "NETAMT": 800, "DOCSTAT": ""})
        self.trn[2]["DOCSTAT"] = "C"                                    # ยกเลิกลดหนี้
        self.flush()
        P.run(self.cfg, today=D)
        self.assertEqual(sorted(d["doc_no"] for d in self.sent[-1]["docs"]), ["AI6910001", "RE6910002"])
        self.assertEqual(self.sent[-1]["gone"], ["SR6910001"])
        docs = {d["doc_no"]: d for d in self.sb.t["sales_doc"]}
        self.assertEqual((docs["AI6910001"]["total"], docs["SR6910001"]["active"]), (5100.0, False))

    def test_window_drift_is_not_a_deletion(self):
        self.flush()
        P.run(self.cfg, today=D)
        cfg = dict(self.cfg, START_DATE="")
        P.run(cfg, today=D + datetime.timedelta(days=20))               # ทุกใบหลุดหน้าต่าง 14 วัน
        self.assertEqual(self.sent[-1]["gone"], [])


if __name__ == "__main__":
    unittest.main()
