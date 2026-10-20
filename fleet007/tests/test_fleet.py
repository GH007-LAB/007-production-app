# -*- coding: utf-8 -*-
"""python3 -m unittest discover -s fleet007/tests -v"""
import datetime
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "salesreport007", "tests"))

import fleet_api as F                 # noqa: E402
from fake_sb import FakeSB as _Base   # noqa: E402  PostgREST จำลองตัวเดียวกับ Sales007

ENV = {"CRON_SECRET": "c" * 20, "RESEND_API_KEY": "re_test"}


class FakeSB(_Base):
    def __init__(self):
        super().__init__()
        self.t.update({"apps": [{"id": 12, "code": "fleet007"}], "fleet_vehicle": [], "fleet_item": [],
                       "fleet_renewal": [], "fleet_alert_log": []})

    def insert(self, table, rows, returning=True):
        out = []
        for r in rows:
            self.seq += 1
            new = dict({"active": True} if table in ("fleet_vehicle", "fleet_item") else {}, **r)
            new.setdefault("id", self.seq)
            new.setdefault("ts" if table == "fleet_alert_log" else "created_at", self.clock.isoformat())
            if table == "fleet_alert_log":
                new.setdefault("ok", True)
                dup = [x for x in self.t[table] if x["ok"] and new["ok"] and new["stage"] != "test" and
                       (x["item_id"], str(x["due_date"]), x["stage"]) == (new["item_id"], str(new["due_date"]), new["stage"])]
                assert not dup, "unique index fleet_alert_once"
            if table == "fleet_renewal":
                new.setdefault("renewed_at", self.clock.isoformat())
            if table == "fleet_item":
                new.setdefault("remind_days", [60, 30, 15, 7, 1])
            self.t[table].append(new)
            out.append(dict(new))
        return out

    def update(self, table, query, patch):
        rows = self._filter(table, query)
        for r in rows:
            r.update(patch)
        return [dict(r) for r in rows]


class Fleet(unittest.TestCase):
    def setUp(self):
        self.sb = FakeSB()
        self.sb.add_staff(1, "tok-hr", "", "แอน", position="เจ้าหน้าที่ฝ่ายบุคคล (HR)", app_id=12)
        self.sb.add_staff(2, "tok-buy", "", "บอย", position="จัดซื้อ", app_id=12)
        self.sb.add_staff(3, "tok-admin", "", "ผบ.", admin=True, position="ผู้บริหาร", app_id=12)
        self.sb.add_staff(4, "tok-sales", "SKN", "นิด", position="พนักงานขาย", app_id=12)   # ติ๊กสิทธิ์แล้วแต่ตำแหน่งไม่ใช่
        self.sb.add_staff(5, "tok-noacc", "", "เอ", position="จัดซื้อ", app_id=99)           # ตำแหน่งใช่แต่ไม่ได้ติ๊กสิทธิ์
        self.sb.add_staff(6, "tok-test", "", "ทดสอบ", position="HR", is_test=True, app_id=12)
        self.mail = []
        self._send, F.send_email = F.send_email, lambda env, to, subject, html, text: (
            self.mail.append({"to": to, "subject": subject, "html": html, "text": text}) or "fake")

    def tearDown(self):
        F.send_email = self._send

    def call(self, action, day, method="GET", body=None, token="tok-hr", headers=None, env=None):
        now = datetime.datetime(day.year, day.month, day.day, 1, 0, tzinfo=datetime.timezone.utc)   # 08:00 น.
        self.sb.clock = now
        h = dict(headers or {})
        if token:
            h["Authorization"] = "Bearer " + token
        st, out = F.handle(action, method, h, json.dumps(body).encode() if body is not None else b"", {},
                           env=env or ENV, sb=self.sb, now=now)
        return st, json.loads(json.dumps(out, default=str))

    def save(self, day, body, token="tok-hr", status=200):
        st, out = self.call("save", day, "POST", body, token=token)
        self.assertEqual(st, status, out)
        return out

    def cron(self, day):
        st, out = self.call("cron", day, token=None, headers={"Authorization": "Bearer " + "c" * 20})
        self.assertEqual(st, 200, out)
        return out

    def test_access_only_admin_hr_purchasing(self):
        T = datetime.date(2026, 10, 20)
        for tok in ("tok-hr", "tok-buy", "tok-admin", "tok-test"):
            self.assertEqual(self.call("list", T, token=tok)[0], 200, tok)
        self.assertEqual(self.call("list", T, token="tok-sales"), (403, {"error": "role-not-allowed"}))
        self.assertEqual(self.call("list", T, token="tok-noacc"), (403, {"error": "no-app-access"}))
        self.assertEqual(self.call("list", T, token=None)[0], 401)
        self.sb.users["tok-forged"] = {"id": "ux", "user_metadata": {"line_id": "L1"}}   # C1: ปลอม user_metadata
        self.assertEqual(self.call("list", T, token="tok-forged")[0], 404)
        self.assertEqual(self.save(T, {"op": "vehicle_save", "plate": "1กข 1"}, token="tok-test", status=403),
                         {"error": "test-account-read-only"})
        self.assertEqual(self.call("cron", T, token=None, headers={"Authorization": "Bearer wrong"})[0], 401)

    def test_vehicle_items_alerts_and_renewal(self):
        T = datetime.date(2026, 10, 20)
        vid = self.save(T, {"op": "vehicle_save", "plate": " 1กข  1234 ", "province": "สกลนคร", "brand": "Isuzu",
                            "model": "D-Max", "vtype": "กระบะ", "year": "2021", "branch": "SKN", "driver": "สมชาย"})["id"]
        self.save(T, {"op": "vehicle_save", "plate": ""}, status=400)
        ins = self.save(T, {"op": "item_save", "vehicle_id": vid, "kind": "ประกันภัย", "due_date": "2026-11-19",
                            "provider": "วิริยะ", "policy_no": "P-1", "amount": "15000"})["id"]
        prb = self.save(T, {"op": "item_save", "vehicle_id": vid, "kind": "พรบ.", "due_date": "2026-10-15",
                            "remind_days": [30, 7]})["id"]
        self.save(T, {"op": "item_save", "vehicle_id": vid, "kind": "ภาษีรถยนต์ (ป้ายวงกลม)", "due_date": "2027-06-01"})
        st, lst = self.call("list", T)
        v = lst["vehicles"][0]
        self.assertEqual((v["plate"], v["year"], v["status"], v["worst_days"]), ("1กข 1234", 2021, "overdue", -5))
        self.assertEqual({i["kind"]: (i["days"], i["status"]) for i in v["items"]},
                         {"พรบ.": (-5, "overdue"), "ประกันภัย": (30, "due30"), "ภาษีรถยนต์ (ป้ายวงกลม)": (224, "ok")})
        self.assertEqual(lst["alert_to"], ["hr007@007metals.com"])

        # 08:00 วันนี้: ประกันเหลือ 30 วัน + พรบ. เกินกำหนด 5 วัน → อีเมลเดียวถึง hr007
        out = self.cron(T)
        self.assertEqual((out["sent"], out["to"]), (2, ["hr007@007metals.com"]))
        m = self.mail[-1]
        self.assertEqual(m["to"], ["hr007@007metals.com"])
        self.assertIn("เกินกำหนด 1", m["subject"])
        self.assertIn("ใกล้ครบ 1", m["subject"])
        self.assertIn("1กข 1234 สกลนคร", m["html"])
        self.assertIn("เกินกำหนด 5 วัน", m["text"])
        self.assertIn("อีก 30 วัน", m["text"])
        self.assertEqual(self.cron(T)["sent"], 0)                               # cron ซ้ำวันเดียวกัน ไม่ส่งซ้ำ
        self.assertEqual(self.cron(T + datetime.timedelta(days=1))["sent"], 0)  # วันถัดไปยังอยู่ขั้นเดิม
        # cron หายไปหลายวัน → ส่งขั้นล่าสุดให้ (ประกันเหลือ 13 วัน = ขั้น 15) + พรบ. เกิน 22 วัน = ขั้น overdue สัปดาห์ที่ 4
        out = self.cron(T + datetime.timedelta(days=17))
        self.assertEqual(out["sent"], 2)
        stages = {r["item_id"]: r["stage"] for r in self.sb.t["fleet_alert_log"][-2:]}
        self.assertEqual(stages, {ins: "15", prb: "overdue-22"})

        # ต่ออายุ พรบ. → หยุดเตือน · เก็บประวัติ
        self.save(T, {"op": "renew", "id": prb, "new_due": "2026-10-01"}, status=400)        # ต้องหลังวันเดิม
        self.save(T, {"op": "renew", "id": prb, "new_due": "2027-10-15", "amount": "645.21", "provider": "กรุงเทพประกัน"})
        st, lst = self.call("list", T)
        p = next(i for i in lst["vehicles"][0]["items"] if i["id"] == prb)
        self.assertEqual((p["due_date"], p["status"], p["amount"], p["history"][0]["old_due"]),
                         ("2027-10-15", "ok", 645.21, "2026-10-15"))
        self.assertEqual(p["history"][0]["renewed_by"], "แอน")

        # เลิกใช้รถ → ไม่เตือนแล้ว
        self.save(T, {"op": "vehicle_archive", "id": vid, "active": False})
        self.assertEqual(self.cron(T + datetime.timedelta(days=29))["sent"], 0)

    def test_mail_failure_is_retried_next_run(self):
        T = datetime.date(2026, 10, 20)
        vid = self.save(T, {"op": "vehicle_save", "plate": "2ขค 99"})["id"]
        self.save(T, {"op": "item_save", "vehicle_id": vid, "kind": "ตรวจสภาพรถ", "due_date": "2026-10-27"})

        def boom(*a):
            raise F.ApiError(502, "mail-500")
        F.send_email = boom
        st, out = self.call("cron", T, token=None, headers={"Authorization": "Bearer " + "c" * 20})
        self.assertEqual((st, out["error"]), (502, "mail-500"))
        self.assertFalse(self.sb.t["fleet_alert_log"][-1]["ok"])
        F.send_email = lambda env, to, s, h, t: self.mail.append(s) or "fake"
        self.assertEqual(self.cron(T)["sent"], 1)                                # ส่งไม่ผ่าน = รอบหน้าส่งใหม่

    def test_alert_stage(self):
        T = datetime.date(2026, 10, 20)
        st = lambda due, rd=None: F.alert_stage({"due_date": due, "remind_days": rd}, T)
        self.assertIsNone(st("2027-01-01"))                                     # 73 วัน > 60
        self.assertEqual(st("2026-12-19"), "60")
        self.assertEqual(st("2026-10-21"), "1")
        self.assertEqual(st("2026-10-20"), "0")
        self.assertEqual(st("2026-10-19"), "overdue-1")
        self.assertEqual(st("2026-10-13"), "overdue-1")                         # เกิน 7 วัน ยังสัปดาห์แรก
        self.assertEqual(st("2026-10-12"), "overdue-8")
        self.assertEqual(st("2026-11-10", [90]), "90")

    def test_real_send_email_needs_config(self):
        with self.assertRaises(F.ApiError) as e:
            self._send({}, ["hr007@007metals.com"], "s", "<p>h</p>", "t")
        self.assertEqual(e.exception.code, "mail-not-configured")


if __name__ == "__main__":
    unittest.main()
