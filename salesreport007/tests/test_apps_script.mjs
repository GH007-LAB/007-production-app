// node salesreport007/tests/test_apps_script.mjs
// รัน Code.gs จริงใน vm กับ SpreadsheetApp/DriveApp จำลอง — ไล่ flow 15:55 → 16:30 → ส่ง/16:55 ตามสเปก v4
// + เทียบ computeSummary() กับ engine/calc.py ทุกสตางค์
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CODE = fs.readFileSync(path.join(HERE, '..', 'apps_script', 'Code.gs'), 'utf8');

// ------------------------------------------------------------------ mocks
let NOW = Date.parse('2026-10-03T15:56:00+07:00');
class FakeDate extends Date {
  constructor(...a) { if (a.length) super(...a); else super(NOW); }
  static now() { return NOW; }
}
const pad = (n) => String(n).padStart(2, '0');
function bkk(d) {
  const t = new Date(d.getTime() + 7 * 3600e3);
  return { y: t.getUTCFullYear(), M: pad(t.getUTCMonth() + 1), d: pad(t.getUTCDate()), H: pad(t.getUTCHours()),
           m: pad(t.getUTCMinutes()), s: pad(t.getUTCSeconds()) };
}
const Utilities = {
  formatDate(d, tz, fmt) {
    assert.equal(tz, 'Asia/Bangkok');
    const p = bkk(d);
    return fmt.replace("'T'", 'T').replace('yyyy', p.y).replace('MM', p.M).replace('dd', p.d)
      .replace('HH', p.H).replace('mm', p.m).replace('ss', p.s).replace('XXX', '+07:00');
  },
};
let idSeq = 0;
const nid = (p) => p + (++idSeq);

function a1(s) {
  const m = /^([A-Z]+)(\d+)$/.exec(s);
  let c = 0;
  for (const ch of m[1]) c = c * 26 + ch.charCodeAt(0) - 64;
  return [Number(m[2]), c];
}
const colName = (c) => { let s = ''; while (c) { const r = (c - 1) % 26; s = String.fromCharCode(65 + r) + s; c = (c - 1 - r) / 26; } return s; };

class Range {
  constructor(sh, r, c, nr = 1, nc = 1) { Object.assign(this, { sh, r, c, nr, nc }); }
  each(fn) { for (let i = 0; i < this.nr; i++) for (let j = 0; j < this.nc; j++) fn(this.r + i, this.c + j, i, j); }
  getValues() { const o = []; for (let i = 0; i < this.nr; i++) { o.push([]); for (let j = 0; j < this.nc; j++) o[i].push(this.sh.get(this.r + i, this.c + j)); } return o; }
  getValue() { return this.sh.get(this.r, this.c); }
  setValues(v) { assert.equal(v.length, this.nr); this.each((r, c, i, j) => this.sh.set(r, c, v[i][j])); return this; }
  setValue(v) { this.each((r, c) => this.sh.set(r, c, v)); return this; }
  clearContent() { this.each((r, c) => this.sh.set(r, c, '')); return this; }
  insertCheckboxes() { return this.setValue(false); }
  setDataValidation(v) { this.each((r, c) => { this.sh.dv[`${r},${c}`] = v; }); return this; }
  setNote(n) { this.sh.notes[`${this.r},${this.c}`] = n; return this; }
  getA1Notation() { return colName(this.c) + this.r + (this.nr > 1 || this.nc > 1 ? ':' + colName(this.c + this.nc - 1) + (this.r + this.nr - 1) : ''); }
  getNumRows() { return this.nr; } getNumColumns() { return this.nc; } getSheet() { return this.sh; }
  contains(r, c) { return r >= this.r && r < this.r + this.nr && c >= this.c && c < this.c + this.nc; }
}
for (const m of ['setFontWeight', 'setFontSize', 'setBackground', 'setNumberFormat', 'setFontColor']) Range.prototype[m] = function () { return this; };

class Protection {
  constructor() { this.editors = [USER, STAFF]; this.unprot = []; }
  setDescription() { return this; }
  addEditor(u) { if (!this.editors.some((e) => e.getEmail() === u.getEmail())) this.editors.push(u); return this; }
  removeEditors(list) { const rm = new Set(list.map((u) => u.getEmail())); this.editors = this.editors.filter((e) => !rm.has(e.getEmail())); return this; }
  getEditors() { return this.editors.slice(); }
  canDomainEdit() { return false; }
  setUnprotectedRanges(r) { this.unprot = r; return this; }
}
class Sheet {
  constructor(name) { this.name = name; this.cells = {}; this.dv = {}; this.notes = {}; this.prot = null; }
  get(r, c) { return this.cells[`${r},${c}`] ?? ''; }
  set(r, c, v) { this.cells[`${r},${c}`] = v; }
  getRange(a, c, nr, nc) {
    if (typeof a === 'string') {
      const [p, q] = a.split(':'); const [r, cc] = a1(p);
      if (!q) return new Range(this, r, cc);
      const [r2, c2] = a1(q); return new Range(this, r, cc, r2 - r + 1, c2 - cc + 1);
    }
    return new Range(this, a, c, nr ?? 1, nc ?? 1);
  }
  getLastRow() { let m = 0; for (const [k, v] of Object.entries(this.cells)) if (v !== '' && v !== false) m = Math.max(m, Number(k.split(',')[0])); return m; }
  getName() { return this.name; }
  protect() { this.prot = new Protection(); return this.prot; }
  getProtections() { return this.prot ? [this.prot] : []; }
  setFrozenRows() {} setColumnWidth() {}
  setName(n) { this.name = n; return this; }
  appendRow(r) { (this.rows ||= []).push(r); }
  // พนักงานแก้ช่อง: ห้ามถ้าช่องถูกป้องกันและไม่ใช่ผู้แก้ protection
  staffEdit(a, v) {
    const [r, c] = a1(a);
    const ok = !this.prot || this.prot.editors.some((e) => e.getEmail() === STAFF.getEmail()) || this.prot.unprot.some((x) => x.contains(r, c));
    if (!ok) throw new Error('protected ' + a);
    const old = this.get(r, c);
    this.set(r, c, v);
    return { range: this.getRange(a), oldValue: old === '' ? undefined : old, source: this.ss };
  }
  cell(a) { const [r, c] = a1(a); return this.get(r, c); }
}
class Spreadsheet {
  constructor(name) { this.id = nid('ss'); this.name = name; this.sheets = [new Sheet('ชีต1')]; this.sheets[0].ss = this; SS[this.id] = this; }
  getId() { return this.id; }
  insertSheet(n, i) { const s = new Sheet(n); s.ss = this; this.sheets.splice(i, 0, s); return s; }
  getSheetByName(n) { return this.sheets.find((s) => s.name === n) || null; }
  getSheets() { return this.sheets.slice(); }
  deleteSheet(s) { this.sheets = this.sheets.filter((x) => x !== s); }
  setSpreadsheetTimeZone() {} setSpreadsheetLocale() {}
}
const SS = {};
class DVB { constructor() { this.rule = {}; } requireValueInList(l) { this.rule.list = l; return this; } requireNumberGreaterThan(n) { this.rule.gt = n; return this; } requireNumberGreaterThanOrEqualTo(n) { this.rule.gte = n; return this; } setAllowInvalid() { return this; } build() { return this.rule; } }
const SpreadsheetApp = {
  create(n) { const s = new Spreadsheet(n); FILES[s.id] = new File(n, '', s.id); return s; },
  openById(id) { if (!SS[id]) throw new Error('no ss'); return SS[id]; },
  newDataValidation: () => new DVB(), ProtectionType: { SHEET: 'SHEET' }, flush() {},
};
class File {
  constructor(name, content, id) { this.id = id || nid('f'); this.name = name; this.content = content; this.updated = NOW; this.editors = []; this.viewers = []; FILES[this.id] = this; }
  getName() { return this.name; } getLastUpdated() { return new Date(this.updated); }
  getBlob() { return { getDataAsString: () => this.content }; }
  setContent(c) { this.content = c; this.updated = NOW; }
  moveTo(f) { f.files.push(this); } setSharing(a, p) { this.sharing = [a, p]; } setShareableByEditors(b) { this.reshare = b; }
  addEditor(e) { this.editors.push(e); } addViewer(e) { this.viewers.push(e); }
}
const FILES = {};
class Folder {
  constructor(name) { this.id = nid('d'); this.name = name; this.files = []; this.folders = []; FOLDERS[this.id] = this; }
  getFoldersByName(n) { return iter(this.folders.filter((f) => f.name === n)); }
  createFolder(n) { const f = new Folder(n); this.folders.push(f); return f; }
  getFilesByName(n) { return iter(this.files.filter((f) => f.name === n)); }
  getFiles() { return iter(this.files); }
  createFile(n, c) { const f = new File(n, c); this.files.push(f); return f; }
  put(n, c) { const f = this.files.find((x) => x.name === n); if (f) f.setContent(c); else this.createFile(n, c); }
}
const FOLDERS = {};
const iter = (a) => { let i = 0; return { hasNext: () => i < a.length, next: () => a[i++] }; };
const DriveApp = {
  getFolderById: (id) => FOLDERS[id], getFileById: (id) => FILES[id],
  Access: { PRIVATE: 'PRIVATE' }, Permission: { NONE: 'NONE' },
};
const PROPS = {};
const PropertiesService = { getScriptProperties: () => ({
  getProperty: (k) => PROPS[k] ?? null, setProperty: (k, v) => { PROPS[k] = String(v); },
  deleteProperty: (k) => { delete PROPS[k]; }, getProperties: () => ({ ...PROPS }) }) };
const TRIGGERS = [];
const ScriptApp = {
  getProjectTriggers: () => TRIGGERS.slice(),
  deleteTrigger: (t) => TRIGGERS.splice(TRIGGERS.indexOf(t), 1),
  newTrigger: (fn) => { const t = { fn, src: null, getHandlerFunction: () => fn, getTriggerSourceId: () => t.src };
    const b = { timeBased: () => b, everyMinutes: () => b, forSpreadsheet: (s) => { t.src = s.getId(); return b; }, onEdit: () => b,
      create: () => { TRIGGERS.push(t); return t; } }; return b; },
};
const USER = { getEmail: () => '007skn0777@gmail.com' };
const STAFF = { getEmail: () => 'staff.skn@gmail.com' };
const ctx = {
  Date: FakeDate, Math, JSON, Number, String, Object, Array, isFinite, Error,
  Utilities, SpreadsheetApp, DriveApp, PropertiesService, ScriptApp,
  LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock() {} }) },
  Session: { getEffectiveUser: () => USER }, Logger: { log: (m) => { if (/\n\s+at /.test(m)) throw new Error('poll error: ' + m); } },
};
vm.createContext(ctx);
vm.runInContext(CODE, ctx);

// ------------------------------------------------------------------ Drive จำลอง
const root = new Folder('sales_report');
PROPS.ROOT_FOLDER_ID = root.id;
const receipts = new Folder('receipts_SKN');
root.createFile('config.json', JSON.stringify({
  times: { ready: '16:00', cutoff: '16:30', deadline: '16:55' }, summary_viewers: ['gem@x.com'],
  branches: { SKN: { float: 500, receipt_folder_id: receipts.id, staff: [{ name: 'นิด', email: 'staff.skn@gmail.com' }] },
              BK: { float: 0, staff: [] }, PPS: { float: 0, staff: [] } },
}));
ctx.setup();
const sumSS = SS[PROPS.SUMMARY_SPREADSHEET_ID];
const sumRows = () => sumSS.getSheetByName('สรุป').rows || [];
assert.ok(TRIGGERS.some((t) => t.fn === 'poll'));
const brFolder = (b) => root.folders.find((f) => f.name === b);
// เอกสารจาก Express: ช่องทางมากับ RE/AI แล้ว (cash/transfer) — พนักงานไม่ต้องเลือก
const doc = (no, type, total, pay = {}, extra = {}) => {
  const p = { cash: 0, transfer: 0, cheque: 0, other: 0, ...pay };
  const used = Object.keys(p).filter((k) => p[k] > 0);
  const th = { cash: 'เงินสด', transfer: 'โอน', cheque: 'เช็ค', other: 'อื่น ๆ' };
  const channel = type === 'SR' && !p.cash ? 'ลดหนี้ (ไม่กระทบเงินสด)' : !used.length ? '⚠️ ไม่ระบุช่องทางใน Express'
    : used.length === 1 ? th[used[0]] : 'ผสม (' + used.map((k) => th[k]).join('+') + ')';
  return { doc_no: no, doc_date: '2026-10-03', type, customer: 'ลูกค้า ' + no, total, channel,
           pay_known: used.length > 0, ...p, ...extra };
};
const inJson = (br, round, at, docs, carried = [], iv = []) => JSON.stringify({
  branch: br, date: '2026-10-03', round, cutoff_at: at, carried_in: carried, docs, iv,
  counts: {}, warnings: [], no_channel: docs.filter((d) => ['RE', 'AI', 'HS'].includes(d.type) && !d.pay_known).map((d) => d.doc_no) });
const set = (iso) => { NOW = Date.parse(iso); };

// ---- 08:30 รอบแรกของวัน: แท็บพร้อมให้ลงรายจ่ายทั้งวัน ----
brFolder('SKN').put('691003_in.json', inJson('SKN', 'ready', '2026-10-03T08:30:00+07:00',
  [doc('AI1', 'AI', 5000, { cash: 5000 }), doc('RE1', 'RE', 3000, { cash: 1000, transfer: 2000 }),
   doc('SR1', 'SR', 450), doc('RE2', 'RE', 800)],
  [], [{ doc_no: 'IV1', customer: 'ก', total: 12000, unpaid: true }, { doc_no: 'IV2', customer: 'ข', total: 3000, unpaid: false }]));
brFolder('BK').put('691003_in.json', inJson('BK', 'ready', '2026-10-03T08:30:00+07:00', [doc('RE9', 'RE', 100, { transfer: 100 })]));
set('2026-10-03T07:40:00+07:00'); ctx.poll();
assert.equal(Object.keys(PROPS).filter((k) => k.startsWith('tab_')).length, 0, 'นอกช่วงเวลา poll ต้องไม่ทำอะไร');
set('2026-10-03T08:31:00+07:00'); ctx.poll();
const meta = JSON.parse(PROPS['tab_SKN_2026-10-03']);
const ss = SS[meta.ssId];
const sh = ss.getSheetByName('3 ต.ค. 69');
assert.ok(sh, 'แท็บชื่อ = วันที่');
assert.deepEqual(ss.getSheets().map((s) => s.name), ['3 ต.ค. 69'], 'ลบชีตเปล่าตอนสร้างไฟล์');
assert.equal(FILES[ss.id].name, 'รายงานขายประจำวัน_SKN_2569-10');
assert.deepEqual(FILES[ss.id].sharing, ['PRIVATE', 'NONE']);
assert.equal(FILES[ss.id].reshare, false);
assert.deepEqual(FILES[ss.id].editors, ['staff.skn@gmail.com']);
assert.ok(TRIGGERS.some((t) => t.fn === 'onSheetEdit' && t.src === ss.id));
assert.deepEqual([7, 8, 9, 10].map((r) => sh.cell('B' + r)), ['AI1', 'RE1', 'SR1', 'RE2']);
assert.deepEqual([7, 8, 9, 10].map((r) => sh.cell('G' + r)),
  ['เงินสด', 'ผสม (เงินสด+โอน)', 'ลดหนี้ (ไม่กระทบเงินสด)', '⚠️ ไม่ระบุช่องทางใน Express']);
assert.match(sh.cell('H10'), /แก้ RE\/AI ใน Express/);
assert.match(sh.cell('G2'), /1 ใบไม่ระบุช่องทาง/);
assert.deepEqual([sh.cell('Q7'), sh.cell('T7'), sh.cell('Q8'), sh.cell('T8')], ['IV1', 'ค้างรับ', 'IV2', 'รับแล้ว']);
assert.deepEqual(sh.prot.editors.map((e) => e.getEmail()), ['007skn0777@gmail.com']);
for (const a of ['F7', 'G7', 'B7', 'Q7']) assert.throws(() => sh.staffEdit(a, 1), /protected/, 'แถวเอกสารแก้ไม่ได้ ' + a);
// ไม่มียอดเงินแยกเงินสด/โอน และไม่มียอดรวมในแท็บพนักงาน
const allVals = Object.values(sh.cells).map(String);
assert.ok(!allVals.includes('1000') && !allVals.includes('2000'), 'ไม่โชว์ยอดเงินสด/โอนรายใบ');
assert.ok(!/ควรมี|รวมเงินสด|รวมโอน/.test(allVals.join('|')));

// ---- ระหว่างวัน: ลงรายจ่ายประจำวัน ----
set('2026-10-03T11:05:00+07:00');
const ev = (e) => ctx.onSheetEdit(e);
ev(sh.staffEdit('J7', 'น้ำมัน/ค่าเดินทาง')); ev(sh.staffEdit('K7', 'เติมน้ำมันรถส่งของ')); ev(sh.staffEdit('L7', 'ปตท.'));
ev(sh.staffEdit('M7', 120)); ev(sh.staffEdit('N7', 'INV-889')); ev(sh.staffEdit('O7', '691003_1.jpg'));
ev(sh.staffEdit('J8', 'อาหาร/น้ำดื่ม')); ev(sh.staffEdit('K8', 'ข้าวกลางวันคนงาน')); ev(sh.staffEdit('M8', 60));
receipts.createFile('691003_1.jpg', '');
assert.equal(sh.dv['7,10'].list.length, 8, 'หมวดรายจ่ายเป็น dropdown');

// ---- 14:30 รอบระหว่างวัน: สาขาแก้ RE2 ใน Express ให้ระบุเงินสด → แถวเดิมอัปเดต ไม่ย้ายลำดับ ----
brFolder('SKN').put('691003_in.json', inJson('SKN', 'ready', '2026-10-03T14:30:00+07:00',
  [doc('AI1', 'AI', 5000, { cash: 5000 }), doc('RE1', 'RE', 3000, { cash: 1000, transfer: 2000 }),
   doc('SR1', 'SR', 450), doc('RE2', 'RE', 800, { cash: 800 })], [], []));
set('2026-10-03T14:31:00+07:00'); ctx.poll();
assert.equal(sh.cell('B10'), 'RE2');
assert.equal(sh.cell('G10'), 'เงินสด');
assert.equal(sh.cell('H10'), '');
assert.equal(sh.cell('K7'), 'เติมน้ำมันรถส่งของ', 'รายจ่ายที่กรอกไว้ไม่ถูกแตะ');

ev(sh.staffEdit('B3', 7000));
ev(sh.staffEdit('D3', 'นิด'));
ev(sh.staffEdit('F3', true));
assert.equal(sh.cell('F3'), false, 'ส่งก่อนตัดรอบไม่ได้');
assert.match(sh.cell('G3'), /รอตัดรอบ 16:30/);

// ---- 16:30 ตัดรอบ: เติมต่อท้าย ----
brFolder('SKN').put('691003_in.json', inJson('SKN', 'cutoff', '2026-10-03T16:30:00+07:00',
  [doc('AI1', 'AI', 5000, { cash: 5000 }), doc('RE1', 'RE', 3000, { cash: 1000, transfer: 2000 }),
   doc('SR1', 'SR', 450), doc('RE2', 'RE', 800, { cash: 800 }), doc('AI2', 'AI', 700, { transfer: 700 })], [], []));
set('2026-10-03T16:31:00+07:00'); ctx.poll();
assert.equal(sh.cell('B11'), 'AI2');
assert.equal(sh.cell('Q7'), '', 'IV เขียนทับตามรอบล่าสุด');
ctx.poll();   // ไฟล์เดิมซ้ำ → ไม่เติมซ้ำ
assert.equal(sh.cell('B12'), '');

ev(sh.staffEdit('J9', 'อื่น ๆ (ระบุในรายการ)'));
ev(sh.staffEdit('F3', true));
assert.equal(sh.cell('F3'), false);
assert.match(sh.cell('G3'), /รายจ่ายแถว 3: ต้องมี หมวด \+ รายการ \+ จำนวนเงิน/);
ev(sh.staffEdit('J9', ''));
set('2026-10-03T16:42:00+07:00');
ev(sh.staffEdit('F3', true));
assert.match(sh.cell('G3'), /ส่งแล้ว 16:42/);

// ---- ผลหลังส่ง ----
const out = JSON.parse(brFolder('SKN').files.find((f) => f.name === '691003_out.json').content);
// เงินสด: 0 float(500) + (5000 + 1000 + 800) − 0 คืน − 120 (ข้าวไม่มีบิล = ไม่นับ) = 7180 · นับ 7000 → −180
assert.deepEqual({ ...out.summary }, { cash_in: 6800, transfer_in: 2700, cheque_in: 0, other_in: 0, cash_refund: 0,
  cash_expense: 120, cash_expected: 7180, diff: -180, deposit: 6500 });
assert.equal(out.version, 5);
assert.equal(out.submitted_at, '2026-10-03T16:42:00+07:00');
assert.equal(out.preparer, 'นิด');
assert.equal(out.doc_count_at_cutoff, 5);
assert.deepEqual([...out.expense_no_receipt], ['ข้าวกลางวันคนงาน']);
assert.deepEqual({ ...out.expenses[0] }, { row: 1, category: 'น้ำมัน/ค่าเดินทาง', item: 'เติมน้ำมันรถส่งของ', payee: 'ปตท.',
  amount: 120, bill_no: 'INV-889', receipt: '691003_1.jpg', receipt_found: true });
assert.equal(out.docs.find((d) => d.doc_no === 'RE1').transfer, 2000);
assert.equal(sh.cell('E4'), -180, 'เผยเฉพาะส่วนต่างหลังส่ง');
assert.ok(!Object.values(sh.cells).includes(7180), 'ไม่เผยเงินสดที่ควรมี');
assert.equal(sh.prot.unprot.length, 0, 'ล็อกทั้งแท็บ');
assert.throws(() => sh.staffEdit('M7', 999), /protected/);
assert.equal(sumRows().length, 1);
assert.equal(sumRows()[0][16], -180);
assert.deepEqual(FILES[sumSS.id].viewers, ['gem@x.com']);
// ตรวจซ้ำด้วย Python (Finny: salesreport.py summarize)
const chk = execFileSync('python3', ['-c', `
import json,sys
sys.path.insert(0, ${JSON.stringify(path.join(HERE, '..', 'engine'))})
import calc
j=json.load(sys.stdin); s=calc.summarize(j['docs'],j['expenses'],j['cash_counted'],j['float'])
print(all(abs(s[k]-j['summary'][k])<0.005 for k in calc.MONEY_KEYS))`], { input: JSON.stringify(out) }).toString().trim();
assert.equal(chk, 'True');

// ---- BK ไม่ส่ง → 16:55 ล็อกเอง ----
set('2026-10-03T16:50:00+07:00'); ctx.poll();
assert.ok(!JSON.parse(PROPS['tab_BK_2026-10-03']).locked);
set('2026-10-03T16:56:00+07:00'); ctx.poll();
const bk = JSON.parse(brFolder('BK').files.find((f) => f.name === '691003_out.json').content);
assert.equal(bk.submitted_at, null);
assert.equal(bk.lock_reason, 'deadline');
assert.equal(bk.summary.transfer_in, 100);
assert.equal(sumRows().length, 2);
ctx.poll();
assert.equal(sumRows().length, 2, 'ล็อกแล้วไม่สรุปซ้ำ');

// ---- แก้หลังเส้นตาย (ยังไม่ถูก poll ล็อก) → คืนค่า + ล็อก ----
NOW = Date.parse('2026-10-04T16:00:00+07:00');
brFolder('PPS').put('691004_in.json', JSON.stringify({ branch: 'PPS', date: '2026-10-04', round: 'cutoff',
  cutoff_at: '2026-10-04T16:30:00+07:00', carried_in: [doc('AI7', 'AI', 10, { cash: 10 })], docs: [], iv: [] }));
ctx.runNow();
const pm = JSON.parse(PROPS['tab_PPS_2026-10-04']);
const psh = SS[pm.ssId].getSheetByName('4 ต.ค. 69');
assert.equal(psh.cell('A7'), 'ยกมา');
NOW = Date.parse('2026-10-04T16:57:00+07:00');
ctx.onSheetEdit(psh.staffEdit('B3', 10));
assert.equal(psh.cell('B3'), '', 'ค่าที่แก้หลัง 16:55 ถูกคืน');
assert.ok(JSON.parse(PROPS['tab_PPS_2026-10-04']).locked);

// ------------------------------------------------------------------ parity กับ calc.py
const cases = [];
let seed = 7;
const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
for (let k = 0; k < 200; k++) {
  const docs = [], exps = [];
  for (let i = 0; i < 1 + Math.floor(rnd() * 12); i++) {
    const total = Math.round(rnd() * 5e6) / 100 + (rnd() < 0.1 ? 0.005 : 0);
    const pk = rnd() < 0.85, r = () => Math.round(rnd() * total * 50) / 100;
    docs.push({ doc_no: 'D' + i, type: ['RE', 'AI', 'SR', 'HS', 'IV'][Math.floor(rnd() * 5)], total, pay_known: pk,
      cash: pk ? r() : 0, transfer: pk ? r() : 0, cheque: rnd() < 0.1 ? r() : 0, other: rnd() < 0.05 ? r() + 0.005 : 0 });
  }
  for (let i = 0; i < Math.floor(rnd() * 4); i++) {
    exps.push({ item: 'e' + i, amount: Math.round(rnd() * 50000) / 100, receipt: rnd() < 0.7 ? 'r.jpg' : '',
      ...(rnd() < 0.2 ? { receipt_found: false } : {}) });
  }
  cases.push({ docs, exps, counted: Math.round(rnd() * 1e7) / 100, float: [0, 500, 1000][k % 3] });
}
const py = JSON.parse(execFileSync('python3', ['-c', `
import json,sys
sys.path.insert(0, ${JSON.stringify(path.join(HERE, '..', 'engine'))})
import calc
cs=json.load(sys.stdin)
print(json.dumps([calc.summarize(c['docs'],c['exps'],c['counted'],c['float']) for c in cs]))`],
{ input: JSON.stringify(cases) }).toString());
cases.forEach((c, i) => {
  const js = JSON.parse(JSON.stringify(ctx.computeSummary(c.docs, c.exps, c.counted, c.float)));
  assert.deepEqual(js, py[i], 'parity case ' + i);
});
console.log('test_apps_script: ALL OK (flow + parity 200 เคส)');
