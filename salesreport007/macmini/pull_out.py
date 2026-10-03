# -*- coding: utf-8 -*-
"""
ดึงรายงานที่ล็อกแล้วจาก /api/sales/export → เขียน All_on_Cloud/AutoExport/sales_report/{BR}/YYMMDD_out.json
ให้ Finny อ่านจาก Drive ตามเดิม (ข้อมูลเดียวกับหน้าตรวจในแอป)

usage:  SALES007_PUSH_TOKEN=... python3 pull_out.py [YYYY-MM-DD ...]     ไม่ใส่วันที่ = เมื่อวาน + วันนี้
env:    APPROVE007_ALL_ON_CLOUD (ที่อยู่ All_on_Cloud — ตัวเดียวกับ approve007) · SALES007_API (ค่าเริ่ม production)
"""
import datetime
import json
import os
import sys
import urllib.request

API = os.environ.get("SALES007_API", "https://production.007metals.com/api/sales")
BRANCHES = ("BK", "SKN", "PPS")


def be_yymmdd(d):
    return f"{(d.year + 543) % 100:02d}{d.month:02d}{d.day:02d}"


def fetch(br, day, token):
    req = urllib.request.Request(f"{API}/export?branch={br}&date={day.isoformat()}", headers={"X-Sales-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main(argv):
    token = os.environ.get("SALES007_PUSH_TOKEN") or ""
    root = os.environ.get("APPROVE007_ALL_ON_CLOUD") or ""
    if not token or not os.path.isdir(os.path.join(root, "AutoExport")):
        raise SystemExit("ตั้ง SALES007_PUSH_TOKEN และ APPROVE007_ALL_ON_CLOUD=<All_on_Cloud> ก่อน (ห้ามเดา path)")
    today = datetime.date.today()
    days = [datetime.date.fromisoformat(a) for a in argv[1:]] or [today - datetime.timedelta(days=1), today]
    for day in days:
        for br in BRANCHES:
            j = fetch(br, day, token)
            if j.get("status") == "not-locked":
                print(f"{br} {day}: ยังไม่ล็อก — ข้าม")
                continue
            p = os.path.join(root, "AutoExport", "sales_report", br, be_yymmdd(day) + "_out.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(j, f, ensure_ascii=False, indent=1)
            os.replace(p + ".tmp", p)
            s = j["summary"]
            print(f"{br} {day}: {j['lock_reason']} · เอกสาร {j['doc_count_at_cutoff']} · ส่วนต่าง {s['diff']} → {p}")


if __name__ == "__main__":
    main(sys.argv)
