# -*- coding: utf-8 -*-
"""
Fleet007 API — รถบริษัท: ทะเบียนรถ + พรบ./ประกัน/ภาษี/ตรวจสภาพ/อื่น ๆ + แจ้งเตือนอีเมล · Vercel Python + Supabase (service role)

  GET  /api/fleet/list    Bearer <session กลาง>   → รถทั้งหมด + รายการครบกำหนด + ประวัติต่ออายุ + log อีเมล
  POST /api/fleet/save    Bearer                  {op: vehicle_save | vehicle_archive | item_save | item_del | renew
                                                        | test_email | run_alerts}
  GET  /api/fleet/cron    Vercel cron (Authorization: Bearer CRON_SECRET) → ส่งอีเมลแจ้งเตือนประจำวัน (08:00 น.)

สิทธิ์: ต้องติ๊กแอป fleet007 ใน app_access และเป็น แอดมิน (is_admin) · HR · จัดซื้อ (ดูจากตำแหน่งในทะเบียนพนักงาน)
       บัญชีทดสอบ (employees.is_test) ดูได้อย่างเดียว

แจ้งเตือน: ทุกเช้า ดูทุกรายการของรถที่ยังใช้งาน
  - ยังไม่ถึงกำหนด: ส่งเมื่อเข้าช่วงเตือน (ค่าเริ่ม 60/30/15/7/1 วัน และวันครบกำหนด) · ขั้นละครั้ง · cron พลาดวันไหนก็ตามส่งขั้นล่าสุดให้
  - เกินกำหนด: ส่งทุก 7 วันจนกว่าจะกด "ต่ออายุแล้ว"
  รวมเป็นอีเมลเดียวต่อวัน → FLEET007_ALERT_TO (ค่าเริ่ม hr007@007metals.com)

env: SUPABASE_URL · SUPABASE_SERVICE_ROLE_KEY · CRON_SECRET (มีอยู่แล้ว)
     อีเมล (เลือกอย่างใดอย่างหนึ่ง): RESEND_API_KEY + FLEET007_MAIL_FROM (โดเมน 007metals.com ที่ยืนยันใน Resend แล้ว)
                                  หรือ SMTP_HOST · SMTP_PORT (465) · SMTP_USER · SMTP_PASS (เช่น Google Workspace + App Password)
     ไม่บังคับ: FLEET007_ALERT_TO (คั่นด้วย ,) · FLEET007_ROLE_WORDS (คำในตำแหน่งที่ให้เข้าได้) · FLEET007_EXTRA_IDS (employee id)
"""
import datetime
import hmac
import html
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

APP_CODE = "fleet007"
TZ = datetime.timezone(datetime.timedelta(hours=7))
DEFAULT_TO = "hr007@007metals.com"
DEFAULT_ROLE_WORDS = ("บุคคล", "hr", "จัดซื้อ", "purchas")
KINDS = ["พรบ.", "ประกันภัย", "ภาษีรถยนต์ (ป้ายวงกลม)", "ตรวจสภาพรถ", "เปลี่ยนถ่ายน้ำมันเครื่อง", "อื่น ๆ"]
DEFAULT_REMIND = [60, 30, 15, 7, 1]
BRANCHES = ["BK", "SKN", "PPS", "สำนักงานใหญ่"]
VEHICLE_FIELDS = ("plate", "province", "brand", "model", "vtype", "year", "branch", "driver", "chassis_no", "note")
ITEM_FIELDS = ("kind", "due_date", "remind_days", "provider", "policy_no", "amount", "note")


class ApiError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


def q(v):
    return urllib.parse.quote(str(v), safe="")


# ------------------------------------------------------------------ Supabase (REST, zero-dependency)
class Supabase:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def _req(self, method, path, body=None, headers=None, token=None):
        h = {"apikey": self.key, "Authorization": "Bearer " + (token or self.key), "Content-Type": "application/json"}
        h.update(headers or {})
        data = json.dumps(body, ensure_ascii=False, default=str).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and path.startswith("/auth/"):
                return None
            if e.code == 409:
                raise ApiError(409, "duplicate")
            raise ApiError(502, f"db-{e.code}")

    def get_user(self, token):
        return self._req("GET", "/auth/v1/user", token=token)

    def select(self, table, query):
        return self._req("GET", f"/rest/v1/{table}?{query}") or []

    def insert(self, table, rows):
        return self._req("POST", f"/rest/v1/{table}", rows, {"Prefer": "return=representation"}) or []

    def update(self, table, query, patch):
        return self._req("PATCH", f"/rest/v1/{table}?{query}", patch, {"Prefer": "return=representation"}) or []


# ------------------------------------------------------------------ ตัวตน + สิทธิ์ (หลักเดียวกับ approve007 · C1 app_metadata)
def identify(sb, token, env):
    if not token:
        raise ApiError(401, "unauthorized")
    user = sb.get_user(token)
    if not user or not user.get("id"):
        raise ApiError(401, "unauthorized")
    line_id = (user.get("app_metadata") or {}).get("line_id")      # C1: ห้ามใช้ user_metadata (ผู้ใช้แก้เองได้)
    email = (user.get("email") or "").lower()
    if email.endswith("@line.007metals.local"):
        email = ""
    cols = "id,nickname,full_name,branch,position,is_admin,active,is_test"
    emp = None
    if line_id:
        rows = sb.select("employees", f"select={cols}&active=eq.true&line_id=eq.{q(line_id)}&limit=1")
        emp = rows[0] if rows else None
    if not emp and email:
        rows = sb.select("employees", f"select={cols}&active=eq.true&email=ilike.{q(email)}&limit=2")
        if len(rows) > 1:
            raise ApiError(409, "email-ambiguous")
        emp = rows[0] if rows else None
    if not emp:
        raise ApiError(404, "not-linked")
    app = sb.select("apps", f"select=id&code=eq.{APP_CODE}&limit=1")
    if not app:
        raise ApiError(500, "app-missing")
    if not sb.select("app_access", f"select=app_id&employee_id=eq.{q(emp['id'])}&app_id=eq.{q(app[0]['id'])}&limit=1"):
        raise ApiError(403, "no-app-access")
    words = [w.strip().lower() for w in (env.get("FLEET007_ROLE_WORDS") or "").split(",") if w.strip()] \
        or list(DEFAULT_ROLE_WORDS)
    extra = {x.strip() for x in (env.get("FLEET007_EXTRA_IDS") or "").split(",") if x.strip()}
    pos = (emp.get("position") or "").strip().lower()
    if not (emp.get("is_admin") or str(emp["id"]) in extra or any(w in pos for w in words)):
        raise ApiError(403, "role-not-allowed")                      # แอดมิน · HR · จัดซื้อ เท่านั้น
    return {"id": emp["id"], "name": emp.get("nickname") or emp.get("full_name") or "",
            "position": emp.get("position") or "", "is_test": emp.get("is_test") is True}


# ------------------------------------------------------------------ วันครบกำหนด
def today_bkk(now=None):
    return (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(TZ).date()


def days_left(item, today):
    return (datetime.date.fromisoformat(str(item["due_date"])) - today).days


def status_of(days):
    return "overdue" if days < 0 else "due7" if days <= 7 else "due30" if days <= 30 else "ok"


def alert_stage(item, today):
    """ขั้นแจ้งเตือนของวันนี้ (None = ยังไม่ต้องเตือน)
    ยังไม่ถึงกำหนด: ขั้นที่แคบที่สุดที่ผ่านมาแล้ว (cron พลาดวันไหนก็ยังส่งขั้นปัจจุบัน ไม่ส่งขั้นที่ผ่านไปแล้วซ้ำ)
    เกินกำหนด: ขั้นละ 7 วัน (เกิน 1–7 วัน = overdue-1, 8–14 = overdue-8 ...)"""
    d = days_left(item, today)
    if d < 0:
        return "overdue-%d" % (((-d - 1) // 7) * 7 + 1)
    marks = sorted({int(x) for x in (item.get("remind_days") or DEFAULT_REMIND) if int(x) >= 0} | {0})
    hit = [m for m in marks if d <= m]
    return str(hit[0]) if hit else None


def thai_date(s):
    d = datetime.date.fromisoformat(str(s))
    months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    return f"{d.day} {months[d.month - 1]} {d.year + 543}"


def when_text(days):
    if days < 0:
        return f"เกินกำหนด {-days} วัน"
    return "ครบกำหนดวันนี้" if days == 0 else f"อีก {days} วัน"


# ------------------------------------------------------------------ อีเมล
def recipients(env):
    return [x.strip() for x in (env.get("FLEET007_ALERT_TO") or DEFAULT_TO).split(",") if x.strip()]


def send_email(env, to, subject, html_body, text_body):
    if env.get("RESEND_API_KEY"):
        sender = env.get("FLEET007_MAIL_FROM") or "Fleet007 <fleet@007metals.com>"
        req = urllib.request.Request("https://api.resend.com/emails", method="POST",
                                     data=json.dumps({"from": sender, "to": to, "subject": subject, "html": html_body,
                                                      "text": text_body}).encode(),
                                     headers={"Authorization": "Bearer " + env["RESEND_API_KEY"],
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise ApiError(502, f"mail-{e.code}")
        return "resend"
    if env.get("SMTP_HOST"):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, env.get("FLEET007_MAIL_FROM") or env["SMTP_USER"], ", ".join(to)
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        port = int(env.get("SMTP_PORT") or 465)
        try:
            if port == 465:
                with smtplib.SMTP_SSL(env["SMTP_HOST"], port, context=ssl.create_default_context(), timeout=20) as s:
                    s.login(env["SMTP_USER"], env["SMTP_PASS"])
                    s.send_message(msg)
            else:
                with smtplib.SMTP(env["SMTP_HOST"], port, timeout=20) as s:
                    s.starttls(context=ssl.create_default_context())
                    s.login(env["SMTP_USER"], env["SMTP_PASS"])
                    s.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise ApiError(502, "mail-smtp-" + type(e).__name__)
        return "smtp"
    raise ApiError(500, "mail-not-configured")


def render_alert(rows, overdue_all, today):
    """rows / overdue_all = [{plate, branch, model, kind, due_date, days, provider, policy_no}]"""
    def table(rs):
        tr = "".join(
            f"<tr><td style='padding:6px;border-bottom:1px solid #eee'><b>{html.escape(r['plate'])}</b>"
            f"<br><small>{html.escape(r.get('model') or '')} · {html.escape(r.get('branch') or '')}</small></td>"
            f"<td style='padding:6px;border-bottom:1px solid #eee'>{html.escape(r['kind'])}"
            f"{'<br><small>' + html.escape(r['provider']) + '</small>' if r.get('provider') else ''}</td>"
            f"<td style='padding:6px;border-bottom:1px solid #eee'>{thai_date(r['due_date'])}</td>"
            f"<td style='padding:6px;border-bottom:1px solid #eee;color:{'#b3261e' if r['days'] < 0 else '#9a6700' if r['days'] <= 7 else '#1a7f37'}'>"
            f"<b>{when_text(r['days'])}</b></td></tr>" for r in rs)
        return ("<table style='border-collapse:collapse;width:100%;font-size:14px'><tr style='background:#f3f5f3'>"
                "<th align=left style='padding:6px'>รถ</th><th align=left style='padding:6px'>รายการ</th>"
                "<th align=left style='padding:6px'>ครบกำหนด</th><th align=left style='padding:6px'>สถานะ</th></tr>"
                + tr + "</table>")
    n_over = sum(1 for r in rows if r["days"] < 0)
    subject = f"[Fleet007] แจ้งเตือนรถบริษัท {thai_date(today.isoformat())}: " + " · ".join(
        x for x in (f"เกินกำหนด {n_over}" if n_over else "", f"ใกล้ครบ {len(rows) - n_over}" if len(rows) > n_over else "") if x)
    body = (f"<div style='font-family:Sarabun,Tahoma,sans-serif'><h3>แจ้งเตือน พรบ. / ประกัน / ภาษี / อื่น ๆ ของรถบริษัท</h3>"
            f"<p>รายการที่ถึงรอบแจ้งเตือนวันนี้ ({len(rows)} รายการ)</p>{table(rows)}")
    shown = {x["item_id"] for x in rows}
    others = [r for r in overdue_all if r["item_id"] not in shown]
    if others:
        body += f"<p style='margin-top:16px'>ยังค้างเกินกำหนดอยู่อีก {len(others)} รายการ</p>{table(others)}"
    body += ("<p style='margin-top:16px;font-size:13px;color:#666'>ต่ออายุแล้วให้กด \"ต่ออายุแล้ว\" ในแอป "
             "https://production.007metals.com/fleet007 — ระบบจะหยุดเตือนรายการนั้นเอง</p></div>")
    text = "\n".join(f"{r['plate']} ({r.get('branch') or '-'}) · {r['kind']} · ครบ {thai_date(r['due_date'])} · {when_text(r['days'])}"
                     for r in rows + others)
    return subject, body, text + "\n\nhttps://production.007metals.com/fleet007"


def load_all(sb):
    vehicles = sb.select("fleet_vehicle", "select=*&order=branch,plate&limit=2000")
    items = sb.select("fleet_item", "select=*&active=is.true&order=due_date&limit=5000")
    return vehicles, items


def run_alerts(sb, env, now=None, force=False):
    today = today_bkk(now)
    vehicles, items = load_all(sb)
    vmap = {v["id"]: v for v in vehicles if v.get("active")}
    due, overdue_all = [], []
    sent = {(r["item_id"], str(r["due_date"]), r["stage"]) for r in
            sb.select("fleet_alert_log", f"select=item_id,due_date,stage&ok=is.true&ts=gte.{q((today - datetime.timedelta(days=400)).isoformat())}&limit=10000")}
    for it in items:
        v = vmap.get(it["vehicle_id"])
        if not v:
            continue
        d = days_left(it, today)
        row = {"item_id": it["id"], "plate": " ".join(x for x in (v["plate"], v.get("province")) if x),
               "branch": v.get("branch"), "model": " ".join(x for x in (v.get("brand"), v.get("model")) if x),
               "kind": it["kind"], "due_date": str(it["due_date"]), "days": d, "provider": it.get("provider")}
        if d < 0:
            overdue_all.append(row)
        st = alert_stage(it, today)
        if st and (force or (it["id"], str(it["due_date"]), st) not in sent):
            due.append(dict(row, stage=st))
    if not due:
        return {"sent": 0, "date": today.isoformat()}
    to = recipients(env)
    subject, body, text = render_alert(due, overdue_all, today)
    try:
        via = send_email(env, to, subject, body, text)
        ok, err = True, None
    except ApiError as e:
        via, ok, err = None, False, e.code
    sb.insert("fleet_alert_log", [{"item_id": r["item_id"], "due_date": r["due_date"], "stage": r["stage"],
                                   "sent_to": ",".join(to), "ok": ok, "error": err} for r in due])
    if not ok:
        raise ApiError(502, err)
    return {"sent": len(due), "to": to, "via": via, "date": today.isoformat(), "subject": subject}


# ------------------------------------------------------------------ อ่าน / บันทึก
def list_all(sb, env, who, now=None):
    today = today_bkk(now)
    vehicles, items = load_all(sb)
    ids = [str(i["id"]) for i in items]
    hist = {}
    for i in range(0, len(ids), 200):
        for r in sb.select("fleet_renewal", "select=*&item_id=in.(" + ",".join(ids[i:i + 200]) + ")&order=renewed_at.desc"):
            hist.setdefault(r["item_id"], []).append(r)
    by_v = {}
    for it in items:
        d = days_left(it, today)
        by_v.setdefault(it["vehicle_id"], []).append(dict(it, days=d, status=status_of(d), history=hist.get(it["id"], [])[:10]))
    out = []
    for v in vehicles:
        its = by_v.get(v["id"], [])
        worst = min((i["days"] for i in its), default=None)
        out.append(dict(v, items=its, worst_days=worst,
                        status=status_of(worst) if worst is not None and v.get("active") else "none"))
    log = sb.select("fleet_alert_log", "select=*&order=id.desc&limit=30")
    return {"today": today.isoformat(), "vehicles": out, "kinds": KINDS, "branches": BRANCHES,
            "default_remind": DEFAULT_REMIND, "alert_to": recipients(env),
            "alert_log": log, "viewer": {"name": who["name"], "position": who["position"], "read_only": who["is_test"]}}


def _clean(body, fields):
    out = {}
    for f in fields:
        if f not in body:
            continue
        v = body[f]
        if isinstance(v, str):
            v = v.strip()[:200] or None
        out[f] = v
    return out


def _date(v):
    try:
        return datetime.date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise ApiError(400, "bad-date")


def save(sb, env, who, body, now=None):
    if who["is_test"]:
        raise ApiError(403, "test-account-read-only")
    op = body.get("op")
    stamp = {"updated_by": who["name"], "updated_at": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()}
    if op == "vehicle_save":
        rec = _clean(body, VEHICLE_FIELDS)
        if "plate" in rec or not body.get("id"):
            rec["plate"] = " ".join(str(rec.get("plate") or "").split())
            if not rec["plate"]:
                raise ApiError(400, "plate-required")
        if rec.get("year") not in (None, ""):
            try:
                rec["year"] = int(rec["year"])
            except (TypeError, ValueError):
                raise ApiError(400, "bad-year")
        else:
            rec.pop("year", None)
        if body.get("id"):
            r = sb.update("fleet_vehicle", f"id=eq.{int(body['id'])}", dict(rec, **stamp))
            if not r:
                raise ApiError(404, "vehicle-not-found")
            return {"ok": True, "id": int(body["id"])}
        r = sb.insert("fleet_vehicle", [dict(rec, **stamp)])
        return {"ok": True, "id": r[0]["id"]}
    if op == "vehicle_archive":
        r = sb.update("fleet_vehicle", f"id=eq.{int(body.get('id') or 0)}", dict(stamp, active=bool(body.get("active", False))))
        if not r:
            raise ApiError(404, "vehicle-not-found")
        return {"ok": True}
    if op == "item_save":
        rec = _clean(body, ITEM_FIELDS)
        if not body.get("id"):
            if not rec.get("kind") or not rec.get("due_date"):
                raise ApiError(400, "kind-and-due-required")
            rec["vehicle_id"] = int(body.get("vehicle_id") or 0)
            if not sb.select("fleet_vehicle", f"select=id&id=eq.{rec['vehicle_id']}&limit=1"):
                raise ApiError(404, "vehicle-not-found")
        if "due_date" in rec:
            rec["due_date"] = _date(rec["due_date"])
        if "remind_days" in rec:
            try:
                rd = sorted({int(x) for x in (rec["remind_days"] or DEFAULT_REMIND) if 0 <= int(x) <= 365}, reverse=True)
            except (TypeError, ValueError):
                raise ApiError(400, "bad-remind-days")
            rec["remind_days"] = rd or DEFAULT_REMIND
        if rec.get("amount") not in (None, ""):
            try:
                rec["amount"] = round(float(rec["amount"]), 2)
            except (TypeError, ValueError):
                raise ApiError(400, "bad-amount")
        else:
            rec.pop("amount", None)
        if body.get("id"):
            r = sb.update("fleet_item", f"id=eq.{int(body['id'])}", dict(rec, **stamp))
            if not r:
                raise ApiError(404, "item-not-found")
            return {"ok": True, "id": int(body["id"])}
        r = sb.insert("fleet_item", [dict(rec, **stamp)])
        return {"ok": True, "id": r[0]["id"]}
    if op == "item_del":
        r = sb.update("fleet_item", f"id=eq.{int(body.get('id') or 0)}", dict(stamp, active=False))
        if not r:
            raise ApiError(404, "item-not-found")
        return {"ok": True}
    if op == "renew":
        iid = int(body.get("id") or 0)
        cur = sb.select("fleet_item", f"select=*&id=eq.{iid}&active=is.true&limit=1")
        if not cur:
            raise ApiError(404, "item-not-found")
        cur = cur[0]
        new_due = _date(body.get("new_due") or "")
        if new_due <= str(cur["due_date"]):
            raise ApiError(400, "new-due-must-be-later")
        patch = {"due_date": new_due}
        for f in ("provider", "policy_no", "amount"):
            if body.get(f) not in (None, ""):
                patch[f] = round(float(body[f]), 2) if f == "amount" else str(body[f]).strip()[:200]
        sb.insert("fleet_renewal", [{"item_id": iid, "old_due": str(cur["due_date"]), "new_due": new_due,
                                     "provider": patch.get("provider", cur.get("provider")),
                                     "policy_no": patch.get("policy_no", cur.get("policy_no")),
                                     "amount": patch.get("amount", cur.get("amount")),
                                     "note": (str(body.get("note") or "").strip() or None), "renewed_by": who["name"]}])
        sb.update("fleet_item", f"id=eq.{iid}", dict(patch, **stamp))
        return {"ok": True}
    if op == "test_email":
        to = recipients(env)
        via = send_email(env, to, "[Fleet007] ทดสอบอีเมลแจ้งเตือน",
                         f"<p>ทดสอบจาก Fleet007 โดย {html.escape(who['name'])} — ถ้าได้รับอีเมลนี้ แปลว่าแจ้งเตือนรายวันจะมาถึงกล่องนี้</p>",
                         f"ทดสอบจาก Fleet007 โดย {who['name']}")
        sb.insert("fleet_alert_log", [{"item_id": None, "due_date": None, "stage": "test", "sent_to": ",".join(to)}])
        return {"ok": True, "to": to, "via": via}
    if op == "run_alerts":
        return dict(run_alerts(sb, env, now), ok=True)
    raise ApiError(400, "bad-op")


# ------------------------------------------------------------------ router
def handle(action, method, headers, body_bytes, query, env=None, sb=None, now=None):
    env = env if env is not None else os.environ
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    try:
        if sb is None:
            if not env.get("SUPABASE_URL") or not env.get("SUPABASE_SERVICE_ROLE_KEY"):
                raise ApiError(500, "server-misconfigured")
            sb = Supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
        if action == "cron" and method == "GET":
            want = env.get("CRON_SECRET") or ""
            if len(want) < 16 or not hmac.compare_digest("Bearer " + want, headers.get("authorization") or ""):
                raise ApiError(401, "unauthorized")
            return 200, run_alerts(sb, env, now)
        body = {}
        if body_bytes:
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "bad-json")
        authz = headers.get("authorization") or ""
        who = identify(sb, authz[7:].strip() if authz.startswith("Bearer ") else None, env)
        if action == "list" and method == "GET":
            return 200, list_all(sb, env, who, now)
        if action == "save" and method == "POST":
            return 200, save(sb, env, who, body, now)
        raise ApiError(405, "method-not-allowed")
    except ApiError as e:
        return e.status, {"error": e.code}


def vercel_handler(action):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _go(self, method):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b""
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            status, out = handle(action, method, dict(self.headers.items()), body, query)
            data = json.dumps(out, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, *a):
            pass

    return Handler
