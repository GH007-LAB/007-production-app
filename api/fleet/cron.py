# /api/fleet/cron — Fleet007 รถบริษัท (โค้ดจริงอยู่ที่ fleet007/server/fleet_api.py)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fleet007", "server"))

from fleet_api import vercel_handler  # noqa: E402


# Vercel ตรวจ entrypoint จาก "class handler" เท่านั้น
class handler(vercel_handler("cron")):
    pass
