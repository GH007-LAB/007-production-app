# -*- coding: utf-8 -*-
"""
Approve007 API (เฟส 1) — รันบน Vercel Python ใช้ engine ตัวเดียวกับ Mac mini/ตัวเฝ้าบิล (approve_engine.py)
ทุนอยู่ฝั่งเซิร์ฟเวอร์เท่านั้น: ตาราง approve_* เปิด RLS ไม่มี policy → อ่านได้แค่ service role

  POST /api/approve/check   Bearer <session กลาง>   {so, branch?} | {branch, text}     → เกรดบิล (ตัดตามสิทธิ์)
  GET  /api/approve/bands   Bearer <session กลาง>                                       → ช่วงราคา (ไม่มีทุน)
  POST /api/approve/push    X-Approve-Token (Mac mini)   {kind: snapshot|so_lines, ...} → รับข้อมูลจาก All_on_Cloud
  GET  /api/approve/log     X-Approve-Token (Mac mini)   ?after=<id>                    → ผล < 75% ไปต่อท้าย approval_requests.jsonl

env: SUPABASE_URL · SUPABASE_SERVICE_ROLE_KEY (มีอยู่แล้วบน Vercel) · APPROVE007_PUSH_TOKEN (ใหม่)
     APPROVE007_GEM_IDS (ไม่บังคับ: employee id ของ ผบ. คั่นด้วย , — ไม่ตั้ง = is_admin ทุกคนเป็นโหมด ผบ.)
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))

import approve_engine as E  # noqa: E402
import quick as Q           # noqa: E402

APP_CODE = "approve007"
BRANCHES = ("BK", "SKN", "PPS")
CHASE_LIMIT = 5              # รายการเดิมจากคนเดิม > 5 ครั้ง/ชม. → หยุดตอบ (กันไล่ราคาหาทุน)
SNAPSHOT_TTL = 300           # วินาที — cache snapshot ใน lambda ที่ยังอุ่น
MANAGER_POSITIONS = {"ผู้จัดการสาขา"}
SALES_POSITIONS = {"หัวหน้าฝ่ายขาย", "พนักงานขาย", "พนักงานขายออนไลน์", "พนักงานไลฟ์สด", "ผู้จัดการสาขา"}


class ApiError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


# ------------------------------------------------------------------ Supabase (REST, zero-dependency)
class Supabase:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def _req(self, method, path, body=None, headers=None, token=None):
        h = {"apikey": self.key, "Authorization": "Bearer " + (token or self.key),
             "Content-Type": "application/json"}
        h.update(headers or {})
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and path.startswith("/auth/"):
                return None
            raise ApiError(502, f"db-{e.code}")

    def get_user(self, token):
        return self._req("GET", "/auth/v1/user", token=token)

    def select(self, table, query):
        return self._req("GET", f"/rest/v1/{table}?{query}") or []

    def insert(self, table, rows, on_conflict=None):
        q = f"?on_conflict={on_conflict}" if on_conflict else ""
        prefer = "return=minimal" + (",resolution=merge-duplicates" if on_conflict else "")
        return self._req("POST", f"/rest/v1/{table}{q}", rows, {"Prefer": prefer})

    def delete(self, table, query):
        return self._req("DELETE", f"/rest/v1/{table}?{query}", headers={"Prefer": "return=minimal"})


def q(v):
    return urllib.parse.quote(str(v), safe="")


# ------------------------------------------------------------------ ตัวตน + สิทธิ์
def identify(sb, token, env):
    """session กลาง → พนักงาน → role (SALES/MGR/GEM) · ใช้หลักเดียวกับ /api/line/enter (ไม่รับอีเมลที่พิมพ์เอง)"""
    if not token:
        raise ApiError(401, "unauthorized")
    user = sb.get_user(token)
    if not user or not user.get("id"):
        raise ApiError(401, "unauthorized")
    meta = user.get("user_metadata") or {}
    line_id = meta.get("line_id")
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
    acc = sb.select("app_access", f"select=app_id&employee_id=eq.{q(emp['id'])}&app_id=eq.{q(app[0]['id'])}&limit=1")
    if not acc:
        raise ApiError(403, "no-app-access")
    gem_ids = {x.strip() for x in (env.get("APPROVE007_GEM_IDS") or "").split(",") if x.strip()}
    pos = (emp.get("position") or "").strip()
    if (str(emp["id"]) in gem_ids) if gem_ids else emp.get("is_admin"):
        role = "GEM"
    elif pos in MANAGER_POSITIONS:
        role = "MGR"
    else:
        role = "SALES"
    return {"id": emp["id"], "name": emp.get("nickname") or emp.get("full_name") or "",
            "branch": (emp.get("branch") or "").upper(), "role": role}


# ------------------------------------------------------------------ snapshot (ทุน · Rate 1 · สินค้า · ช่วงราคา)
_CACHE = {"at": 0, "snap": None}


def load_snapshot(sb, now=None):
    now = now or time.time()
    if _CACHE["snap"] is None or now - _CACHE["at"] > SNAPSHOT_TTL:
        rows = sb.select("approve_snapshot", "select=id,payload&order=id.desc&limit=1")
        if not rows:
            raise ApiError(503, "no-snapshot")
        _CACHE.update(at=now, snap=rows[0]["payload"])
    return _CACHE["snap"]


def book_of(snap):
    return E.CostBook(snap["rules"])


def rate1_fn(snap, br):
    r1 = (snap.get("rate1") or {}).get(br) or {}
    return lambda code: r1.get(code)


# ------------------------------------------------------------------ handlers
def effective_role(who, br):
    """ผจก. เห็นช่วง GP เฉพาะสาขาตัวเอง — สาขาอื่นเห็นแบบเซล (เหมือน checkso)"""
    if who["role"] == "MGR" and br != who["branch"]:
        return "SALES"
    return who["role"]


def so_rows(sb, sonum, branch=None):
    sel = "select=branch,sonum,seq,sodat,stkcod,stkdes,qty,price,value,tfactor,cusnam"
    f = f"&sonum=eq.{q(sonum)}" + (f"&branch=eq.{q(branch)}" if branch else "")
    return sb.select("approve_so_line", sel + f + "&order=branch,seq&limit=500")


def check(sb, who, body, env, now=None):
    snap = load_snapshot(sb, now)
    book = book_of(snap)
    so = (body.get("so") or "").strip().upper()
    br = (body.get("branch") or "").strip().upper() or None
    if br and br not in BRANCHES:
        raise ApiError(400, "bad-branch")
    if so:
        rows = so_rows(sb, so, br)
        by = {}
        for r in rows:
            by.setdefault(r["branch"], []).append(r)
        if not by:
            return {"found": False, "so": so, "branch": br,
                    "note": "ไม่พบ SO นี้ในข้อมูลล่าสุด — บิลที่เพิ่งบันทึกอาจยังไม่ขึ้น (อัปเดตทุก ~15 นาที)"}
        if len(by) > 1:
            return {"ambiguous": [{"branch": b, "date": ls[0].get("sodat"), "lines": len(ls),
                                   "total": round(sum(float(x.get("value") or 0) for x in ls), 2),
                                   "customer": ls[0].get("cusnam") or ""} for b, ls in sorted(by.items())],
                    "so": so, "note": "เลข SO นี้มีหลายสาขา — เลือกสาขาก่อน"}
        b, ls = next(iter(by.items()))
        lines = [{"code": x["stkcod"], "qty": x["qty"], "price": x["price"], "value": x.get("value"),
                  "tfactor": x.get("tfactor") or 1} for x in ls]
        res = E.grade_bill(lines, b, book, role=effective_role(who, b), rate1_of=rate1_fn(snap, b), layer="B",
                            policy=snap.get("policy"))
        res.update(so=so, customer=ls[0].get("cusnam") or "", data_as_of=snap.get("so_as_of", {}).get(b))
        log_check(sb, who, res, key="so:" + b + ":" + so, so=so)
        return res
    text = body.get("text") or ""
    if not br:
        raise ApiError(400, "branch-required")
    raw = [l for l in (text.splitlines() if isinstance(text, str) else text) if l.strip()][:60]
    if not raw:
        raise ApiError(400, "empty")
    lines, view = Q.quick_lines(raw, (snap.get("catalog") or {}).get(br) or [])
    key = "quick:" + br + ":" + hashlib.sha1("|".join(sorted(v["code"] or v["text"] for v in view)).encode()).hexdigest()[:16]
    if chased(sb, who, key, now):
        log_check(sb, who, {"branch": br, "layer": "A", "grade": None, "approval_pct": None, "total": 0}, key=key, blocked=True)
        return {"blocked": True, "note": "เช็ครายการนี้ซ้ำหลายครั้งในชั่วโมงนี้แล้ว — ส่งเข้าแชทให้ ผจก./ผบ. ช่วยดู"}
    res = E.grade_bill(lines, br, book, role=effective_role(who, br), rate1_of=rate1_fn(snap, br), layer="A",
                        policy=snap.get("policy"))
    res["items"] = view
    log_check(sb, who, res, key=key)
    return res


def chased(sb, who, key, now=None):
    since = datetime.datetime.fromtimestamp((now or time.time()) - 3600, datetime.timezone.utc).isoformat()
    rows = sb.select("approve_check_log", f"select=id&employee_id=eq.{q(who['id'])}&key=eq.{q(key)}"
                                          f"&ts=gte.{q(since)}&limit={CHASE_LIMIT + 1}")
    return len(rows) >= CHASE_LIMIT


def log_check(sb, who, res, key, so=None, blocked=False):
    """log ทุกครั้งที่เช็ค (ไม่มีทุน/GP) — ใช้ทั้งกันไล่ราคาและส่งเรื่อง < 75% เข้า approval_requests.jsonl"""
    sb.insert("approve_check_log", [{"employee_id": who["id"], "name": who["name"], "role": who["role"],
                                     "branch": res.get("branch"), "layer": res.get("layer"), "key": key,
                                     "sonum": so, "total": res.get("total"), "grade": res.get("grade"),
                                     "chance": res.get("approval_pct"), "coverage": res.get("coverage_pct"),
                                     "blocked": blocked}])


# ------------------------------------------------------------------ 🐄 ติ๊ก cash cow (ผบ./แอดมินที่ CTO กำหนด เท่านั้น)
POLICY_EDITORS_DEFAULT = "66,7"      # CTO 28 ก.ย. 69: CTO (66) + ปอนด์ (7) · เปลี่ยนได้ด้วย env APPROVE007_POLICY_EDITORS
CASHCOW_MAX = 20


def policy_editor(who, env):
    ids = {x.strip() for x in (env.get("APPROVE007_POLICY_EDITORS") or POLICY_EDITORS_DEFAULT).split(",") if x.strip()}
    if str(who["id"]) not in ids:
        raise ApiError(403, "not-policy-editor")


def policy(sb, who, method, body, env):
    """GET = รายการเสนอ + ที่ติ๊กล่าสุด · POST {keys: [...], note} = บันทึก (บันทึกอย่างเดียว ยังไม่เปลี่ยนเกรด)
    มี GP ที่ Rate 1 — ส่งเฉพาะคนที่ติ๊กได้ ห้ามถึงเซล"""
    policy_editor(who, env)
    snap = load_snapshot(sb)
    cc = snap.get("cashcow") or {}
    cands = {c["key"]: c for c in cc.get("candidates") or []}
    if method == "POST":
        keys = body.get("keys") if isinstance(body, dict) else None
        if (not isinstance(keys, list) or not keys or len(keys) > CASHCOW_MAX
                or not all(isinstance(k, str) for k in keys) or len(set(keys)) != len(keys)):
            raise ApiError(400, "bad-keys")          # ว่าง = ไม่รับ (กันทับรายการเดิมด้วยรายการว่าง)
        unknown = [k for k in keys if k not in cands]
        if unknown:
            raise ApiError(400, "unknown-keys")
        codes = sorted({c for k in keys for c in cands[k]["codes"]})
        note = str(body.get("note") or "")[:500]
        sb.insert("approve_policy_pick", [{"tag": "cash_cow", "keys": keys, "codes": codes,
                                           "employee_id": str(who["id"]), "name": who["name"], "note": note}])
    picks = sb.select("approve_policy_pick", "select=id,ts,keys,codes,name,note&tag=eq.cash_cow&order=id.desc&limit=5")
    return {"cashcow": cc, "generated": snap.get("generated"), "picks": picks, "max": CASHCOW_MAX}


def bands(sb):
    b = load_snapshot(sb).get("bands")
    if not b:
        raise ApiError(503, "no-bands")
    return b


def require_push_token(headers, env):
    want = env.get("APPROVE007_PUSH_TOKEN") or ""
    got = headers.get("x-approve-token") or ""
    if len(want) < 24 or not hmac.compare_digest(want, got):
        raise ApiError(401, "unauthorized")


def push(sb, body):
    kind = body.get("kind")
    if kind == "snapshot":
        payload = body.get("payload") or {}
        for k in ("rules", "rate1", "catalog", "bands"):
            if k not in payload:
                raise ApiError(400, f"missing-{k}")
        E.CostBook(payload["rules"])                      # ตรวจรูปแบบก่อนรับ
        sb.insert("approve_snapshot", [{"payload": payload}])
        old = sb.select("approve_snapshot", "select=id&order=id.desc&offset=5&limit=100")
        if old:
            sb.delete("approve_snapshot", "id=in.(" + ",".join(str(r["id"]) for r in old) + ")")
        _CACHE.update(at=0, snap=None)
        return {"ok": True, "kind": kind}
    if kind == "so_lines":
        br = (body.get("branch") or "").upper()
        since = body.get("since") or ""
        if br not in BRANCHES or len(since) != 10:
            raise ApiError(400, "bad-request")
        rows = body.get("rows") or []
        if body.get("first"):                              # ตัดบิลที่เก่ากว่าช่วงที่เก็บ
            sb.delete("approve_so_line", f"branch=eq.{br}&sodat=lt.{since}")
        gone = [str(x) for x in (body.get("delete_sos") or [])]
        if body.get("keep_sos") is not None:              # รอบเต็ม: SO บนเซิร์ฟเวอร์ที่ไม่อยู่ในรายชื่อนี้ = ค้าง → ลบ
            keep, have, off = {str(x) for x in body["keep_sos"]}, set(), 0
            while True:                                    # PostgREST ตัด 1000 แถว/คำขอ ต้องแบ่งหน้า
                page = sb.select("approve_so_line", f"select=sonum&branch=eq.{br}&order=sonum,seq&limit=1000&offset={off}")
                have |= {str(r["sonum"]) for r in page}
                if len(page) < 1000:
                    break
                off += 1000
            gone = sorted(set(gone) | (have - keep))
        for i in range(0, len(gone), 200):                 # SO ที่ถูกลบใน Express (Mac mini ส่งเฉพาะที่เปลี่ยน)
            sb.delete("approve_so_line", f"branch=eq.{br}&sonum=in.(" + ",".join(q(x) for x in gone[i:i + 200]) + ")")
        if rows:
            # แทนที่ทีละ SO (ลบของเก่าเฉพาะ SO ในชุดนี้ แล้วใส่ใหม่) — บรรทัดที่ถูกลบใน Express ไม่ค้าง
            # และไม่มีช่วงที่ทั้งสาขาว่าง
            sos = sorted({str(r.get("sonum")) for r in rows})
            sb.delete("approve_so_line", f"branch=eq.{br}&sonum=in.(" + ",".join(q(x) for x in sos) + ")")
            keep = ("sonum", "seq", "sodat", "stkcod", "stkdes", "qty", "price", "value", "tfactor", "cusnam")
            sb.insert("approve_so_line", [dict({k: r.get(k) for k in keep}, branch=br) for r in rows])
        return {"ok": True, "kind": kind, "rows": len(rows), "deleted_sos": len(gone)}
    raise ApiError(400, "bad-kind")


def pull_log(sb, query):
    after = int((query.get("after") or ["0"])[0] or 0)
    return sb.select("approve_check_log", f"select=id,ts,name,branch,layer,sonum,total,grade,chance,coverage,blocked"
                                          f"&id=gt.{after}&or=(chance.lt.75,blocked.is.true)&order=id&limit=1000")


# ------------------------------------------------------------------ router (ใช้ได้ทั้ง Vercel และเทส)
def handle(action, method, headers, body_bytes, query, env=None, sb=None):
    env = env if env is not None else os.environ
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    try:
        if not env.get("SUPABASE_URL") or not env.get("SUPABASE_SERVICE_ROLE_KEY"):
            if sb is None:
                raise ApiError(500, "server-misconfigured")
        sb = sb or Supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
        body = {}
        if body_bytes:
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "bad-json")
        if action in ("push", "log"):
            require_push_token(headers, env)
            if action == "push" and method == "POST":
                return 200, push(sb, body)
            if action == "log" and method == "GET":
                return 200, {"rows": pull_log(sb, query)}
            raise ApiError(405, "method-not-allowed")
        authz = headers.get("authorization") or ""
        token = authz[7:].strip() if authz.startswith("Bearer ") else None
        who = identify(sb, token, env)
        if action == "check" and method == "POST":
            out = check(sb, who, body, env)
            out["viewer"] = {"name": who["name"], "role": who["role"], "branch": who["branch"]}
            return 200, out
        if action == "policy" and method in ("GET", "POST"):
            return 200, policy(sb, who, method, body, env)
        if action == "bands" and method == "GET":
            return 200, dict(bands(sb), viewer={"name": who["name"], "branch": who["branch"]})
        raise ApiError(405, "method-not-allowed")
    except ApiError as e:
        return e.status, {"error": e.code}


def vercel_handler(action):
    """สร้างคลาส handler สำหรับไฟล์ api/approve/<action>.py"""
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _go(self, method):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b""
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            status, out = handle(action, method, dict(self.headers.items()), body, query)
            data = json.dumps(out, ensure_ascii=False).encode("utf-8")
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
