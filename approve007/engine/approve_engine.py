# -*- coding: utf-8 -*-
"""
Approve007 — "ขายได้เลยไหม" · สมองก้อนเดียว (RULE ENGINE) ของ P-17
ทุกช่องทาง (ตาราง/แท็บช่วงราคา · เช็คไว · ตัวเฝ้าบิล · รูป LINE) ต้องเรียกฟังก์ชันในไฟล์นี้เท่านั้น
ถ้าช่องทางหนึ่งบอก ✅ อีกทางบอก ⛔ = บั๊กระดับหยุดงาน (HANDOVER_CheckBill_v2 ข้อ 5)

เกณฑ์ทั้งหมดคัดจาก PRICE_APPROVAL_MODE v1.1 + HANDOVER_P17_PriceBands_Trial ข้อ 3
❌ ห้ามแก้ตัวเลขในหมวด "POLICY" เองโดยไม่ได้รับอนุมัติจาก ผบ. (ข้อ 9.1)
"""
import base64
import datetime
import json
import math

# ============================== POLICY (ผบ. เท่านั้นที่แก้ได้) ==============================
VAT = 1.07
GP_SELF = 0.20          # ชั้น "ลดได้เอง" สินค้าปกติ
GP_SELF_FAST = 0.15     # ชั้น "ลดได้เอง" สินค้าหมุนเร็ว (≥ 8 บิล/60 วัน)
GP_MGR = 0.10           # ชั้น "ผจก.อนุมัติ" — ต่ำกว่านี้ = ขอ ผบ.
SELF_DISCOUNT_PER_M = 5.0   # อำนาจเซลลดเองจาก Rate 1 (บาท/เมตร) — ใช้กับสินค้าหน่วยเมตรเท่านั้น
AUTO_LIMIT_BAHT = 300000    # วงเงินที่ระบบอนุมัติเองได้ต่อใบ — เกินส่ง ผบ.
MIN_COVERAGE = 70.0         # บรรทัดที่รู้ทุนรวม < 70% ของมูลค่าใบ → ไม่สรุป (กฎ v0.3)
FAST_SHARE = 0.70           # บิลที่ ≥70% ของมูลค่า (ส่วนที่รู้ทุน) เป็นของหมุนเร็ว → ใช้เกณฑ์หมุนเร็ว
FRESH_DAYS = 14             # ทุนเก่ากว่านี้ → เกรดสูงสุด C (ประตูความสด)
TRANSFER_TOLERANCE = 0.005  # โอนข้ามสาขา (ZZC) ที่ราคาทุน ±0.5% ไม่นับว่าต่ำกว่าทุน
CARD_FEE = 0.016            # ค่าธรรมเนียมบัตร (ถ้าไม่ชาร์จลูกค้า)

GRADE_PCT = {"A": 100, "B": 75, "C": 50, "D": 25, "X": 0}
GRADE_TEXT = {
    "A": "ราคาดี ปิดเลย ⭐",
    "B": "ขายได้เลย ✅",
    "C": "ผจก.อนุมัติ 🟡",
    "D": "ต้องขอ ผบ. 🔴",
    "X": "ห้ามขาย ⛔ ปรับราคาก่อน",
}
TIERS = [  # ชั้นราคา (เรียงจากสูงลงต่ำ) — ชื่อที่เซลเห็น
    ("stand", "🟢 ยืนราคา"),
    ("self", "🟢 ลดได้เอง"),
    ("mgr", "🟡 ผจก.อนุมัติ"),
    ("gem", "🔴 ขอ ผบ."),
]
# ============================================================================================

METER_UNITS = {"ม", "ม.", "เมตร", "m", "M", "MT", "MTR"}
PU_PREFIX = "03VP-PU"
FOLD_PREFIX = "07ETC"


def unit_kind(unit):
    u = (unit or "").strip()
    return "meter" if u in METER_UNITS else "piece"


def ceil_to(x, step):
    """ปัดขึ้นเสมอ (ข้อ 8.4 ห้ามปัดลง) — กัน float เพี้ยน 1e-9"""
    return round(math.ceil(x / step - 1e-9) * step, 2)


def price_step(kind, ref_price):
    # บาทเต็มสำหรับสินค้าต่อเมตร/แผ่น · 0.05 บาทสำหรับสกรู/ชิ้นเล็ก
    return 1.0 if kind == "meter" or (ref_price or 0) >= 50 else 0.05


def p_at(cost, g):
    """ราคาที่ให้ GP = g : P(g) = ทุน ÷ (1 − g)"""
    return cost / (1.0 - g)


# ------------------------------------------------------------------ ทุน
def load_rules(path):
    """อ่าน costbook_rules.json (base64 v2 จาก dealscore.py rules) · ตัด PIN ทิ้งทันที ไม่ส่งต่อที่ไหน"""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    rules = json.loads(base64.b64decode(d["data"])) if "data" in d else d
    rules.pop("pins", None)
    return rules


class CostBook:
    """ลำดับทุน v0.4 (ผบ. ยืนยัน — ห้ามสลับ):
    ① ทุนเฉลี่ยสต็อกการ์ด Express แยกรายสาขา (exact[br]) — ยกเว้นกลุ่ม 02 ที่หน่วยสต็อกไม่ใช่หน่วยขาย
    ② prefix วัตถุดิบคัดมือ (สินค้าผลิตเอง)
    ③ ใบซื้อล่าสุด POPRIT / ทุนสาขาอื่น (exact_any — fallback)
    ทุนทั้งหมดเทียบแบบรวม VAT (ยกเว้น ZZC ที่ dealscore เก็บ ex-VAT ตามราคาโอน)"""

    def __init__(self, rules, today=None):
        self.rules = rules
        self.prefix = rules.get("prefix", [])
        ex = rules.get("exact", {})
        first = next(iter(ex.values()), None) if ex else None
        self.per_branch = ex if isinstance(first, dict) else {"*": ex}
        self.any = rules.get("exact_any", {})
        self.fast = set(rules.get("fast", []))
        self.updated = rules.get("updated")
        self.today = today or datetime.date.today()

    @property
    def age_days(self):
        try:
            return (self.today - datetime.date.fromisoformat(self.updated)).days
        except (TypeError, ValueError):
            return 999

    def _prefix(self, code):
        return next(((c, r1) for pre, c, r1 in self.prefix if code.startswith(pre)), None)

    def cost(self, code, branch, tfactor=1.0):
        """คืน dict {cost, source, rate1_hint, unit_verified} หรือ None ถ้าหาไม่ได้ (= ถามก่อนลด ห้ามเดา)"""
        code = (code or "").strip()
        if not code:
            return None
        tf = tfactor or 1.0
        pref = self._prefix(code)
        exb = self.per_branch.get(branch) or self.per_branch.get("*") or {}
        group02 = code.startswith("02")
        if not group02 and code in exb:
            return {"cost": round(exb[code] * tf, 2), "source": "express_avg",
                    "rate1_hint": pref[1] if pref else None, "unit_verified": True}
        if pref:
            # กลุ่ม 02 (ครอบ) หน่วยสต็อกเป็นเส้น 2/4 ม. — ทุน prefix เป็นต่อเมตร แปลงไม่ได้จนกว่าจะมี unit-map
            return {"cost": round(pref[0], 2), "source": "prefix",
                    "rate1_hint": pref[1], "unit_verified": not group02}
        if not group02 and code in self.any:
            return {"cost": round(self.any[code] * tf, 2), "source": "fallback",
                    "rate1_hint": None, "unit_verified": True}
        return None

    def is_fast(self, code):
        return code in self.fast


# ------------------------------------------------------------------ ช่วงราคา (เฟส 0.5)
def price_bands(cost, rate1, unit, fast=False, protect=False, code=""):
    """ขอบล่างของแต่ละชั้น (รวม VAT ต่อหน่วย) — ผลนี้ไม่มีทุน/GP ส่งให้เซลได้
    คืน dict: stand (≥Rate1), self_low, mgr_low (ต่ำกว่านี้ = ขอ ผบ.), self_empty, flags"""
    if code.startswith(FOLD_PREFIX):
        return {"status": "fold", "note": "งานพับ: ขั้นต่ำ = ราคาเหล็กเต็มหน้ากว้าง + 30% (ไม่ออกช่วงราคา)"}
    if cost is None or cost <= 0:
        return {"status": "ask", "note": "ถามก่อนลด (ระบบยังไม่มีทุนรหัสนี้)"}
    kind = unit_kind(unit)
    step = price_step(kind, rate1 or cost)
    g_self = GP_SELF_FAST if fast else GP_SELF
    p_self, p_mgr = p_at(cost, g_self), p_at(cost, GP_MGR)
    flags = []
    if rate1:
        self_low = max(rate1 - SELF_DISCOUNT_PER_M, p_self) if kind == "meter" else p_self
        if p_at(cost, GP_SELF) > rate1:
            flags.append("rate1_below_target")     # ราคาป้ายเองก็ได้ GP ไม่ถึง 20% → รายงาน ผบ.
        if rate1 < p_mgr:
            # ราคาป้ายต่ำกว่า GP 10% (หรือต่ำกว่าทุน) → ห้ามขึ้นเขียว "ยืนราคา" ที่ Rate 1 · รอ ผบ. ตัดสินในรายงาน
            return {"status": "ask", "note": "ถามก่อนขาย — ราคาป้ายต่ำกว่าเกณฑ์ขั้นต่ำ รอ ผบ. ตัดสิน",
                    "unit": unit, "kind": kind, "fast": bool(fast), "flags": flags + ["rate1_below_floor"]}
    else:
        self_low = p_self
        flags.append("no_rate1")
    self_low = ceil_to(self_low, step)
    mgr_low = ceil_to(p_mgr, step)
    stand = ceil_to(rate1, step) if rate1 else None
    # ไม่มี Rate 1 = ไม่มีคำว่า "ลดจากป้าย" → ชั้นเขียวเดียว ≥ P(20%) (สินค้าชิ้น/สกรู)
    self_empty = stand is not None and (protect or self_low >= stand)
    if self_empty:
        self_low = stand
    if protect:
        flags.append("protect")
    mgr_low = min(mgr_low, self_low)
    return {"status": "ok", "unit": unit, "kind": kind, "fast": bool(fast),
            "stand": stand, "self_low": self_low, "mgr_low": mgr_low,
            "self_empty": bool(self_empty), "flags": flags}


def classify(price, bands):
    """ชั้นของราคาที่เซลจะให้ (ใช้เฉพาะขอบที่คำนวณแล้ว — ไม่ต้องรู้ทุน)"""
    if bands.get("status") != "ok":
        return bands.get("status")
    if bands["stand"] is not None and price >= bands["stand"]:
        return "stand"
    if not bands["self_empty"] and price >= bands["self_low"]:
        return "self"
    if price >= bands["mgr_low"]:
        return "mgr"
    return "gem"


# ------------------------------------------------------------------ เกรดบิล (เฟส 1)
def _base_grade(gpp, fast):
    if gpp >= 35:
        return "A"
    if gpp >= 20 or (fast and gpp >= 15):
        return "B"
    if gpp >= 10:
        return "C"
    return "D"


def grade_bill(lines, branch, book, role="SALES", total_override=None, freight=0.0,
               card_unpaid=False, extra_costs=0.0, rate1_of=None, layer="B", policy=None):
    """คิดเกรดทั้งบิล (ไม่ใช่รายบรรทัด) · lines = [{code, qty, price, tfactor?, value?, desc?}]
    rate1_of(code) → Rate 1 ของรหัส (ใช้ทำคำแนะนำ "ยืน Rate 1") · role = SALES | MGR | GEM
    คืน dict ตามสเปคข้อ 5.5 — โหมด SALES ไม่มี gp_pct / ทุน แม้แต่ในคีย์ย่อย"""
    rev = known_rev = cost_total = fast_rev = 0.0
    at_rate1_rev = at_rate1_cost = 0.0
    below, detail, cats = [], [], set()
    for ln in lines:
        code = (ln.get("code") or "").strip()
        qty = float(ln.get("qty") or 0)
        price = float(ln.get("price") or 0)
        value = float(ln.get("value") if ln.get("value") is not None else qty * price)
        rev += value
        cats.add(code[:2])
        if code.startswith(PU_PREFIX):
            cats.add("PU")
        c = book.cost(code, branch, ln.get("tfactor") or 1.0)
        row = {"code": code, "qty": qty, "price": price, "known": bool(c)}
        if c and value > 0:
            known_rev += value
            cost_total += qty * c["cost"]
            if book.is_fast(code):
                fast_rev += value
            tol = TRANSFER_TOLERANCE if code.startswith("ZZC") else 0.0
            if price < c["cost"] * (1 - tol):
                below.append(code)
                row["below_cost"] = True
            r1 = (rate1_of(code) if rate1_of else None) or c.get("rate1_hint")
            p1 = max(price, r1) if r1 else price
            at_rate1_rev += qty * p1
            at_rate1_cost += qty * c["cost"]
            if r1 and price < r1:
                row["below_rate1"] = True
            row["cost"] = c["cost"]
        detail.append(row)
    total = total_override if total_override is not None else rev
    hidden = freight + extra_costs + (known_rev * CARD_FEE if card_unpaid else 0.0)
    coverage = known_rev / rev * 100 if rev else 0.0
    gpp = (known_rev - cost_total - hidden) / known_rev * 100 if known_rev else 0.0
    fast = known_rev > 0 and fast_rev / known_rev >= FAST_SHARE
    age = book.age_days
    reasons, tags = [], []
    if fast:
        tags.append("fast_mover")
        reasons.append("บิลนี้ส่วนใหญ่เป็นสินค้าหมุนเร็ว — ใช้เกณฑ์ผ่อน (ตามกติกา v1.1)")
    if "PU" in cats:
        tags.append("profit_maker")

    if coverage < MIN_COVERAGE:
        grade = None
        reasons.append("ระบบรู้ทุนไม่ถึง 70% ของบิล — ยังสรุปไม่ได้ ส่งเลข SO ให้ผจก./แชทช่วยเช็ค")
    elif below or gpp < 0:
        grade = "X"
        reasons.append("มีรายการราคาต่ำกว่าทุน — ต้องปรับราคาขึ้นก่อน ห้ามขาย")
    else:
        grade = _base_grade(gpp, fast)
        if total > AUTO_LIMIT_BAHT and grade in ("A", "B", "C"):
            grade = "D"
            reasons.append("ยอดบิลเกิน 300,000 บาท — ต้องให้ ผบ. อนุมัติทุกกรณี")
        if age > FRESH_DAYS and grade in ("A", "B"):
            grade = "C"
            reasons.append(f"ข้อมูลทุนเก่า {age} วัน — ระบบลดเกรดสูงสุดเป็น C จนกว่าจะอัปเดต")

    floor_b = 15 if fast else 20
    if grade is None:
        headroom = None
    elif grade == "X" or gpp < floor_b:
        headroom = "red"
    elif gpp - floor_b >= 10:
        headroom = "green"
    else:
        headroom = "yellow"

    suggest = None
    if any(r.get("below_rate1") for r in detail) and at_rate1_rev > 0:
        g1 = (at_rate1_rev - at_rate1_cost - hidden) / at_rate1_rev * 100
        suggest = "Rate 1" + (" = เกรด A ⭐" if g1 >= 35 else "")
    upsell = []
    if "01" in cats and "02" not in cats:
        upsell.append("ครอบสีเดียวกัน")
    if ("01" in cats or "02" in cats) and "04" not in cats:
        upsell.append("สกรู")
    if "01" in cats and "PU" not in cats:
        upsell.append("PU Foam")

    out = {
        "grade": grade,
        "grade_text": GRADE_TEXT.get(grade, "ยังสรุปไม่ได้ 🟡"),
        "approval_pct": GRADE_PCT.get(grade) if grade else None,
        "headroom": headroom,
        "suggest_price_level": suggest,
        "upsell": upsell,
        "tags_hit": tags,
        "script": _script(grade, "PU" in cats, headroom),
        "reasons": reasons,
        "below_cost_codes": below,           # รหัสเท่านั้น — ไม่มีตัวเลขทุน
        "costbook_age_days": age,
        "coverage_pct": round(coverage),
        "branch": branch,
        "layer": layer,
        "total": round(total, 2),
    }
    if layer in ("A", "C"):
        out["disclaimer"] = ("ผลนี้ตรวจจากรายการที่พิมพ์/ถ่ายมา — ก่อนปริ้นส่งลูกค้า "
                             "ให้เช็คซ้ำจากบิล Express จริง")
    if role == "MGR" and coverage >= MIN_COVERAGE:
        out["gp_band"] = ("ต่ำกว่าทุน" if gpp < 0 else "0-10%" if gpp < 10 else "10-20%"
                          if gpp < 20 else "20-35%" if gpp < 35 else "≥35%")
        out["flags"] = [r["code"] + (" ⛔ต่ำกว่าทุน" if r.get("below_cost") else " 🔻ต่ำกว่า Rate1")
                        for r in detail if r.get("below_cost") or r.get("below_rate1")]
    if role == "GEM":
        out["gp_pct"] = round(gpp, 1)
        out["cost_total"] = round(cost_total, 2)
        out["hidden_costs"] = round(hidden, 2)
        out["lines"] = detail
    return out


def _script(grade, has_pu, headroom):
    base = "ตัวนี้ของแท้ Bluescope มีใบรับประกันผู้ผลิต ส่งถึงไม่บุบ 100% ครับ"
    if grade in ("A", "B") and headroom == "green":
        return base + " — ราคานี้คุ้มสุดแล้วครับ"
    if grade in ("B", "C"):
        return base + (" · ถ้าลูกค้าต่ออีก ให้ลดค่าส่ง/ของแถมก่อน ไม่ใช่ลด PU" if has_pu
                       else " · ถ้าลูกค้าต่ออีก ให้ลดค่าส่ง/ของแถมก่อน")
    if grade == "D":
        return "ขอเวลาเช็คราคาพิเศษกับผู้บริหารสักครู่นะครับ (ส่งเข้าแชทพร้อมเหตุผล)"
    if grade == "X":
        return "ราคานี้ต่ำกว่าที่บริษัทขายได้ — เสนอรุ่น/ความหนาอื่น หรือยืนราคาเดิมครับ"
    return "ขอเช็คราคาให้ชัวร์ก่อนยืนยันนะครับ"


def approval_log_entry(result, who, items_text=""):
    """แถว log สำหรับผล < 75% (ข้อ 5 ข้อบังคับร่วม) — ไม่มีทุน/GP"""
    return {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "br": result["branch"],
            "by": who or "sales", "layer": result["layer"], "items": items_text,
            "total": result["total"], "grade": result["grade"], "chance": result["approval_pct"],
            "cov": result["coverage_pct"]}
