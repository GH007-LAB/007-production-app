// ทดสอบหน้า Fleet007 จริงใน Chromium กับ API ตัวจริง (FakeSB + อีเมลจำลอง)
// usage: node fleet007/tests/test_app.mjs [screenshot_dir]
import { createRequire } from 'module';
import { execSync, spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const shots = process.argv[2];
const PORT = 8775, BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn('python3', [path.join(HERE, 'serve_fixture.py'), String(PORT)], { stdio: 'inherit' });
await new Promise(r => setTimeout(r, 800));
const fail = [];
const ok = (c, m) => { console.log((c ? '  ✅ ' : '  ❌ ') + m); if (!c) fail.push(m); };

try {
  const browser = await chromium.launch();
  const errors = [];
  // พนักงานขาย (ไม่ใช่ แอดมิน/HR/จัดซื้อ) เข้าไม่ได้
  const sp = await browser.newPage();
  sp.on('pageerror', e => errors.push(e.message));
  await sp.addInitScript(() => { localStorage.t = 'tok-sales'; });
  await sp.goto(BASE + '/fleet007'); await sp.waitForSelector('.banner');
  ok((await sp.textContent('.banner')).includes('เฉพาะ แอดมิน / HR / จัดซื้อ'), 'พนักงานขายเปิดแอปไม่ได้');

  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => { localStorage.t = 'tok-hr'; });
  await page.goto(BASE + '/fleet007'); await page.waitForSelector('text=+ เพิ่มรถ');

  // เพิ่มรถ
  await page.click('text=+ เพิ่มรถ');
  await page.fill('#f_plate', '1กข 1234'); await page.fill('#f_prov', 'สกลนคร'); await page.fill('#f_brand', 'Isuzu');
  await page.fill('#f_model', 'D-Max 1.9'); await page.fill('#f_type', 'กระบะ'); await page.fill('#f_year', '2021');
  await page.selectOption('#f_branch', 'SKN'); await page.fill('#f_driver', 'สมชาย');
  await page.click('#dlgSave'); await page.waitForSelector('.plate');
  ok((await page.textContent('.car')).includes('Isuzu D-Max 1.9'), 'เพิ่มรถแล้วขึ้นรายการ');

  // เพิ่ม พรบ. (เกินกำหนด) + ประกัน (อีก 30 วัน) + อื่น ๆ
  const addItem = async (kind, due, extra = {}) => {
    await page.click('.car .acts >> text=+ รายการ');
    await page.selectOption('#i_kind', kind);
    if (extra.other) await page.fill('#i_other', extra.other);
    await page.fill('#i_due', due);
    if (extra.prov) await page.fill('#i_prov', extra.prov);
    await page.click('#dlgSave'); await page.waitForTimeout(300);
  };
  await addItem('พรบ.', '2026-10-15');
  await addItem('ประกันภัย', '2026-11-19', { prov: 'วิริยะ' });
  await addItem('อื่น ๆ', '2027-03-01', { other: 'ใบอนุญาตขนส่ง' });
  const car = await page.textContent('.car');
  ok(car.includes('เกินกำหนด 5 วัน') && car.includes('อีก 30 วัน') && car.includes('ใบอนุญาตขนส่ง'), 'รายการขึ้นพร้อมนับวันถอยหลัง');
  ok(await page.$eval('.car', e => e.classList.contains('overdue')), 'การ์ดรถเป็นสีแดงเมื่อมีรายการเกินกำหนด');
  ok((await page.textContent('.chip.overdue')).startsWith('1'), 'ตัวนับเกินกำหนด = 1');
  if (shots) await page.screenshot({ path: `${shots}/f7_list.png`, fullPage: true });

  // ส่งแจ้งเตือนตอนนี้ → อีเมลถึง hr007
  await page.click('text=ส่งแจ้งเตือนรอบนี้เลย'); await page.waitForSelector('text=✅ ส่ง');
  const mail = await (await fetch(BASE + '/__mail')).json();
  ok(mail.length === 1 && mail[0].to[0] === 'hr007@007metals.com', 'อีเมลแจ้งเตือนส่งถึง hr007@007metals.com');
  ok(mail[0].text.includes('พรบ.') && mail[0].text.includes('ประกันภัย'), 'อีเมลมี พรบ. เกินกำหนด + ประกันใกล้ครบ');

  // ต่ออายุ พรบ. → หายจากเกินกำหนด + มีประวัติ
  await page.click('.item:has-text("พรบ.") >> text=ต่ออายุแล้ว');
  ok(await page.inputValue('#r_due') === '2027-10-15', 'ต่ออายุ: วันใหม่ตั้งให้ +1 ปีอัตโนมัติ');
  await page.fill('#r_amt', '645.21');
  await page.click('#dlgSave'); await page.waitForSelector('text=ประวัติต่ออายุ 1 ครั้ง');
  ok(!(await page.textContent('.car')).includes('เกินกำหนด'), 'ต่ออายุแล้วไม่เกินกำหนด');
  if (shots) { await page.setViewportSize({ width: 390, height: 844 }); await page.screenshot({ path: `${shots}/f7_mobile.png`, fullPage: true }); }

  ok(errors.length === 0, 'ไม่มี JS error' + (errors.length ? ': ' + errors.join(' | ') : ''));
  await browser.close();
} finally {
  srv.kill();
}
console.log(fail.length ? `❌ ${fail.length} ข้อไม่ผ่าน` : 'test_app: ALL OK');
process.exit(fail.length ? 1 : 0);
