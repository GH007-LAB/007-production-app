# -*- coding: utf-8 -*-
"""
007 Metals - SO Push (Production Process realtime feed)
อ่าน SO ใหม่/ที่เปลี่ยนจาก DBF ของ Express ที่ต้นทาง -> upsert ตรงเข้า Supabase
ออกแบบให้รันบนเครื่องสาขาผ่าน Task Scheduler ทุก 2 นาที (zero-dependency, pure Python 3)

usage:  python so_push.py <config_file> [--dry]
        --dry = อ่าน+เทียบ delta อย่างเดียว ไม่ยิงขึ้น Supabase (ทดสอบ)

config file (KEY=VALUE):
  BRANCH=SKN
  SRC=Z:\\skn2569
  SUPABASE_URL=https://xxxx.supabase.co
  SUPABASE_KEY=eyJ...        (anon key เท่านั้น — ห้ามใช้ service_role)
  WINDOW_DAYS=45             (มองย้อน SO กี่วัน)

state/log เก็บที่ %LOCALAPPDATA%\\007so_push\\ (ไม่ปนโฟลเดอร์ Drive)
"""
import sys, os, struct, json, datetime, hashlib, urllib.request, urllib.error, time

# ---------- pure-python DBF reader (โครงเดียวกับ sopo_live_feeder.py ที่พิสูจน์แล้ว) ----------
def read_dbf(path, fields=None, encoding="cp874"):
    with open(path, "rb") as f:
        hdr = f.read(32)
        nrec = struct.unpack("<I", hdr[4:8])[0]
        hdrlen = struct.unpack("<H", hdr[8:10])[0]
        reclen = struct.unpack("<H", hdr[10:12])[0]
        fdefs = []
        nfields = (hdrlen - 33) // 32
        for _ in range(nfields):
            fd = f.read(32)
            if fd[0:1] == b"\r":
                break
            name = fd[0:11].split(b"\x00")[0].decode("ascii", "replace")
            ftype = fd[11:12].decode("ascii", "replace")
            flen = fd[16]
            fdefs.append((name, ftype, flen))
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
                elif ftype == "B":         # VFP double (8-byte LE)
                    row[name] = struct.unpack("<d", raw)[0] if len(raw) == 8 else 0.0
                elif ftype == "I":         # VFP int32
                    row[name] = struct.unpack("<i", raw)[0] if len(raw) == 4 else 0
                elif ftype == "Y":         # VFP currency
                    row[name] = struct.unpack("<q", raw)[0] / 10000.0 if len(raw) == 8 else 0.0
                elif ftype == "D":
                    s = raw.strip()
                    if len(s) == 8 and s.isdigit():
                        try:
                            row[name] = datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
                        except ValueError:
                            row[name] = None
                    else:
                        row[name] = None
                else:
                    row[name] = raw.decode(encoding, "replace").strip()
            yield row

# ---------- helpers ----------
def log(msg):
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

def load_config(path):
    cfg = {"WINDOW_DAYS": "45"}
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
    return cfg

def state_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "007so_push")
    os.makedirs(d, exist_ok=True)
    return d

def d2s(d):
    return d.isoformat() if isinstance(d, datetime.date) else None

# ---------- Supabase REST (urllib, no deps) ----------
def sb_request(cfg, method, path, payload=None, prefer=None):
    url = cfg["SUPABASE_URL"].rstrip("/") + path
    headers = {
        "apikey": cfg["SUPABASE_KEY"],
        "Authorization": "Bearer " + cfg["SUPABASE_KEY"],
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            body = e.read()[:300]
            raise RuntimeError("HTTP %s %s %s -> %s %s" % (method, path[:60], e.code, e.reason, body))
        except (urllib.error.URLError, OSError) as e:
            if attempt == 3:
                raise
            log("  network retry %d (%s)" % (attempt, e))
            time.sleep(3 * attempt)

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ---------- main ----------
def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cfg = load_config(sys.argv[1])
    dry = ("--dry" in sys.argv) or not cfg.get("SUPABASE_URL") or not cfg.get("SUPABASE_KEY")
    branch = cfg["BRANCH"]
    src = cfg["SRC"]
    window = int(cfg["WINDOW_DAYS"])
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=window)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ---- lock กันรันซ้อน ----
    lock = os.path.join(state_dir(), "lock_%s.txt" % branch)
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 170:
        log("SKIP: previous run still active")
        return
    open(lock, "w").write(str(os.getpid()))

    try:
        if not os.path.exists(os.path.join(src, "OESO.DBF")):
            raise SystemExit("source not found: " + src)

        # ---- อ่านชื่อลูกค้า ----
        names = {}
        for r in read_dbf(os.path.join(src, "ARMAS.DBF"), fields={"CUSCOD", "PRENAM", "CUSNAM"}):
            names[r.get("CUSCOD", "")] = (r.get("PRENAM", "") + " " + r.get("CUSNAM", "")).strip()

        # ---- อ่าน SO header ในหน้าต่างเวลา ----
        heads = {}
        for r in read_dbf(os.path.join(src, "OESO.DBF"),
                          fields={"SONUM", "SODAT", "DLVDAT", "CUSCOD", "SLMCOD",
                                  "NETAMT", "DOCSTAT", "YOUREF"}):
            sod = r.get("SODAT")
            if not sod or sod < cutoff:
                continue
            so = (r.get("SONUM") or "").strip()
            if not so:
                continue
            cus = (r.get("CUSCOD") or "").strip()
            heads[so] = {
                "branch": branch, "sonum": so,
                "sodat": d2s(sod), "dlvdat": d2s(r.get("DLVDAT")),
                "cuscod": cus, "cusnam": names.get(cus, cus) or cus,
                "slmcod": (r.get("SLMCOD") or "").strip(),
                "netamt": round(float(r.get("NETAMT") or 0), 2),
                "docstat": (r.get("DOCSTAT") or "").strip(),
                "youref": (r.get("YOUREF") or "").strip(),
            }

        # ---- 🧾 อ่านบิลขาย (IV/AI) → map SO -> เลข IV (v9.8: ยืนยันจากคลัง Finny R65 8/7/2569) ----
        # Express เก็บเอกสารขายใน ARTRN.DBF: DOCNUM ขึ้นต้น IV=ใบกำกับ · AI=ขายสด/มัดจำ
        # รายการบิลอยู่ ARTRNIT.DBF — แถวที่ดึงจาก SO จะอ้างเลข SO (SONUM) → ใช้ map
        # fallback: header ARTRN ใช้ SONUM/YOUREF · ไฟล์ชื่ออื่น (รุ่นเก่า) ลอง OEIV/OEIVIT
        so_iv = {}
        def _collect_iv(fp, num_keys):
            n0 = len(so_iv)
            for r in read_dbf(fp, fields={"DOCNUM", "IVNUM", "SONUM", "YOUREF"}):
                iv = ""
                for k in num_keys:
                    iv = (r.get(k) or "").strip()
                    if iv:
                        break
                if not iv or iv[:2] not in ("IV", "AI"):
                    continue
                so_ref = (r.get("SONUM") or "").strip() or (r.get("YOUREF") or "").strip()
                if so_ref in heads:
                    so_iv.setdefault(so_ref, set()).add(iv)
            return len(so_iv) - n0
        for f in ("ARTRNIT.DBF", "ARTRN.DBF", "OEIVIT.DBF", "OEIV.DBF"):
            fp = os.path.join(src, f)
            if not os.path.exists(fp):
                continue
            try:
                got = _collect_iv(fp, ("DOCNUM", "IVNUM"))
                log("IV source: %s (+%d SO matched, total %d)" % (f, got, len(so_iv)))
                if so_iv:
                    break        # ได้ mapping จากไฟล์รายการแล้ว ไม่ต้องอ่าน header ซ้ำ
            except Exception as e:
                log("IV read skip %s: %s" % (f, e))
        if not so_iv:
            log("IV mapping ว่าง — เช็คว่ามี ARTRN/ARTRNIT ใน %s (แจ้ง Claude ถ้าไฟล์ชื่ออื่น)" % src)
        for so, ivs in so_iv.items():
            heads[so]["ivnum"] = ",".join(sorted(ivs))

        # ---- อ่านรายการ (seq = ลำดับแถวต่อเอกสารตามตำแหน่งไฟล์ — convention เดียวกับ gen_sopo) ----
        items = {}
        for r in read_dbf(os.path.join(src, "OESOIT.DBF"),
                          fields={"SONUM", "STKCOD", "STKDES", "ORDQTY", "REMQTY", "TQUCOD"}):
            so = (r.get("SONUM") or "").strip()
            if so not in heads:
                continue
            L = items.setdefault(so, [])
            L.append({
                "branch": branch, "sonum": so, "seq": len(L) + 1,
                "stkcod": (r.get("STKCOD") or "").strip(),
                "stkdes": (r.get("STKDES") or "").strip(),
                "ordqty": round(float(r.get("ORDQTY") or 0), 2),
                "remqty": round(float(r.get("REMQTY") or 0), 2),
                "unit": (r.get("TQUCOD") or "").strip(),
            })

        # ---- delta เทียบ state ----
        state_file = os.path.join(state_dir(), "state_%s.json" % branch)
        try:
            state = json.load(open(state_file, encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        changed = []
        for so, h in heads.items():
            fp = hashlib.md5(json.dumps([h, items.get(so, [])],
                                        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if state.get(so) != fp:
                changed.append((so, fp))
        log("%s: %d SO in window, %d changed%s" %
            (branch, len(heads), len(changed), " (DRY)" if dry else ""))

        if not changed:
            return
        if dry:
            for so, _ in changed[:10]:
                log("  would push %s %s (%d items)" %
                    (so, heads[so]["cusnam"][:24], len(items.get(so, []))))
            if len(changed) > 10:
                log("  ... +%d more" % (len(changed) - 10))
            return

        # ---- push: header upsert เป็น batch ----
        # DB เก่าที่ยังไม่รัน migration (ไม่มีคอลัมน์ ivnum) → ตัด ivnum ทิ้งแล้วส่งใหม่ ห้าม sync ล่มทั้งกระดาน
        for batch in chunks([dict(heads[so], synced_at=now_iso) for so, _ in changed], 200):
            try:
                sb_request(cfg, "POST", "/rest/v1/so_live?on_conflict=branch,sonum",
                           batch, prefer="resolution=merge-duplicates,return=minimal")
            except Exception as e:
                if "ivnum" not in str(e):
                    raise
                log("DB ยังไม่มีคอลัมน์ ivnum (รัน migration v8.4 section 8) — ส่งแบบไม่มี ivnum ไปก่อน")
                slim = [{k: v for k, v in row.items() if k != "ivnum"} for row in batch]
                sb_request(cfg, "POST", "/rest/v1/so_live?on_conflict=branch,sonum",
                           slim, prefer="resolution=merge-duplicates,return=minimal")

        # ---- push: items — ลบชุดเก่าของ SO ที่เปลี่ยน (กันแถวที่ถูกลบใน Express ค้าง) แล้ว insert ใหม่ ----
        for batch in chunks([so for so, _ in changed], 40):
            solist = ",".join('"%s"' % s for s in batch)
            sb_request(cfg, "DELETE",
                       "/rest/v1/so_item_live?branch=eq.%s&sonum=in.(%s)" % (branch, solist))
        all_items = [it for so, _ in changed for it in items.get(so, [])]
        for batch in chunks([dict(it, synced_at=now_iso) for it in all_items], 500):
            sb_request(cfg, "POST", "/rest/v1/so_item_live?on_conflict=branch,sonum,seq",
                       batch, prefer="resolution=merge-duplicates,return=minimal")

        # ---- สำเร็จ -> บันทึก state ----
        for so, fp in changed:
            state[so] = fp
        # ตัด state ของ SO ที่หลุดหน้าต่างเวลาแล้ว (กันไฟล์โต)
        state = {so: fp for so, fp in state.items() if so in heads or len(state) < 5000}
        json.dump(state, open(state_file, "w", encoding="utf-8"))
        log("pushed %d SO (%d item rows) OK" % (len(changed), len(all_items)))
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass

if __name__ == "__main__":
    main()
