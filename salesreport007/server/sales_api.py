# -*- coding: utf-8 -*-
"""
Sales007 API — รายงานขายประจำวันแบบ live (salesreport007 v6) · Vercel Python + Supabase (service role)

  POST /api/sales/push    X-Sales-Token (sales_push.py เครื่องสาขา ทุก 1 นาที)  {branch, docs, gone, heartbeat}
  GET  /api/sales/day     Bearer <session กลาง>  ?date=&branch=   → รายงานของวัน (พนักงานเห็นเฉพาะสาขาตัวเอง ไม่มียอดรวม)
  POST /api/sales/act     Bearer                 {op: channel | expense_add | expense_photo | expense_del | submit}
  GET  /api/sales/audit   Bearer (ผบ./Finny/CTO) ?date=          → สรุปทุกสาขา + ข้อผิดปกติ + ยอดต่อประเภทตาม Express
  GET  /api/sales/export  X-Sales-Token (Mac mini) ?date=&branch= → YYMMDD_out.json ของรายงานที่ล็อกแล้ว (Finny อ่านจาก Drive)
  GET  /api/sales/cron    Vercel cron (Authorization: Bearer CRON_SECRET) → ล็อกทุกสาขาที่เลยเส้นตาย

รอบ: เอกสารรับเงิน/ลดหนี้ที่ "ระบบเห็นครั้งแรก" ก่อนตัดรอบ 16:30 และยังไม่อยู่ในรายงานใด = รายงานวันนี้
     ที่เห็นหลัง 16:30 ไปรายงานวันทำการถัดไปเอง (เอกสารยกมา) · ล็อกแล้วประทับ report_date ให้เอกสารชุดนั้น

env: SUPABASE_URL · SUPABASE_SERVICE_ROLE_KEY · SALES007_PUSH_TOKEN (≥24 ตัว) · CRON_SECRET
     SALES007_START_DATE (YYYY-MM-DD วันเริ่มใช้ — เอกสารก่อนหน้านี้ไม่ขึ้น) · SALES007_AUDIT_IDS (employee id คั่นด้วย ,)
     SALES007_CUTOFF (16:30) · SALES007_DEADLINE (16:55) · SALES007_FLOAT (JSON เช่น {"BK":0,"SKN":500})
"""
import base64
import datetime
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))

import calc  # noqa: E402

APP_CODE = "sales007"
BRANCHES = ("BK", "SKN", "PPS")
DOC_TYPES = ("IV", "AI", "SR", "HS", "RE")
ROUND_TYPES = calc.RECEIVE_TYPES + calc.REFUND_TYPES
TZ = datetime.timezone(datetime.timedelta(hours=7))
BUCKET = "sales007"
MAX_PHOTO = 3_000_000           # byte หลังถอด base64 (หน้าเว็บย่อรูปก่อนส่ง · Vercel รับ body ≤ 4.5MB)
EXPENSE_CATEGORIES = ["น้ำมัน/ค่าเดินทาง", "ค่าขนส่ง/ค่าส่งของ", "ค่าแรงรายวัน", "อาหาร/น้ำดื่ม",
                      "วัสดุสิ้นเปลือง/อุปกรณ์", "ค่าซ่อมบำรุง", "ค่าสาธารณูปโภค", "อื่น ๆ (ระบุในรายการ)"]
DOC_COLS = "branch,doc_no,type,doc_date,cuscod,customer,total,remain,refs,active,first_seen_at,report_date"


class ApiError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


def q(v):
    return urllib.parse.quote(str(v), safe="")


def in_list(vals):
    return "in.(" + ",".join(q('"%s"' % v) for v in vals) + ")"


# ------------------------------------------------------------------ Supabase (REST + Storage, zero-dependency)
class Supabase:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def _req(self, method, path, body=None, headers=None, token=None, raw=None):
        h = {"apikey": self.key, "Authorization": "Bearer " + (token or self.key)}
        h.update(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                out = r.read()
                return json.loads(out) if out else None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and path.startswith("/auth/"):
                return None
            raise ApiError(502, f"db-{e.code}")

    def get_user(self, token):
        return self._req("GET", "/auth/v1/user", token=token)

    def select(self, table, query):
        return self._req("GET", f"/rest/v1/{table}?{query}") or []

    def upsert(self, table, rows, on_conflict):
        return self._req("POST", f"/rest/v1/{table}?on_conflict={on_conflict}", rows,
                         {"Prefer": "return=minimal,resolution=merge-duplicates"})

    def insert(self, table, rows, returning=False):
        return self._req("POST", f"/rest/v1/{table}", rows,
                         {"Prefer": "return=representation" if returning else "return=minimal"})

    def update(self, table, query, patch):
        return self._req("PATCH", f"/rest/v1/{table}?{query}", patch, {"Prefer": "return=minimal"})

    def upload(self, path, data, content_type="image/jpeg"):
        return self._req("POST", f"/storage/v1/object/{BUCKET}/{path}", raw=data,
                         headers={"Content-Type": content_type, "x-upsert": "false"})

    def signed_url(self, path, expires=3600):
        r = self._req("POST", f"/storage/v1/object/sign/{BUCKET}/{path}", {"expiresIn": expires}) or {}
        u = r.get("signedURL") or r.get("signedUrl")
        return (self.url + "/storage/v1" + u) if u and u.startswith("/") else u


def select_all(sb, table, query, page=1000):
    out, off = [], 0
    while True:                                    # PostgREST ตัด 1000 แถว/คำขอ
        rows = sb.select(table, f"{query}&limit={page}&offset={off}")
        out += rows
        if len(rows) < page:
            return out
        off += page


# ------------------------------------------------------------------ เวลา / ค่าตั้ง
def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def bkk(dt):
    return dt.astimezone(TZ)


def iso_z(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    if isinstance(s, datetime.datetime):
        return s
    return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def hm(env, key, default):
    h, m = (env.get(key) or default).split(":")
    return datetime.time(int(h), int(m))


def at_time(day, t):
    return datetime.datetime.combine(day, t, TZ)


def cutoff_of(env, day):
    return at_time(day, hm(env, "SALES007_CUTOFF", "16:30"))


def deadline_of(env, day):
    return at_time(day, hm(env, "SALES007_DEADLINE", "16:55"))


def start_date(env):
    s = env.get("SALES007_START_DATE") or ""
    return datetime.date.fromisoformat(s) if s else datetime.date(2026, 10, 1)


def float_of(env, br):
    try:
        return float((json.loads(env.get("SALES007_FLOAT") or "{}")).get(br, 0))
    except (ValueError, AttributeError):
        return 0.0


def be_yymmdd(d):
    return f"{(d.year + 543) % 100:02d}{d.month:02d}{d.day:02d}"


# ------------------------------------------------------------------ ตัวตน + สิทธิ์ (หลักเดียวกับ approve007 / line/enter)
def identify(sb, token, env):
    if not token:
        raise ApiError(401, "unauthorized")
    user = sb.get_user(token)
    if not user or not user.get("id"):
        raise ApiError(401, "unauthorized")
    line_id = (user.get("user_metadata") or {}).get("line_id")
    email = (user.get("email") or "").lower()
    if email.endswith("@line.007metals.local"):
        email = ""
    cols = "id,nickname,full_name,branch,position,is_admin,active"
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
    audit_ids = {x.strip() for x in (env.get("SALES007_AUDIT_IDS") or "").split(",") if x.strip()}
    audit = bool(emp.get("is_admin")) or str(emp["id"]) in audit_ids
    br = (emp.get("branch") or "").upper()
    if not audit and br not in BRANCHES:
        raise ApiError(403, "no-branch")
    return {"id": emp["id"], "name": emp.get("nickname") or emp.get("full_name") or "", "branch": br,
            "audit": audit}


def branch_for(who, asked):
    br = (asked or who["branch"] or (BRANCHES[0] if who["audit"] else "")).upper()
    if br not in BRANCHES:
        raise ApiError(400, "bad-branch")
    if not who["audit"] and br != who["branch"]:
        raise ApiError(403, "other-branch")
    return br


# ------------------------------------------------------------------ push จากเครื่องสาขา
def require_token(headers, env):
    want = env.get("SALES007_PUSH_TOKEN") or ""
    got = headers.get("x-sales-token") or ""
    if len(want) < 24 or not hmac.compare_digest(want, got):
        raise ApiError(401, "unauthorized")


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


def push(sb, body):
    br = (body.get("branch") or "").upper()
    if br not in BRANCHES:
        raise ApiError(400, "bad-branch")
    rows = []
    for d in body.get("docs") or []:
        no, t = str(d.get("doc_no") or "").strip(), str(d.get("type") or "").upper()
        try:
            dd = datetime.date.fromisoformat(str(d.get("doc_date")))
        except ValueError:
            raise ApiError(400, "bad-doc-date")
        if not no or t not in DOC_TYPES:
            raise ApiError(400, "bad-doc")
        rows.append({"branch": br, "doc_no": no, "type": t, "doc_date": dd.isoformat(),
                     "cuscod": str(d.get("cuscod") or "")[:20], "customer": str(d.get("customer") or "")[:120],
                     "total": abs(_num(d.get("total"))),
                     "remain": None if d.get("remain") is None else _num(d.get("remain")),
                     "refs": [str(x) for x in (d.get("refs") or [])][:50],
                     "active": True, "updated_at": iso_z(now_utc())})
    # first_seen_at ไม่ส่ง → แถวใหม่ได้ default now() · แถวเดิมคงค่าเดิม (ใช้แบ่งรอบ)
    for i in range(0, len(rows), 500):
        sb.upsert("sales_doc", rows[i:i + 500], "branch,doc_no")
    gone = [str(x) for x in (body.get("gone") or [])]
    for i in range(0, len(gone), 200):
        sb.update("sales_doc", f"branch=eq.{br}&doc_no={in_list(gone[i:i + 200])}",
                  {"active": False, "updated_at": iso_z(now_utc())})
    sb.upsert("sales_feed", [{"branch": br, "last_push_at": iso_z(now_utc()),
                              "info": body.get("heartbeat") or {}}], "branch")
    return {"ok": True, "upserted": len(rows), "gone": len(gone)}


# ------------------------------------------------------------------ ชุดเอกสารของรอบ
def report_row(sb, br, day):
    rows = sb.select("sales_report", f"select=*&branch=eq.{br}&report_date=eq.{day.isoformat()}&limit=1")
    return rows[0] if rows else None


def round_docs(sb, env, br, day, upto):
    """เอกสารรับเงิน/ลดหนี้ที่ยังไม่อยู่ในรายงานใด และระบบเห็นครั้งแรกก่อน upto (= เวลาตัดรอบ)"""
    return select_all(sb, "sales_doc", f"select={DOC_COLS}&branch=eq.{br}&active=is.true&report_date=is.null"
                                       f"&type={in_list(ROUND_TYPES)}&doc_date=gte.{start_date(env).isoformat()}"
                                       f"&first_seen_at=lt.{q(iso_z(upto))}&order=first_seen_at,doc_no")


def after_cutoff_docs(sb, env, br, cut):
    return select_all(sb, "sales_doc", f"select={DOC_COLS}&branch=eq.{br}&active=is.true&report_date=is.null"
                                       f"&type={in_list(ROUND_TYPES)}&doc_date=gte.{start_date(env).isoformat()}"
                                       f"&first_seen_at=gte.{q(iso_z(cut))}&order=first_seen_at,doc_no")


def choices_for(sb, br, docs):
    out, nos = {}, [d["doc_no"] for d in docs]
    for i in range(0, len(nos), 200):
        for c in sb.select("sales_choice", f"select=doc_no,channel,set_by,set_at&branch=eq.{br}"
                                           f"&doc_no={in_list(nos[i:i + 200])}"):
            out[c["doc_no"]] = c
    return out


def expenses_for(sb, br, day):
    return sb.select("sales_expense", f"select=id,category,item,payee,amount,bill_no,receipt_path,created_by,created_at"
                                      f"&branch=eq.{br}&report_date=eq.{day.isoformat()}&deleted=is.false&order=id")


def iv_today(sb, br, day):
    ivs = select_all(sb, "sales_doc", f"select={DOC_COLS}&branch=eq.{br}&active=is.true&type=eq.IV"
                                      f"&doc_date=eq.{day.isoformat()}&order=doc_no")
    if not ivs:
        return []
    res = select_all(sb, "sales_doc", f"select=doc_no,refs&branch=eq.{br}&active=is.true&type=eq.RE"
                                      f"&doc_date=gte.{day.isoformat()}&order=doc_no")
    paid_by = {}
    for r in res:
        for iv in r.get("refs") or []:
            paid_by.setdefault(iv, []).append(r["doc_no"])
    out = []
    for d in ivs:
        by = paid_by.get(d["doc_no"], [])
        paid = bool(by) or (d.get("remain") is not None and abs(float(d["remain"])) < 0.005)
        out.append({"doc_no": d["doc_no"], "customer": d.get("customer"), "total": float(d["total"]),
                    "paid": paid, "paid_by": by})
    return out


def doc_view(d, ch, day):
    t = d["type"]
    return {"doc_no": d["doc_no"], "type": t, "doc_date": d["doc_date"], "customer": d.get("customer"),
            "total": float(d["total"]), "refs": d.get("refs") or [], "carried": d["doc_date"] < day.isoformat(),
            "channel": (ch or {}).get("channel"), "channel_by": (ch or {}).get("set_by"),
            "options": calc.channels_for(t)}


# ------------------------------------------------------------------ ล็อก (ส่ง / เลยเส้นตาย)
def lock(sb, env, br, day, reason, who=None, cash_counted=None, now=None):
    now = now or now_utc()
    if report_row(sb, br, day):
        return None
    cut = cutoff_of(env, day)
    docs = round_docs(sb, env, br, day, cut)
    ch = choices_for(sb, br, docs)
    view = [doc_view(d, ch.get(d["doc_no"]), day) for d in docs]
    exps = expenses_for(sb, br, day)
    fl = float_of(env, br)
    s = calc.summarize(view, exps, cash_counted, fl)
    nos = [d["doc_no"] for d in docs]
    for i in range(0, len(nos), 200):
        sb.update("sales_doc", f"branch=eq.{br}&doc_no={in_list(nos[i:i + 200])}&report_date=is.null",
                  {"report_date": day.isoformat()})
    row = {"branch": br, "report_date": day.isoformat(), "status": "locked", "lock_reason": reason,
           "cash_counted": cash_counted, "preparer": (who or {}).get("name"),
           "submitted_at": iso_z(now) if reason == "submit" else None, "locked_at": iso_z(now), "float": fl,
           "summary": s, "snapshot": {"docs": [dict(v, first_seen_at=d["first_seen_at"]) for v, d in zip(view, docs)],
                                      "expenses": exps, "iv": iv_today(sb, br, day),
                                      "cutoff_at": iso_z(cut)}}
    sb.upsert("sales_report", [row], "branch,report_date")
    return row


def lock_overdue(sb, env, br, now=None):
    """ก่อนอ่านรายงานใด ๆ: วันที่เลยเส้นตายแล้วแต่ยังไม่ล็อก (มีเอกสารในรอบ) → ล็อกอัตโนมัติ"""
    now = now or now_utc()
    today = bkk(now).date()
    day = today if now >= deadline_of(env, today) else today - datetime.timedelta(days=1)
    if day < start_date(env) or report_row(sb, br, day):
        return None
    if not round_docs(sb, env, br, day, cutoff_of(env, day)) and not expenses_for(sb, br, day):
        return None                                # วันหยุด/ไม่มีอะไร → ไม่สร้างรายงาน เอกสารยกไปวันถัดไป
    return lock(sb, env, br, day, "deadline", now=now)


# ------------------------------------------------------------------ อ่านรายงานของวัน
def day_view(sb, env, who, query, now=None):
    now = now or now_utc()
    br = branch_for(who, (query.get("branch") or [None])[0])
    lock_overdue(sb, env, br, now)
    today = bkk(now).date()
    ds = (query.get("date") or [None])[0]
    day = datetime.date.fromisoformat(ds) if ds else today
    cut, dl = cutoff_of(env, day), deadline_of(env, day)
    rep = report_row(sb, br, day)
    feed = sb.select("sales_feed", f"select=last_push_at&branch=eq.{br}&limit=1")
    out = {"branch": br, "date": day.isoformat(), "today": today.isoformat(),
           "cutoff": cut.strftime("%H:%M"), "deadline": dl.strftime("%H:%M"),
           "now": bkk(now).strftime("%H:%M"), "after_cutoff": now >= cut,
           "feed_at": feed[0]["last_push_at"] if feed else None,
           "categories": EXPENSE_CATEGORIES, "viewer": {"name": who["name"], "branch": who["branch"],
                                                        "audit": who["audit"]}}
    if rep:
        snap = rep["snapshot"]
        out.update(status="submitted" if rep["lock_reason"] == "submit" else "locked", lock_reason=rep["lock_reason"],
                   docs=snap["docs"], expenses=snap["expenses"], iv=snap.get("iv", []), next=[],
                   submitted_at=rep.get("submitted_at"), locked_at=rep["locked_at"], preparer=rep.get("preparer"))
        if rep["lock_reason"] == "submit" and rep["summary"].get("diff") is not None:
            out["diff"] = rep["summary"]["diff"]          # พนักงานเห็นเฉพาะส่วนต่าง หลังส่ง
        if who["audit"]:
            out.update(summary=rep["summary"], cash_counted=rep.get("cash_counted"), float=rep.get("float"))
    else:
        docs = round_docs(sb, env, br, day, cut)          # first_seen_at ไม่มีทางอยู่ในอนาคต → ตัดที่เวลาตัดรอบพอ
        nxt = after_cutoff_docs(sb, env, br, cut) if day == today and now >= cut else []
        ch = choices_for(sb, br, docs + nxt)
        out.update(status="open" if day == today else ("future" if day > today else "not-reported"),
                   docs=[doc_view(d, ch.get(d["doc_no"]), day) for d in docs],
                   next=[doc_view(d, ch.get(d["doc_no"]), day + datetime.timedelta(days=1)) for d in nxt],
                   expenses=expenses_for(sb, br, day), iv=iv_today(sb, br, day))
    for e in out["expenses"]:
        e["has_receipt"] = calc.expense_counts(e)
        if who["audit"] and e.get("receipt_path"):
            e["receipt_url"] = sb.signed_url(e["receipt_path"])
        e.pop("receipt_path", None)
    out["pending"] = sum(1 for d in out["docs"] if not d.get("channel"))
    return out


# ------------------------------------------------------------------ การกระทำของพนักงาน
def _open_today(sb, env, who, body, now):
    br = branch_for(who, body.get("branch"))
    lock_overdue(sb, env, br, now)
    today = bkk(now).date()
    if (body.get("date") or today.isoformat()) != today.isoformat():
        raise ApiError(409, "not-today")
    if report_row(sb, br, today):
        raise ApiError(409, "locked")
    if now >= deadline_of(env, today):
        lock(sb, env, br, today, "deadline", now=now)
        raise ApiError(409, "locked")
    return br, today


def _photo(sb, br, day, b64):
    if not b64:
        return None
    if "," in b64[:64]:
        b64 = b64.split(",", 1)[1]
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        raise ApiError(400, "bad-photo")
    if len(data) > MAX_PHOTO or not data.startswith(b"\xff\xd8"):
        raise ApiError(400, "bad-photo")
    path = f"{br}/{be_yymmdd(day)}/{uuid.uuid4().hex}.jpg"
    sb.upload(path, data)
    return path


def act(sb, env, who, body, now=None):
    now = now or now_utc()
    op = body.get("op")
    br, today = _open_today(sb, env, who, body, now)
    if op == "channel":
        no = str(body.get("doc_no") or "")
        rows = sb.select("sales_doc", f"select={DOC_COLS}&branch=eq.{br}&doc_no=eq.{q(no)}&active=is.true"
                                      f"&report_date=is.null&limit=1")
        if not rows or rows[0]["type"] not in ROUND_TYPES:
            raise ApiError(404, "doc-not-open")
        ch = body.get("channel")
        if ch not in calc.channels_for(rows[0]["type"]):
            raise ApiError(400, "bad-channel")
        rec = {"branch": br, "doc_no": no, "channel": ch, "set_by": who["name"], "set_at": iso_z(now)}
        sb.upsert("sales_choice", [rec], "branch,doc_no")
        sb.insert("sales_choice_log", [{k: rec[k] for k in ("branch", "doc_no", "channel", "set_by")}])
        return {"ok": True}
    if op == "expense_add":
        cat, item = str(body.get("category") or "").strip(), str(body.get("item") or "").strip()
        amt = _num(body.get("amount"))
        if cat not in EXPENSE_CATEGORIES or not item or amt <= 0:
            raise ApiError(400, "bad-expense")
        rec = {"branch": br, "report_date": today.isoformat(), "category": cat, "item": item[:200],
               "payee": str(body.get("payee") or "").strip()[:120], "amount": amt,
               "bill_no": str(body.get("bill_no") or "").strip()[:60],
               "receipt_path": _photo(sb, br, today, body.get("photo")), "created_by": who["name"]}
        sb.insert("sales_expense", [rec])
        return {"ok": True}
    if op in ("expense_photo", "expense_del"):
        eid = int(body.get("id") or 0)
        rows = sb.select("sales_expense", f"select=id&id=eq.{eid}&branch=eq.{br}&report_date=eq.{today.isoformat()}"
                                          f"&deleted=is.false&limit=1")
        if not rows:
            raise ApiError(404, "expense-not-found")
        patch = {"deleted": True} if op == "expense_del" else {"receipt_path": _photo(sb, br, today, body.get("photo"))}
        if op == "expense_photo" and not patch["receipt_path"]:
            raise ApiError(400, "bad-photo")
        sb.update("sales_expense", f"id=eq.{eid}", patch)
        return {"ok": True}
    if op == "submit":
        if now < cutoff_of(env, today):
            raise ApiError(409, "before-cutoff")
        try:
            counted = float(body.get("cash_counted"))
        except (TypeError, ValueError):
            raise ApiError(400, "cash-counted-required")
        if counted < 0:
            raise ApiError(400, "cash-counted-required")
        docs = round_docs(sb, env, br, today, cutoff_of(env, today))
        ch = choices_for(sb, br, docs)
        missing = [d["doc_no"] for d in docs if (ch.get(d["doc_no"]) or {}).get("channel")
                   not in calc.channels_for(d["type"])]
        if missing:
            return {"ok": False, "error": "channel-missing", "docs": missing}
        row = lock(sb, env, br, today, "submit", who, round(counted, 2), now)
        if not row:
            raise ApiError(409, "locked")
        return {"ok": True, "diff": row["summary"]["diff"]}
    raise ApiError(400, "bad-op")


# ------------------------------------------------------------------ ผบ. / Finny / CTO
def audit(sb, env, who, query, now=None):
    if not who["audit"]:
        raise ApiError(403, "audit-only")
    now = now or now_utc()
    ds = (query.get("date") or [None])[0]
    day = datetime.date.fromisoformat(ds) if ds else bkk(now).date() - datetime.timedelta(days=1)
    out = {"date": day.isoformat(), "branches": []}
    for br in BRANCHES:
        lock_overdue(sb, env, br, now)
        rep = report_row(sb, br, day)
        b = {"branch": br, "status": "none"}
        express = select_all(sb, "sales_doc", f"select={DOC_COLS}&branch=eq.{br}&doc_date=eq.{day.isoformat()}"
                                              f"&order=doc_no")
        by_type = {}
        for d in express:
            if d["active"]:
                by_type[d["type"]] = round(by_type.get(d["type"], 0) + float(d["total"]), 2)
        b["express_by_type"] = by_type                    # ตารางเทียบฟอร์มเดิม: IV/AI/SR/RE ตามวันที่เอกสาร
        later = [d for d in express if d["active"] and d["type"] in ROUND_TYPES
                 and (d.get("report_date") or "9999") > day.isoformat()]
        b["after_cutoff"] = {"count": len(later), "total": round(sum(float(d["total"]) for d in later), 2),
                             "docs": [d["doc_no"] for d in later]}
        if rep:
            snap = rep["snapshot"]
            cur = {}
            nos = [d["doc_no"] for d in snap["docs"]]
            for i in range(0, len(nos), 200):
                for d in sb.select("sales_doc", f"select=doc_no,total,active&branch=eq.{br}&doc_no={in_list(nos[i:i + 200])}"):
                    cur[d["doc_no"]] = d
            changed = []
            for d in snap["docs"]:
                c = cur.get(d["doc_no"])
                if not c or not c["active"]:
                    changed.append({"doc_no": d["doc_no"], "issue": "ถูกลบ/ยกเลิกใน Express หลังล็อก"})
                elif abs(float(c["total"]) - float(d["total"])) >= 0.005:
                    changed.append({"doc_no": d["doc_no"], "issue": f"แก้ยอดหลังล็อก {d['total']:,.2f} → {float(c['total']):,.2f}"})
            b.update(status=rep["lock_reason"], preparer=rep.get("preparer"), submitted_at=rep.get("submitted_at"),
                     locked_at=rep["locked_at"], cash_counted=rep.get("cash_counted"), float=rep.get("float"),
                     summary=rep["summary"], doc_count=len(snap["docs"]),
                     carried=[d["doc_no"] for d in snap["docs"] if d.get("carried")],
                     changed_after_lock=changed,
                     channels=[{k: d[k] for k in ("doc_no", "type", "customer", "total", "channel")} for d in snap["docs"]],
                     expenses=[dict({k: e.get(k) for k in ("category", "item", "payee", "amount", "bill_no", "created_by")},
                                    receipt_url=sb.signed_url(e["receipt_path"]) if e.get("receipt_path") else None)
                               for e in snap["expenses"]])
        out["branches"].append(b)
    return out


def export(sb, env, query, now=None):
    """รายงานที่ล็อกแล้ว → โครง YYMMDD_out.json (Mac mini เขียนลง Drive ให้ Finny)"""
    br = ((query.get("branch") or [""])[0]).upper()
    ds = (query.get("date") or [""])[0]
    if br not in BRANCHES or len(ds) != 10:
        raise ApiError(400, "bad-request")
    day = datetime.date.fromisoformat(ds)
    lock_overdue(sb, env, br, now)
    rep = report_row(sb, br, day)
    if not rep:
        return {"branch": br, "date": ds, "status": "not-locked"}
    snap = rep["snapshot"]
    return {"version": 6, "branch": br, "date": ds, "cutoff_at": snap.get("cutoff_at"),
            "submitted_at": rep.get("submitted_at"), "locked_at": rep["locked_at"], "lock_reason": rep["lock_reason"],
            "preparer": rep.get("preparer"),
            "docs": [{k: d.get(k) for k in ("doc_no", "doc_date", "type", "customer", "total", "carried", "channel",
                                            "first_seen_at", "refs")} for d in snap["docs"]],
            "expenses": [{k: e.get(k) for k in ("category", "item", "payee", "amount", "bill_no", "receipt_path",
                                                "created_by")} for e in snap["expenses"]],
            "iv": snap.get("iv", []), "cash_counted": rep.get("cash_counted"), "float": rep.get("float"),
            "summary": {k: rep["summary"].get(k) for k in calc.MONEY_KEYS},
            "unchosen": rep["summary"].get("unchosen", []), "expense_no_receipt": rep["summary"].get("expense_no_receipt", []),
            "doc_count_at_cutoff": len(snap["docs"])}


def cron(sb, env, headers, now=None):
    want = env.get("CRON_SECRET") or ""
    if len(want) < 16 or not hmac.compare_digest("Bearer " + want, headers.get("authorization") or ""):
        raise ApiError(401, "unauthorized")
    return {"locked": [br for br in BRANCHES if lock_overdue(sb, env, br, now)]}


# ------------------------------------------------------------------ router
def handle(action, method, headers, body_bytes, query, env=None, sb=None, now=None):
    env = env if env is not None else os.environ
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    try:
        if sb is None:
            if not env.get("SUPABASE_URL") or not env.get("SUPABASE_SERVICE_ROLE_KEY"):
                raise ApiError(500, "server-misconfigured")
            sb = Supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
        body = {}
        if body_bytes:
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "bad-json")
        if action == "cron" and method == "GET":
            return 200, cron(sb, env, headers, now)
        if action in ("push", "export"):
            require_token(headers, env)
            if action == "push" and method == "POST":
                return 200, push(sb, body)
            if action == "export" and method == "GET":
                return 200, export(sb, env, query, now)
            raise ApiError(405, "method-not-allowed")
        authz = headers.get("authorization") or ""
        who = identify(sb, authz[7:].strip() if authz.startswith("Bearer ") else None, env)
        if action == "day" and method == "GET":
            return 200, day_view(sb, env, who, query, now)
        if action == "act" and method == "POST":
            return 200, act(sb, env, who, body, now)
        if action == "audit" and method == "GET":
            return 200, audit(sb, env, who, query, now)
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
