# -*- coding: utf-8 -*-
"""
Approve007 · build — รันบน Mac mini (launchd 06:30 ทุกเช้า) อ่าน/เขียนใน All_on_Cloud

  python3 build.py preflight          ตรวจโฟลเดอร์/ไฟล์/ความสดก่อนทำงาน (ห้ามข้าม)
  python3 build.py                    สร้างช่วงราคา 3 สาขา → Approve007/pricebands.js + PDF + รายงาน ผบ. + status
  python3 build.py --inspect          รหัสขายดีที่ยังไม่มี Rate 1 / ยังไม่มีทุน (ไว้แก้ config/families.json)
  python3 build.py verify             ทดสอบเคสจริงตาม DoD (SO6903141 PPS · SO6904651 SKN)
  python3 build.py check SO6903141 [PPS] [GEM|MGR] เกรดบิลจริงจาก Express (ไม่ใส่สาขา = ค้นทุกสาขา · ซ้ำ = ให้เลือก)
  python3 build.py backtest [วัน=90]  baseline สัดส่วนเกรดรายสาขา/รายเซล (Charter K1/K6)
  python3 build.py push               เฟส 1: ส่งทุน/Rate 1/บิล 60 วันขึ้น API + ดึงผล < 75% ลง approval_requests.jsonl
  python3 build.py pull-log           ดึงผล < 75% อย่างเดียว

ไฟล์ที่เซลเปิดได้ (Approve007/*) ห้ามมีทุน/GP — build จะ assert ก่อนเขียนทุกครั้ง
"""
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import approve_engine as E          # noqa: E402
import pricesheet as PS             # noqa: E402
from dbf import fields_of, read_dbf  # noqa: E402
from paths import Layout            # noqa: E402

BRANCHES = ("BK", "SKN", "PPS")
BR_NAME = {"BK": "บึงกาฬ", "SKN": "สกลนคร", "PPS": "โพนพิสัย"}
SALES_DAYS = 90
TOP_SHARE = 0.80
VALID_DAYS = 7
FORBIDDEN_KEYS = {"cost", "cost_total", "gp", "gp_pct", "gp_band", "p20", "p10", "p15", "hidden_costs",
                  "express_cost", "coil_cost", "cost_source"}


def today():
    return datetime.date.today()


def be_yymmdd(d):
    return f"{(d.year + 543) % 100:02d}{d.month:02d}{d.day:02d}"


def th_date(d):
    return f"{d.day}/{d.month}/{d.year + 543}"


def assert_no_cost(obj, where="output"):
    """กันทุนรั่วลงไฟล์ที่เซลเปิดได้ (HANDOVER ข้อ 9.2) — เจอคีย์ต้องห้าม = หยุดทันที"""
    if isinstance(obj, dict):
        bad = FORBIDDEN_KEYS & set(obj)
        if bad:
            raise AssertionError(f"⛔ พบข้อมูลทุน/GP {sorted(bad)} ใน {where} — ยกเลิกการเขียน")
        for v in obj.values():
            assert_no_cost(v, where)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_cost(v, where)


def backup_then_write(path, data, backup_dir, binary=False):
    """ห้ามเขียนทับไฟล์ที่ใช้งานอยู่โดยไม่สำรอง (ข้อ 9.6) → _backup/<ชื่อ>.<YYMMDD>"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.makedirs(backup_dir, exist_ok=True)
        dst = os.path.join(backup_dir, f"{os.path.basename(path)}.{be_yymmdd(today())}")
        if not os.path.exists(dst):
            shutil.copy2(path, dst)
    tmp = path + ".tmp"
    with open(tmp, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as f:
        f.write(data)
    os.replace(tmp, path)


def as_date(v):
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str) and len(v) == 8 and v.isdigit():
        return datetime.date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    return None


# ------------------------------------------------------------------ โหลดข้อมูล
class Data:
    def __init__(self, L, days=SALES_DAYS):
        self.L = L
        self.rules = E.load_rules(L.rules_file)
        self.book = E.CostBook(self.rules)
        fam_cfg = json.load(open(os.path.join(HERE, "config", "families.json"), encoding="utf-8"))
        self.families = fam_cfg["families"]
        self.coil_adder = fam_cfg.get("coil_processing_per_m", 2.5)
        for f in self.families:
            f["_re"] = [re.compile(x) for x in f["stkcod"]]
        self.rate_sheet = L.latest_sheet("ใบราคาขายแผ่น")
        self.coil_sheet = L.latest_sheet("ใบต้นทุนราคาขายคอยล์")
        self.rate_rows = PS.read_rate_sheet(self.rate_sheet[1]) if self.rate_sheet else []
        self.coil_rows = PS.read_coil_sheet(self.coil_sheet[1]) if self.coil_sheet else []
        for f in self.families:
            row = PS.match_rate(self.rate_rows, f["rate"]) if self.rate_rows else None
            f["_rate1"] = row["rates"][0] if row and row["rates"][0] else None
            coil = PS.match_coil(self.coil_rows, f.get("coil")) if self.coil_rows else None
            f["_coil_m"] = round(coil["per_m"] + self.coil_adder, 2) if coil else None
        self.stmas = {br: self._stmas(br) for br in BRANCHES}
        self.sales = {br: self._sales(br, days) for br in BRANCHES}

    def _stmas(self, br):
        p = self.L.dbf(br, "STMAS.DBF")
        out = {}
        if not os.path.exists(p):
            return out
        for r in read_dbf(p, {"STKCOD", "STKDES", "SQUCOD", "QUCOD", "SELLPR1", "STKGRP"}):
            c = (r.get("STKCOD") or "").strip()
            if c:
                out[c] = r
        return out

    def _sales(self, br, days):
        p = self.L.dbf(br, "OESOIT.DBF")
        cut = today() - datetime.timedelta(days=days)
        agg = defaultdict(lambda: {"val": 0.0, "qty": 0.0, "bills": set()})
        if not os.path.exists(p):
            return agg
        for r in read_dbf(p, {"SONUM", "SODAT", "STKCOD", "TRNVAL", "ORDQTY"}):
            d = as_date(r.get("SODAT"))
            c = (r.get("STKCOD") or "").strip()
            if not d or d < cut or not c or not (r.get("SONUM") or "").startswith("SO"):
                continue
            a = agg[c]
            a["val"] += r.get("TRNVAL") or 0
            a["qty"] += r.get("ORDQTY") or 0
            a["bills"].add(r["SONUM"])
        return agg

    def family_of(self, code):
        return next((f for f in self.families if any(rx.search(code) for rx in f["_re"])), None)

    def rate1_of(self, code, br):
        """Rate 1 (รวม VAT): ① ใบราคาขายแผ่นล่าสุดตามกลุ่ม ② SELLPR1 ใน Express ③ ค่าเก่าจาก costbook prefix"""
        f = self.family_of(code)
        if f and f["_rate1"]:
            return f["_rate1"], "price_sheet"
        s = self.stmas[br].get(code) or {}
        if (s.get("SELLPR1") or 0) > 0:
            return round(s["SELLPR1"], 2), "express_sellpr1"
        c = self.book.cost(code, br)
        if c and c.get("rate1_hint"):
            return c["rate1_hint"], "legacy_prefix"
        return None, None

    def unit_of(self, code, br):
        s = self.stmas[br].get(code) or {}
        return (s.get("SQUCOD") or s.get("QUCOD") or "").strip()

    def desc_of(self, code, br):
        s = self.stmas[br].get(code) or {}
        return (s.get("STKDES") or code).strip()

    def pick_codes(self, br):
        """รหัสที่รวมยอดขาย ≥ 80% (90 วัน) + ทุกรหัสที่อยู่ในกลุ่มหลักของ Quote007 และมีขายจริง"""
        agg = self.sales[br]
        total = sum(a["val"] for a in agg.values()) or 1
        picked, run = [], 0.0
        for c, a in sorted(agg.items(), key=lambda kv: -kv[1]["val"]):
            if run / total < TOP_SHARE or self.family_of(c):
                picked.append(c)
            run += a["val"]
        return [c for c in picked if not c.startswith("ZZ")]   # ZZ = คอยล์/โอนข้ามสาขา ไม่ใช่สินค้าขายหน้าร้าน


# ------------------------------------------------------------------ สร้างช่วงราคา
def build_branch(D, br):
    rows, report, missing = {}, [], []
    for code in D.pick_codes(br):
        c = D.book.cost(code, br)
        rate1, r1src = D.rate1_of(code, br)
        unit = D.unit_of(code, br) or ("ม." if code.startswith(("01", "03")) else "")
        fam = D.family_of(code)
        usable = c if (c and c["unit_verified"]) else None
        b = E.price_bands(usable["cost"] if usable else None, rate1, unit,
                          fast=D.book.is_fast(code), code=code)
        if b["status"] == "ask" and not usable:
            missing.append((code, D.desc_of(code, br), round(D.sales[br][code]["val"])))
        name = fam["label"] if fam else D.desc_of(code, br)
        key = (fam["key"] if fam else "c:" + code, b.get("status"), b.get("stand"), b.get("self_low"),
               b.get("mgr_low"), b.get("self_empty"))
        row = rows.setdefault(key, {"name": name, "cat": fam["category"] if fam else _cat(code),
                                    "unit": unit or "หน่วย", "codes": [], "sales90": 0,
                                    "status": b["status"], "note": b.get("note"),
                                    "stand": b.get("stand"), "self_low": b.get("self_low"),
                                    "mgr_low": b.get("mgr_low"), "self_empty": b.get("self_empty"),
                                    "fast": b.get("fast", False), "rate1_src": r1src})
        row["codes"].append(code)
        row["sales90"] += round(D.sales[br][code]["val"])
        if usable and rate1 and "rate1_below_target" in b.get("flags", []):
            need = E.ceil_to(E.p_at(usable["cost"], E.GP_SELF), 1.0)
            coil = fam["_coil_m"] if fam else None
            drift = abs(usable["cost"] - coil) / coil * 100 if coil else None
            report.append({"branch": br, "code": code, "name": D.desc_of(code, br), "rate1": rate1,
                           "rate1_src": r1src, "cost": usable["cost"], "cost_source": usable["source"],
                           "coil_cost": coil, "drift_pct": round(drift, 1) if drift is not None else None,
                           "need_rate1_for_20": need, "pile": "ก" if (drift is not None and drift > 5) else "ข",
                           "below_floor": "rate1_below_floor" in b["flags"],
                           "sales90": round(D.sales[br][code]["val"])})
    out = sorted(rows.values(), key=lambda r: (_cat_order(r["cat"]), -r["sales90"]))
    for r in out:
        if len(r["codes"]) > 1 and r["name"] == D.desc_of(r["codes"][0], br):
            r["name"] += f" (+{len(r['codes']) - 1} รหัส)"
    return out, report, missing


CAT_ORDER = ["แผ่นรีดลอน", "PU Foam", "ครอบ/อุปกรณ์", "สกรู", "อื่น ๆ"]


def _cat(code):
    return ("แผ่นรีดลอน" if code.startswith("01") else "PU Foam" if code.startswith("03")
            else "ครอบ/อุปกรณ์" if code.startswith("02") else "สกรู" if code.startswith("04") else "อื่น ๆ")


def _cat_order(c):
    return CAT_ORDER.index(c) if c in CAT_ORDER else 99


def public_rows(rows):
    keep = ("name", "cat", "unit", "codes", "status", "note", "stand", "self_low", "mgr_low", "self_empty", "fast")
    return [{k: r[k] for k in keep} for r in rows]


# ------------------------------------------------------------------ ตาราง PDF (HTML → Chrome headless)
SCRIPT_LINES = [
    "ของแท้ Bluescope/แบรนด์ มีใบรับประกันผู้ผลิต — ไม่ใช่ของเกรดรอง",
    "ส่งถึงหน้างาน ไม่บุบ 100% · เปลี่ยนให้ถ้าเสียหายจากการขนส่ง",
    "ลูกค้าต่อราคา → ลดค่าส่ง/ให้ของแถม (สกรู/ครอบ) ก่อน · ห้ามลด PU เป็นตัวนำ",
]


def fmt(v):
    if v is None:
        return "–"
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.2f}"


def band_cells(r):
    if r["status"] == "fold":
        return '<td colspan="4" class="note">งานพับ — ขั้นต่ำ = ราคาเหล็กเต็มหน้ากว้าง + 30%</td>'
    if r["status"] != "ok":
        return f'<td colspan="4" class="note">{html.escape(r.get("note") or "ถามก่อนลด")}</td>'
    stand = f"≥ {fmt(r['stand'])}" if r["stand"] is not None else "–"
    if r["stand"] is None:
        self_ = f"≥ {fmt(r['self_low'])}"
    elif r["self_empty"]:
        self_ = '<span class="none">ลดไม่ได้</span>'
    else:
        self_ = f"{fmt(r['self_low'])} – {fmt(r['stand'] - (1 if r['stand'] >= 50 else 0.05))}"
    top_mgr = r["self_low"] - (1 if r["self_low"] >= 50 else 0.05)
    mgr = (f"{fmt(r['mgr_low'])} – {fmt(top_mgr)}" if r["mgr_low"] < r["self_low"]
           else '<span class="none">–</span>')
    return (f'<td class="g">{stand}</td><td class="g">{self_}</td>'
            f'<td class="y">{mgr}</td><td class="r">&lt; {fmt(r["mgr_low"])}</td>')


def render_pdf_html(br, rows, gen, valid_until, stale_reason, sheet_date):
    body = []
    cat = None
    for r in rows:
        if r["cat"] != cat:
            cat = r["cat"]
            body.append(f'<tr class="cat"><td colspan="6">{html.escape(cat)}</td></tr>')
        fast = ' <span class="fast">⚡หมุนเร็ว</span>' if r.get("fast") else ""
        body.append(f'<tr><td>{html.escape(r["name"])}{fast}</td><td class="u">{html.escape(r["unit"])}</td>'
                    f'{band_cells(r)}</tr>')
    banner = (f'<div class="expired">⛔ หมดอายุ ห้ามใช้ — {html.escape(stale_reason)}</div>' if stale_reason else "")
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<title>ช่วงราคา {br} {be_yymmdd(gen)}</title><style>
@page {{ size: A4; margin: 10mm 9mm; }}
body {{ font-family: 'Sarabun','Leelawadee UI','Thonburi','Sukhumvit Set','Loma',sans-serif; font-size: 10.5pt; color:#111; }}
h1 {{ font-size: 15pt; margin: 0; }} .sub {{ font-size: 9pt; margin: 2px 0 6px; }}
table {{ width: 100%; border-collapse: collapse; }} th, td {{ border: 1px solid #555; padding: 2px 4px; }}
th {{ background: #e6e6e6; font-size: 9.5pt; }} td.g, td.y, td.r {{ text-align: center; white-space: nowrap; }}
td.u {{ text-align:center; font-size:9pt; }} tr.cat td {{ background:#f2f2f2; font-weight:700; }}
.note {{ text-align:center; font-style: italic; }} .none {{ color:#666; }} .fast {{ font-size:8pt; }}
.expired {{ background:#c00; color:#fff; font-weight:700; font-size:14pt; padding:6px; text-align:center; margin-bottom:6px; }}
.foot {{ margin-top: 6px; font-size: 9.5pt; }} .foot li {{ margin: 1px 0; }}
tr {{ page-break-inside: avoid; }}
</style></head><body>{banner}
<h1>ช่วงราคาขาย · สาขา{BR_NAME[br]} ({br}) — ทดลองใช้</h1>
<div class="sub">ออก {th_date(gen)} · <b>ใช้ได้ถึง {th_date(valid_until)}</b> · ใบราคาอ้างอิง {sheet_date or '–'} ·
ราคารวม VAT ยังไม่รวมค่าส่ง — <b>งานส่งไกลให้เช็คบิลก่อนยืนยัน</b></div>
<table><thead><tr><th>สินค้า</th><th>หน่วย</th><th>🟢 ยืนราคา</th><th>🟢 ลดได้เอง</th>
<th>🟡 ผจก.อนุมัติ</th><th>🔴 ขอ ผบ.</th></tr></thead><tbody>{''.join(body)}</tbody></table>
<div class="foot"><b>สคริปต์ยืนราคา</b><ul>{''.join(f'<li>{html.escape(s)}</li>' for s in SCRIPT_LINES)}</ul>
ต่ำกว่าช่องแดง = ส่ง ผบ. พร้อมเหตุผลเท่านั้น · ราคาใดไม่อยู่ในตาราง = ถามก่อนลด ·
ส่งความเห็นในกลุ่ม LINE สาขา: <b>#ช่วงราคา [สินค้า] ลูกค้าขอ [ราคา] คู่แข่งให้ [ราคา] ผล [ปิดได้/หลุด]</b></div>
</body></html>"""


CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "google-chrome", "chromium", "chromium-browser",
]


def html_to_pdf(html_path, pdf_path):
    for exe in [os.environ.get("APPROVE007_CHROME")] + CHROME_CANDIDATES:
        if not exe or (os.path.isabs(exe) and not os.path.exists(exe)) or (not os.path.isabs(exe) and not shutil.which(exe)):
            continue
        try:
            subprocess.run([exe, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf_path}", "file://" + os.path.abspath(html_path)],
                           check=True, capture_output=True, timeout=90)
            return os.path.exists(pdf_path)
        except (subprocess.SubprocessError, OSError):
            continue
    return False


# ------------------------------------------------------------------ คำสั่งหลัก
def make_bands(D, gen):
    """ช่วงราคาทั้ง 3 สาขา (ไม่มีทุน) + รายงาน ผบ. — ใช้ทั้งตอนสร้างไฟล์ใน Drive และตอนส่งขึ้น API"""
    valid_until = gen + datetime.timedelta(days=VALID_DAYS)
    age = D.book.age_days
    stale = None
    if age > VALID_DAYS:
        stale = f"ข้อมูลทุนเก่า {age} วัน (costbook_rules อัปเดตล่าสุด {D.book.updated})"
    if not D.rate_sheet:
        stale = "หาใบราคาขายแผ่นไม่เจอ"
    payload = {"app": "Approve007", "kind": "pricebands", "generated": gen.isoformat(),
               "valid_until": valid_until.isoformat(), "stale": stale,
               "rate_sheet": D.rate_sheet[0] if D.rate_sheet else None,
               "policy": {"self_discount_per_m": E.SELF_DISCOUNT_PER_M}, "branches": {}}
    report, missing_all, summary = [], {}, {}
    for br in BRANCHES:
        rows, rep, missing = build_branch(D, br)
        report += rep
        missing_all[br] = missing
        payload["branches"][br] = public_rows(rows)
        summary[br] = {"rows": len(rows), "codes": sum(len(r["codes"]) for r in rows),
                       "ask": sum(1 for r in rows if r["status"] == "ask"),
                       "rate1_below_target": len(rep)}
    assert_no_cost(payload, "pricebands")
    return payload, report, missing_all, summary


def cmd_build(L, inspect=False):
    D = Data(L)
    gen = today()
    payload, report, missing_all, summary = make_bands(D, gen)
    valid_until = datetime.date.fromisoformat(payload["valid_until"])
    stale, age = payload["stale"], D.book.age_days
    tag = be_yymmdd(gen)
    for br in BRANCHES:
        if inspect:
            continue
        page = render_pdf_html(br, payload["branches"][br], gen, valid_until, stale,
                               D.rate_sheet[0] if D.rate_sheet else None)
        assert_no_cost(payload["branches"][br], f"PDF {br}")
        hp = os.path.join(L.app, "print", f"ช่วงราคา_{br}_{tag}.html")
        backup_then_write(hp, page, L.backup)
        pdf = os.path.join(L.app, f"ช่วงราคา_{br}_{tag}.pdf")
        summary[br]["pdf"] = pdf if html_to_pdf(hp, pdf) else None
    if inspect:
        return _print_inspect(D, missing_all, summary)

    assert_no_cost(payload, "pricebands.js")
    js = ("// pricebands.js — สร้างอัตโนมัติโดย Approve007 build.py (ห้ามแก้มือ) · ไม่มีทุน/GP\n"
          "window.PRICEBANDS = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    backup_then_write(os.path.join(L.app, "pricebands.js"), js, L.backup)
    app_src = os.path.join(os.path.dirname(HERE), "app", "approve007.html")
    if os.path.exists(app_src):
        backup_then_write(os.path.join(L.app, "approve007.html"), open(app_src, encoding="utf-8").read(), L.backup)

    # รายงาน ผบ. (มีทุน) → โฟลเดอร์โปรเจกต์ ไม่ใช่โฟลเดอร์แอป
    os.makedirs(L.private, exist_ok=True)
    rp = os.path.join(L.private, f"Rate1_ต่ำกว่าเป้าGP_{tag}.md")
    backup_then_write(rp, render_rate1_report(report, D, gen), os.path.join(L.private, "_backup"))
    status = {"agent": "approve007.pricebands", "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "costbook_age_days": age, "costbook_updated": D.book.updated, "stale": stale,
              "rate_sheet": D.rate_sheet[0] if D.rate_sheet else None,
              "coil_sheet": D.coil_sheet[0] if D.coil_sheet else None,
              "branches": {b: {k: v for k, v in s.items() if k != "pdf"} | {"pdf_ok": bool(s.get("pdf"))}
                           for b, s in summary.items()},
              "rate1_below_target": len(report), "report": rp}
    backup_then_write(os.path.join(L.agent_status, "pricebands_latest.json"),
                      json.dumps(status, ensure_ascii=False, indent=1), L.backup)
    print(json.dumps(status, ensure_ascii=False, indent=1))
    return status


def render_rate1_report(report, D, gen):
    lines = [f"# รายงาน \"Rate 1 ต่ำกว่าเป้า GP 20%\" — {th_date(gen)}",
             f"ใบราคาขายแผ่น {D.rate_sheet[0] if D.rate_sheet else '–'} · ใบต้นทุนคอยล์ "
             f"{D.coil_sheet[0] if D.coil_sheet else '–'} · costbook_rules {D.book.updated}",
             "", "⚠️ มีทุน — สำหรับ ผบ./CTO เท่านั้น ห้ามส่งต่อเซล", "",
             "กอง (ก) ทุนน่าจะเพี้ยน = ทุน Express ต่างจากใบต้นทุนคอยล์ > 5% → CTO ตรวจทุนก่อน",
             "กอง (ข) ทุนจริงขึ้นแล้วป้ายไม่ขยับ → **ผบ. ตัดสิน**: ขึ้นป้าย / ยอมเป็น cash cow / ทุนยังเพี้ยน", ""]
    for pile in ("ข", "ก"):
        rows = [r for r in report if r["pile"] == pile]
        lines += [f"## กอง ({pile}) — {len(rows)} รายการ", "",
                  "| สาขา | รหัส | สินค้า | Rate 1 | ทุน (ที่มา) | ทุนใบคอยล์ | ต่าง% | ต้องขึ้นป้ายเป็น | ยอดขาย 90 วัน |",
                  "|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in sorted(rows, key=lambda x: -x["sales90"]):
            warn = " ⛔ป้ายต่ำกว่า GP10% (ตารางขึ้น 'ถามก่อนขาย')" if r["below_floor"] else ""
            lines.append(f"| {r['branch']} | {r['code']} | {r['name']}{warn} | {fmt(r['rate1'])} ({r['rate1_src']}) | "
                         f"{fmt(r['cost'])} ({r['cost_source']}) | {fmt(r['coil_cost'])} | "
                         f"{'–' if r['drift_pct'] is None else r['drift_pct']} | {fmt(r['need_rate1_for_20'])} | "
                         f"{r['sales90']:,} |")
        lines.append("")
    return "\n".join(lines)


def _print_inspect(D, missing_all, summary):
    print(f"ใบราคา: {D.rate_sheet} · ใบคอยล์: {D.coil_sheet} · costbook {D.book.updated} (อายุ {D.book.age_days} วัน)")
    print("\nกลุ่มสินค้าที่ยังหา Rate 1 ในใบราคาไม่เจอ:")
    for f in D.families:
        if not f["_rate1"]:
            print("  -", f["key"], f["label"])
    for br in BRANCHES:
        agg = D.sales[br]
        nofam = [(c, a["val"]) for c, a in agg.items() if not D.family_of(c) and c.startswith(("01", "03"))]
        print(f"\n[{br}] {summary[br]} · แผ่น/PU ขายดีที่ยังไม่เข้ากลุ่มใดใน families.json:")
        for c, v in sorted(nofam, key=lambda x: -x[1])[:25]:
            print(f"   {c:26s} {D.desc_of(c, br)[:40]:40s} {v:>12,.0f}")
        print(f"[{br}] ขายดีแต่ยังไม่มีทุน (จะขึ้น 'ถามก่อนลด'):")
        for c, desc, v in sorted(missing_all[br], key=lambda x: -x[2])[:15]:
            print(f"   {c:26s} {desc[:40]:40s} {v:>12,}")
    return summary


def cmd_preflight(L):
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + msg)
        ok = ok and cond

    print("All_on_Cloud =", L.root)
    for br in BRANCHES:
        for f in ("OESOIT.DBF", "STMAS.DBF", "STCRD.DBF", "POPRIT.DBF"):
            p = L.dbf(br, f)
            if os.path.exists(p):
                age_h = (datetime.datetime.now().timestamp() - os.path.getmtime(p)) / 3600
                chk(True, f"{br}/{f} (แก้ล่าสุด {age_h:.1f} ชม.ก่อน)")
            else:
                chk(False, f"{br}/{f} ไม่มี")
    chk(os.path.exists(L.rules_file), "AutoExport/scripts/costbook_rules.json")
    if os.path.exists(L.rules_file):
        b = E.CostBook(E.load_rules(L.rules_file))
        chk(b.age_days <= E.FRESH_DAYS, f"costbook_rules อัปเดต {b.updated} (อายุ {b.age_days} วัน · เกณฑ์ ≤ {E.FRESH_DAYS})")
    rs, cs = L.latest_sheet("ใบราคาขายแผ่น"), L.latest_sheet("ใบต้นทุนราคาขายคอยล์")
    chk(bool(rs), f"ใบราคาขายแผ่นล่าสุด: {rs[0] if rs else 'ไม่เจอ'}")
    chk(bool(cs), f"ใบต้นทุนคอยล์ล่าสุด: {cs[0] if cs else 'ไม่เจอ'}")
    try:
        import openpyxl  # noqa: F401
        chk(True, "openpyxl")
    except ImportError:
        chk(False, "openpyxl ไม่มี → pip3 install openpyxl")
    p = L.dbf("SKN", "STMAS.DBF")
    if os.path.exists(p):
        names = {n for n, _, _ in fields_of(p)}
        chk({"STKCOD", "STKDES", "SELLPR1", "SQUCOD"} <= names, "STMAS มีฟิลด์ STKCOD/STKDES/SELLPR1/SQUCOD")
    p = L.dbf("SKN", "OESOIT.DBF")
    if os.path.exists(p):
        names = {n for n, _, _ in fields_of(p)}
        chk({"SONUM", "SODAT", "STKCOD", "ORDQTY", "UNITPR", "TRNVAL"} <= names, "OESOIT มีฟิลด์ที่ต้องใช้")
    print("PRE-FLIGHT OK" if ok else "PRE-FLIGHT FAIL — หยุด รายงาน ผบ. ห้ามเดา path")
    return ok


def so_lines(L, sonum, br):
    rows = [r for r in read_dbf(L.dbf(br, "OESOIT.DBF"),
                                {"SONUM", "SODAT", "STKCOD", "ORDQTY", "UNITPR", "TRNVAL", "TFACTOR", "STKDES"})
            if r.get("SONUM") == sonum]
    return [{"code": r.get("STKCOD"), "qty": r.get("ORDQTY"), "price": r.get("UNITPR"),
             "value": r.get("TRNVAL"), "tfactor": r.get("TFACTOR") or 1, "desc": r.get("STKDES"),
             "date": as_date(r.get("SODAT"))} for r in rows]


def so_header(L, sonum, br):
    """วันที่/ลูกค้าจาก OESO (ถ้ามี) — ใช้ช่วยเซลเลือกสาขาเมื่อเลข SO ซ้ำ"""
    p = L.dbf(br, "OESO.DBF")
    if os.path.exists(p):
        for r in read_dbf(p, {"SONUM", "SODAT", "CUSCOD", "CUSNAM"}):
            if r.get("SONUM") == sonum:
                return r
    return {}


def find_so(L, sonum, branches=BRANCHES):
    """หา SO ในทุกสาขาที่ระบุ → [(สาขา, lines)] · เลข SO ซ้ำข้ามสาขาได้จริง (SO6903141 มี 3 สาขา)"""
    return [(br, lines) for br in branches if os.path.exists(L.dbf(br, "OESOIT.DBF"))
            for lines in [so_lines(L, sonum, br)] if lines]


def cmd_check(L, sonum, br=None, role="SALES"):
    """เช็คบิลจากเลข SO · ไม่ระบุสาขา = ใช้ APPROVE007_BRANCH (เครื่องสาขา) หรือค้นทั้ง 3 สาขา
    เจอมากกว่า 1 สาขา → ไม่เดา แสดงรายการให้เลือกแล้วรันใหม่พร้อมสาขา (HANDOVER ข้อ 8)"""
    sonum = sonum.strip().upper()
    br = (br or os.environ.get("APPROVE007_BRANCH") or "").upper() or None
    hits = find_so(L, sonum, (br,) if br else BRANCHES)
    if not hits:
        print(f"ไม่พบ {sonum} ใน {br or 'ทั้ง 3 สาขา'}")
        return None
    if len(hits) > 1:
        print(f"⚠️ เลข {sonum} มีใน {len(hits)} สาขา — เลือกสาขาให้ถูกก่อน แล้วรันใหม่: build.py check {sonum} <สาขา>")
        for b, lines in hits:
            h = so_header(L, sonum, b)
            d = as_date(h.get("SODAT")) or lines[0].get("date")
            total = sum((l["value"] if l["value"] is not None else (l["qty"] or 0) * (l["price"] or 0)) for l in lines)
            cus = (h.get("CUSNAM") or h.get("CUSCOD") or "").strip()
            print(f"  • {b} ({BR_NAME[b]}): วันที่ {th_date(d) if d else '–'} · ลูกค้า {cus or '–'} · "
                  f"{len(lines)} บรรทัด · ยอด {total:,.2f} บาท")
        return {"ambiguous": [b for b, _ in hits]}
    b, lines = hits[0]
    D = Data(L, days=1)
    res = E.grade_bill(lines, b, D.book, role=role, rate1_of=lambda c: D.rate1_of(c, b)[0])
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def cmd_verify(L):
    """DoD 30 ก.ย. — ต้องผ่านทุกข้อก่อนเปิดทดลอง"""
    D = Data(L, days=1)
    cases = [
        ("SO6903141", "PPS", r"^01A-.*-035-(ZC|COOL)", 125, {"gem"}, "Zacs Cool 0.35 @125 → 🔴 หรือต่ำกว่า"),
        ("SO6903141", "PPS", r"^04S-75", 2.50, {"self"}, "สกรู 75 มม. @2.50 → ลดได้เอง (ทุนจริง 1.93 · CTO ยืนยัน 27 ก.ย.)"),
        ("SO6903141", "PPS", r"^03VP-PU.*(WALN|WOOD|LW)", 100, {"mgr", "gem"}, "PU ลายไม้ @100 → ต่ำกว่า 'ลดได้เอง'"),
        ("SO6904651", "SKN", r"^03VP-", 148, {"stand", "self"}, "สแน็ปล็อค+PU @148 → ชั้น 'ลดได้เอง' (ผบ. อนุมัติจริง GP 32%)"),
    ]
    allok = True
    for so, br, pat, price, want, label in cases:
        lines = [l for l in so_lines(L, so, br) if re.search(pat, l["code"] or "")]
        if not lines:
            print(f"  ⚠️ {label}: ไม่พบบรรทัดที่ตรง {pat} ใน {so} {br} — ตรวจ regex เทียบรหัสจริง")
            allok = False
            continue
        code = lines[0]["code"]
        c = D.book.cost(code, br)
        rate1, _ = D.rate1_of(code, br)
        b = E.price_bands(c["cost"] if c and c["unit_verified"] else None, rate1,
                          D.unit_of(code, br) or "ม.", fast=D.book.is_fast(code), code=code)
        tier = E.classify(price, b)
        ok = tier in want
        allok &= ok
        print(f"  {'✅' if ok else '❌'} {label}: {code} → {tier}")
    res = cmd_check(L, "SO6903141", "PPS", "SALES")
    ok = bool(res) and res["grade"] == "X" and res["approval_pct"] == 0
    print(f"  {'✅' if ok else '❌'} SO6903141 PPS ทั้งบิล → ⛔ 0% (ได้ {res and res['grade']})")
    print("VERIFY OK" if allok and ok else "VERIFY FAIL")
    return allok and ok


def cmd_backtest(L, days=90):
    """baseline เฟส 0: สัดส่วนเกรดรายสาขา/รายเซล (ย้อนหลัง) — เขียนลงโฟลเดอร์โปรเจกต์ (มีข้อมูลรายคน)"""
    D = Data(L, days=1)
    cut = today() - datetime.timedelta(days=days)
    table = defaultdict(lambda: defaultdict(int))
    for br in BRANCHES:
        slm = {}
        p = L.dbf(br, "OESO.DBF")
        if os.path.exists(p):
            for r in read_dbf(p, {"SONUM", "SLMCOD"}):
                slm[r.get("SONUM")] = (r.get("SLMCOD") or "").strip() or "(ไม่ระบุเซล)"
        bills = defaultdict(list)
        for r in read_dbf(L.dbf(br, "OESOIT.DBF"), {"SONUM", "SODAT", "STKCOD", "ORDQTY", "UNITPR", "TRNVAL", "TFACTOR"}):
            d = as_date(r.get("SODAT"))
            if d and d >= cut and (r.get("SONUM") or "").startswith("SO"):
                bills[r["SONUM"]].append({"code": r.get("STKCOD"), "qty": r.get("ORDQTY"), "price": r.get("UNITPR"),
                                          "value": r.get("TRNVAL"), "tfactor": r.get("TFACTOR") or 1})
        for so, lines in bills.items():
            g = E.grade_bill(lines, br, D.book)["grade"] or "?"
            table[(br, "ทั้งสาขา")][g] += 1
            table[(br, slm.get(so, "(ไม่ระบุเซล)"))][g] += 1
    out = ["| สาขา | เซล | A | B | C | D | X | ?(ไม่สรุป) | A+B % |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for (br, who), g in sorted(table.items()):
        n = sum(g.values())
        out.append(f"| {br} | {who} | " + " | ".join(str(g.get(k, 0)) for k in "ABCDX?") +
                   f" | {(g.get('A', 0) + g.get('B', 0)) / n * 100:.0f}% |")
    os.makedirs(L.private, exist_ok=True)
    p = os.path.join(L.private, f"baseline_เกรดบิล_{days}วัน_{be_yymmdd(today())}.md")
    backup_then_write(p, f"# Baseline เกรดบิลย้อนหลัง {days} วัน (costbook {D.book.updated})\n\n" + "\n".join(out),
                      os.path.join(L.private, "_backup"))
    print("\n".join(out))
    print("เขียน", p)


# ------------------------------------------------------------------ เฟส 1: ส่งขึ้น API (Mac mini → Vercel)
API_BASE = os.environ.get("APPROVE007_API", "https://production.007metals.com/api/approve")
SO_DAYS = 60
SO_CHUNK = 1500


def api_call(method, action, body=None, query=""):
    import urllib.request
    token = os.environ.get("APPROVE007_PUSH_TOKEN") or ""
    if len(token) < 24:
        raise SystemExit("❌ ไม่มี APPROVE007_PUSH_TOKEN (≥ 24 ตัว) — ตั้งค่าเดียวกับบน Vercel ใน env ของ launchd")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{API_BASE}/{action}{query}", data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Approve-Token": token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def build_snapshot(D, gen):
    """ของที่เซิร์ฟเวอร์ต้องใช้คิดเกรด: ทุน (ไม่มี PIN) · Rate 1 · รายการสินค้าไว้จับคู่ชื่อ · ช่วงราคา (ไม่มีทุน)"""
    bands, _, _, _ = make_bands(D, gen)
    rules = {k: D.rules.get(k) for k in ("updated", "prefix", "exact", "exact_any", "fast")}
    rate1, catalog, as_of = {}, {}, {}
    for br in BRANCHES:
        r1, cat = {}, []
        for code, a in D.sales[br].items():
            if code.startswith("ZZ"):
                continue
            v, _ = D.rate1_of(code, br)
            if v:
                r1[code] = v
            fam = D.family_of(code)
            cat.append([code, D.desc_of(code, br), fam["label"] if fam else None, D.unit_of(code, br),
                        round(a["val"])])
        rate1[br], catalog[br] = r1, cat
        p = D.L.dbf(br, "OESOIT.DBF")
        if os.path.exists(p):
            as_of[br] = datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="minutes")
    return {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "rules": rules,
            "rate1": rate1, "catalog": catalog, "bands": bands, "so_as_of": as_of}


def so_rows_recent(L, br, days=SO_DAYS):
    cut = today() - datetime.timedelta(days=days)
    cus = {}
    p = L.dbf(br, "OESO.DBF")
    if os.path.exists(p):
        for r in read_dbf(p, {"SONUM", "CUSNAM", "CUSCOD"}):
            cus[r.get("SONUM")] = (r.get("CUSNAM") or r.get("CUSCOD") or "").strip()
    by = defaultdict(list)
    for r in read_dbf(L.dbf(br, "OESOIT.DBF"), {"SONUM", "SODAT", "STKCOD", "STKDES", "ORDQTY", "UNITPR", "TRNVAL", "TFACTOR"}):
        d = as_date(r.get("SODAT"))
        so = r.get("SONUM") or ""
        if d and d >= cut and so.startswith("SO"):
            by[so].append({"sonum": so, "seq": len(by[so]) + 1, "sodat": d.isoformat(), "stkcod": r.get("STKCOD"),
                           "stkdes": r.get("STKDES"), "qty": r.get("ORDQTY"), "price": r.get("UNITPR"),
                           "value": r.get("TRNVAL"), "tfactor": r.get("TFACTOR") or 1, "cusnam": cus.get(so, "")})
    return cut, by


def cmd_push(L):
    """ทุก 15 นาที (launchd): snapshot + บรรทัดบิล 60 วัน ขึ้น API · แล้วดึงผล < 75% ลง approval_requests.jsonl"""
    D = Data(L)
    snap = build_snapshot(D, today())
    print("snapshot:", api_call("POST", "push", {"kind": "snapshot", "payload": snap}))
    for br in BRANCHES:
        if not os.path.exists(L.dbf(br, "OESOIT.DBF")):
            continue
        cut, by = so_rows_recent(L, br)
        chunk, first, sent = [], True, 0
        for so in sorted(by):                      # ไม่ตัด SO เดียวข้ามชุด (เซิร์ฟเวอร์แทนที่ทีละ SO)
            chunk += by[so]
            if len(chunk) >= SO_CHUNK:
                api_call("POST", "push", {"kind": "so_lines", "branch": br, "since": cut.isoformat(),
                                          "first": first, "rows": chunk})
                sent, chunk, first = sent + len(chunk), [], False
        api_call("POST", "push", {"kind": "so_lines", "branch": br, "since": cut.isoformat(),
                                  "first": first, "rows": chunk})
        print(f"{br}: ส่ง {sent + len(chunk)} บรรทัด ({len(by)} SO ตั้งแต่ {cut})")
    cmd_pull_log(L)


def cmd_pull_log(L):
    """ผลเช็คออนไลน์ที่ < 75% → ต่อท้าย AutoExport/Live/approval_requests.jsonl (รูปแบบเดียวกับ checkso)"""
    state_p = os.path.join(L.agent_status, "approve007_log_state.json")
    try:
        with open(state_p, encoding="utf-8") as f:
            after = json.load(f).get("after", 0)
    except (OSError, ValueError):
        after = 0
    rows = api_call("GET", "log", query=f"?after={after}").get("rows") or []
    if rows:
        os.makedirs(L.live, exist_ok=True)
        with open(L.approval_log, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"ts": r["ts"][:19], "br": r.get("branch"), "so": r.get("sonum") or "",
                                    "total": r.get("total"), "chance": r.get("chance"), "cov": r.get("coverage"),
                                    "by": r.get("name") or "sales", "layer": r.get("layer"), "grade": r.get("grade"),
                                    "blocked": r.get("blocked", False), "src": "approve007"},
                                   ensure_ascii=False) + "\n")
        after = rows[-1]["id"]
        os.makedirs(L.agent_status, exist_ok=True)
        with open(state_p, "w", encoding="utf-8") as f:
            json.dump({"after": after}, f)
    print(f"approval_requests.jsonl: +{len(rows)} แถว")


def main(argv):
    L = Layout()
    cmd = argv[1] if len(argv) > 1 else "build"
    if cmd == "preflight":
        sys.exit(0 if cmd_preflight(L) else 1)
    if cmd == "--inspect":
        cmd_build(L, inspect=True)
    elif cmd == "verify":
        sys.exit(0 if cmd_verify(L) else 1)
    elif cmd == "check":
        rest = [a.upper() for a in argv[3:]]
        cmd_check(L, argv[2], next((a for a in rest if a in BRANCHES), None),
                  next((a for a in rest if a in ("SALES", "MGR", "GEM")), "SALES"))
    elif cmd == "push":
        cmd_push(L)
    elif cmd == "pull-log":
        cmd_pull_log(L)
    elif cmd == "backtest":
        cmd_backtest(L, int(argv[2]) if len(argv) > 2 else 90)
    else:
        cmd_build(L)


if __name__ == "__main__":
    main(sys.argv)
