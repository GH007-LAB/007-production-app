# -*- coding: utf-8 -*-
"""python3 -m unittest discover -s approve007/tests -v"""
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")
sys.path.insert(0, ENGINE)
sys.path.insert(0, HERE)

import approve_engine as E  # noqa: E402

TODAY = datetime.date.today()


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def book(exact=None, prefix=None, fast=(), updated=None):
    return E.CostBook({"updated": (updated or TODAY).isoformat(), "prefix": prefix or [],
                       "exact": {"PPS": exact or {}}, "exact_any": {}, "fast": list(fast)})


class Bands(unittest.TestCase):
    def test_meter_self_tier_uses_rate1_minus_5_when_gp_allows(self):
        b = E.price_bands(72.8, 120, "ม.")                     # PU ลายไม้: P20 = 91 < 115
        self.assertEqual((b["stand"], b["self_low"], b["mgr_low"]), (120, 115, 81))
        self.assertFalse(b["self_empty"])

    def test_p20_above_rate1_empties_self_tier_and_flags_report(self):
        b = E.price_bands(131.6, 153, "ม.")                    # Zacs Cool 0.35: P20 = 164.5 > 153
        self.assertTrue(b["self_empty"])
        self.assertIn("rate1_below_target", b["flags"])
        self.assertEqual(E.classify(153, b), "stand")
        self.assertEqual(E.classify(150, b), "mgr")
        self.assertEqual(E.classify(125, b), "gem")

    def test_rate1_below_gp10_is_never_green(self):
        b = E.price_bands(110.2, 110, "ม.")                    # JJL สี 0.35: ทุน > ป้าย
        self.assertEqual(b["status"], "ask")
        self.assertIn("rate1_below_floor", b["flags"])

    def test_fast_mover_uses_15pct(self):
        slow, fast = E.price_bands(2.78, None, "ตัว"), E.price_bands(2.78, None, "ตัว", fast=True)
        self.assertEqual(slow["self_low"], 3.50)                # 2.78/0.8 = 3.475 → ปัดขึ้น 0.05
        self.assertEqual(fast["self_low"], 3.30)                # 2.78/0.85 = 3.2706 → 3.30
        self.assertEqual(E.classify(2.50, fast), "gem")

    def test_piece_items_ignore_5_baht_discount(self):
        b = E.price_bands(40.0, 60, "ตัว")
        self.assertEqual(b["self_low"], 50.0)                   # P20 เท่านั้น ไม่ใช่ 60−5

    def test_edges_always_round_up_and_keep_gp(self):
        for cost in (37.3, 60.2, 69.6, 72.8, 101.1, 131.6, 0.52, 2.78):
            b = E.price_bands(cost, None, "ม." if cost > 5 else "ตัว")
            self.assertGreaterEqual(b["self_low"], cost / 0.8 - 1e-9)
            self.assertGreaterEqual(b["mgr_low"], cost / 0.9 - 1e-9)

    def test_no_cost_means_ask_and_fold_is_excluded(self):
        self.assertEqual(E.price_bands(None, 100, "ม.")["status"], "ask")
        self.assertEqual(E.price_bands(45, None, "ม.", code="07ETC-X")["status"], "fold")

    def test_protect_empties_self_tier(self):
        self.assertTrue(E.price_bands(72.8, 120, "ม.", protect=True)["self_empty"])


class Costs(unittest.TestCase):
    def test_order_express_then_prefix_then_fallback_and_group02_unverified(self):
        b = E.CostBook({"updated": TODAY.isoformat(), "prefix": [["01A-", 90.0, 110], ["02KK", 70.0, 95]],
                        "exact": {"PPS": {"01A-X": 84.24, "02KK-1": 10.0}}, "exact_any": {"09Z": 5.0}})
        self.assertEqual(b.cost("01A-X", "PPS")["source"], "express_avg")
        self.assertEqual(b.cost("01A-X", "PPS")["cost"], 84.24)   # SO6904983: ใช้ทุนเฉลี่ย ไม่ใช่ราคาโอน
        self.assertEqual(b.cost("01A-Y", "PPS")["source"], "prefix")
        self.assertFalse(b.cost("02KK-1", "PPS")["unit_verified"])
        self.assertEqual(b.cost("09Z", "PPS")["source"], "fallback")
        self.assertIsNone(b.cost("ZZZ", "PPS"))

    def test_pins_are_stripped_on_load(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"v": 2, "data": base64.b64encode(json.dumps({"pins": {"7007": {}}, "prefix": []}).encode()).decode()}, f)
        self.assertNotIn("pins", E.load_rules(f.name))


class Grade(unittest.TestCase):
    def setUp(self):
        self.b = book(exact={"A": 70.0, "B": 90.0, "S": 2.78}, fast=["S"])

    def g(self, lines, **kw):
        return E.grade_bill([{"code": c, "qty": q, "price": p} for c, q, p in lines], "PPS", self.b, **kw)

    def test_grades(self):
        self.assertEqual(self.g([("A", 10, 110)])["grade"], "A")        # 36%
        self.assertEqual(self.g([("A", 10, 90)])["grade"], "B")         # 22%
        self.assertEqual(self.g([("A", 10, 80)])["grade"], "C")         # 12.5%
        self.assertEqual(self.g([("A", 10, 72)])["grade"], "D")         # 2.8%
        self.assertEqual(self.g([("A", 10, 69)])["grade"], "X")

    def test_any_line_below_cost_is_x_even_if_bill_profitable(self):
        r = self.g([("A", 100, 200), ("S", 10, 2.5)])
        self.assertEqual((r["grade"], r["approval_pct"]), ("X", 0))
        self.assertEqual(r["below_cost_codes"], ["S"])

    def test_fast_mover_15_19_is_b(self):
        self.assertEqual(self.g([("S", 1000, 3.30)])["grade"], "B")     # 15.8% หมุนเร็ว

    def test_over_300k_goes_to_gem(self):
        self.assertEqual(self.g([("A", 3000, 110)])["grade"], "D")

    def test_low_coverage_does_not_conclude(self):
        r = self.g([("A", 1, 110), ("UNKNOWN", 10, 100)])
        self.assertIsNone(r["grade"])

    def test_freshness_gate_caps_at_c(self):
        old = book(exact={"A": 70.0}, updated=TODAY - datetime.timedelta(days=20))
        r = E.grade_bill([{"code": "A", "qty": 10, "price": 110}], "PPS", old)
        self.assertEqual(r["grade"], "C")

    def test_sales_mode_leaks_no_cost_or_gp(self):
        r = self.g([("A", 10, 110), ("B", 5, 100)])
        blob = json.dumps(r)
        for k in ("gp_pct", "cost", "gp_band", "lines", "hidden_costs"):
            self.assertNotIn(f'"{k}"', blob)
        self.assertNotIn("70.0", blob)
        self.assertIn("gp_pct", self.g([("A", 10, 110)], role="GEM"))
        self.assertIn("gp_band", self.g([("A", 10, 110)], role="MGR"))

    def test_quick_layers_carry_disclaimer(self):
        self.assertIn("disclaimer", self.g([("A", 10, 110)], layer="A"))

    def test_card_fee_and_freight_reduce_gp(self):
        base = self.g([("A", 10, 94)], role="GEM")["gp_pct"]
        self.assertLess(self.g([("A", 10, 94)], role="GEM", card_unpaid=True, freight=50)["gp_pct"], base)


class EndToEnd(unittest.TestCase):
    """สร้าง All_on_Cloud จำลอง → preflight → build → verify · ไฟล์ที่เซลเปิดต้องไม่มีทุน"""

    @classmethod
    def setUpClass(cls):
        import make_fixture
        cls.tmp = tempfile.mkdtemp()
        cls.aoc = make_fixture.make(cls.tmp)
        cls.env = dict(os.environ, APPROVE007_ALL_ON_CLOUD=cls.aoc, APPROVE007_CHROME="/nonexistent")

    def run_build(self, *args):
        return subprocess.run([sys.executable, os.path.join(ENGINE, "build.py"), *args], env=self.env,
                              capture_output=True, text=True, timeout=120)

    def test_pipeline(self):
        self.assertIn("PRE-FLIGHT OK", self.run_build("preflight").stdout)
        out = self.run_build()
        self.assertEqual(out.returncode, 0, out.stderr)
        js = read(os.path.join(self.aoc, "Approve007", "pricebands.js"))
        data = json.loads(js[js.index("=") + 1:].strip().rstrip(";"))
        for v in ("131.6", "110.2", "101.1", "72.8", "2.78", "7007", '"cost"', "gp"):
            self.assertNotIn(v, js, f"พบ {v} ใน pricebands.js")
        pps = {r["name"]: r for r in data["branches"]["PPS"]}
        self.assertEqual(pps["Zacs Cool/Dazzle/Natural 0.35"]["stand"], 153)     # ใช้ใบ 260907 ไม่ใช่ 260601
        self.assertEqual(pps["JJL สี 0.35"]["status"], "ask")
        self.assertTrue(os.path.exists(os.path.join(self.aoc, "Approve007", "approve007.html")))
        html_page = read(os.path.join(self.aoc, "Approve007", "approve007.html"))
        self.assertNotIn('src="costbook.js"', html_page)
        status = json.loads(read(os.path.join(self.aoc, "AutoExport", "agent_status", "pricebands_latest.json")))
        self.assertIsNone(status["stale"])
        report = status["report"]
        self.assertTrue(os.path.exists(report))
        self.assertNotIn(os.path.join("All_on_Cloud", "Approve007"), report)       # รายงานมีทุน อยู่นอกโฟลเดอร์เซล
        v = self.run_build("verify")
        self.assertIn("VERIFY OK", v.stdout, v.stdout + v.stderr)
        again = self.run_build()                                                   # รอบสองต้องสำรองไฟล์เดิม
        self.assertEqual(again.returncode, 0)
        self.assertTrue(any(n.startswith("pricebands.js.") for n in os.listdir(os.path.join(self.aoc, "Approve007", "_backup"))))

    def test_backtest_and_check(self):
        c = self.run_build("check", "SO6903141", "SKN")
        self.assertIn('"branch": "SKN"', c.stdout)                                 # SO ซ้ำข้ามสาขา → เลือกตามสาขา
        dup = self.run_build("check", "so6903141")                                 # ไม่ระบุสาขา + เลขซ้ำ → ไม่เดา
        self.assertIn("มีใน 2 สาขา", dup.stdout, dup.stdout + dup.stderr)
        self.assertNotIn('"grade"', dup.stdout)
        self.assertIn("PPS (โพนพิสัย)", dup.stdout)
        one = self.run_build("check", "SO6904651")                                 # มีสาขาเดียว → เกรดเลย
        self.assertIn('"branch": "SKN"', one.stdout)
        self.assertIn("ไม่พบ", self.run_build("check", "SO0000000").stdout)
        env = dict(self.env, APPROVE007_BRANCH="PPS")                              # เครื่องสาขา → ใช้สาขาตัวเอง
        own = subprocess.run([sys.executable, os.path.join(ENGINE, "build.py"), "check", "SO6903141"], env=env,
                             capture_output=True, text=True, timeout=120)
        self.assertIn('"branch": "PPS"', own.stdout)
        self.assertIn('"grade": "X"', own.stdout)
        b = self.run_build("backtest", "30")
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertIn("(ไม่ระบุเซล)", b.stdout)


if __name__ == "__main__":
    unittest.main()
