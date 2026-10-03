# /api/sales/day — Sales007 รายงานขายประจำวัน (โค้ดจริงอยู่ที่ salesreport007/server/sales_api.py)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "salesreport007", "server"))

from sales_api import vercel_handler  # noqa: E402


# Vercel ตรวจ entrypoint จาก "class handler" เท่านั้น
class handler(vercel_handler("day")):
    pass
