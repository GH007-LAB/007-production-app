# -*- coding: utf-8 -*-
"""
สูตรปิดยอดเงินสด (salesreport007 v6) — ใช้ทั้ง API (/api/sales) และ Mac mini/Finny ตรวจซ้ำ
คิดเป็นสตางค์ (int) ทั้งหมด

ช่องทางที่พนักงานเลือกในแอปเมื่อ RE/AI/HS ขึ้นมา:  cash = เงินสด · transfer = เงินโอน · qr = QR Code
ลดหนี้ SR:  deduct = หักใน RE (ไม่กระทบเงินสด) · refund_cash = คืนลูกค้าเป็นเงินสด

  รับเงินสด      = Σ ยอด RE/AI/HS ที่เลือก "เงินสด"
  รับโอน        = Σ ยอด ที่เลือก "เงินโอน"         รับ QR = Σ ยอด ที่เลือก "QR Code"
  คืนเงินสด      = Σ ยอด SR ที่เลือก "คืนเงินสด"
  เงินสดที่ควรมี  = float + รับเงินสด − คืนเงินสด − รายจ่ายประจำวัน (เฉพาะที่มีรูปบิล)
  ส่วนต่าง       = เงินสดนับจริง − เงินสดที่ควรมี
  ยอดนำฝาก      = เงินสดนับจริง − float
"""
import math

RECEIVE_TYPES = ("RE", "AI", "HS")
REFUND_TYPES = ("SR",)
RECEIVE_CHANNELS = {"cash": "เงินสด", "transfer": "เงินโอน", "qr": "QR Code"}
REFUND_CHANNELS = {"deduct": "หักใน RE", "refund_cash": "คืนเงินสด"}
MONEY_KEYS = ("cash_in", "transfer_in", "qr_in", "cash_refund", "cash_expense", "cash_expected", "diff", "deposit")


def channels_for(doc_type):
    return RECEIVE_CHANNELS if doc_type in RECEIVE_TYPES else REFUND_CHANNELS if doc_type in REFUND_TYPES else {}


def satang(v):
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return 0
    return int(math.floor(abs(v) * 100 + 0.5 + 1e-9))      # ปัดครึ่งขึ้น (ไม่ใช่ banker's rounding)


def baht(s):
    return round(s / 100.0, 2)


def expense_counts(e):
    """ไม่มีรูปบิล = ไม่นับเป็นรายจ่าย (ส่วนต่างตกเป็นเงินขาด)"""
    return bool(str(e.get("receipt_path") or "").strip())


def summarize(docs, expenses, cash_counted, float_amt=0):
    acc = {"cash": 0, "transfer": 0, "qr": 0}
    cash_refund = cash_expense = 0
    unchosen = []
    for d in docs:
        t, ch, tot = d.get("type"), d.get("channel"), satang(d.get("total"))
        if ch not in channels_for(t):
            unchosen.append(d.get("doc_no"))
            continue
        if t in RECEIVE_TYPES:
            acc[ch] += tot
        elif ch == "refund_cash":
            cash_refund += tot
    no_receipt = []
    for e in expenses:
        if expense_counts(e):
            cash_expense += satang(e.get("amount"))
        else:
            no_receipt.append(e.get("item"))
    fl, counted = satang(float_amt), satang(cash_counted)
    expected = fl + acc["cash"] - cash_refund - cash_expense
    return {
        "cash_in": baht(acc["cash"]), "transfer_in": baht(acc["transfer"]), "qr_in": baht(acc["qr"]),
        "cash_refund": baht(cash_refund), "cash_expense": baht(cash_expense), "cash_expected": baht(expected),
        "diff": baht(counted - expected) if cash_counted is not None else None, "deposit": baht(counted - fl),
        "unchosen": unchosen, "expense_no_receipt": no_receipt,
    }
