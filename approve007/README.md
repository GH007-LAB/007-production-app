# Approve007 — "ขายได้เลยไหม" (P-17 เกรดบิล)

แอปตรวจบิลและเช็คราคาขายของทีมขาย 3 สาขา (BK / SKN / PPS)
เซลเห็นแค่ **ชั้นราคา / เกรดบิล / โอกาสอนุมัติ** และไม่เห็นทุนหรือ GP เลย
ชื่อตั้งให้เข้าชุดเดียวกับ Quote007 · Sales007 · HR007

สเปค: `007 Project Map/P-17_เกรดบิล/` → `HANDOVER_P17_PriceBands_Trial.md` (เฟส 0.5 · ทำก่อน) · `HANDOVER_CheckBill_v2.md` (v2.3) · `P17_CheckBill_Charter.md` (v1.1)

## เชื่อมกับ All_on_Cloud ยังไง

```
Google Drive 007skn0777
├── 0. ใบประเมินราคาเหล็ก/            ← build อ่าน: ใบราคาขายแผ่น<ล่าสุด>.xlsx (Rate 1–5) · ใบต้นทุนราคาขายคอยล์<ล่าสุด>.xlsx
├── All_on_Cloud/
│   ├── AutoExport/{BK,SKN,PPS}/*.DBF  ← build อ่าน (read-only): OESOIT · OESO · STMAS
│   ├── AutoExport/scripts/costbook_rules.json  ← ทุน v0.4 ตัวเดียวกับ checkso.py (dealscore.py rules อัปเดตทุกวัน)
│   ├── AutoExport/scripts/approve007/ ← โค้ดที่ Mac mini รัน (install_macmini.sh ก๊อปมา + MD5SUMS)
│   ├── AutoExport/agent_status/pricebands_latest.json  ← build เขียน: สถานะให้ Exec Brief อ่าน
│   └── Approve007/                    ← build เขียน: ของที่เซลเปิดได้ (ไม่มีทุน)
│       ├── approve007.html            ← เปิดจากเครื่องสาขาผ่าน Drive (เหมือน Quote007)
│       ├── pricebands.js              ← ขอบราคาแต่ละชั้นเท่านั้น (build assert ว่าไม่มีทุน/GP ก่อนเขียน)
│       ├── ช่วงราคา_<สาขา>_<YYMMDD>.pdf ← ตาราง A4 พิมพ์ขาวดำ
│       └── _backup/                   ← สำรองไฟล์เดิมทุกครั้งก่อนเขียนทับ
└── 007 Project Map/P-17_เกรดบิล/trial/ ← รายงานที่มีทุน (Rate 1 ต่ำกว่าเป้า GP · baseline) → ผบ./CTO เท่านั้น
```

## โครงสร้าง

| ไฟล์ | ทำอะไร |
|---|---|
| `engine/approve_engine.py` | **สมองก้อนเดียว**: ลำดับทุน v0.4 · สูตรช่วงราคา P(g)=ทุน÷(1−g) · เกรดบิล A/B/C/D/X ตามสเปคข้อ 5.5 · ตัดข้อมูลตามสิทธิ์ SALES/MGR/GEM |
| `engine/build.py` | preflight · สร้างช่วงราคา + PDF + รายงาน ผบ. + status · `verify` (เคส DoD) · `check SO สาขา` · `backtest` |
| `engine/pricesheet.py` | อ่านใบราคาขายแผ่น / ใบต้นทุนคอยล์ (เลือกใบที่เลข YYMMDD ใหม่สุดเอง) |
| `engine/config/families.json` | แผนที่ STKCOD ↔ แถวในใบราคา ↔ แถวใบคอยล์ (**ต้องตรวจกับรหัสจริง** ดูข้อ 2 ด้านล่าง) |
| `engine/config/POLICY_TAGS.json` | ร่างป้ายเงื่อนไข · ทุกป้ายยังเป็น TO-CONFIRM จนกว่า ผบ. จะเคาะ |
| `app/approve007.html` | หน้าเว็บเซล: 💰 ช่วงราคา (พิมพ์ราคา → สีเปลี่ยนตามชั้น) · ⚡ เช็คไว (พิมพ์รายการจากสมุด) |
| `tests/` | `make_fixture.py` (All_on_Cloud จำลอง) · `test_engine.py` (21 เทส) · `test_app.mjs` (Chromium) |

## ติดตั้งบน Mac mini (ทำตามลำดับ)

```bash
cd <clone ของ 007-production-app>
bash approve007/engine/launchd/install_macmini.sh
```
สคริปต์นี้ทำ 5 อย่าง: ก๊อปโค้ด → ติดตั้ง launchd 06:30 → `preflight` → `--inspect` → build รอบแรก → `verify`

1. **PRE-FLIGHT ต้องขึ้น `PRE-FLIGHT OK`** ถ้าไม่ขึ้น ให้หยุดแล้วรายงาน ผบ. ห้ามเดา path
2. **`--inspect` จะแสดงรายการ "แผ่น/PU ขายดีที่ยังไม่เข้ากลุ่มใดใน families.json"** ตัว regex ของ STKCOD ในไฟล์ config เดามาจากรหัสที่เห็นใน dealscore.py เท่านั้น เพราะเครื่องที่สร้างแอปนี้เปิด DBF จริงไม่ได้ ต้องแก้ให้ตรงรหัสจริงก่อน แล้วรันใหม่
3. **`verify` ต้องขึ้น `VERIFY OK` ก่อนเปิดทดลอง 30 ก.ย.** เคสที่ต้องผ่าน: SO6903141 PPS (Zacs Cool 0.35 @125 → 🔴 · สกรู 75 @2.50 → ต่ำกว่า 🔴 · PU ลายไม้ @100 → ต่ำกว่าลดได้เอง · ทั้งบิล ⛔ 0%) และ SO6904651 SKN @148 → ลดได้เอง

## กติกาที่ฝังในโค้ด (ห้ามแก้เองโดยไม่ได้รับอนุมัติจาก ผบ.)

- **ทุน**: ① ทุนเฉลี่ย Express รายสาขา → ② prefix วัตถุดิบคัดมือ → ③ ใบซื้อล่าสุด ทั้งหมดอ่านจาก `costbook_rules.json` ตัวเดียวกับ checkso ทุกชั้นจึงได้ทุนชุดเดียวกัน · กลุ่ม 02 (ครอบ) ยังไม่ออกช่วงราคาจนกว่าจะมี unit-map
- **ช่วงราคา**:
  - ยืนราคา ≥ Rate 1
  - ลดได้เอง ≥ max(Rate 1 − 5, P(20%)) · สินค้าหมุนเร็วใช้ P(15%) · สินค้าชิ้นใช้ P(20%) อย่างเดียว
  - ผจก. ≥ P(10%)
  - ต่ำกว่านั้นขอ ผบ.
  - ขอบล่างปัดขึ้นเสมอ (บาทเต็ม / 0.05) · ไม่แสดงเส้นทุน
- **เพิ่มเพื่อความปลอดภัย**: ถ้า Rate 1 ต่ำกว่า P(10%) หรือต่ำกว่าทุน สินค้านั้นจะไม่ขึ้นเขียว "ยืนราคา" แต่ขึ้นว่า "ถามก่อนขาย — รอ ผบ. ตัดสิน" และไปอยู่ในรายงาน ผบ. แทน (ตัวอย่าง: JJL สี 0.35 ใน costbook.js เดิม ทุน 110.2 แต่ Rate 1 = 110)
- **เกรดบิล**:
  - A ≥35% · B 20–34.9% (หมุนเร็ว ≥15%) · C 10–19.9% · D <10% หรือบิล >300,000 · X มีบรรทัดต่ำกว่าทุน
  - รู้ทุนไม่ถึง 70% ของบิล = ไม่สรุป
  - ทุนเก่ากว่า 14 วัน = เกรดสูงสุด C
- **หมดอายุ**: ตารางใช้ได้ 7 วัน · หน้าเว็บขึ้นแถบแดงเองเมื่อเลยวัน · PDF ขึ้นแถบแดงเมื่อทุนเก่ากว่า 7 วันตอน build

## ทดสอบ

```bash
python3 -m unittest discover -s approve007/tests -v          # engine + pipeline เต็ม (ต้องมี openpyxl)
python3 approve007/tests/make_fixture.py /tmp/fx && APPROVE007_ALL_ON_CLOUD="/tmp/fx/My Drive (007skn0777@gmail.com)/All_on_Cloud" python3 approve007/engine/build.py
node approve007/tests/test_app.mjs "/tmp/fx/My Drive (007skn0777@gmail.com)/All_on_Cloud/Approve007"
```

## ยังไม่ได้ทำ (ตามลำดับเฟส)

- เฟส 1: เกรดทั้งบิลบนเว็บ (ตอนนี้ ⚡ เช็คไว ดูรายบรรทัดตามช่วงราคา) ต้องมี API ฝั่งเซิร์ฟเวอร์ถือทุน เช่น `/api/approve/check` บน Vercel · ต่อปุ่ม "ใช้รายการนี้ทำใบเสนอราคา" เข้า Quote007 · ป้ายเงื่อนไขเมื่อ ผบ. เคาะ
- เฟส 2: `watcher.py` ข้าง Express โดยเรียก `approve_engine.grade_bill` ตัวเดียวกัน
- เฟส 3: รูปผ่าน LINE "007 Ops" ต้องมีขั้นให้เซลยืนยันก่อนเสมอ
