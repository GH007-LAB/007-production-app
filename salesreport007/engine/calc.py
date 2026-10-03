# -*- coding: utf-8 -*-
"""
สูตรสรุปผล (สเปก v5) — ตัวเดียวกับ computeSummary() ใน apps_script/Code.gs
คิดเป็นสตางค์ (int) ทั้งหมดเพื่อให้ Python กับ JS ได้ผลตรงกันทุกสตางค์ · tests/test_apps_script.mjs เทียบสองฝั่ง 200 เคส

v5: เงินสด/โอน/เช็ค ของแต่ละใบมาจาก RE/AI ที่พนักงานออกใน Express (ไม่มีการติ๊กในรายงาน)
    RE ที่หักลดหนี้ ยอดรับในช่องทางคือยอดหลังหักแล้ว → ใช้ยอดช่องทาง ไม่ใช้ยอดเอกสาร
  รับเงินสด      = Σ เงินสด ของ RE/AI/HS ในรอบ
  รับโอน/QR     = Σ โอน   ของ RE/AI/HS ในรอบ        (เช็ค/อื่น ๆ แยกช่องของมันเอง)
  คืนเงินสด      = Σ เงินสด ของ SR ในรอบ (ลดหนี้ที่หักใน RE ไม่มีเงินสด = 0)
  เงินสดที่ควรมี  = float + รับเงินสด − คืนเงินสด − รายจ่ายประจำวัน (เฉพาะที่มีรูปบิล)
  ส่วนต่าง       = เงินสดนับจริง − เงินสดที่ควรมี
  ยอดนำฝาก      = เงินสดนับจริง − float
"""
import math

RECEIVE_TYPES = ("RE", "AI", "HS")
REFUND_TYPES = ("SR",)
MONEY_KEYS = ("cash_in", "transfer_in", "cheque_in", "other_in", "cash_refund", "cash_expense",
              "cash_expected", "diff", "deposit")


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
    """ไม่มีรูปบิล = ไม่นับเป็นรายจ่าย · receipt_found=False = ใส่ชื่อไฟล์แต่หาไฟล์ใน Drive ไม่เจอ"""
    return bool(str(e.get("receipt") or "").strip()) and e.get("receipt_found") is not False


def summarize(docs, expenses, cash_counted, float_amt=0, receive_types=RECEIVE_TYPES, refund_types=REFUND_TYPES):
    cash_in = transfer_in = cheque_in = other_in = cash_refund = cash_expense = 0
    no_channel = []
    for d in docs:
        t = d.get("type")
        if t in receive_types:
            if not d.get("pay_known"):
                no_channel.append(d.get("doc_no"))
                continue
            cash_in += satang(d.get("cash"))
            transfer_in += satang(d.get("transfer"))
            cheque_in += satang(d.get("cheque"))
            other_in += satang(d.get("other"))
        elif t in refund_types:
            cash_refund += satang(d.get("cash"))
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
        "cash_in": baht(cash_in), "transfer_in": baht(transfer_in), "cheque_in": baht(cheque_in),
        "other_in": baht(other_in), "cash_refund": baht(cash_refund), "cash_expense": baht(cash_expense),
        "cash_expected": baht(expected), "diff": baht(counted - expected), "deposit": baht(counted - fl),
        "no_channel": no_channel, "expense_no_receipt": no_receipt,
    }
