// ทดสอบหน้าเว็บ Approve007 จริงใน Chromium (file:// เหมือนเปิดจาก Drive)
// usage: node approve007/tests/test_app.mjs "<All_on_Cloud>/Approve007" [screenshot_dir]
import { createRequire } from 'module';
import { execSync } from 'child_process';
const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');

const dir = process.argv[2], shots = process.argv[3];
const browser = await chromium.launch();
const fail = [];
const ok = (c, m) => { console.log((c ? '  ✅ ' : '  ❌ ') + m); if (!c) fail.push(m); };

for (const vp of [{ width: 1200, height: 900, name: 'desktop' }, { width: 390, height: 844, name: 'mobile' }]) {
  const page = await browser.newPage({ viewport: vp });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('file://' + dir + '/approve007.html');
  await page.selectOption('#br', 'PPS');
  const src = await page.content();
  ok(!/costbook\.js/.test(src.replace(/<!--[\s\S]*?-->/g, '')), `${vp.name}: หน้าเว็บไม่โหลด costbook.js`);
  ok(!/131\.6|110\.2|"cost"/.test(await page.evaluate(() => JSON.stringify(window.PRICEBANDS))), `${vp.name}: ข้อมูลในหน้าไม่มีทุน`);

  // ใส่ราคาในแท็บช่วงราคา → สีเปลี่ยนตามชั้น
  await page.fill('#q', 'Cool 0.35');
  const inp = page.locator('input.price').first();
  await inp.fill('153'); ok(await inp.evaluate(e => e.classList.contains('stand')), `${vp.name}: Zacs Cool @153 = ยืนราคา`);
  await inp.fill('150'); ok(await inp.evaluate(e => e.classList.contains('mgr')), `${vp.name}: @150 = ผจก.`);
  await inp.fill('125'); ok(await inp.evaluate(e => e.classList.contains('gem')), `${vp.name}: @125 = ขอ ผบ.`);
  if (shots) await page.screenshot({ path: `${shots}/a7_bands_${vp.name}.png`, fullPage: vp.name === 'desktop' });

  // ⚡ เช็คไว
  await page.fill('#q', '');
  await page.click('#t_quick');
  await page.fill('#lines', 'ลอน 0.35 zacs cool ขาว 800 ม. 125\nPU 25 ท้องไม้ 120 ม. 105\nสกรู 75 มม. 2000 ตัว 2.5\nPU 25 ฟอยล์ 50 ม.\nของแปลก 10 ชิ้น 99');
  await page.click('text=⚡ เช็คเลย');
  const cellsTxt = await page.locator('#qout tbody tr').allTextContents();
  ok(/Zacs Cool/.test(cellsTxt[0]) && /ขอ ผบ/.test(cellsTxt[0]), `${vp.name}: บรรทัด 1 จับคู่ Zacs Cool → ขอ ผบ.`);
  ok(/ลายไม้/.test(cellsTxt[1]) && /ผจก/.test(cellsTxt[1]), `${vp.name}: บรรทัด 2 PU ท้องไม้ @105 → ผจก.`);
  ok(/ไม่รู้จัก|ถามก่อน/.test(cellsTxt[2]), `${vp.name}: บรรทัด 3 สกรู (ไม่มีในตาราง PPS) → ไม่ฟันธง`);
  ok(/ฟอยล์/.test(cellsTxt[3]) && /ลดเองได้ถึง/.test(cellsTxt[3]), `${vp.name}: บรรทัด 4 ไม่ใส่ราคา → บอกราคาต่ำสุดที่ลดเองได้`);
  ok(/ไม่รู้จัก/.test(cellsTxt[4]), `${vp.name}: บรรทัด 5 สินค้าไม่รู้จัก → ไม่ฟันธง`);
  ok(/เช็คซ้ำจากบิล Express/.test(await page.innerText('#qout')), `${vp.name}: มีข้อความกำกับชั้น A`);
  if (shots) await page.screenshot({ path: `${shots}/a7_quick_${vp.name}.png`, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  ok(!overflow, `${vp.name}: ไม่มี horizontal scroll`);
  ok(errors.length === 0, `${vp.name}: ไม่มี JS error ${errors.join(' | ')}`);
  await page.close();
}

// ตารางหมดอายุ → แถบแดง
const page = await browser.newPage();
await page.addInitScript(() => { const D = Date; window.Date = class extends D { constructor(...a) { super(...(a.length ? a : [D.now() + 10 * 864e5])); } static now() { return D.now() + 10 * 864e5; } }; });
await page.goto('file://' + dir + '/approve007.html');
ok(/หมดอายุ ห้ามใช้/.test(await page.innerText('#banner')), 'ตารางเกิน 7 วัน → แถบแดง "หมดอายุ ห้ามใช้"');
await page.close();
// ---------- โหมดออนไลน์: หน้าเว็บ → API ตัวจริง (engine เดียวกัน) บน Supabase จำลอง ----------
{
  const { spawn } = await import('child_process');
  const { mkdtempSync, copyFileSync } = await import('fs');
  const { tmpdir } = await import('os');
  const here = new URL('.', import.meta.url).pathname;
  const proc = spawn('python3', [here + 'serve_api_fixture.py'], { stdio: ['ignore', 'pipe', 'inherit'] });
  const base = await new Promise((res, rej) => { proc.stdout.once('data', d => res(d.toString().trim())); proc.once('exit', c => rej(new Error('api exit ' + c))); });
  const bare = mkdtempSync(tmpdir() + '/a7online-');                     // ไม่มี pricebands.js → ต้องโหลดจาก API
  copyFileSync(dir + '/approve007.html', bare + '/approve007.html');
  for (const [tok, role] of [['tok-sale', 'SALES'], ['tok-gem', 'GEM']]) {
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const apiBodies = []; page.on('response', async r => { if (r.url().includes('/api/approve/')) apiBodies.push(await r.text()); });
    await page.addInitScript(([b, t]) => { window.__A7_API__ = b; window.__A7_TOKEN__ = t; localStorage.setItem('a7_br', '"PPS"'); }, [base, tok]);
    await page.goto('file://' + bare + '/approve007.html');
    await page.waitForSelector('#rows tr');
    ok(/ใช้ได้ถึง/.test(await page.innerText('#banner')), `${role}: โหลดช่วงราคาจาก API ได้`);
    await page.click('#t_so');
    await page.fill('#soNum', 'so6903141');
    await page.click('#soForm button[type=submit]');
    await page.waitForSelector('#soOut .sum');
    ok(/หลายสาขา/.test(await page.innerText('#soOut')), `${role}: SO ซ้ำข้ามสาขา → ให้เลือกสาขา`);
    await page.click('#soOut button:has-text("PPS")');
    await page.waitForFunction(() => /เกรด/.test(document.querySelector('#soOut').innerText));
    const t = await page.innerText('#soOut');
    ok(/เกรด X/.test(t) && /0%/.test(t), `${role}: SO6903141 PPS → เกรด X 0%`);
    ok(role === 'GEM' ? /GP -?\d/.test(t) : !/GP -?\d/.test(t), `${role}: ${role === 'GEM' ? 'เห็น GP' : 'ไม่เห็น GP'}`);
    await page.click('#t_quick');
    await page.fill('#lines', 'ลอน 0.35 zacs cool ขาว 800 ม. 125\nสกรู 75 มม. 2000 ตัว 2.5\nPU 25 ท้องไม้ 300 ม. 100');
    await page.click('#btnGrade');
    await page.waitForSelector('#qout .sum');
    ok(/เกรด X/.test(await page.innerText('#qout')), `${role}: เช็คไว (เกรดทั้งบิล) ตรงกับบิลจริง = X`);
    if (role === 'SALES') {
      const all = apiBodies.join('\n');
      ok(!/"gp_pct"|"cost"|131\.6|72\.8|2\.78/.test(all), 'SALES: network response ไม่มีทุน/GP');
      if (shots) await page.screenshot({ path: `${shots}/a7_online_quick.png`, fullPage: true });
      await page.click('#t_so'); if (shots) await page.screenshot({ path: `${shots}/a7_online_so.png`, fullPage: true });
    }
    ok(errors.length === 0, `${role}: ไม่มี JS error ${errors.join(' | ')}`);
    await page.close();
  }
  proc.kill();
}
await browser.close();
console.log(fail.length ? `APP TEST FAIL (${fail.length})` : 'APP TEST OK');
process.exit(fail.length ? 1 : 0);
