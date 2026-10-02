/**
 * รายงานขายอัตโนมัติ (สเปก CTO v4 ข้อ 7) — Apps Script แบบ standalone ของบัญชีบริษัทที่ CTO ดูแล
 *
 * ทำไมไม่ผูกกับไฟล์: สเปกให้ 1 ไฟล์ ต่อสาขา ต่อเดือน → ถ้าผูกสคริปต์ทีละไฟล์ต้องก๊อปโค้ด 36 ชุด/ปี
 * สคริปต์ตัวเดียวนี้สร้างไฟล์ประจำเดือนเอง แล้วติด trigger onEdit ให้แต่ละไฟล์ (ผลเหมือนผูกกับไฟล์)
 *
 * ติดตั้ง (ครั้งเดียว): ดู salesreport007/README.md
 *   Script Properties: ROOT_FOLDER_ID = id โฟลเดอร์ All_on_Cloud/AutoExport/sales_report
 *   แล้วรัน setup() จาก editor
 *
 * กติกาที่โค้ดนี้บังคับ:
 *   - ไม่มีสูตร/ยอดรวมเงินในแท็บพนักงาน (ข้อ 4 · 9.1) — สรุปไปอยู่ไฟล์ "สรุป" ที่เห็นเฉพาะ CTO/ผบ./Finny
 *   - เพิ่มแถวต่อท้ายอย่างเดียว ไม่แตะแถวเดิม (ข้อ 7.2)
 *   - ไม่มีค่าเริ่มต้นช่องทาง · ส่งได้เมื่อเลือกครบ + กรอกยอดนับ + เติมรอบ 16:30 แล้ว (ข้อ 9.2)
 *   - ส่ง หรือถึง 16:55 → ล็อกทั้งแท็บ · เขียน YYMMDD_out.json · เผยเฉพาะส่วนต่าง (ข้อ 5 · 9.3)
 */

var TZ = 'Asia/Bangkok';
var BRANCHES = ['BK', 'SKN', 'PPS'];
var BR_NAME = { BK: 'บึงกาฬ', SKN: 'สกลนคร', PPS: 'โพนพิสัย' };
var DEFAULT_TIMES = { ready: '16:00', cutoff: '16:30', deadline: '16:55' };
var POLL_WINDOW = ['15:45', '17:30'];       // นอกช่วงนี้ poll() ออกทันที (ประหยัดโควตา trigger)
var RECEIVE_TYPES = ['RE', 'AI', 'HS'];
var REFUND_TYPES = ['SR'];
var CHANNELS = { 'เงินสด': 'cash', 'โอน-QR': 'transfer', 'ผสม': 'mixed' };
var TH_MONTH = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];

// ---- ผังแท็บ (แถว/คอลัมน์ 1-based) ----
var L = {
  counted: 'B3', preparer: 'D3', submit: 'F3', status: 'G3', qr: 'B4', diff: 'E4',
  cutoff: 'B2', counts: 'E2', round: 'G2',
  docHeader: 6, docFirst: 7, docCols: 8,          // A–H: กลุ่ม เลข วันที่ ประเภท ลูกค้า ยอด ช่องทาง ยอดเงินสด
  colChannel: 7, colCash: 8,
  expCol: 10, expRows: 20,                          // J–L: รายการ จำนวนเงิน ชื่อไฟล์รูปบิล
  ivCol: 14,                                        // N–P: ค้างรับ (ดูอย่างเดียว)
};

// ===================================================================== สูตร (ข้อ 5) — ตรงกับ engine/calc.py
function satang_(v) {
  var n = Number(v);
  if (!isFinite(n)) return 0;
  return Math.floor(Math.abs(n) * 100 + 0.5 + 1e-9);   // ปัดครึ่งขึ้น — ตรงกับ calc.py
}
function baht_(s) { return Math.round(s) / 100; }
function expenseCounts_(e) {
  return String(e.receipt || '').trim() !== '' && e.receipt_found !== false;
}
function computeSummary(docs, expenses, cashCounted, floatAmt) {
  var cashIn = 0, transferIn = 0, cashRefund = 0, cashExpense = 0, unticked = [], noReceipt = [];
  docs.forEach(function (d) {
    var ch = d.channel, t = d.type, tot = satang_(d.total), cash = satang_(d.cash_amount);
    if (ch !== 'cash' && ch !== 'transfer' && ch !== 'mixed') { unticked.push(d.doc_no); return; }
    if (ch === 'mixed') cash = Math.min(cash, tot);
    if (RECEIVE_TYPES.indexOf(t) >= 0) {
      if (ch === 'cash') cashIn += tot;
      else if (ch === 'transfer') transferIn += tot;
      else { cashIn += cash; transferIn += tot - cash; }
    } else if (REFUND_TYPES.indexOf(t) >= 0) {
      if (ch === 'cash') cashRefund += tot;
      else if (ch === 'mixed') cashRefund += cash;
    }
  });
  expenses.forEach(function (e) {
    if (expenseCounts_(e)) cashExpense += satang_(e.amount);
    else if (satang_(e.amount)) noReceipt.push(e.item);
  });
  var fl = satang_(floatAmt), counted = satang_(cashCounted);
  var expected = fl + cashIn - cashRefund - cashExpense;
  return {
    cash_in: baht_(cashIn), transfer_in: baht_(transferIn), cash_refund: baht_(cashRefund),
    cash_expense: baht_(cashExpense), cash_expected: baht_(expected),
    diff: baht_(counted - expected), deposit: baht_(counted - fl),
    unticked: unticked, expense_no_receipt: noReceipt,
  };
}

// ===================================================================== เวลา / config
function nowParts_() {
  var d = new Date();
  return { date: Utilities.formatDate(d, TZ, 'yyyy-MM-dd'), hm: Utilities.formatDate(d, TZ, 'HH:mm'),
           iso: Utilities.formatDate(d, TZ, "yyyy-MM-dd'T'HH:mm:ssXXX") };
}
function yymmdd_(iso) {               // 2026-10-03 → 691003 (พ.ศ. เหมือนชื่อไฟล์ฝั่ง Mac mini)
  var p = iso.split('-');
  return ('0' + ((Number(p[0]) + 543) % 100)).slice(-2) + p[1] + p[2];
}
function tabName_(iso) {              // 2026-10-03 → "3 ต.ค. 69"
  var p = iso.split('-');
  return Number(p[2]) + ' ' + TH_MONTH[Number(p[1]) - 1] + ' ' + ('0' + ((Number(p[0]) + 543) % 100)).slice(-2);
}
function monthKey_(iso) { var p = iso.split('-'); return (Number(p[0]) + 543) + '-' + p[1]; }

function props_() { return PropertiesService.getScriptProperties(); }
function rootFolder_() {
  var id = props_().getProperty('ROOT_FOLDER_ID');
  if (!id) throw new Error('ตั้ง Script Property ROOT_FOLDER_ID = id โฟลเดอร์ AutoExport/sales_report ก่อน');
  return DriveApp.getFolderById(id);
}
function subFolder_(parent, name, create) {
  var it = parent.getFoldersByName(name);
  if (it.hasNext()) return it.next();
  return create ? parent.createFolder(name) : null;
}
function latestFile_(folder, name) {
  var it = folder.getFilesByName(name), best = null;
  while (it.hasNext()) {
    var f = it.next();
    if (!best || f.getLastUpdated() > best.getLastUpdated()) best = f;
  }
  return best;
}
var CONFIG_CACHE_ = null;
function config_() {
  if (CONFIG_CACHE_) return CONFIG_CACHE_;
  var f = latestFile_(rootFolder_(), 'config.json');
  if (!f) throw new Error('ไม่เจอ config.json ในโฟลเดอร์ sales_report (ก๊อปจาก apps_script/config.example.json)');
  var c = JSON.parse(f.getBlob().getDataAsString('UTF-8'));
  c.times = Object.assign({}, DEFAULT_TIMES, c.times || {});
  CONFIG_CACHE_ = c;
  return c;
}
function brCfg_(br) { return (config_().branches || {})[br] || {}; }

// ===================================================================== meta ต่อแท็บ (ScriptProperties)
function metaKey_(br, iso) { return 'tab_' + br + '_' + iso; }
function getMeta_(br, iso) {
  var s = props_().getProperty(metaKey_(br, iso));
  return s ? JSON.parse(s) : null;
}
function setMeta_(m) { props_().setProperty(metaKey_(m.branch, m.date), JSON.stringify(m)); }
function pruneMeta_(todayIso) {          // ScriptProperties จำกัด 500KB → เก็บ meta แค่ 60 วัน
  var limit = new Date(new Date(todayIso + 'T00:00:00+07:00').getTime() - 60 * 864e5);
  var cut = Utilities.formatDate(limit, TZ, 'yyyy-MM-dd'), all = props_().getProperties();
  Object.keys(all).forEach(function (k) {
    if (k.indexOf('tab_') === 0 && k.slice(-10) < cut) props_().deleteProperty(k);
  });
}
function metaBySheet_(ssId, sheetName) {
  var all = props_().getProperties();
  for (var k in all) {
    if (k.indexOf('tab_') !== 0) continue;
    var m = JSON.parse(all[k]);
    if (m.ssId === ssId && m.sheet === sheetName) return m;
  }
  return null;
}

// ===================================================================== setup
function setup() {
  var root = rootFolder_();
  config_();
  BRANCHES.forEach(function (br) { subFolder_(root, br, true); });
  summarySheet_();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'poll') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('poll').timeBased().everyMinutes(5).create();
  Logger.log('setup OK — poll ทุก 5 นาที (ทำงานจริงเฉพาะ ' + POLL_WINDOW.join('–') + ')');
}

/** รันมือได้จาก editor: เติมแท็บทุกสาขาทันที (ไม่สนช่วงเวลา) */
function runNow() { BRANCHES.forEach(function (br) { ingest_(br, nowParts_().date); }); }
/** รันมือ: ล็อก + สรุปทุกสาขาของวันนี้ทันที */
function finalizeNow() { BRANCHES.forEach(function (br) { finalize_(br, nowParts_().date, 'manual'); }); }

function poll() {
  var n = nowParts_();
  if (n.hm < POLL_WINDOW[0] || n.hm > POLL_WINDOW[1]) return;
  var times = config_().times;
  BRANCHES.forEach(function (br) {
    try {
      ingest_(br, n.date);
      if (n.hm >= times.deadline) finalize_(br, n.date, 'deadline');
    } catch (e) {
      Logger.log(br + ': ' + e.stack);
    }
  });
}

// ===================================================================== ไฟล์ประจำเดือน + แท็บ
function monthlySpreadsheet_(br, iso) {
  var key = 'ss_' + br + '_' + monthKey_(iso);
  var id = props_().getProperty(key);
  if (id) { try { return SpreadsheetApp.openById(id); } catch (e) { /* ไฟล์ถูกลบ → สร้างใหม่ */ } }
  var ss = SpreadsheetApp.create('รายงานรับเงิน_' + br + '_' + monthKey_(iso));
  ss.setSpreadsheetTimeZone(TZ);
  ss.setSpreadsheetLocale('th_TH');
  var file = DriveApp.getFileById(ss.getId());
  file.moveTo(subFolder_(subFolder_(rootFolder_(), '_sheets', true), br, true));
  file.setSharing(DriveApp.Access.PRIVATE, DriveApp.Permission.NONE);   // ปิด "ทุกคนที่มีลิงก์"
  file.setShareableByEditors(false);
  (brCfg_(br).staff || []).forEach(function (s) { if (s.email) file.addEditor(s.email); });
  props_().setProperty(key, ss.getId());
  // trigger onEdit ของไฟล์นี้ + ลบของเดือนเก่า (trigger ได้ไม่เกิน 20 ตัวต่อโปรเจกต์)
  var keep = {};
  BRANCHES.forEach(function (b) {
    var v = props_().getProperty('ss_' + b + '_' + monthKey_(iso));
    if (v) keep[v] = true;
  });
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'onSheetEdit' && !keep[t.getTriggerSourceId()]) ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onSheetEdit').forSpreadsheet(ss).onEdit().create();
  return ss;
}

function readIn_(br, iso) {
  var folder = subFolder_(rootFolder_(), br, false);
  var f = folder && latestFile_(folder, yymmdd_(iso) + '_in.json');
  if (!f) return null;
  var j = JSON.parse(f.getBlob().getDataAsString('UTF-8'));
  return j.date === iso && j.branch === br ? j : null;    // Drive sync ยังไม่มา = ไฟล์ของเมื่อวาน → รอ
}

function createTab_(ss, br, iso) {
  var name = tabName_(iso);
  var sh = ss.getSheetByName(name);
  if (sh) return sh;
  sh = ss.insertSheet(name, 0);
  var staff = (brCfg_(br).staff || []).map(function (s) { return s.name; }).filter(String);
  sh.getRange('A1').setValue('รายงานรับเงิน สาขา' + (BR_NAME[br] || br) + ' (' + br + ') · ' + tabName_(iso))
    .setFontWeight('bold').setFontSize(13);
  sh.getRange('A2:G2').setValues([['ตัดรอบ', '', 'จำนวนเอกสาร', '', '', '', '']]);
  sh.getRange('A3:G3').setValues([['เงินสดนับจริง', '', 'ผู้จัดทำ', '', 'ส่งรายงาน', false, '']]);
  sh.getRange('A4:E4').setValues([['รูปสรุป QR (ชื่อไฟล์)', '', '', 'ส่วนต่าง (เห็นหลังส่ง)', '']]);
  sh.getRange('A5').setValue('B. รายการรับเงิน — เลือกช่องทางให้ครบทุกแถว (B1 ยกมา อยู่บนสุด)').setFontWeight('bold');
  sh.getRange(5, L.expCol).setValue('C. ค่าใช้จ่ายเงินสดในรอบ (ต้องแนบรูปบิล)').setFontWeight('bold');
  sh.getRange(5, L.ivCol).setValue('B3. ค้างรับ — ดูอย่างเดียว ไม่ต้องเลือก').setFontWeight('bold');
  sh.getRange(L.docHeader, 1, 1, L.docCols).setValues([['กลุ่ม', 'เลขเอกสาร', 'วันที่เอกสาร', 'ประเภท', 'ลูกค้า',
    'ยอดรวม VAT', 'ช่องทาง', 'ยอดเงินสด (เฉพาะผสม)']]).setFontWeight('bold').setBackground('#eeeeee');
  sh.getRange(L.docHeader, L.expCol, 1, 3).setValues([['รายการ', 'จำนวนเงิน', 'ชื่อไฟล์รูปบิล (ขึ้นต้น ' +
    yymmdd_(iso) + ')']]).setFontWeight('bold').setBackground('#eeeeee');
  sh.getRange(L.docHeader, L.ivCol, 1, 3).setValues([['เลขเอกสาร', 'ลูกค้า', 'ยอด']])
    .setFontWeight('bold').setBackground('#eeeeee');
  sh.getRange(L.submit).insertCheckboxes();
  sh.getRange(L.counted).setDataValidation(SpreadsheetApp.newDataValidation()
    .requireNumberGreaterThanOrEqualTo(0).setAllowInvalid(false).build()).setNumberFormat('#,##0.00')
    .setBackground('#fff8c4');
  if (staff.length) {
    sh.getRange(L.preparer).setDataValidation(SpreadsheetApp.newDataValidation()
      .requireValueInList(staff, true).setAllowInvalid(false).build());
  }
  sh.getRange(L.preparer).setBackground('#fff8c4');
  sh.getRange(L.qr).setBackground('#fff8c4');
  var exp = sh.getRange(L.docFirst, L.expCol, L.expRows, 3);
  exp.setBackground('#fff8c4');
  sh.getRange(L.docFirst, L.expCol + 1, L.expRows, 1).setNumberFormat('#,##0.00').setDataValidation(
    SpreadsheetApp.newDataValidation().requireNumberGreaterThan(0).setAllowInvalid(false).build());
  sh.setFrozenRows(L.docHeader);
  sh.setColumnWidth(5, 220);
  sh.setColumnWidth(L.expCol, 180);
  sh.setColumnWidth(L.expCol + 2, 200);
  sh.setColumnWidth(L.ivCol + 1, 200);
  // ทั้งแท็บป้องกัน · เปิดเฉพาะช่องพนักงาน (อัปเดตทุกครั้งที่เพิ่มแถว)
  var p = sh.protect().setDescription('ระบบเติม — แก้ได้เฉพาะเจ้าของไฟล์');
  p.addEditor(Session.getEffectiveUser());
  p.removeEditors(p.getEditors().filter(function (u) { return u.getEmail() !== Session.getEffectiveUser().getEmail(); }));
  if (p.canDomainEdit()) p.setDomainEdit(false);
  // ลบแท็บเปล่าตอนสร้างไฟล์
  var blank = ss.getSheets().filter(function (s) { return s.getName() !== name && s.getLastRow() === 0; });
  if (blank.length && ss.getSheets().length > 1) blank.forEach(function (s) { ss.deleteSheet(s); });
  return sh;
}

function docRowCount_(sh) {
  var last = sh.getLastRow();
  if (last < L.docFirst) return 0;
  var v = sh.getRange(L.docFirst, 2, last - L.docFirst + 1, 1).getValues();
  var n = 0;
  while (n < v.length && String(v[n][0]).trim() !== '') n++;
  return n;
}

function setInputRanges_(sh, nDocs) {
  var p = sh.getProtections(SpreadsheetApp.ProtectionType.SHEET)[0];
  if (!p) return;
  var r = [sh.getRange(L.counted), sh.getRange(L.preparer), sh.getRange(L.submit), sh.getRange(L.qr),
           sh.getRange(L.docFirst, L.expCol, L.expRows, 3)];
  if (nDocs) r.push(sh.getRange(L.docFirst, L.colChannel, nDocs, 2));
  p.setUnprotectedRanges(r);
}

function ingest_(br, iso) {
  var j = readIn_(br, iso);
  if (!j) return;
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    var meta = getMeta_(br, iso);
    if (meta && meta.locked) return;
    if (meta && meta.cutoffAt === j.cutoff_at && meta.round === j.round) return;   // ไฟล์เดิม ไม่มีอะไรใหม่
    var ss = monthlySpreadsheet_(br, iso);
    var sh = createTab_(ss, br, iso);
    var n = docRowCount_(sh);
    var have = {};
    if (n) sh.getRange(L.docFirst, 2, n, 1).getValues().forEach(function (r) { have[String(r[0]).trim()] = true; });
    var add = [];
    (j.carried_in || []).forEach(function (d) { if (!have[d.doc_no]) add.push(['ยกมา', d, true]); });
    (j.docs || []).forEach(function (d) { if (!have[d.doc_no]) add.push(['วันนี้', d, false]); });
    if (add.length) {
      var start = L.docFirst + n;
      sh.getRange(start, 1, add.length, 6).setValues(add.map(function (a) {
        var d = a[1];
        return [a[0], d.doc_no, d.doc_date || iso, d.type, d.customer || '', Number(d.total) || 0];
      }));
      sh.getRange(start, 2, add.length, 1).setNumberFormat('@');
      sh.getRange(start, 6, add.length, 1).setNumberFormat('#,##0.00');
      sh.getRange(start, L.colChannel, add.length, 1).setDataValidation(SpreadsheetApp.newDataValidation()
        .requireValueInList(Object.keys(CHANNELS), true).setAllowInvalid(false).build());
      sh.getRange(start, L.colCash, add.length, 1).setNumberFormat('#,##0.00').setDataValidation(
        SpreadsheetApp.newDataValidation().requireNumberGreaterThan(0).setAllowInvalid(false).build());
      sh.getRange(start, L.colChannel, add.length, 2).setBackground('#fff8c4');
      if (meta && meta.round) {   // แถวที่เติมรอบหลัง → ไฮไลต์ให้เห็นว่าเพิ่งมา
        sh.getRange(start, 1, add.length, 6).setBackground('#e3f2fd');
      }
      add.forEach(function (a, i) {
        if (a[1].type === 'HS') sh.getRange(start + i, 5).setNote(a[1].note || 'HS — แจ้ง ผบ.');
      });
      n += add.length;
    }
    // B3 ค้างรับ: เขียนทับทั้งก้อนทุกรอบ (ไม่ใช่ช่องที่พนักงานกรอก)
    var iv = j.unpaid_iv || [];
    var ivRows = Math.max(sh.getLastRow() - L.docHeader, iv.length, 1);
    sh.getRange(L.docFirst, L.ivCol, ivRows, 3).clearContent();
    if (iv.length) {
      sh.getRange(L.docFirst, L.ivCol, iv.length, 3).setValues(iv.map(function (d) {
        return [d.doc_no, d.customer || '', Number(d.total) || 0];
      }));
      sh.getRange(L.docFirst, L.ivCol + 2, iv.length, 1).setNumberFormat('#,##0.00');
    }
    var counts = j.counts || {};
    sh.getRange(L.cutoff).setValue(j.round === 'cutoff' ? Utilities.formatDate(new Date(j.cutoff_at), TZ, 'HH:mm') +
      ' (ตัดรอบแล้ว)' : 'รอบ 16:30 ยังไม่มา');
    sh.getRange(L.counts).setValue(Object.keys(counts).sort().map(function (k) { return k + ' ' + counts[k]; })
      .join(' · ') + ((j.carried_in || []).length ? ' · ยกมา ' + j.carried_in.length : ''));
    sh.getRange(L.round).setValue(j.round === 'cutoff' ? 'เติมรอบสุดท้ายแล้ว — เลือกช่องทางแถวสีฟ้า · นับเงิน · ส่ง'
      : 'เริ่มทำได้ — 16:30 จะมีรายการเพิ่มต่อท้าย');
    setInputRanges_(sh, n);
    setMeta_({ branch: br, date: iso, ssId: ss.getId(), sheet: sh.getName(), round: j.round,
               cutoffAt: j.cutoff_at, rows: n, locked: false, warnings: j.warnings || [],
               cutoffRows: j.round === 'cutoff' ? n : (meta && meta.cutoffRows) || null });
  } finally {
    lock.releaseLock();
  }
}

// ===================================================================== onEdit (installable ต่อไฟล์)
function onSheetEdit(e) {
  var sh = e.range.getSheet();
  var meta = metaBySheet_(e.source.getId(), sh.getName());
  if (!meta || meta.locked) return;
  var n = nowParts_(), times = config_().times;
  var late = n.date > meta.date || (n.date === meta.date && n.hm >= times.deadline);
  if (late) {
    // แก้หลังเส้นตาย = ไม่นับ: คืนค่าเดิม (แก้ทีละช่อง) แล้วล็อกทันที
    if (e.range.getNumRows() === 1 && e.range.getNumColumns() === 1) {
      if (e.oldValue === undefined) e.range.clearContent(); else e.range.setValue(e.oldValue);
    }
    finalize_(meta.branch, meta.date, 'deadline');
    return;
  }
  if (e.range.getA1Notation() === L.submit && e.range.getValue() === true) trySubmit_(meta, sh);
}

function readTab_(sh, meta) {
  var n = docRowCount_(sh);
  var docs = n ? sh.getRange(L.docFirst, 1, n, L.docCols).getValues().map(function (r) {
    var ch = CHANNELS[String(r[6]).trim()] || null;
    var dd = r[2] instanceof Date ? Utilities.formatDate(r[2], TZ, 'yyyy-MM-dd') : String(r[2]);
    return { doc_no: String(r[1]).trim(), doc_date: dd, type: String(r[3]).trim(), total: Number(r[5]) || 0,
             carried: r[0] === 'ยกมา', channel: ch,
             cash_amount: ch === 'mixed' ? (Number(r[7]) || 0) : (ch === 'cash' ? Number(r[5]) || 0 : 0) };
  }) : [];
  var expenses = sh.getRange(L.docFirst, L.expCol, L.expRows, 3).getValues()
    .filter(function (r) { return String(r[0]).trim() || String(r[1]).trim() || String(r[2]).trim(); })
    .map(function (r) { return { item: String(r[0]).trim(), amount: Number(r[1]) || 0, receipt: String(r[2]).trim() }; });
  var counted = sh.getRange(L.counted).getValue();
  return { docs: docs, expenses: expenses,
           cash_counted: counted === '' ? null : Number(counted),
           preparer: String(sh.getRange(L.preparer).getValue()).trim(),
           qr_image: String(sh.getRange(L.qr).getValue()).trim() };
}

function validate_(t, meta) {
  var err = [];
  if (meta.round !== 'cutoff') err.push('รอรายการรอบ 16:30 ขึ้นก่อน');
  var miss = t.docs.filter(function (d) { return !d.channel; }).length;
  if (miss) err.push('ยังไม่เลือกช่องทาง ' + miss + ' แถว');
  t.docs.forEach(function (d) {
    if (d.channel === 'mixed' && !(d.cash_amount > 0 && d.cash_amount < Math.abs(d.total))) {
      err.push(d.doc_no + ': ผสม ต้องกรอกยอดเงินสดมากกว่า 0 และน้อยกว่ายอดเอกสาร');
    }
  });
  if (t.cash_counted === null || !(t.cash_counted >= 0)) err.push('กรอกเงินสดนับจริง');
  if (!t.preparer) err.push('เลือกผู้จัดทำ');
  t.expenses.forEach(function (e, i) {
    if (!e.item || !(e.amount > 0)) err.push('ค่าใช้จ่ายแถว ' + (i + 1) + ': ต้องมีทั้งรายการและจำนวนเงิน');
  });
  return err;
}

function trySubmit_(meta, sh) {
  var t = readTab_(sh, meta);
  var err = validate_(t, meta);
  if (err.length) {
    sh.getRange(L.submit).setValue(false);
    sh.getRange(L.status).setValue('ส่งไม่ได้: ' + err.slice(0, 4).join(' · ') + (err.length > 4 ? ' …' : ''))
      .setFontColor('#c62828');
    return;
  }
  finalize_(meta.branch, meta.date, 'submit');
}

// ===================================================================== ล็อก + สรุป + out.json
function receiptNames_(br, iso) {
  var id = brCfg_(br).receipt_folder_id, names = {};
  if (!id) return null;
  var it = DriveApp.getFolderById(id).getFiles(), pre = yymmdd_(iso);
  while (it.hasNext()) {
    var name = it.next().getName();
    if (name.indexOf(pre) === 0) { names[name] = true; names[name.replace(/\.[^.]+$/, '')] = true; }
  }
  return names;
}

function finalize_(br, iso, reason) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    var meta = getMeta_(br, iso);
    if (!meta || meta.locked) return;
    var ss = SpreadsheetApp.openById(meta.ssId), sh = ss.getSheetByName(meta.sheet);
    var n = nowParts_();
    var t = readTab_(sh, meta);
    var submitted = reason === 'submit';
    // ล็อกทั้งแท็บก่อน แล้วค่อยคำนวณ — ค่าที่สรุปคือค่า ณ เวลาล็อก
    var p = sh.getProtections(SpreadsheetApp.ProtectionType.SHEET)[0] || sh.protect();
    p.setUnprotectedRanges([]);
    p.addEditor(Session.getEffectiveUser());
    p.removeEditors(p.getEditors().filter(function (u) { return u.getEmail() !== Session.getEffectiveUser().getEmail(); }));
    if (p.canDomainEdit()) p.setDomainEdit(false);
    SpreadsheetApp.flush();

    var rn = receiptNames_(br, iso);
    t.expenses.forEach(function (e) { if (rn && e.receipt) e.receipt_found = !!rn[e.receipt]; });
    var fl = Number(brCfg_(br).float || 0);
    var s = computeSummary(t.docs, t.expenses, t.cash_counted, fl);
    var out = {
      branch: br, date: iso, cutoff_at: meta.cutoffAt, submitted_at: submitted ? n.iso : null,
      locked_at: n.iso, lock_reason: reason, preparer: t.preparer, qr_image: t.qr_image,
      docs: t.docs, expenses: t.expenses, cash_counted: t.cash_counted, float: fl,
      summary: { cash_in: s.cash_in, transfer_in: s.transfer_in, cash_refund: s.cash_refund,
                 cash_expense: s.cash_expense, cash_expected: s.cash_expected, diff: s.diff, deposit: s.deposit },
      unticked: s.unticked, expense_no_receipt: s.expense_no_receipt,
      doc_count_at_cutoff: meta.cutoffRows || t.docs.length, warnings: meta.warnings || [],
    };
    writeOut_(br, iso, out);
    appendSummary_(out);

    sh.getRange(L.status).setFontColor('#1b5e20').setValue(submitted
      ? 'ส่งแล้ว ' + n.hm + ' · ล็อกแล้ว แก้ไม่ได้'
      : 'ล็อกอัตโนมัติ ' + n.hm + ' (' + (reason === 'deadline' ? 'เลยเส้นตาย ' + config_().times.deadline : reason) +
        ') — ยังไม่ได้กดส่ง');
    if (submitted) sh.getRange(L.diff).setValue(s.diff).setNumberFormat('+#,##0.00;-#,##0.00;0.00');  // เผยเฉพาะส่วนต่าง
    meta.locked = true;
    meta.submittedAt = out.submitted_at;
    setMeta_(meta);
    pruneMeta_(iso);
  } finally {
    lock.releaseLock();
  }
}

function writeOut_(br, iso, out) {
  var folder = subFolder_(rootFolder_(), br, true), name = yymmdd_(iso) + '_out.json';
  var body = JSON.stringify(out, null, 1), f = latestFile_(folder, name);
  if (f) f.setContent(body); else folder.createFile(name, body, 'application/json');
}

var SUMMARY_HEAD = ['วันที่', 'สาขา', 'ตัดรอบ', 'ส่งเมื่อ', 'สถานะ', 'ผู้จัดทำ', 'เอกสาร', 'รับเงินสด', 'รับโอน/QR',
  'คืนเงินสด', 'ค่าใช้จ่ายเงินสด', 'float', 'เงินสดที่ควรมี', 'นับจริง', 'ส่วนต่าง', 'ยอดนำฝาก', 'ยังไม่เลือกช่องทาง',
  'ค่าใช้จ่ายไม่มีบิล', 'เตือนจาก Express'];

function summarySheet_() {
  var id = props_().getProperty('SUMMARY_SPREADSHEET_ID'), ss = null;
  if (id) { try { ss = SpreadsheetApp.openById(id); } catch (e) { ss = null; } }
  if (!ss) {
    ss = SpreadsheetApp.create('สรุปรายงานรับเงิน (CTO · ผบ. · Finny เท่านั้น)');
    ss.setSpreadsheetTimeZone(TZ);
    var file = DriveApp.getFileById(ss.getId());
    file.moveTo(subFolder_(rootFolder_(), '_sheets', true));
    file.setSharing(DriveApp.Access.PRIVATE, DriveApp.Permission.NONE);
    file.setShareableByEditors(false);
    (config_().summary_viewers || []).forEach(function (m) { if (m) file.addViewer(m); });
    var sh = ss.getSheets()[0].setName('สรุป');
    sh.getRange(1, 1, 1, SUMMARY_HEAD.length).setValues([SUMMARY_HEAD]).setFontWeight('bold');
    sh.setFrozenRows(1);
    props_().setProperty('SUMMARY_SPREADSHEET_ID', ss.getId());
  }
  return ss.getSheetByName('สรุป') || ss.getSheets()[0];
}

function appendSummary_(o) {
  var s = o.summary;
  summarySheet_().appendRow([o.date, o.branch, o.cutoff_at, o.submitted_at || '', o.submitted_at ? 'ส่งแล้ว' :
    'ล็อกอัตโนมัติ (' + o.lock_reason + ')', o.preparer, o.docs.length, s.cash_in, s.transfer_in, s.cash_refund,
    s.cash_expense, o.float, s.cash_expected, o.cash_counted === null ? '' : o.cash_counted, s.diff, s.deposit,
    o.unticked.join(' '), o.expense_no_receipt.join(' · '),
    (o.warnings || []).map(function (w) { return w.doc_no + ':' + w.issue; }).join(' ')]);
}
