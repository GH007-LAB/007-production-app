# -*- coding: utf-8 -*-
"""
ชั้น A "เช็คไว" ฝั่งเซิร์ฟเวอร์ — อ่านรายการที่เซลจดไว้ (ภาษาหน้างาน) → รหัสสินค้า → ส่งเข้า grade_bill ตัวเดียวกับทุกชั้น
  "ลอน 0.30 ขาว MS 800 ม. 88"  "PU 25 ท้องไม้ 120 ม. 105"  "สกรู 75 มม. 2000 ตัว 2.5"
แมตช์ไม่ได้ = ไม่ฟันธง (ห้ามเดา) · ความมั่นใจ < 0.8 = ไม่ใช้บรรทัดนั้นคิดเกรด (HANDOVER ข้อ 5 ชั้น A)
catalog = [(code, desc, label, unit, sales90)] ต่อสาขา — สร้างอัตโนมัติจาก STKDES ของรหัสที่ขายจริง 90 วัน
"""
import re

MIN_CONFIDENCE = 0.8

SYN = [
    (r"ท้องไม้|ลายไม้|วอลนัท|ไม้", " ลายไม้ "), (r"ฟอยล์|ฟอยด์|foil", " ฟอยล์ "),
    (r"ซิ้ง|ซิงก์|ซิงค์|zinc|zi(?![a-z])", " ซิงค์ "), (r"สแน็ปล็อค|สแนปล็อค|snaplock|สแนป|sl(?![a-z])", " snaplock "),
    (r"คูล|cool", " cool "), (r"แซ็คส์|แซค|zacs", " zacs "), (r"จิงโจ้|jjl", " jjl "),
    (r"(?<![a-z])(ms|dmn|dm)(?![a-z])|ไดมอนด์|diamond|total|นำเข้า", " นำเข้า "),
    (r"(?<![a-z])pu(?![a-z])|พียู", " pu "), (r"สกรู", " สกรู "), (r"ครอบ", " ครอบ "),
]
# รุ่นลอน — ต้องตรงกันทั้งสองฝั่ง (ไม่ระบุ = แผ่นหลังคาปกติ) · ตรวจจากข้อความดิบ แยกจากการให้คะแนนคำ
PROFILE_RE = {"รั้ว": r"รั้ว", "ผนัง": r"ผนัง", "พาแนล": r"พาแนล", "ฝ้า": r"ฝ้า", "เวนิส": r"เวนิส",
              "สเปน": r"สเปน", "กันสาด": r"กันสาด", "snaplock": r"สแน็ปล็อค|สแนปล็อค|snaplock|สแนป",
              # อุปกรณ์ — ไม่พิมพ์ถึง = ไม่จับคู่ (เคยให้ "JJL 0.30 เทาเข้ม" กำกวมกับครอบข้าง/ครอบจั่วสีเดียวกัน)
              "ครอบ": r"ครอบ", "ราง": r"รางน้ำ|ราง", "บานเกล็ด": r"บานเกล็ด", "ปลอกเสา": r"ปลอกเสา",
              "เชิงชาย": r"เชิงชาย", "แผ่นใส": r"แผ่นใส"}


def profiles(s):
    t = (s or "").lower()
    return {k for k, rx in PROFILE_RE.items() if re.search(rx, t)}
COLORS = r"ขาว|แดง|น้ำเงิน|ฟ้า|เขียว|เทา|ครีม|ดำ|ส้ม|น้ำตาล|สี"
FLUFF = {"แผ่น", "ลอน", "เมทัลชีท", "หลังคา", "เมตร", "ม.", "ม", "มม.", "มม", "ตัว", "เส้น", "ท่อน", "k",
         "ราคา", "บาท", "บ.", "ละ", "ต่อ"}
UNIT_RE = re.compile(r"^(ม\.|ม|เมตร|แผ่น|ตัว|เส้น|ท่อน|ม้วน|ชิ้น|ถุง)$")
THK_RE = re.compile(r"0\.\d\d")
BRANDS = {"zacs", "cool", "jjl", "นำเข้า", "snaplock", "colorbond", "supergalum", "liger", "rooftech", "zincalume"}


def tokens(s, exclude_nums=()):
    t = " " + (s or "").lower() + " "
    for pat, rep in SYN:
        t = re.sub(pat, rep, t)
    has_color = bool(re.search(COLORS, t))
    t = re.sub(COLORS, " ", t)                     # สีไหนก็ได้ = "สี" (ต้นทุนคอยล์สีเดียวกันทั้งรุ่น)
    words = {w for w in re.split(r"[\s,/()\-]+", t) if len(w) > 1 and not w[0].isdigit() and w not in FLUFF}
    if has_color and "ซิงค์" not in words:
        words.add("สี")
    thk = THK_RE.search(s or "")
    nums = set(re.findall(r"(?<![\d.])(\d{2})(?:\s*(?:มม|mm|k))?(?![\d.])", (s or "").lower())) - set(exclude_nums)
    return words, (thk.group(0) if thk else None), nums


def parse_line(line):
    """คืน {text, qty, unit, price} · จำนวน = ตัวเลขที่มีหน่วย (ม./ตัว/แผ่น…) · ราคา = ตัวเลขเปล่าหลังจำนวน
    ความหนา 0.xx และตัวเลขสเปค (25 มม. / 35k) ไม่นับเป็นจำนวนหรือราคา · ไม่มีราคา = None"""
    s = (line or "").replace(",", "").strip()
    if not s:
        return None
    toks = [(m.group(1), m.group(2) or "", m.start()) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([ก-๙a-zA-Z.]*)", s)]
    toks = [t for t in toks if not THK_RE.fullmatch(t[0])]
    q = next((t for t in toks if UNIT_RE.match(t[1])), None)
    bare = [t for t in toks if t is not q and not t[1]]
    price = None
    tagged = re.search(r"(?:ราคา|@|ละ)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:บาท|บ\.)", s)
    if tagged:                                   # "ราคา 90" / "@90" / "90 บาท" = ราคาชัด ๆ
        price = float(tagged.group(1) or tagged.group(2))
    elif q:
        after = [t for t in bare if t[2] > q[2]]
        price = float(after[-1][0]) if after else None
    elif len(bare) >= 2:
        price = float(bare[-1][0])
    return {"text": s, "qty": float(q[0]) if q else None, "unit": q[1] if q else None, "price": price}


def _numstr(v):
    return "" if v is None else (str(int(v)) if float(v).is_integer() else str(v))


def _rank(line, catalog):
    """ให้คะแนนทุกรหัส → (qw, scored) · scored เรียงมาก→น้อย: (conf, -extra, sales, code, label|desc, fam_label, desc)"""
    p = parse_line(line) or {}
    qw, qthk, qnum = tokens(line, {_numstr(p.get("qty")), _numstr(p.get("price"))})
    if not qw:
        return qw, []
    qprof = profiles(line)
    scored = []
    for code, desc, label, unit, sales in catalog:
        cw, cthk, cnum = tokens(f"{label or ''} {desc or ''}")
        if qthk and cthk and qthk != cthk:
            continue
        if ("pu" in qw) != ("pu" in cw):
            continue
        if ("สี" in qw and "ซิงค์" in cw and "สี" not in cw) or ("ซิงค์" in qw and "สี" in cw and "ซิงค์" not in cw):
            continue
        if qprof != profiles(f"{label or ''} {desc or ''}"):   # รั้ว ≠ แผ่นหลังคา · ไม่ระบุรุ่น = ไม่จับคู่รุ่นพิเศษ
            continue
        hit, need = len(qw & cw), len(qw)
        if qthk:                                   # ความหนาตรงกันนับเป็นคำสำคัญ 1 คำ
            need += 1
            hit += 1 if cthk == qthk else 0
        if qnum:                                   # 25/35/75 มม. — ต้องมีในชื่อสินค้าถึงนับ
            need += 1
            hit += 1 if (qnum & cnum) else 0
        # คำในชื่อสินค้าที่ลูกค้าไม่ได้พูดถึงเลย (เช่น zacs/cool) = เสียคะแนนเล็กน้อย ให้ตัวที่ตรงกว่าชนะ
        extra = len({w for w in cw if w in BRANDS} - qw)
        scored.append((hit / need if need else 0.0, -extra, sales or 0, code, label or desc, label, desc or ""))
    scored.sort(reverse=True)
    return qw, scored


def _color_words(line):
    """คำสีที่เซลพิมพ์ทั้งคำ (เช่น "แดงอิฐ" ไม่ใช่แค่ "แดง") — ไม่นับคำว่า "สี" เฉย ๆ"""
    return [w for w in re.split(r"[\s,/()]+", (line or "").replace("\xa0", " ")) if re.search(COLORS, w) and w != "สี"]


def _tied(qw, scored):
    conf, extra, _, code, label = scored[0][:5]
    named_brand = bool(qw & BRANDS)   # ไม่ระบุยี่ห้อเลย = ห้ามใช้ตัวตัดสินเสมอ เลือกยี่ห้อแทนเซลไม่ได้
    rivals = [x for x in scored[1:] if x[0] == conf and x[4] != label and (x[1] == extra or not named_brand)]
    return conf, rivals


def _color_only_variants(group):
    """ต่างกันแค่สี: ไม่มีกลุ่มราคา (สกรู/อุปกรณ์ — ทุนแต่ละสีไม่เท่ากัน) และรหัสต่างกันแค่ช่องเดียว
    เช่น 04S-75-WA#12 / 04S-75-ZI#12 (ดูจากรหัส ไม่ใช่ชื่อ — ชื่อใน Express เว้นวรรคไม่สม่ำเสมอ)"""
    if len(group) < 2 or any(x[5] for x in group):
        return False
    parts = [x[3].split("-") for x in group]
    if len({len(p) for p in parts}) != 1:
        return False
    diff = [i for i in range(len(parts[0])) if len({p[i] for p in parts}) > 1]
    return len(diff) == 1


def match(line, catalog):
    """คืน (code, label, confidence) ของรหัสที่ใกล้ที่สุด หรือ (None, None, conf) ถ้าไม่ถึงเกณฑ์
    สินค้าต่างกลุ่มได้คะแนนเท่ากัน = กำกวม → ไม่ฟันธง (ไม่เลือกตามยอดขาย)
    ยกเว้นรหัสที่ต่างกันแค่สี (สกรู ฯลฯ): ใช้สีที่เซลพิมพ์ตัดสิน ถ้าตรงตัวเดียว"""
    qw, scored = _rank(line, catalog)
    if not scored:
        return None, None, 0.0
    conf, rivals = _tied(qw, scored)
    code, label = scored[0][3], scored[0][4]
    if conf >= MIN_CONFIDENCE and not rivals:
        return code, label, round(conf, 2)
    group = [scored[0]] + rivals
    cols = _color_words(line)
    if conf >= MIN_CONFIDENCE and cols and _color_only_variants(group):
        pick = [x for x in group if all(c in x[6] for c in cols)]
        if len(pick) == 1:
            return pick[0][3], pick[0][4], round(conf, 2)
    return None, None, round(conf, 2)


def needs_color(line, catalog):
    """จับคู่ไม่ได้เพราะรหัสต่างกันแค่สี (ทุนไม่เท่ากัน) และเซลยังไม่ได้ระบุสีที่ชี้ตัวเดียว → บอกให้ระบุสี"""
    qw, scored = _rank(line, catalog)
    if not scored:
        return False
    conf, rivals = _tied(qw, scored)
    return bool(rivals) and conf >= MIN_CONFIDENCE and _color_only_variants([scored[0]] + rivals)


def item_name(text):
    """ชื่อสินค้าตามที่เซลพิมพ์ (ตัดจำนวน/หน่วย/ราคาท้ายบรรทัด) — ใช้ลงใบเสนอราคา
    ห้ามใช้ชื่อรหัสที่จับคู่ได้: จับคู่ระดับกลุ่มราคา (ทุกสีราคาเดียว) รหัสตัวแทนอาจคนละสีกับที่ลูกค้าสั่ง"""
    s = (text or "").strip()
    toks = [m for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([ก-๙a-zA-Z.]*)", s) if not THK_RE.fullmatch(m.group(1))]
    q = next((m for m in toks if UNIT_RE.match(m.group(2) or "")), None)
    tagged = re.search(r"(?:ราคา|@|ละ)\s*\d|\d+(?:\.\d+)?\s*(?:บาท|บ\.)", s)
    if q:
        cut = q.start()
    elif tagged:
        cut = tagged.start()
    else:
        bare = [m for m in toks if not m.group(2)]
        cut = bare[-1].start() if bare else len(s)
    name = re.sub(r"\s*(?:ราคา|@|ละ)\s*$", "", s[:cut].strip(" -,:"))
    return name.strip(" -,:") or s


def quick_lines(text_lines, catalog, price_of_unknown=None):
    """แปลงข้อความหลายบรรทัด → ([lines สำหรับ grade_bill], [รายงานต่อบรรทัดให้เซลเห็น])"""
    lines, view = [], []
    info = {c[0]: (c[1], c[3]) for c in catalog}   # code → (ชื่อสินค้า, หน่วยใน Express) ใช้ต่อใบเสนอราคา (ไม่มีทุน)
    for raw in text_lines:
        p = parse_line(raw)
        if not p:
            continue
        code, label, conf = match(p["text"], catalog)
        desc, cat_unit = info.get(code, (None, None))
        view.append({"text": p["text"], "code": code, "label": label, "confidence": conf,
                     "qty": p["qty"], "unit": p["unit"], "price": p["price"], "matched": bool(code),
                     "desc": desc, "cat_unit": cat_unit, "name": item_name(p["text"]),
                     "hint": "ระบุสี" if not code and needs_color(p["text"], catalog) else None})
        qty = p["qty"] or 1
        if code and p["price"] is not None:
            lines.append({"code": code, "qty": qty, "price": p["price"]})
        elif p["price"] is not None:
            lines.append({"code": "?", "qty": qty, "price": p["price"]})   # นับเข้ายอด แต่ไม่รู้ทุน → กด coverage
    return lines, view
