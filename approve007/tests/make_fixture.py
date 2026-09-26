# -*- coding: utf-8 -*-
"""สร้าง All_on_Cloud จำลอง (DBF รูปแบบเดียวกับ Express + costbook_rules + ใบราคา) สำหรับทดสอบ
ตัวเลขใบราคา/ใบคอยล์คัดจากไฟล์จริง 260907 / 260901 · ทุนจาก costbook.js 26/09/2569 · รหัสสินค้าเป็นรหัสตัวอย่าง"""
import base64
import datetime
import json
import os
import struct
import sys


def write_dbf(path, fields, rows):
    """fields = [(name, type C/N/D, len, dec)] · เขียน dBase III แบบง่ายด้วย cp874"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    reclen = 1 + sum(f[2] for f in fields)
    hdrlen = 32 + 32 * len(fields) + 1
    t = datetime.date.today()
    with open(path, "wb") as f:
        f.write(struct.pack("<BBBBIHH20x", 3, t.year - 1900, t.month, t.day, len(rows), hdrlen, reclen))
        for name, typ, ln, dec in fields:
            f.write(struct.pack("<11sc4xBB14x", name.encode(), typ.encode(), ln, dec))
        f.write(b"\r")
        for r in rows:
            f.write(b" ")
            for name, typ, ln, dec in fields:
                v = r.get(name)
                if typ == "N":
                    s = ("" if v is None else f"{v:.{dec}f}").rjust(ln).encode()
                elif typ == "D":
                    s = (v.strftime("%Y%m%d") if v else "").ljust(8).encode()
                else:
                    s = (v or "").encode("cp874")[:ln].ljust(ln)
                f.write(s)
        f.write(b"\x1a")


STMAS_F = [("STKCOD", "C", 20, 0), ("STKDES", "C", 50, 0), ("SQUCOD", "C", 6, 0), ("QUCOD", "C", 6, 0),
           ("SELLPR1", "N", 12, 2), ("STKGRP", "C", 4, 0)]
OESOIT_F = [("SONUM", "C", 12, 0), ("SODAT", "D", 8, 0), ("STKCOD", "C", 20, 0), ("STKDES", "C", 50, 0),
            ("ORDQTY", "N", 12, 2), ("UNITPR", "N", 12, 2), ("TRNVAL", "N", 14, 2), ("TFACTOR", "N", 8, 2)]
OESO_F = [("SONUM", "C", 12, 0), ("SLMCOD", "C", 10, 0)]
EMPTY_F = [("STKCOD", "C", 20, 0)]

PRODUCTS = [  # code, desc, unit, sellpr1
    ("01A-WA-035-ZC", "แผ่นหลังคา Zacs Cool 0.35 ขาว", "ม.", 0),
    ("01A-RD-035-ZC", "แผ่นหลังคา Zacs Cool 0.35 แดง", "ม.", 0),
    ("01A-ZI-035-JJL", "แผ่นหลังคา JJL ซิงค์ 0.35", "ม.", 0),
    ("01A-RD-035-JJL", "แผ่นหลังคา JJL สีแดง 0.35", "ม.", 0),
    ("01A-BL-030-MS", "แผ่นหลังคา นำเข้า สี 0.30 MS", "ม.", 0),
    ("03VP-PU2525FOILWALNU", "PU 25มม. 25K ท้องไม้วอลนัท", "ม.", 0),
    ("03VP-PU2525FOIWHITE", "PU 25มม. 25K ท้องฟอยล์ขาว", "ม.", 0),
    ("03VP-PUSL2525FOIL", "สแน็ปล็อค PU 25มม. 25K ฟอยล์", "ม.", 0),
    ("04S-75-DOME", "สกรูปลายสว่าน 75 มม.", "ตัว", 3.5),
    ("04S-16-HEX", "สกรูหัวหกเหลี่ยม 16 มม.", "ตัว", 1.2),
    ("02KK-457-AW-035-ZC", "ครอบข้าง 457 Zacs Cool 0.35", "เส้น", 0),
    ("07ETC-FOLD", "งานพับตามแบบ", "ม.", 0),
    ("09X-UNKNOWN", "สินค้าไม่มีทุน", "ชิ้น", 0),
]

COST = {  # ทุนรวม VAT (หน่วยสต็อก) — ของแต่ละสาขาเท่ากันเพื่อความง่าย
    "01A-WA-035-ZC": 131.6, "01A-RD-035-ZC": 131.6, "01A-ZI-035-JJL": 101.1, "01A-RD-035-JJL": 110.2,
    "01A-BL-030-MS": 60.2, "04S-75-DOME": 2.78, "04S-16-HEX": 0.52,
}
PREFIX = [["03VP-PU2525FOILWALNU", 72.8, 120], ["03VP-PU2525FOIWHITE", 69.6, 115],
          ["03VP-PUSL2525", 37.3, 74], ["02KK-457-AW-035-ZC", 70.0, 95], ["07ETC", 45.0, None]]


def sales_rows(branch, today):
    d = today - datetime.timedelta(days=5)
    rows = []

    def add(so, code, qty, pr, day=d):
        desc = next(p[1] for p in PRODUCTS if p[0] == code)
        rows.append({"SONUM": so, "SODAT": day, "STKCOD": code, "STKDES": desc, "ORDQTY": qty,
                     "UNITPR": pr, "TRNVAL": round(qty * pr, 2), "TFACTOR": 1})
    n = 6800000
    for i, code in enumerate([p[0] for p in PRODUCTS if p[0] not in ("09X-UNKNOWN",)]):
        pr = {"04S-75-DOME": 3.5, "04S-16-HEX": 1.2}.get(code, 150)
        for k in range(9):                                   # ≥ 8 บิล/60 วัน ให้บางตัวเป็นหมุนเร็ว
            add(f"SO{n + i * 10 + k}", code, 100, pr)
    add("SO6812345", "09X-UNKNOWN", 1, 50)
    if branch == "PPS":
        add("SO6903141", "01A-WA-035-ZC", 800, 125)
        add("SO6903141", "04S-75-DOME", 2000, 2.50)
        add("SO6903141", "03VP-PU2525FOILWALNU", 300, 100)
    if branch == "SKN":
        add("SO6903141", "01A-ZI-035-JJL", 200, 110)          # เลข SO ซ้ำข้ามสาขาได้จริง
        add("SO6904651", "03VP-PUSL2525FOIL", 340, 148)
    return rows


def make(root):
    today = datetime.date.today()
    aoc = os.path.join(root, "My Drive (007skn0777@gmail.com)", "All_on_Cloud")
    ae = os.path.join(aoc, "AutoExport")
    for br in ("BK", "SKN", "PPS"):
        write_dbf(os.path.join(ae, br, "STMAS.DBF"), STMAS_F,
                  [{"STKCOD": c, "STKDES": d, "SQUCOD": u, "QUCOD": u, "SELLPR1": s, "STKGRP": c[:2]} for c, d, u, s in PRODUCTS])
        sr = sales_rows(br, today)
        write_dbf(os.path.join(ae, br, "OESOIT.DBF"), OESOIT_F, sr)
        write_dbf(os.path.join(ae, br, "OESO.DBF"), OESO_F,
                  [{"SONUM": so, "SLMCOD": ("S01" if i % 3 else "")} for i, so in enumerate(sorted({r["SONUM"] for r in sr}))])
        for n in ("STCRD.DBF", "POPRIT.DBF"):
            write_dbf(os.path.join(ae, br, n), EMPTY_F, [])
    rules = {"updated": today.isoformat(), "vat": 1.07,
             "pins": {"7007": {"role": "GEM", "name": "Gem"}},     # ของจริงมี PIN ในไฟล์ — engine ต้องตัดทิ้ง
             "prefix": PREFIX, "exact": {br: dict(COST) for br in ("BK", "SKN", "PPS")},
             "exact_any": {}, "fast": ["04S-75-DOME", "04S-16-HEX"],
             "chance": [[35, 100], [20, 75], [10, 50], [0, 25]], "chance_fast": [[30, 100], [15, 75], [10, 50], [0, 25]]}
    os.makedirs(os.path.join(ae, "scripts"), exist_ok=True)
    with open(os.path.join(ae, "scripts", "costbook_rules.json"), "w") as f:
        json.dump({"v": 2, "data": base64.b64encode(json.dumps(rules, ensure_ascii=False).encode()).decode()}, f)
    for d in ("Live", "agent_status"):
        os.makedirs(os.path.join(ae, d), exist_ok=True)

    import openpyxl
    pf = os.path.join(root, "My Drive (007skn0777@gmail.com)", "0. ใบประเมินราคาเหล็ก")
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["NO.", "สี และ แบรนด์สินค้า", "ความหนารวมชั้นเคลือบ มม.", "ชนิดเหล็กและชั้นเคลือบ", "เรทราคา/หน่วย"])
    data = [
        (4, "อลูซิงค์", "0.30 JJL", "จิงโจ้เหล็ก AZ70", [109, 111, 112, 113, 114]),
        (5, None, "0.35 JJL", "จิงโจ้เหล็ก AZ70 โปรโมชั่น", [110, 112, 113, 114, 115]),
        (7, None, "0.35 Zacs", "BLUESCOPE Zacs AZ90", [135, 137, 138, 139, 140]),
        (12, "รุ่นสี จิงโจ้เหล็ก JJL", "0.35 JJL", "จิงโจ้เหล็ก AZ70 สี", [110, 112, 113, 114, 115]),
        (14, "สี Bluescope Zacs Cool(สีเงา) Dazzle(สีมุก) Natural(สีด้าน)", "0.35 Cool", "Zacs Cool AZ90", [153, 155, 156, 157, 158]),
        (47, "สี เหล็กต่างประเทศ", "0.30", "เหล็กนำเข้า AZ20-70", [78, 80, 81, 82, 83]),
        (55, "ลอนมาตรฐาน 760 ฉนวนกันความร้อน PU FOAM", "25mm / 25k", "ฟอยล์สีเงิน / ฟอยล์สีดำ / ฟอยล์สีขาว มาตรฐาน", [115, 115, 115, 120, 120]),
        (56, None, "25mm / 25k", "ไม้วอลนัทเข้ม / ไม้วอลนัทอ่อน / ฟอยล์หินอ่อนขาว มาตรฐาน", [120, 120, 120, 125, 125]),
        (61, "ลอนสแนปล็อค 310 ฉนวนกันความร้อน PU FOAM", "25mm / 25k", "ฟอยล์สีเงิน / ฟอยล์สีดำ / ฟอยล์สีขาว มาตรฐาน", [74, 74, 74, 79, 79]),
    ]
    for no, sec, thk, spec, rates in data * 2:      # ใบจริงพิมพ์ตารางซ้ำ 2 ชุด
        ws.append([no, sec, thk, spec] + rates)
    os.makedirs(os.path.join(pf, "ใบราคาขายแผ่น"), exist_ok=True)
    wb.save(os.path.join(pf, "ใบราคาขายแผ่น", "ใบราคาขายแผ่น260601.xlsx"))
    ws.cell(row=6, column=5, value=999)   # ใบเก่ากว่าต้องไม่ถูกใช้
    wb.save(os.path.join(pf, "ใบราคาขายแผ่น", "ใบราคาขายแผ่น260907.xlsx"))
    # ใบ 260907 = ค่าที่ถูก · ใส่ค่า 999 เข้า 260601 แทน เพื่อจับบั๊กเลือกใบผิด
    wb2 = openpyxl.load_workbook(os.path.join(pf, "ใบราคาขายแผ่น", "ใบราคาขายแผ่น260907.xlsx"))
    wb2.active.cell(row=6, column=5, value=153); wb2.save(os.path.join(pf, "ใบราคาขายแผ่น", "ใบราคาขายแผ่น260907.xlsx"))
    wb3 = openpyxl.load_workbook(os.path.join(pf, "ใบราคาขายแผ่น", "ใบราคาขายแผ่น260601.xlsx"))
    wb3.active.cell(row=6, column=5, value=999); wb3.save(os.path.join(pf, "ใบราคาขายแผ่น", "ใบราคาขายแผ่น260601.xlsx"))

    cb = openpyxl.Workbook(); cs = cb.active
    cs.append(["ราคาต้นทุนขั้นต้น"])
    cs.append(["NO", "THICKNESS", "WIDTH", "Weight/Length"])
    cs.append([1, "คอยล์ อลูซิงค์ รุ่นซิงค์ จิงโจ้เหล็ก (Jing Joe Lek)"])
    cs.append([6, "0.35 JJL มอก.", 914, 2.40, "G550", "AZ70", "ซิงค์", 48.10, 38.40, 41.09, 98.61])
    cs.append([7, "คอยล์ อลูซิงค์ รุ่นสี จิงโจ้เหล็ก (Jing Joe Lek)"])
    cs.append([9, "0.35 JJL มอก.", 914, 2.39, "G550", "AZ70", "สีทัวไป", 49.60, 42.10, 45.05, 107.66])
    cs.append([19, "คอยล์ อลูซิงค์ รุ่นสี บลูสโคป แซ็คส์ คูล (Bluescope Zacs Cool/Natural)"])
    cs.append([21, "0.35 Cool/Natural", 914, 2.32, "G550", "AZ70", "สีทัวไป", 57.50, 52.00, 55.64, 129.08])
    cs.append([21, "0.35 Cool/Natural", 914, 2.32, "G550", "AZ90", "สีทัวไป", 57.50, 53.00, 56.71, 131.57])
    os.makedirs(os.path.join(pf, "ประเมินราคาคอยล์", "2569"), exist_ok=True)
    cb.save(os.path.join(pf, "ประเมินราคาคอยล์", "2569", "ใบต้นทุนราคาขายคอยล์260901.xlsx"))
    return aoc


if __name__ == "__main__":
    print(make(sys.argv[1] if len(sys.argv) > 1 else "/tmp/a7fixture"))
