# -*- coding: utf-8 -*-
"""python3 -m unittest discover -s salesreport007/tests -v"""
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "salesreport007", "engine"))
sys.path.insert(0, os.path.join(REPO, "approve007", "tests"))

import calc                     # noqa: E402
import salesreport as S         # noqa: E402
from make_fixture import write_dbf  # noqa: E402
from paths import Layout        # noqa: E402

D1 = datetime.date(2026, 10, 3)
D2 = datetime.date(2026, 10, 5)      # วันทำการถัดไป (ข้ามวันอาทิตย์)
ARTRN_F = [("DOCNUM", "C", 12, 0), ("DOCDAT", "D", 8, 0), ("CUSCOD", "C", 10, 0), ("NETAMT", "N", 14, 2),
           ("REMAMT", "N", 14, 2), ("DOCSTAT", "C", 1, 0), ("CSHAMT", "N", 14, 2), ("TRNAMT", "N", 14, 2)]
ARRCPT_F = [("RCPNUM", "C", 12, 0), ("RCPDAT", "D", 8, 0), ("CUSCOD", "C", 10, 0), ("NETAMT", "N", 14, 2),
            ("DOCSTAT", "C", 1, 0), ("CSHAMT", "N", 14, 2), ("TRNAMT", "N", 14, 2), ("CHQAMT", "N", 14, 2)]
ARRCPIT_F = [("RCPNUM", "C", 12, 0), ("DOCNUM", "C", 12, 0)]
ARMAS_F = [("CUSCOD", "C", 10, 0), ("PRENAM", "C", 10, 0), ("CUSNAM", "C", 40, 0)]


def at(d, hm):
    h, m = map(int, hm.split(":"))
    return datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=S.TZ)


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "All_on_Cloud")
        os.makedirs(os.path.join(self.root, "AutoExport", "SKN"))
        self.L = Layout(self.root)
        self.trn, self.rcp, self.link = [], [], []
        write_dbf(self.L.dbf("SKN", "ARMAS.DBF"), ARMAS_F, [
            {"CUSCOD": "C001", "PRENAM": "คุณ", "CUSNAM": "สมชาย"},
            {"CUSCOD": "BR-BK", "PRENAM": "", "CUSNAM": "007 สาขาบึงกาฬ"}])

    def trn_add(self, no, d, total, cus="C001", remain=0.0, stat="", cash=None, transfer=0.0):
        if cash is None:                                    # AI/HS ค่าเริ่ม = รับเงินสดเต็มยอด · IV/SR = 0
            cash = abs(total) if no[:2] in ("AI", "HS") else 0.0
        self.trn.append({"DOCNUM": no, "DOCDAT": d, "CUSCOD": cus, "NETAMT": total, "REMAMT": remain,
                         "DOCSTAT": stat, "CSHAMT": cash, "TRNAMT": transfer})

    def rcp_add(self, no, d, total, iv=None, cus="C001", cash=0.0, transfer=None, cheque=0.0):
        if transfer is None:
            transfer = total - cash - cheque
        self.rcp.append({"RCPNUM": no, "RCPDAT": d, "CUSCOD": cus, "NETAMT": total, "DOCSTAT": "",
                         "CSHAMT": cash, "TRNAMT": transfer, "CHQAMT": cheque})
        if iv:
            self.link.append({"RCPNUM": no, "DOCNUM": iv})

    def flush(self):
        write_dbf(self.L.dbf("SKN", "ARTRN.DBF"), ARTRN_F, self.trn)
        write_dbf(self.L.dbf("SKN", "ARRCPT.DBF"), ARRCPT_F, self.rcp)
        write_dbf(self.L.dbf("SKN", "ARRCPIT.DBF"), ARRCPIT_F, self.link)

    def export(self, d, hm, rnd=None, force=False):
        self.flush()
        cfg = S.load_cfg()
        cfg["interbranch_customers"]["SKN"] = ["BR-BK"]
        real_now = S.now
        S.now = lambda: at(d, hm)
        try:
            with redirect_stdout(io.StringIO()) as out:
                S.cmd_export(self.L, cfg, rnd, d, ("SKN",), force)
        finally:
            S.now = real_now
        return out.getvalue()

    def inj(self, d):
        return S.read_json(os.path.join(S.report_dir(self.L, "SKN"), S.be_yymmdd(d) + "_in.json"))


class Export(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        f = self.f
        f.trn_add("AI6910001", D1, 5000)
        f.trn_add("IV6910001", D1, 12000, remain=12000)      # ขายเชื่อ ยังไม่มี RE → ค้างรับ
        f.trn_add("IV6910002", D1, 3000, remain=0)           # มี RE แล้ว
        f.trn_add("SR6910001", D1, -450)
        f.trn_add("HS6910001", D1, 800, cus="BR-BK")          # ขายระหว่างสาขา → ไม่ขึ้น
        f.trn_add("HS6910002", D1, 650)                       # HS ไม่ใช่ระหว่างสาขา → ขึ้น + note
        f.trn_add("AI6910009", D1, 999, stat="C")             # ยกเลิก
        f.trn_add("AI6909999", D1 - datetime.timedelta(days=1), 100)   # ก่อนวันแรก → ไม่ยกมา
        f.rcp_add("RE6910001", D1, 3000, iv="IV6910002", cash=1000, transfer=2000)

    def tearDown(self):
        self.f.tmp.cleanup()

    def test_ready_round_layout(self):
        self.f.export(D1, "15:55")
        j = self.f.inj(D1)
        self.assertEqual(j["round"], "ready")
        self.assertEqual([d["doc_no"] for d in j["docs"]], ["AI6910001", "HS6910002", "RE6910001", "SR6910001"])
        self.assertEqual(j["carried_in"], [])                # วันแรกไม่มีเอกสารยกมา
        self.assertEqual([d["doc_no"] for d in j["unpaid_iv"]], ["IV6910001"])
        self.assertEqual(next(d for d in j["docs"] if d["type"] == "SR")["total"], 450.0)
        self.assertEqual(next(d for d in j["docs"] if d["doc_no"] == "RE6910001")["customer"], "คุณ สมชาย")
        self.assertIn("note", next(d for d in j["docs"] if d["type"] == "HS"))
        by = {d["doc_no"]: d for d in j["docs"]}
        self.assertEqual(by["RE6910001"]["channel"], "ผสม (เงินสด+โอน)")
        self.assertEqual((by["RE6910001"]["cash"], by["RE6910001"]["transfer"]), (1000.0, 2000.0))
        self.assertEqual(by["AI6910001"]["channel"], "เงินสด")
        self.assertEqual(by["SR6910001"]["channel"], "ลดหนี้ (ไม่กระทบเงินสด)")
        self.assertEqual(j["no_channel"], [])
        self.assertEqual([(x["doc_no"], x["unpaid"]) for x in j["iv"]], [("IV6910001", True), ("IV6910002", False)])
        for forbidden in ("cash_expected", "summary", "diff"):
            self.assertNotIn(forbidden, json.dumps(j))

    def test_cutoff_round_appends_and_refreshes_from_express(self):
        f = self.f
        f.rcp_add("RE6910005", D1, 800)                         # ออก RE ลืมระบุช่องทาง
        f.rcp[-1]["TRNAMT"] = 0
        f.export(D1, "15:55")
        self.assertEqual(f.inj(D1)["no_channel"], ["RE6910005"])
        f.trn[0]["NETAMT"] = 5100                              # แก้ยอด AI ก่อนตัดรอบ
        f.trn[0]["CSHAMT"] = 5100
        f.rcp[-1]["CSHAMT"] = 800                               # สาขาแก้ RE ใน Express ให้ระบุเงินสด
        f.trn_add("AI6910002", D1, 700)                         # ออก 16:10
        f.export(D1, "16:30")
        j = f.inj(D1)
        self.assertEqual(j["round"], "cutoff")
        self.assertEqual([d["doc_no"] for d in j["docs"]][-1], "AI6910002")      # ต่อท้าย ไม่เรียงใหม่
        self.assertEqual(j["docs"][0]["total"], 5100.0)                           # ก่อนตัดรอบ ตาม Express ล่าสุด
        self.assertEqual(j["no_channel"], [])
        self.assertEqual(sorted(j["rounds"][-1]["updated"]), ["AI6910001", "RE6910005"])
        self.assertEqual(j["warnings"], [])
        self.assertEqual(len(j["rounds"]), 2)
        csvs = [n for n in os.listdir(S.report_dir(f.L, "SKN")) if n.endswith(".csv")]
        self.assertEqual(len(csvs), 2)
        # หลังตัดรอบ: export ซ้ำต้องไม่เติมเข้าวันนี้
        f.trn_add("AI6910003", D1, 300)                         # ออก 16:40
        out = f.export(D1, "16:45")
        self.assertIn("ตัดรอบไปแล้ว", out)
        self.assertNotIn("AI6910003", [d["doc_no"] for d in f.inj(D1)["docs"]])

    def test_after_cutoff_docs_carry_to_next_working_day(self):
        f = self.f
        f.export(D1, "15:55")
        f.export(D1, "16:30")
        f.trn_add("AI6910003", D1, 300)                         # ออกหลัง 16:30
        f.rcp_add("RE6910002", D1 + datetime.timedelta(days=1), 900)   # วันอาทิตย์ (ไม่มีรายงาน)
        f.trn_add("AI6910050", D2, 2000)
        f.export(D2, "15:55")
        j = f.inj(D2)
        self.assertEqual([d["doc_no"] for d in j["carried_in"]], ["AI6910003", "RE6910002"])
        self.assertEqual([d["doc_no"] for d in j["docs"]], ["AI6910050"])
        self.assertEqual(j["unpaid_iv"], [])

    def test_carry_uses_out_json_rows_when_present(self):
        """ถ้าแท็บถูกล็อกก่อนรอบ 16:30 มา เอกสาร 16:00–16:30 ไม่เคยถึงมือพนักงาน → ต้องยกไปวันถัดไป"""
        f = self.f
        f.export(D1, "15:55")
        out = {"branch": "SKN", "date": D1.isoformat(),
               "docs": [dict(d, carried=False, channel="cash") for d in f.inj(D1)["docs"]]}
        with open(os.path.join(S.report_dir(f.L, "SKN"), S.be_yymmdd(D1) + "_out.json"), "w") as fp:
            json.dump(out, fp)
        f.trn_add("AI6910002", D1, 700)
        f.export(D1, "16:30")                                   # รอบตัดมาถึงหลังล็อก
        f.export(D2, "15:55")
        self.assertEqual([d["doc_no"] for d in f.inj(D2)["carried_in"]], ["AI6910002"])

    def test_reconcile_finds_every_doc(self):
        f = self.f
        f.export(D1, "15:55")
        f.export(D1, "16:30")
        f.trn_add("AI6910003", D1, 300)
        f.export(D2, "15:55")
        cfg = S.load_cfg()
        cfg["interbranch_customers"]["SKN"] = ["BR-BK"]
        with redirect_stdout(io.StringIO()) as o:
            ok = S.cmd_reconcile(f.L, cfg, D1, ("SKN",))
        self.assertTrue(ok, o.getvalue())
        self.assertIn("เอกสารหลังตัดรอบ: 1 ใบ · 300.00", o.getvalue())
        f.rcp[0]["CSHAMT"], f.rcp[0]["TRNAMT"] = 0, 3000         # แก้ช่องทาง RE หลังตัดรอบ
        f.flush()
        with redirect_stdout(io.StringIO()) as o:
            self.assertFalse(S.cmd_reconcile(f.L, cfg, D1, ("SKN",)))
        self.assertIn("RE6910001 เงินสด/โอนในรายงานไม่ตรง RE", o.getvalue())
        f.trn[0]["DOCSTAT"] = "C"                               # ลบ/ยกเลิกหลังตัดรอบ
        f.flush()
        with redirect_stdout(io.StringIO()) as o:
            ok = S.cmd_reconcile(f.L, cfg, D1, ("SKN",))
        self.assertFalse(ok)
        self.assertIn("AI6910001 อยู่ในรายงานแต่ไม่มี/ถูกยกเลิกใน Express", o.getvalue())


class Calc(unittest.TestCase):
    def test_v5_formula_uses_express_channels(self):
        docs = [
            {"doc_no": "RE1", "type": "RE", "total": 1000, "pay_known": True, "cash": 1000},
            {"doc_no": "RE2", "type": "RE", "total": 5000, "pay_known": True, "cash": 300, "transfer": 4200},  # หักลดหนี้ 500
            {"doc_no": "AI1", "type": "AI", "total": 2500.5, "pay_known": True, "transfer": 2500.5},
            {"doc_no": "RE3", "type": "RE", "total": 900, "pay_known": True, "cheque": 900},
            {"doc_no": "SR1", "type": "SR", "total": 500, "pay_known": False},               # ลดหนี้หักใน RE2
            {"doc_no": "SR2", "type": "SR", "total": 200, "pay_known": True, "cash": 200},   # คืนเงินสด
            {"doc_no": "RE4", "type": "RE", "total": 50, "pay_known": False},
        ]
        exp = [{"item": "น้ำมัน", "amount": 120, "receipt": "691003_1.jpg"},
               {"item": "ข้าว", "amount": 60, "receipt": ""},
               {"item": "ค่าส่ง", "amount": 40, "receipt": "691003_x.jpg", "receipt_found": False}]
        s = calc.summarize(docs, exp, 2000, 500)
        self.assertEqual(s["cash_in"], 1300.0)
        self.assertEqual(s["transfer_in"], 6700.5)
        self.assertEqual(s["cheque_in"], 900.0)
        self.assertEqual(s["cash_refund"], 200.0)
        self.assertEqual(s["cash_expense"], 120.0)
        self.assertEqual(s["cash_expected"], 1480.0)            # 500 + 1300 − 200 − 120
        self.assertEqual(s["diff"], 520.0)
        self.assertEqual(s["deposit"], 1500.0)
        self.assertEqual(s["no_channel"], ["RE4"])
        self.assertEqual(s["expense_no_receipt"], ["ข้าว", "ค่าส่ง"])


if __name__ == "__main__":
    unittest.main()
