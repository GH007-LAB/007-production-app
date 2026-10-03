// ทดสอบหน้า Sales007 จริงใน Chromium กับ API ตัวจริง (FakeSB) — มือถือ + เดสก์ท็อป
// usage: node salesreport007/tests/test_app.mjs [screenshot_dir]
import { createRequire } from 'module';
import { execSync, spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const shots = process.argv[2];
const PORT = 8765, BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn('python3', [path.join(HERE, 'serve_fixture.py'), String(PORT)], { stdio: 'inherit' });
await new Promise(r => setTimeout(r, 800));
const fail = [];
const ok = (c, m) => { console.log((c ? '  ✅ ' : '  ❌ ') + m); if (!c) fail.push(m); };
const post = (p, b) => fetch(BASE + p, { method: 'POST', body: JSON.stringify(b) }).then(r => r.json());
const clock = at => post('/__clock', { at });
const doc = (no, type, total, extra = {}) => ({ doc_no: no, type, doc_date: '2026-10-05', customer: 'ลูกค้า ' + no, total, ...extra });

try {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => { localStorage.t = localStorage.t || 'tok-skn'; });
  const reload = async () => { await page.goto(BASE + '/sales007'); await page.waitForSelector('h2'); };

  await clock('2026-10-05T09:00:00+07:00');
  await post('/__push', { branch: 'SKN', docs: [doc('IV6910001', 'IV', 12000, { remain: 12000 }), doc('AI6910001', 'AI', 5000), doc('SR6910001', 'SR', 450)] });
  await reload();
  ok(await page.locator('.doc.need').count() === 2, 'AI + ลดหนี้ ขึ้นรอเลือกช่องทาง');
  ok((await page.textContent('main')).includes('ค้างรับ'), 'IV ขึ้น live สถานะค้างรับ');
  ok(!(await page.isVisible('#tabs')) && !(await page.isVisible('#br')), 'พนักงานไม่เห็นแท็บตรวจ/ตัวเลือกสาขา');
  ok(!/ควรมี|5,000\.00 \+|รวมเงินสด/.test(await page.textContent('main')), 'ไม่มียอดรวม/เงินสดที่ควรมีบนหน้าพนักงาน');

  // ตัดชำระ IV → RE ขึ้น → เลือก QR
  await clock('2026-10-05T10:00:00+07:00');
  await post('/__push', { branch: 'SKN', docs: [doc('RE6910001', 'RE', 12000, { refs: ['IV6910001'] })] });
  await reload();
  ok(await page.locator('#doc-RE6910001 button', { hasText: 'QR Code' }).count() === 1, 'RE ขึ้นพร้อมปุ่ม เงินสด / เงินโอน / QR Code');
  ok((await page.textContent('main')).includes('ตัดชำระแล้ว RE6910001'), 'IV เปลี่ยนเป็นตัดชำระแล้ว');
  await page.click('#doc-RE6910001 button:has-text("QR Code")');
  await page.waitForSelector('#doc-RE6910001 button.on');
  await page.click('#doc-AI6910001 button:has-text("เงินสด")');
  await page.waitForSelector('#doc-AI6910001 button.on');
  await page.click('#doc-SR6910001 button:has-text("หักใน RE")');
  await page.waitForSelector('#doc-SR6910001 button.on');
  ok((await page.textContent('h2')).includes('ครบแล้ว'), 'นับใบที่ยังไม่เลือก = ครบแล้ว');

  // รายจ่าย + รูปบิล (ย่อรูปในเบราว์เซอร์ก่อนส่ง)
  await page.selectOption('#e_cat', 'น้ำมัน/ค่าเดินทาง');
  await page.fill('#e_amt', '120'); await page.fill('#e_item', 'เติมน้ำมันรถส่งของ'); await page.fill('#e_payee', 'ปตท.');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==', 'base64');
  await page.setInputFiles('#e_photo', { name: 'bill.png', mimeType: 'image/png', buffer: png });
  await page.click('text=+ เพิ่มรายจ่าย');
  await page.waitForSelector('text=เติมน้ำมันรถส่งของ');
  ok((await page.textContent('main')).includes('📷 มีรูป'), 'รายจ่ายพร้อมรูปบิลบันทึกแล้ว');
  await page.fill('#e_amt', '60'); await page.fill('#e_item', 'ข้าวคนงาน');
  await page.click('text=+ เพิ่มรายจ่าย');
  await page.waitForSelector('text=ข้าวคนงาน');
  ok((await page.textContent('main')).includes('ไม่มีรูปบิล = ไม่นับ'), 'รายจ่ายไม่มีรูปถูกเตือน');
  ok(await page.locator('#counted').count() === 0, 'ก่อน 16:30 ยังกรอกยอดนับ/ส่งไม่ได้');
  if (shots) await page.screenshot({ path: `${shots}/s7_day_mobile.png`, fullPage: true });

  // หลังตัดรอบ: บิลใหม่ไปวันถัดไป · ส่ง → เห็นเฉพาะส่วนต่าง
  await clock('2026-10-05T16:40:00+07:00');
  await post('/__push', { branch: 'SKN', docs: [doc('AI6910002', 'AI', 700)] });
  await reload();
  ok((await page.textContent('main')).includes('ออกหลังตัดรอบ'), 'AI หลัง 16:30 แยกไปส่วนวันถัดไป');
  await page.fill('#counted', '5300');
  page.once('dialog', d => d.accept());
  await page.click('text=ส่งรายงาน');
  await page.waitForSelector('.sum.ok');            // ไม่ใช้ text=ส่งแล้ว — ชนกับคำเตือน "กดส่งแล้วแก้ไม่ได้"
  const txt = await page.textContent('main');
  ok(txt.includes('-80.00'), 'หลังส่งเห็นส่วนต่าง −80 (500 + 5000 − 120 = 5380 · นับ 5300)');
  ok(!txt.includes('5,380'), 'ไม่เผยเงินสดที่ควรมี');
  ok(await page.locator('.ch button:not([disabled])').count() === 0, 'ล็อกแล้วกดเปลี่ยนช่องทางไม่ได้');
  if (shots) await page.screenshot({ path: `${shots}/s7_submitted_mobile.png`, fullPage: true });

  // ผบ./Finny: แท็บตรวจ
  const ap = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  ap.on('pageerror', e => errors.push(e.message));
  await ap.addInitScript(() => { localStorage.t = 'tok-finny'; });
  await clock('2026-10-06T09:00:00+07:00');
  await ap.goto(BASE + '/sales007'); await ap.waitForSelector('#t_audit:visible');
  await ap.click('#t_audit'); await ap.waitForSelector('text=เงินสดที่ควรมี');
  const at = await ap.textContent('main');
  ok(at.includes('5,380.00') && at.includes('12,000.00'), 'หน้าตรวจเห็นเงินสดที่ควรมี + ยอด QR');
  ok(at.includes('รายจ่ายไม่มีบิล (ไม่นับ): ข้าวคนงาน'), 'หน้าตรวจเตือนรายจ่ายไม่มีบิล');
  ok(at.includes('1 ใบ · 700.00'), 'หน้าตรวจเห็นเอกสารหลังตัดรอบ');
  if (shots) await ap.screenshot({ path: `${shots}/s7_audit.png`, fullPage: true });

  ok(errors.length === 0, 'ไม่มี JS error' + (errors.length ? ': ' + errors.join(' | ') : ''));
  await browser.close();
} finally {
  srv.kill();
}
console.log(fail.length ? `❌ ${fail.length} ข้อไม่ผ่าน` : 'test_app: ALL OK');
process.exit(fail.length ? 1 : 0);
