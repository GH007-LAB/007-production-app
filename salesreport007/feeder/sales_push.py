# -*- coding: utf-8 -*-
"""
007 Metals - Sales Push (Sales007 รายงานขายประจำวันแบบ live)
อ่านเอกสาร IV / AI / SR / HS / RE จาก DBF ของ Express ที่ต้นทาง (read-only) → ส่งขึ้น /api/sales/push
ออกแบบให้รันบนเครื่องสาขาผ่าน Task Scheduler ทุก 1 นาที แบบเดียวกับ so_push.py (zero-dependency, pure Python 3)

usage:  python sales_push.py <config_file>            ส่งจริง
        python sales_push.py <config_file> --dry      อ่าน + เทียบ อย่างเดียว ไม่ส่ง
        python sales_push.py <config_file> --inspect [YYYY-MM-DD]
                                                      Step 0: ฟิลด์ที่ใช้ + จำนวน/ยอดแต่ละประเภทของวันนั้น (ค่าเริ่ม = เมื่อวาน)
                                                      → เทียบกับฟอร์ม Excel เดิมก่อนเปิดใช้

config file (KEY=VALUE):
  BRANCH=SKN
  SRC=Z:\\skn2569
  API_URL=https://production.007metals.com/api/sales
  PUSH_TOKEN=...            (ค่าเดียวกับ SALES007_PUSH_TOKEN บน Vercel — อยู่ในเครื่องนี้เท่านั้น)
  WINDOW_DAYS=14            (มองย้อนกี่วัน)
  START_DATE=2026-10-05     (เอกสารก่อนวันนี้ไม่ส่ง)

state/log เก็บที่ %LOCALAPPDATA%\\007sales_push\\ (ไม่ปนโฟลเดอร์ Drive)
"""
import datetime
import hashlib
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request

# ไฟล์/ฟิลด์ของ Express — ใส่ได้หลายชื่อ ตัวแรกที่มีในไฟล์ถูกใช้ · ยืนยันด้วย --inspect ก่อนเปิดใช้ (Step 0)
SOURCES = [
    {"file": "ARTRN.DBF", "num": ["DOCNUM"], "date": ["DOCDAT"], "customer": ["CUSCOD"],
     "total": ["NETAMT", "NETVAL", "AMOUNT"], "remain": ["REMAMT"], "types": ["IV", "AI", "SR", "HS", "RE"]},
    {"file": "ARRCPT.DBF", "num": ["RCPNUM", "DOCNUM"], "date": ["RCPDAT", "DOCDAT"], "customer": ["CUSCOD"],
     "total": ["NETAMT", "RCVAMT", "AMOUNT"], "remain": [], "types": ["RE"]},
]
LINKS = [{"file": "ARRCPIT.DBF", "receipt": ["RCPNUM", "DOCNUM"], "doc": ["DOCNUM", "IVNUM", "REFNUM"]}]
CANCEL_FIELDS, CANCEL_VALUES = ["DOCSTAT"], {"C"}
FULL_EVERY_S = 1800          # ส่งครบทุกใบอย่างน้อยทุก 30 นาที กันสถานะในเครื่องกับเซิร์ฟเวอร์เพี้ยนกัน


# ---------- pure-python DBF reader (โครงเดียวกับ so_push.py) ----------
def dbf_fields(path):
    with open(path, "rb") as f:
        hdr = f.read(32)
        hdrlen = struct.unpack("<H", hdr[8:10])[0]
        out = []
        for _ in range((hdrlen - 33) // 32):
            fd = f.read(32)
            if fd[0:1] == b"\r":
                break
            out.append((fd[0:11].split(b"\x00")[0].decode("ascii", "replace"), fd[11:12].decode("ascii", "replace"),
                        fd[16]))
        return out


def read_dbf(path, fields=None, encoding="cp874"):
    with open(path, "rb") as f:
        hdr = f.read(32)
        nrec = struct.unpack("<I", hdr[4:8])[0]
        hdrlen = struct.unpack("<H", hdr[8:10])[0]
        reclen = struct.unpack("<H", hdr[10:12])[0]
        fdefs = dbf_fields(path)
        f.seek(hdrlen)
        for _ in range(nrec):
            rec = f.read(reclen)
            if len(rec) < reclen:
                break
            if rec[0:1] == b"*":
                continue
            row, pos = {}, 1
            for name, ftype, flen in fdefs:
                raw = rec[pos:pos + flen]
                pos += flen
                if fields is not None and name not in fields:
                    continue
                if ftype in ("N", "F"):
                    s = raw.strip()
                    try:
                        row[name] = float(s) if s else 0.0
                    except ValueError:
                        row[name] = 0.0
                elif ftype == "B":
                    row[name] = struct.unpack("<d", raw)[0] if len(raw) == 8 else 0.0
                elif ftype == "I":
                    row[name] = struct.unpack("<i", raw)[0] if len(raw) == 4 else 0
                elif ftype == "Y":
                    row[name] = struct.unpack("<q", raw)[0] / 10000.0 if len(raw) == 8 else 0.0
                elif ftype == "D":
                    s = raw.strip()
                    try:
                        row[name] = datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8])) if len(s) == 8 else None
                    except ValueError:
                        row[name] = None
                else:
                    row[name] = raw.decode(encoding, "replace").strip()
            yield row


# ---------- helpers ----------
def log(msg):
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def load_config(path):
    cfg = {"WINDOW_DAYS": "14", "API_URL": "https://production.007metals.com/api/sales"}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip().upper()] = v.strip()
    for k in ("BRANCH", "SRC"):
        if not cfg.get(k):
            raise SystemExit("config missing " + k)
    cfg["BRANCH"] = cfg["BRANCH"].upper()
    return cfg


def state_dir():
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "007sales_push")
    os.makedirs(d, exist_ok=True)
    return d


def pick(names, cands):
    return next((c for c in cands or () if c in names), None)


def resolve(path, src):
    names = {n for n, _, _ in dbf_fields(path)}
    m = {k: pick(names, src.get(k)) for k in ("num", "date", "customer", "total", "remain")}
    m["cancel"] = [c for c in CANCEL_FIELDS if c in names]
    return m if m["num"] and m["date"] and m["total"] else None


# ---------- อ่าน Express ----------
def read_docs(src_dir, since, until=None):
    names = {}
    p = os.path.join(src_dir, "ARMAS.DBF")
    if os.path.exists(p):
        for r in read_dbf(p, fields={"CUSCOD", "PRENAM", "CUSNAM"}):
            names[(r.get("CUSCOD") or "").strip()] = ((r.get("PRENAM") or "") + " " + (r.get("CUSNAM") or "")).strip()
    docs, used = {}, []
    for src in SOURCES:
        p = os.path.join(src_dir, src["file"])
        if not os.path.exists(p):
            continue
        m = resolve(p, src)
        if not m:
            log("ข้าม %s: ไม่เจอฟิลด์เลขที่/วันที่/ยอด" % src["file"])
            continue
        used.append((src["file"], m))
        keep = {v for k, v in m.items() if v and k != "cancel"} | set(m["cancel"])
        for r in read_dbf(p, fields=keep):
            no = str(r.get(m["num"]) or "").strip()
            d = r.get(m["date"])
            t = no[:2].upper()
            if not no or not d or d < since or (until and d > until) or t not in src["types"] or no in docs:
                continue
            if any(str(r.get(c) or "").strip().upper() in CANCEL_VALUES for c in m["cancel"]):
                continue
            cus = str(r.get(m["customer"]) or "").strip() if m["customer"] else ""
            docs[no] = {"doc_no": no, "type": t, "doc_date": d.isoformat(), "cuscod": cus,
                        "customer": names.get(cus) or cus, "total": round(abs(float(r.get(m["total"]) or 0)), 2),
                        "remain": round(float(r.get(m["remain"]) or 0), 2) if m["remain"] else None, "refs": []}
    for ln in LINKS:                                   # RE → IV ที่ตัดชำระ
        p = os.path.join(src_dir, ln["file"])
        if not os.path.exists(p):
            continue
        fn = {n for n, _, _ in dbf_fields(p)}
        rf, df = pick(fn, ln["receipt"]), pick(fn, ln["doc"])
        if not rf or not df or rf == df:
            continue
        for r in read_dbf(p, fields={rf, df}):
            re_no, iv = str(r.get(rf) or "").strip(), str(r.get(df) or "").strip()
            if re_no in docs and iv and iv not in docs[re_no]["refs"]:
                docs[re_no]["refs"].append(iv)
    return docs, used


# ---------- ส่ง ----------
def post(cfg, body):
    req = urllib.request.Request(cfg["API_URL"].rstrip("/") + "/push",
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Sales-Token": cfg["PUSH_TOKEN"]},
                                 method="POST")
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError("HTTP %s %s" % (e.code, e.read()[:200]))
        except (urllib.error.URLError, OSError) as e:
            if attempt == 3:
                raise
            log("  network retry %d (%s)" % (attempt, e))
            time.sleep(3 * attempt)


def digest(d):
    return hashlib.md5(json.dumps(d, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def run(cfg, dry=False, today=None):
    br = cfg["BRANCH"]
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=int(cfg["WINDOW_DAYS"]))
    if cfg.get("START_DATE"):
        since = max(since, datetime.date.fromisoformat(cfg["START_DATE"]))
    docs, used = read_docs(cfg["SRC"], since)
    if not used:
        raise SystemExit("ไม่เจอ ARTRN/ARRCPT ใน " + cfg["SRC"])
    sp = os.path.join(state_dir(), "state_%s.json" % br)
    try:
        with open(sp, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    seen = state.get("docs", {})
    full = time.time() - state.get("full_at", 0) > FULL_EVERY_S
    changed = [d for no, d in docs.items() if full or seen.get(no, {}).get("h") != digest(d)]
    # หายไปจาก Express (ลบ/ยกเลิก) — เฉพาะที่ยังอยู่ในหน้าต่างเวลา ไม่ใช่แค่เลื่อนหลุดหน้าต่าง
    gone = sorted(no for no, s in seen.items() if no not in docs and s.get("d", "") >= since.isoformat())
    log("%s: %d เอกสาร · เปลี่ยน %d · หายไป %d%s" % (br, len(docs), len(changed), len(gone),
                                                    " (FULL)" if full else "") + (" (DRY)" if dry else ""))
    if dry:
        for d in changed[:10]:
            log("  %s %s %s %.2f %s" % (d["doc_no"], d["type"], d["doc_date"], d["total"], d["customer"][:24]))
        return
    if not cfg.get("PUSH_TOKEN"):
        raise SystemExit("config missing PUSH_TOKEN")
    hb = {"docs": len(docs), "files": [f for f, _ in used], "host": os.environ.get("COMPUTERNAME", "")}
    for i in range(0, max(len(changed), 1), 400):
        post(cfg, {"branch": br, "docs": changed[i:i + 400], "gone": gone if i == 0 else [], "heartbeat": hb})
    state = {"docs": {no: {"h": digest(d), "d": d["doc_date"]} for no, d in docs.items()},
             "full_at": time.time() if full else state.get("full_at", 0)}
    tmp = sp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:     # ต้องปิดไฟล์ก่อน replace (Windows ล็อกไฟล์ที่เปิดอยู่)
        json.dump(state, f)
    os.replace(tmp, sp)


def inspect(cfg, day):
    for src in SOURCES:
        p = os.path.join(cfg["SRC"], src["file"])
        if not os.path.exists(p):
            print("%s: ไม่มีไฟล์" % src["file"])
            continue
        print("\n%s fields: %s" % (src["file"], ", ".join(n for n, _, _ in dbf_fields(p))))
        print("  ใช้: %s" % resolve(p, src))
    docs, _ = read_docs(cfg["SRC"], day, day)
    agg = {}
    for d in docs.values():
        n, s = agg.get(d["type"], (0, 0.0))
        agg[d["type"]] = (n + 1, s + d["total"])
    print("\n== %s %s (ไม่รวมใบยกเลิก) — เทียบกับฟอร์มเดิมของวันเดียวกัน ==" % (cfg["BRANCH"], day))
    for t in ("IV", "AI", "SR", "HS", "RE"):
        n, s = agg.get(t, (0, 0.0))
        print("  %-3s %4d ใบ  %14s" % (t, n, "{:,.2f}".format(s)))
    re_links = [d for d in docs.values() if d["type"] == "RE"]
    print("  RE ที่รู้ว่าตัด IV ใบไหน: %d / %d" % (sum(1 for d in re_links if d["refs"]), len(re_links)))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cfg = load_config(sys.argv[1])
    if "--inspect" in sys.argv:
        rest = [a for a in sys.argv[2:] if not a.startswith("--")]
        day = datetime.date.fromisoformat(rest[0]) if rest else datetime.date.today() - datetime.timedelta(days=1)
        inspect(cfg, day)
        return
    lock = os.path.join(state_dir(), "lock_%s.txt" % cfg["BRANCH"])
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 110:
        log("SKIP: previous run still active")
        return
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    try:
        run(cfg, dry="--dry" in sys.argv)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


if __name__ == "__main__":
    main()
