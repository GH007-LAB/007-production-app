# -*- coding: utf-8 -*-
"""
หาโฟลเดอร์ All_on_Cloud (Google Drive 007skn0777) บนเครื่องที่รัน — ห้ามเดา path (HANDOVER ข้อ 2)
ลำดับ: env APPROVE007_ALL_ON_CLOUD → ตำแหน่งที่รู้จักบน Mac mini / เครื่อง Gem / Cowork mount
ถ้าไม่เจอ → raise พร้อมรายการที่ลองแล้ว ให้รายงาน ผบ. แทนการเดา
"""
import glob
import os
import re

DRIVE_NAMES = [
    "ไดรฟ์ของฉัน (007skn0777@gmail.com)",   # Mac mini (ภาษาไทย) — manifest.json ยืนยัน 26/09/69
    "My Drive (007skn0777@gmail.com)",
]


def _candidates():
    env = os.environ.get("APPROVE007_ALL_ON_CLOUD")
    if env:
        yield env
    home = os.path.expanduser("~")
    for n in DRIVE_NAMES:
        yield os.path.join(home, n, "All_on_Cloud")
        yield os.path.join("/Users/cto007", n, "All_on_Cloud")
    yield os.path.join(home, "Library", "CloudStorage", "GoogleDrive-007skn0777@gmail.com", "My Drive", "All_on_Cloud")
    yield os.path.join(home, "Library", "CloudStorage", "GoogleDrive-007skn0777@gmail.com", "ไดรฟ์ของฉัน", "All_on_Cloud")
    yield os.path.join(home, "mnt", "All_on_Cloud")
    for n in DRIVE_NAMES:
        yield os.path.join(home, "mnt", n, "All_on_Cloud")
    yield r"C:\Users\jbmet\My Drive (007skn0777@gmail.com)\All_on_Cloud"
    yield r"G:\My Drive\All_on_Cloud"


def find_all_on_cloud():
    tried = []
    for p in _candidates():
        tried.append(p)
        if os.path.isdir(os.path.join(p, "AutoExport")):
            return os.path.abspath(p)
    raise FileNotFoundError("หา All_on_Cloud ไม่เจอ — ลองแล้ว:\n  " + "\n  ".join(tried) +
                            "\nตั้ง env APPROVE007_ALL_ON_CLOUD=<path> แล้วรันใหม่ (ห้ามเดา path)")


class Layout:
    """ที่อยู่ไฟล์ทั้งหมดที่ Approve007 อ่าน/เขียน — อ้างจาก All_on_Cloud ตัวเดียว"""

    def __init__(self, root=None):
        self.root = root or find_all_on_cloud()
        self.drive = os.path.dirname(self.root)          # "ไดรฟ์ของฉัน (...)" — ใบราคาอยู่ระดับนี้
        self.autoexport = os.path.join(self.root, "AutoExport")
        self.scripts = os.path.join(self.autoexport, "scripts")
        self.live = os.path.join(self.autoexport, "Live")
        self.agent_status = os.path.join(self.autoexport, "agent_status")
        self.app = os.path.join(self.root, "Approve007")          # แอปที่เซลเปิด (ไม่มีทุน)
        self.backup = os.path.join(self.app, "_backup")
        # รายงานที่มีทุน/GP → โฟลเดอร์โปรเจกต์ P-17 (ผบ./CTO) ไม่ใช่โฟลเดอร์ที่แจกเซล
        self.private = os.environ.get("APPROVE007_PRIVATE_DIR") or os.path.join(
            self.drive, "007 Project Map", "P-17_เกรดบิล", "trial")

    def branch_dir(self, br):
        return os.path.join(self.autoexport, br)

    def dbf(self, br, name):
        return os.path.join(self.autoexport, br, name)

    @property
    def rules_file(self):
        return os.path.join(self.scripts, "costbook_rules.json")

    @property
    def approval_log(self):
        return os.path.join(self.live, "approval_requests.jsonl")

    def price_folder(self):
        return os.path.join(self.drive, "0. ใบประเมินราคาเหล็ก")

    def latest_sheet(self, stem):
        """ใบล่าสุดตามเลข YYMMDD ในชื่อไฟล์ เช่น ใบราคาขายแผ่น260907.xlsx · ข้ามไฟล์ล็อก ~$"""
        best = None
        for p in glob.glob(os.path.join(self.price_folder(), "**", stem + "*.xlsx"), recursive=True):
            name = os.path.basename(p)
            if name.startswith("~$"):
                continue
            m = re.search(stem + r"(\d{6})", name)
            if m and (best is None or m.group(1) > best[0]):
                best = (m.group(1), p)
        return best   # (yymmdd, path) หรือ None
