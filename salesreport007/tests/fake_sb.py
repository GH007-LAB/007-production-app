# -*- coding: utf-8 -*-
"""PostgREST + Storage จำลองเฉพาะรูปแบบ query ที่ sales_api.py ใช้ (ใช้ทั้งเทส Python และ serve_fixture สำหรับเทสหน้าเว็บ)"""
import copy
import datetime
import re
import urllib.parse

KEYS = {"sales_doc": ("branch", "doc_no"), "sales_choice": ("branch", "doc_no"),
        "sales_report": ("branch", "report_date"), "sales_feed": ("branch",)}
DEFAULTS = {"sales_doc": {"active": True, "refs": [], "report_date": None, "remain": None},
            "sales_expense": {"deleted": False, "receipt_path": None}}


class FakeSB:
    def __init__(self):
        self.t = {"employees": [], "apps": [{"id": 11, "code": "sales007"}], "app_access": [], "sales_doc": [],
                  "sales_choice": [], "sales_choice_log": [], "sales_expense": [], "sales_report": [], "sales_feed": []}
        self.users, self.files, self.seq = {}, {}, 0
        self.clock = datetime.datetime(2026, 10, 5, 2, 0, tzinfo=datetime.timezone.utc)

    # ---------- auth ----------
    def get_user(self, token):
        return self.users.get(token)

    def add_staff(self, emp_id, token, branch, name, admin=False):
        self.t["employees"].append({"id": emp_id, "nickname": name, "full_name": name, "branch": branch,
                                    "position": "พนักงานขาย", "is_admin": admin, "active": True, "line_id": "L" + str(emp_id)})
        self.t["app_access"].append({"employee_id": emp_id, "app_id": 11})
        self.users[token] = {"id": "u" + str(emp_id), "user_metadata": {"line_id": "L" + str(emp_id)}}

    # ---------- query ----------
    @staticmethod
    def _val(v):
        return v

    def _match(self, row, key, expr):
        op, _, val = expr.partition(".")
        val = urllib.parse.unquote(val)
        v = row.get(key)
        if op == "eq":
            return str(v).lower() == val.lower() if isinstance(v, bool) else str(v) == val
        if op == "ilike":
            return str(v or "").lower() == val.lower()
        if op == "is":
            return v is None if val == "null" else v is (val == "true")
        if op == "in":
            items = [x.strip().strip('"') for x in val.strip("()").split(",")]
            return str(v) in items
        if op in ("lt", "gte", "gt"):
            if v is None:
                return False
            a, b = str(v), val
            if re.fullmatch(r"\d{4}-\d\d-\d\dT.*", b):
                a = _ts(v)
                b = _ts(b)
            elif re.fullmatch(r"-?\d+(\.\d+)?", b):
                a, b = float(v), float(b)
            return a < b if op == "lt" else a >= b if op == "gte" else a > b
        raise AssertionError("op " + op)

    def _filter(self, table, query):
        rows = self.t[table]
        order, limit, offset = None, None, 0
        for part in query.split("&"):
            if not part:
                continue
            k, _, v = part.partition("=")
            if k == "select":
                continue
            if k == "order":
                order = v.split(",")
            elif k == "limit":
                limit = int(v)
            elif k == "offset":
                offset = int(v)
            else:
                rows = [r for r in rows if self._match(r, k, v)]
        if order:
            for f in reversed(order):
                rows = sorted(rows, key=lambda r: (r.get(f) is None, str(r.get(f))))
        rows = rows[offset:]
        return rows[:limit] if limit is not None else rows

    def select(self, table, query):
        return copy.deepcopy(self._filter(table, query))

    def upsert(self, table, rows, on_conflict):
        keys = tuple(on_conflict.split(","))
        for r in rows:
            cur = next((x for x in self.t[table] if all(str(x.get(k)) == str(r.get(k)) for k in keys)), None)
            if cur:
                cur.update(copy.deepcopy(r))
            else:
                new = dict(DEFAULTS.get(table, {}), **copy.deepcopy(r))
                if table == "sales_doc":
                    new.setdefault("first_seen_at", _iso(self.clock))
                self.t[table].append(new)

    def insert(self, table, rows, returning=False):
        for r in rows:
            self.seq += 1
            new = dict(DEFAULTS.get(table, {}), **copy.deepcopy(r))
            new.setdefault("id", self.seq)
            new.setdefault("created_at", _iso(self.clock))
            self.t[table].append(new)

    def update(self, table, query, patch):
        for r in self._filter(table, query):
            r.update(copy.deepcopy(patch))

    def upload(self, path, data, content_type="image/jpeg"):
        assert path not in self.files
        self.files[path] = data

    def signed_url(self, path, expires=3600):
        return "https://signed.example/" + path


def _iso(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(s):
    return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
