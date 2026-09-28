# /api/approve/policy — Approve007: รายการเสนอ cash cow + บันทึกที่ ผบ./แอดมินติ๊ก (โค้ดจริงอยู่ที่ approve007/server/approve_api.py)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "approve007", "server"))

from approve_api import vercel_handler  # noqa: E402


# Vercel ตรวจ entrypoint จาก "class handler" / "app" เท่านั้น — assign ธรรมดาจะไม่ถูกนับเป็น function
class handler(vercel_handler("policy")):
    pass
