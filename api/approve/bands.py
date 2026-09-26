# /api/approve/bands — Approve007 (โค้ดจริงอยู่ที่ approve007/server/approve_api.py · engine เดียวกับ Mac mini)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "approve007", "server"))

from approve_api import vercel_handler  # noqa: E402

handler = vercel_handler("bands")
