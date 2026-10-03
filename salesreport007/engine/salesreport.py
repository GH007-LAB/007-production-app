# -*- coding: utf-8 -*-
"""
รายงานขายประจำวัน (สเปก v5) — ฝั่ง Mac mini
อ่าน DBF ของ Express แบบ read-only → เขียน YYMMDD_in.json ให้ Apps Script เติมแท็บ Google Sheet
ทุกบรรทัดมาจากเอกสารที่พนักงานคีย์ใน Express ตามเดิม (IV · AI · ลดหนี้ SR · RE ตอนรับชำระ/วางบิล)
ช่องทางเงินสด/โอน อ่านจาก RE/AI ใน Express · พนักงานกรอกในรายงานแค่ รายจ่ายประจำวัน + เงินสดนับได้

usage:  python3 salesreport.py preflight
        python3 salesreport.py inspect [YYYY-MM-DD]        Step 0: นับเอกสารแต่ละประเภทของวันนั้น (ค่าเริ่ม = เมื่อวาน)
        python3 salesreport.py inspect-pay [YYYY-MM-DD]    Step 0: ฟิลด์ตัวเลขทุกตัวของ RE/AI → หาว่าฟิลด์ไหนคือเงินสด/โอน
        python3 salesreport.py export [ready|cutoff] [--date YYYY-MM-DD] [--branch SKN] [--force]
                                                            ไม่ใส่รอบ = ดูจากเวลา (ก่อน 16:15 = ready · หลังจากนั้น = cutoff)
        python3 salesreport.py reconcile YYYY-MM-DD        ข้อ 9.4 + ข้อ 10 ให้ Finny: เอกสารครบทุกใบไหม · ยอดหลังตัดรอบ
        python3 salesreport.py summarize <YYMMDD_out.json> คำนวณสรุปซ้ำ เทียบกับที่ Apps Script เขียน

ที่เก็บ: All_on_Cloud/AutoExport/sales_report/{BK,SKN,PPS}/YYMMDD_in.json · YYMMDD_out.json (Apps Script เขียน)
        + YYMMDD_new_HHMM.csv (แถวที่เพิ่มในรอบนั้น — ใช้วางมือวันแรกถ้า Apps Script ยังไม่พร้อม · ข้อ 7)
"""
import csv
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# dbf.py / paths.py ใช้ตัวเดียวกับ approve007 (install_macmini.sh ก๊อปมาไว้ข้างกัน · ใน repo อ่านจาก approve007/engine)
sys.path.insert(1, os.path.join(os.path.dirname(os.path.dirname(HERE)), "approve007", "engine"))

import calc                           # noqa: E402
from dbf import fields_of, read_dbf   # noqa: E402
from paths import Layout              # noqa: E402

BRANCHES = ("BK", "SKN", "PPS")
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Bangkok")
except Exception:                     # Python เก่า / ไม่มี tzdata
    TZ = datetime.timezone(datetime.timedelta(hours=7))
ROUND_SPLIT = datetime.time(16, 15)   # export ไม่ระบุรอบ: ก่อนนี้ = ready (15:55) · หลังจากนี้ = cutoff (16:30)


def now():
    return datetime.datetime.now(TZ)


def be_yymmdd(d):
    return f"{(d.year + 543) % 100:02d}{d.month:02d}{d.day:02d}"


def parse_yymmdd(s):
    try:
        return datetime.date(int(s[:2]) + 2500 - 543, int(s[2:4]), int(s[4:6]))
    except (ValueError, IndexError):
        return None


def load_cfg():
    with open(os.path.join(HERE, "config", "sources.json"), encoding="utf-8") as f:
        return json.load(f)


def report_dir(L, br):
    return os.path.join(L.autoexport, "sales_report", br)


def write_atomic(path, text):
    """เขียนไฟล์ชั่วคราวแล้ว rename — Drive/Apps Script ไม่มีวันเห็นไฟล์ครึ่งไฟล์"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _pick(fields, cands):
    for c in cands or ():
        if c in fields:
            return c
    return None


def _as_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    return v if isinstance(v, datetime.date) else None


# ------------------------------------------------------------------ อ่าน Express
def resolve_source(path, src):
    """คืน {role: field} ของไฟล์นี้ · None ถ้าขาดฟิลด์บังคับ (num/date/total)"""
    names = {n for n, _, _ in fields_of(path)}
    m = {role: _pick(names, src.get(role)) for role in ("num", "date", "customer", "total", "remain")}
    m["pay"] = {k: f for k, f in ((k, _pick(names, v)) for k, v in (src.get("pay") or {}).items()) if f}
    return m if m["num"] and m["date"] and m["total"] else None


def customer_names(L, br, cfg):
    c = cfg.get("customers") or {}
    p = L.dbf(br, c.get("file", "ARMAS.DBF"))
    if not os.path.exists(p):
        return {}
    keep = {c.get("code", "CUSCOD")} | set(c.get("name") or ())
    out = {}
    for r in read_dbf(p, keep=keep):
        code = (r.get(c.get("code", "CUSCOD")) or "").strip()
        out[code] = " ".join(str(r.get(n) or "").strip() for n in c.get("name") or () if r.get(n)).strip()
    return out


def is_cancelled(r, cfg):
    c = cfg.get("cancel") or {}
    vals = {v.upper() for v in c.get("values") or ()}
    return any(str(r.get(f) or "").strip().upper() in vals for f in c.get("fields") or ())


def express_docs(L, br, cfg, since, until):
    """เอกสารทุกประเภทที่สนใจ วันที่ since..until (รวมทั้งสองวัน) → {doc_no: doc} · ไฟล์แรกที่เจอเลขนั้นชนะ"""
    names = customer_names(L, br, cfg)
    out = {}
    for src in cfg["sources"]:
        p = L.dbf(br, src["file"])
        if not os.path.exists(p):
            continue
        m = resolve_source(p, src)
        if not m:
            continue
        keep = {v for k, v in m.items() if v and k != "pay"} | set(m["pay"].values()) | \
            set((cfg.get("cancel") or {}).get("fields") or ())
        types = set(src.get("types") or ())
        for r in read_dbf(p, keep=keep):
            no = str(r.get(m["num"]) or "").strip()
            d = _as_date(r.get(m["date"]))
            if not no or not d or d < since or d > until or no in out:
                continue
            t = no[:2].upper()
            if t not in types or is_cancelled(r, cfg):
                continue
            cus = str(r.get(m["customer"]) or "").strip() if m["customer"] else ""
            doc = {"doc_no": no, "doc_date": d.isoformat(), "type": t, "cuscod": cus,
                   "customer": names.get(cus) or cus, "total": round(abs(float(r.get(m["total"]) or 0)), 2)}
            if m["remain"]:
                doc["_remain"] = float(r.get(m["remain"]) or 0)
            if m["pay"]:
                doc["pay"] = {k: round(abs(float(r.get(f) or 0)), 2) for k, f in m["pay"].items()}
            out[no] = doc
    return out


def paid_iv_numbers(L, br, cfg):
    """เลข IV ที่มีใบเสร็จอ้างถึงแล้ว (ARRCPIT) · None = ไม่มีไฟล์ลิงก์ให้ใช้"""
    found = None
    for ln in cfg.get("receipt_links") or ():
        p = L.dbf(br, ln["file"])
        if not os.path.exists(p):
            continue
        names = {n for n, _, _ in fields_of(p)}
        rf, df = _pick(names, ln.get("receipt")), _pick(names, ln.get("doc"))
        if not df:
            continue
        found = found or set()
        for r in read_dbf(p, keep={x for x in (rf, df) if x}):
            if rf and not str(r.get(rf) or "").strip().upper().startswith("RE"):
                continue
            found.add(str(r.get(df) or "").strip())
    return found


def sales_iv(docs, paid, D, cfg):
    """IV ของวันนี้ทุกใบ (ยอดขายเชื่อ = แถว IV ในฟอร์มเดิม) + ค้างรับหรือยัง"""
    out = []
    for d in docs.values():
        if d["type"] not in cfg["credit_types"] or d["doc_date"] != D.isoformat():
            continue
        if paid is not None:
            unpaid = d["doc_no"] not in paid
        else:
            unpaid = not ("_remain" in d and abs(d["_remain"]) < 0.005)
        out.append({"doc_no": d["doc_no"], "customer": d["customer"], "total": d["total"], "unpaid": unpaid})
    return sorted(out, key=lambda x: x["doc_no"])


PAY_KEYS = ("cash", "transfer", "cheque", "other")
PAY_TH = {"cash": "เงินสด", "transfer": "โอน", "cheque": "เช็ค", "other": "อื่น ๆ"}


def channel_label(d):
    """ช่องทางที่พนักงานเลือกตอนออก RE/AI ใน Express → ข้อความในรายงาน (ไม่โชว์ยอดแยก)"""
    pay = d.get("pay")
    used = [k for k in PAY_KEYS if pay and pay.get(k, 0) >= 0.005]
    if d["type"] == "SR" and not (pay or {}).get("cash"):
        return "ลดหนี้ (ไม่กระทบเงินสด)"
    if not used:
        return "⚠️ ไม่ระบุช่องทางใน Express"
    return PAY_TH[used[0]] if len(used) == 1 else "ผสม (" + "+".join(PAY_TH[k] for k in used) + ")"


def report_types(cfg):
    return set(cfg["receive_types"]) | set(cfg["refund_types"])


def interbranch(cfg, br, d):
    return d["type"] == "HS" and d["cuscod"] in set((cfg.get("interbranch_customers") or {}).get(br) or ())


# ------------------------------------------------------------------ รอบก่อน ๆ
def prior_reports(L, br, D, lookback):
    """[(date, ไฟล์ที่ใช้)] ของวันก่อน D · ใช้ out.json ก่อน (= สิ่งที่อยู่ในแท็บจริง) ถ้าไม่มีใช้ in.json"""
    found = {}
    for p in glob.glob(os.path.join(report_dir(L, br), "??????_in.json")) + \
            glob.glob(os.path.join(report_dir(L, br), "??????_out.json")):
        name = os.path.basename(p)
        d = parse_yymmdd(name[:6])
        if not d or d >= D or d < D - datetime.timedelta(days=lookback):
            continue
        if name.endswith("_out.json") or d not in found:
            found[d] = p
    return sorted(found.items())


def seen_doc_numbers(reports):
    seen = set()
    for _, p in reports:
        j = read_json(p) or {}
        for k in ("docs", "carried_in"):
            for d in j.get(k) or ():
                seen.add(d.get("doc_no"))
    return seen


# ------------------------------------------------------------------ export
def public(d):
    x = {"doc_no": d["doc_no"], "doc_date": d["doc_date"], "type": d["type"], "customer": d["customer"],
         "total": d["total"], "channel": channel_label(d),
         "pay_known": bool(d.get("pay")) and any(v >= 0.005 for v in d["pay"].values())}
    for k in PAY_KEYS:
        x[k] = (d.get("pay") or {}).get(k, 0.0)
    if d["type"] == "HS":
        x["note"] = "HS ไม่ใช่ขายระหว่างสาขา — แจ้ง ผบ."
    return x


def build_in(L, br, cfg, D, rnd, at, existing=None):
    look = int(cfg.get("carry_lookback_days", 14))
    express = express_docs(L, br, cfg, D - datetime.timedelta(days=look), D)
    paid = paid_iv_numbers(L, br, cfg)
    types = report_types(cfg)
    rows = [d for d in express.values() if d["type"] in types and not interbranch(cfg, br, d)]

    prior = prior_reports(L, br, D, look)
    seen = seen_doc_numbers(prior)
    first_day = prior[0][0] if prior else None
    # วันแรก (ยังไม่มีรายงานก่อนหน้าในช่วง lookback) = ไม่มีเอกสารยกมา (ข้อ 8)
    carry_ok = first_day is not None
    today = sorted((d for d in rows if d["doc_date"] == D.isoformat()), key=lambda d: d["doc_no"])
    carried = sorted((d for d in rows if carry_ok and d["doc_date"] < D.isoformat() and d["doc_no"] not in seen
                      and (first_day is None or d["doc_date"] >= first_day.isoformat())),
                     key=lambda d: (d["doc_date"], d["doc_no"]))

    ex = existing or {}
    warnings = list(ex.get("warnings") or ())
    out_lists = {}
    added, updated = [], []
    for key, fresh, is_carry in (("carried_in", carried, True), ("docs", today, False)):
        keep = []                                            # ลำดับแถวเดิมคงที่ · เพิ่มต่อท้ายอย่างเดียว
        have = set()
        for d in ex.get(key) or ():
            have.add(d["doc_no"])
            now_d = express.get(d["doc_no"])
            if not now_d:                                    # ถูกลบ/ยกเลิกใน Express หลังขึ้นรายงาน → คงแถว + เตือน
                if not any(w.get("doc_no") == d["doc_no"] and w.get("issue") == "missing_in_express" for w in warnings):
                    warnings.append({"doc_no": d["doc_no"], "issue": "missing_in_express",
                                     "at": at.isoformat(timespec="seconds")})
                keep.append(d)
                continue
            fresh_d = public(now_d)                          # ก่อนตัดรอบ: ยอด/ช่องทางตาม Express ล่าสุด (สาขาแก้ RE ได้)
            if any(fresh_d[k] != d.get(k) for k in ("total", "channel") + PAY_KEYS):
                updated.append(d["doc_no"])
            keep.append(fresh_d)
        for d in fresh:
            if d["doc_no"] not in have:
                keep.append(public(d))
                added.append(dict(public(d), carried=is_carry))
        out_lists[key] = keep

    counts = {}
    for d in out_lists["docs"] + out_lists["carried_in"]:
        counts[d["type"]] = counts.get(d["type"], 0) + 1
    hs = [d["doc_no"] for d in out_lists["docs"] + out_lists["carried_in"] if d["type"] == "HS"]
    data = {
        "branch": br, "date": D.isoformat(), "round": rnd, "cutoff_at": at.isoformat(timespec="seconds"),
        "rounds": list(ex.get("rounds") or ()) + [{"round": rnd, "at": at.isoformat(timespec="seconds"),
                                                   "added": len(added), "updated": updated}],
        "carried_in": out_lists["carried_in"], "docs": out_lists["docs"],
        "iv": sales_iv(express, paid, D, cfg),
        "unpaid_iv": [x for x in sales_iv(express, paid, D, cfg) if x["unpaid"]],
        "no_channel": [d["doc_no"] for d in out_lists["docs"] + out_lists["carried_in"]
                       if d["type"] in cfg["receive_types"] and not d.get("pay_known")],
        "counts": counts, "warnings": warnings,
        "hs_rows": hs,
        "unpaid_iv_source": "ARRCPIT" if paid is not None else ("REMAMT" if any("_remain" in d for d in express.values()) else "none"),
    }
    return data, added


def cmd_export(L, cfg, rnd=None, D=None, branches=BRANCHES, force=False):
    at = now()
    D = D or at.date()
    rnd = rnd or ("ready" if at.time() < ROUND_SPLIT else "cutoff")
    ok = True
    for br in branches:
        p = os.path.join(report_dir(L, br), f"{be_yymmdd(D)}_in.json")
        ex = read_json(p)
        if ex and ex.get("date") != D.isoformat():
            ex = None
        if ex and ex.get("round") == "cutoff" and not force:
            # หลังตัดรอบแล้ว เอกสารใหม่ต้องไปเป็น "เอกสารยกมา" ของวันถัดไป — ห้ามเติมเข้าวันนี้
            print(f"{br}: ตัดรอบไปแล้ว {ex.get('cutoff_at')} — ข้าม (ใช้ --force ถ้าตั้งใจทำรอบตัดใหม่)")
            continue
        try:
            data, added = build_in(L, br, cfg, D, rnd, at, ex)
        except FileNotFoundError as e:
            print(f"❌ {br}: {e}")
            ok = False
            continue
        write_atomic(p, json.dumps(data, ensure_ascii=False, indent=1))
        if added:
            cp = os.path.join(report_dir(L, br), f"{be_yymmdd(D)}_new_{at:%H%M}.csv")
            write_atomic(cp, rows_csv(added))
        print(f"{br}: {rnd} {at:%H:%M} · วันนี้ {len(data['docs'])} · ยกมา {len(data['carried_in'])} · "
              f"เพิ่มรอบนี้ {len(added)} · ค้างรับ IV {len(data['unpaid_iv'])}"
              + (f" · ⚠️ {len(data['warnings'])} เตือน" if data["warnings"] else "")
              + (f" · ⚠️ ไม่ระบุช่องทาง {len(data['no_channel'])} ใบ" if data["no_channel"] else "")
              + (f" · HS {len(data['hs_rows'])} ใบ (แจ้ง ผบ.)" if data["hs_rows"] else ""))
    return ok


def rows_csv(rows):
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["กลุ่ม", "เลขเอกสาร", "วันที่เอกสาร", "ประเภท", "ลูกค้า", "ยอดรวม VAT", "ช่องทาง (Express)",
                "เงินสด", "โอน", "เช็ค", "อื่น ๆ"])
    for d in rows:
        w.writerow(["ยกมา" if d.get("carried") else "วันนี้", d["doc_no"], d["doc_date"], d["type"],
                    d["customer"], f"{d['total']:.2f}", d["channel"]] + [f"{d[k]:.2f}" for k in PAY_KEYS])
    return "﻿" + buf.getvalue()


# ------------------------------------------------------------------ preflight / inspect
def cmd_preflight(L, cfg):
    ok = True
    print(f"All_on_Cloud: {L.root}")
    for br in BRANCHES:
        for src in cfg["sources"]:
            p = L.dbf(br, src["file"])
            if not os.path.exists(p):
                print(f"  {br} {src['file']}: ไม่มีไฟล์" + (" ❌" if src is cfg["sources"][0] else " (ข้าม)"))
                ok = ok and src is not cfg["sources"][0]
                continue
            m = resolve_source(p, src)
            print(f"  {br} {src['file']}: " + (", ".join(f"{k}={v}" for k, v in m.items() if v and k != "pay") +
                                                (" · ช่องทาง " + ", ".join(f"{k}={v}" for k, v in m["pay"].items())
                                                 if m["pay"] else " · ⚠️ ไม่เจอฟิลด์ช่องทางรับเงิน → รัน inspect-pay")
                                                if m else
                                                "❌ ขาดฟิลด์ num/date/total — แก้ config/sources.json"))
            ok = ok and bool(m)
        paid = paid_iv_numbers(L, br, cfg)
        print(f"  {br} ค้างรับ IV: " + ("จาก ARRCPIT" if paid is not None else "ไม่มีไฟล์ลิงก์ใบเสร็จ → ใช้ REMAMT ถ้ามี"))
        os.makedirs(report_dir(L, br), exist_ok=True)
    print("PRE-FLIGHT OK" if ok else "PRE-FLIGHT FAILED — ห้ามเดา path/ฟิลด์ แจ้ง ผบ.")
    return ok


def cmd_inspect(L, cfg, D):
    """Step 0: ยอดต่อประเภทของวัน D ทุกไฟล์ที่ตั้งไว้ → เทียบกับฟอร์มปัจจุบันของวันเดียวกัน (สมมติฐาน 1–2)"""
    for br in BRANCHES:
        print(f"\n== {br} {D.isoformat()} ==")
        for src in cfg["sources"]:
            p = L.dbf(br, src["file"])
            if not os.path.exists(p):
                continue
            m = resolve_source(p, src)
            print(f" {src['file']} fields: {', '.join(n for n, _, _ in fields_of(p))}")
            if not m:
                continue
            agg = {}
            for r in read_dbf(p):
                if _as_date(r.get(m["date"])) != D:
                    continue
                no = str(r.get(m["num"]) or "").strip()
                k = (no[:2].upper(), "ยกเลิก" if is_cancelled(r, cfg) else "")
                n, s = agg.get(k, (0, 0.0))
                agg[k] = (n + 1, s + float(r.get(m["total"]) or 0))
            for (t, c), (n, s) in sorted(agg.items()):
                use = "✓" if t in src.get("types", ()) else " "
                print(f"   {use} {t:<3} {c:<6} {n:>4} ใบ  {s:>14,.2f}")


def cmd_inspect_pay(L, cfg, D, branches=BRANCHES):
    """Step 0 (v5): ฟิลด์ตัวเลขทุกตัวของ RE/AI วัน D ที่ไม่เป็น 0 — ฟิลด์ที่รวมกันได้เท่ายอดรับคือช่องทางรับเงิน
    เทียบกับใบ RE ที่รู้ว่ารับเงินสด/โอน แล้วใส่ชื่อฟิลด์ใน sources.json → "pay" """
    for br in branches:
        for src in cfg["sources"]:
            p = L.dbf(br, src["file"])
            if not os.path.exists(p):
                continue
            m = resolve_source(p, src)
            if not m:
                continue
            numeric = [n for n, t, _ in fields_of(p) if t in ("N", "F", "B", "Y", "I")]
            shown = 0
            for r in read_dbf(p):
                no = str(r.get(m["num"]) or "").strip()
                if _as_date(r.get(m["date"])) != D or no[:2].upper() not in set(cfg["receive_types"]) | {"SR"}:
                    continue
                nz = {n: r.get(n) for n in numeric if abs(float(r.get(n) or 0)) >= 0.005}
                if shown == 0:
                    print(f"\n== {br} {src['file']} {D} · ใช้อยู่: {m['pay'] or 'ไม่มี'} ==")
                print(f"  {no}: " + " · ".join(f"{k}={v:,.2f}" for k, v in nz.items()))
                shown += 1
                if shown >= 15:
                    break


# ------------------------------------------------------------------ reconcile (Finny ข้อ 9.4 / 10)
def cmd_reconcile(L, cfg, D, branches=BRANCHES):
    look = int(cfg.get("carry_lookback_days", 14))
    types = report_types(cfg)
    ok = True
    for br in branches:
        rd = report_dir(L, br)
        rep = read_json(os.path.join(rd, f"{be_yymmdd(D)}_out.json")) or \
            read_json(os.path.join(rd, f"{be_yymmdd(D)}_in.json"))
        if not rep:
            print(f"{br} {D}: ไม่มีรายงาน")
            ok = False
            continue
        in_round = {d["doc_no"]: d for d in rep.get("docs") or () if not d.get("carried")
                    and d.get("doc_date", D.isoformat()) == D.isoformat()}
        later = {}
        for i in range(1, look + 1):
            Dn = D + datetime.timedelta(days=i)
            j = read_json(os.path.join(rd, f"{be_yymmdd(Dn)}_out.json")) or \
                read_json(os.path.join(rd, f"{be_yymmdd(Dn)}_in.json"))
            if not j:
                continue
            for d in (j.get("carried_in") or []) + [x for x in j.get("docs") or () if x.get("carried")]:
                if d.get("doc_date") == D.isoformat():
                    later.setdefault(d["doc_no"], dict(d, report=Dn.isoformat()))
        express = {k: v for k, v in express_docs(L, br, cfg, D, D).items()
                   if v["type"] in types and not interbranch(cfg, br, v)}
        issues = []
        for no, e in sorted(express.items()):
            got = in_round.get(no) or later.get(no)
            if not got:
                issues.append(f"{no} {e['type']} {e['total']:,.2f} ไม่อยู่ในรอบ {D} และไม่ถูกยกไปรอบถัดไป")
            elif abs(float(got.get("total") or 0) - e["total"]) >= 0.005:
                issues.append(f"{no} ยอดในรายงาน {float(got['total']):,.2f} ≠ Express {e['total']:,.2f} (แก้ยอดหลังตัดรอบ)")
            elif any(abs(float(got.get(k) or 0) - (e.get("pay") or {}).get(k, 0.0)) >= 0.005 for k in PAY_KEYS):
                issues.append(f"{no} เงินสด/โอนในรายงานไม่ตรง RE ใน Express ตอนนี้ (แก้ RE หลังตัดรอบ)")
            elif e["type"] in cfg["receive_types"] and not got.get("pay_known", True):
                issues.append(f"{no} ไม่ระบุช่องทางรับเงินใน Express — ให้สาขาแก้ RE/AI")
        for no, d in sorted({**in_round, **later}.items()):
            if no not in express:
                issues.append(f"{no} อยู่ในรายงานแต่ไม่มี/ถูกยกเลิกใน Express (ลบหลังตัดรอบ)")
        by_type = {}
        for no, e in express.items():
            by_type.setdefault(e["type"], [0.0, 0.0])[0] += e["total"]
        for no, d in {**in_round, **later}.items():
            by_type.setdefault(d["type"], [0.0, 0.0])[1] += float(d.get("total") or 0)
        after = [d for d in later.values()]
        print(f"\n== {br} {D} ==")
        for t, (ex_s, rep_s) in sorted(by_type.items()):
            print(f"  {t:<3} Express {ex_s:>14,.2f} · รายงานใหม่ (รอบ D + ยกไป) {rep_s:>14,.2f} · ต่าง {rep_s - ex_s:,.2f}")
        print(f"  เอกสารหลังตัดรอบ: {len(after)} ใบ · {sum(float(d['total']) for d in after):,.2f}")
        s = rep.get("summary")
        if s:
            print(f"  เงินสดควรมี {s['cash_expected']:,.2f} · นับจริง {float(rep.get('cash_counted') or 0):,.2f} · "
                  f"ส่วนต่าง {s['diff']:,.2f} · โอน/QR {s['transfer_in']:,.2f} · รายจ่าย {s['cash_expense']:,.2f}")
        for w in rep.get("warnings") or ():
            issues.append(f"{w['doc_no']} {w['issue']} (พบตอน export {w.get('at', '')})")
        for x in issues:
            print("  ⚠️ " + x)
        if not issues:
            print("  ✅ เอกสารครบทุกใบ ยอดตรง Express")
        ok = ok and not issues
    return ok


def cmd_summarize(path):
    j = read_json(path)
    if not j:
        print(f"อ่าน {path} ไม่ได้")
        return False
    s = calc.summarize(j.get("docs") or [], j.get("expenses") or [], j.get("cash_counted"), j.get("float", 0))
    print(json.dumps(s, ensure_ascii=False, indent=1))
    got = j.get("summary") or {}
    bad = [k for k in calc.MONEY_KEYS
           if k in got and abs(float(got[k]) - s[k]) >= 0.005]
    print("✅ ตรงกับ summary ใน out.json" if not bad else f"❌ ไม่ตรง: {bad}")
    return not bad


def _arg(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        return argv[i + 1] if i + 1 < len(argv) else None
    return None


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "export"
    if cmd == "summarize":
        sys.exit(0 if cmd_summarize(argv[2]) else 1)
    L, cfg = Layout(), load_cfg()
    br = _arg(argv, "--branch")
    branches = (br.upper(),) if br else BRANCHES
    ds = _arg(argv, "--date")
    if cmd == "preflight":
        sys.exit(0 if cmd_preflight(L, cfg) else 1)
    if cmd == "inspect":
        D = datetime.date.fromisoformat(argv[2]) if len(argv) > 2 and not argv[2].startswith("-") \
            else now().date() - datetime.timedelta(days=1)
        cmd_inspect(L, cfg, D)
    elif cmd == "inspect-pay":
        D = datetime.date.fromisoformat(argv[2]) if len(argv) > 2 and not argv[2].startswith("-") \
            else now().date() - datetime.timedelta(days=1)
        cmd_inspect_pay(L, cfg, D, branches)
    elif cmd == "reconcile":
        D = datetime.date.fromisoformat(argv[2]) if len(argv) > 2 and not argv[2].startswith("-") \
            else now().date() - datetime.timedelta(days=1)
        sys.exit(0 if cmd_reconcile(L, cfg, D, branches) else 1)
    elif cmd == "export":
        rnd = next((a for a in argv[2:] if a in ("ready", "cutoff")), None)
        sys.exit(0 if cmd_export(L, cfg, rnd, datetime.date.fromisoformat(ds) if ds else None, branches,
                                 "--force" in argv) else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
