# -*- coding: utf-8 -*-
"""
สูตรสรุปผล (สเปก v4 ข้อ 5) — ตัวเดียวกับ computeSummary() ใน apps_script/Code.gs
คิดเป็นสตางค์ (int) ทั้งหมดเพื่อให้ Python กับ JS ได้ผลตรงกันทุกสตางค์ · tests/test_apps_script.mjs เทียบสองฝั่ง 200 เคส
"""
import math

RECEIVE_TYPES = ("RE", "AI", "HS")
REFUND_TYPES = ("SR",)


def satang(v):
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return 0
    # ปัดครึ่งขึ้นแบบเดียวกับ JS (Python round() ปัดแบบ banker's → ต่างกัน 1 สตางค์ที่ .xx5)
    return int(math.floor(abs(v) * 100 + 0.5 + 1e-9))


def baht(s):
    return round(s / 100.0, 2)


def expense_counts(e):
    """ไม่มีรูปบิล = ไม่นับเป็นค่าใช้จ่าย (ข้อ 9.6) · receipt_found=False = ใส่ชื่อไฟล์แต่หาไฟล์ใน Drive ไม่เจอ"""
    return bool(str(e.get("receipt") or "").strip()) and e.get("receipt_found") is not False


def summarize(docs, expenses, cash_counted, float_amt=0, receive_types=RECEIVE_TYPES, refund_types=REFUND_TYPES):
    cash_in = transfer_in = cash_refund = cash_expense = 0
    unticked = []
    for d in docs:
        ch, t = d.get("channel"), d.get("type")
        tot, cash = satang(d.get("total")), satang(d.get("cash_amount"))
        if ch not in ("cash", "transfer", "mixed"):
            unticked.append(d.get("doc_no"))
            continue
        if ch == "mixed":
            cash = min(cash, tot)
        if t in receive_types:
            if ch == "cash":
                cash_in += tot
            elif ch == "transfer":
                transfer_in += tot
            else:
                cash_in += cash
                transfer_in += tot - cash
        elif t in refund_types:
            if ch == "cash":
                cash_refund += tot
            elif ch == "mixed":
                cash_refund += cash
    no_receipt = []
    for e in expenses:
        if expense_counts(e):
            cash_expense += satang(e.get("amount"))
        elif satang(e.get("amount")):
            no_receipt.append(e.get("item"))
    fl = satang(float_amt)
    counted = satang(cash_counted)
    expected = fl + cash_in - cash_refund - cash_expense
    return {
        "cash_in": baht(cash_in), "transfer_in": baht(transfer_in), "cash_refund": baht(cash_refund),
        "cash_expense": baht(cash_expense), "cash_expected": baht(expected),
        "diff": baht(counted - expected), "deposit": baht(counted - fl),
        "unticked": unticked, "expense_no_receipt": no_receipt,
    }
