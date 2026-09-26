# -*- coding: utf-8 -*-
"""
อ่านใบราคาจากโฟลเดอร์ "0. ใบประเมินราคาเหล็ก" (Drive เดียวกับ All_on_Cloud)
- ใบราคาขายแผ่น<YYMMDD>.xlsx   → Rate 1–5 ต่อ (กลุ่มสินค้า, ความหนา)   [คอลัมน์ B=กลุ่ม C=ความหนา D=สเปค E–I=Rate1–5]
- ใบต้นทุนราคาขายคอยล์<YYMMDD>.xlsx → ต้นทุนคอยล์ต่อเมตร (รวม VAT) ใช้เทียบว่า "ทุน Express เพี้ยนไหม" (รายงาน 5.3)
ใบราคาพิมพ์ตารางซ้ำ 2 ชุด (ชุดปริ้นต์ให้ลูกค้า) → เก็บชุดแรกที่เจอเท่านั้น
"""
import re


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace("฿", "").replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _txt(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def _rows(path):
    import openpyxl   # มีบน Mac mini แล้ว (HANDOVER PriceBands ข้อ 1.5)
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            yield ws.title, list(row)


def read_rate_sheet(path):
    """คืน list ของ {no, section, thk, spec, rates:[r1..r5]} — rates ว่าง = None (สินค้ายังไม่ตั้งราคา)"""
    out, seen, section = [], set(), ""
    for _, r in _rows(path):
        r = (r + [None] * 10)[:10]
        no = _num(r[0])
        if no is None:
            continue
        if _txt(r[1]):
            section = _txt(r[1])
        thk, spec = _txt(r[2]), _txt(r[3])
        key = (section, thk, spec)
        if key in seen:
            continue
        seen.add(key)
        rates = [_num(x) for x in r[4:9]]
        out.append({"no": int(no), "section": section, "thk": thk, "spec": spec,
                    "rates": [x if x else None for x in rates]})
    return out


def read_coil_sheet(path):
    """คืน list ของ {block, section, label, kg_m, per_m} · per_m = ราคาเฉลี่ยต่อเมตร (รวม VAT) คอลัมน์สุดท้าย"""
    out, block, section = [], "", ""
    for _, r in _rows(path):
        r = (r + [None] * 11)[:11]
        a, b = _txt(r[0]), _txt(r[1])
        if a and not _num(r[0]) and a not in ("NO", "NO."):
            block = a                               # หัวบล็อกผู้ขาย เช่น "Dongbu", "Diamond"
            continue
        if _num(r[0]) is None:
            continue
        if b.startswith("คอยล์"):
            section = b
            continue
        per_m, kg_m = _num(r[10]), _num(r[3])
        if b and per_m and per_m > 5:
            out.append({"block": block, "section": section, "label": b, "az": _txt(r[5]),
                        "kg_m": kg_m, "per_m": per_m})
    return out


def match_rate(rows, rule):
    """หาแถวในใบราคาตาม rule {section_contains:[...], thk_startswith, spec_contains?} → แถวแรกที่ตรง"""
    secs = rule.get("section_contains") or []
    for row in rows:
        if secs and not all(s.lower() in row["section"].lower() for s in secs):
            continue
        if rule.get("thk_startswith") and not row["thk"].lower().startswith(rule["thk_startswith"].lower()):
            continue
        if rule.get("spec_contains") and rule["spec_contains"].lower() not in row["spec"].lower():
            continue
        return row
    return None


def match_coil(rows, rule):
    if not rule:
        return None
    for row in rows:
        if rule.get("block") and rule["block"].lower() not in row["block"].lower():
            continue
        if rule.get("section_contains") and rule["section_contains"].lower() not in row["section"].lower():
            continue
        if rule.get("az") and row["az"].upper() != rule["az"].upper():
            continue
        if row["label"].lower().startswith(rule["label_startswith"].lower()):
            return row
    return None
