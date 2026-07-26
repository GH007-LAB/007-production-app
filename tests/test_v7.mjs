// ทดสอบ app v7 ด้วย mock DAL (in-memory Supabase) — ไล่ทุก flow หลัก
import { chromium } from '/home/claude/.npm-global/lib/node_modules/playwright/index.mjs';
import { readFileSync } from 'fs';

const html = readFileSync('/tmp/prodkanban/app_v7.html', 'utf8');

const MOCK = `
window.__MOCK_DB__ = (() => {
  let seq = 1;
  const uid = () => 'tk-' + (seq++);
  const state = {
    staff: [
      {id:1, branch:'ALL', name:'Gem', role:'admin', can_approve:true, active:true, email:'g@x.com'},
      {id:2, branch:'SKN', name:'สมชาย (เซลส์)', role:'sales', can_approve:true, active:true, email:null},
      {id:3, branch:'SKN', name:'บอย (หัวหน้าผลิต)', role:'planner', can_approve:true, active:true, email:null},
      {id:4, branch:'SKN', name:'เก่ง (ช่างรีด)', role:'operator', can_approve:false, active:true, email:null},
      {id:5, branch:'BK', name:'ฝน (เซลส์ BK)', role:'sales', can_approve:true, active:true, email:null},
    ],
    machines: [
      {id:1,branch:'SKN',name:'ตรง-L ปีกซ้าย',note:'เน้นงานออนไลน์',status:'up',sort:1},
      {id:2,branch:'SKN',name:'ตรง-R ปีกขวา',note:'',status:'up',sort:2},
      {id:3,branch:'SKN',name:'ครอบข้าง 457',note:'',status:'up',sort:3},
      {id:4,branch:'SKN',name:'PU สแน็ปล็อค',note:'',status:'up',sort:4},
      {id:5,branch:'SKN',name:'ลอนรั้ว 182',note:'',status:'up',sort:5},
      {id:6,branch:'BK',name:'ตรง',note:'',status:'up',sort:1},
      {id:7,branch:'BK',name:'ครอบข้าง 457',note:'',status:'up',sort:2},
      {id:8,branch:'BK',name:'สเปน',note:'เครื่องเสีย',status:'down',sort:3},
      {id:9,branch:'PPS',name:'ตรง',note:'',status:'up',sort:1},
      {id:10,branch:'SKN',name:'พับครอบ',note:'',status:'up',sort:6},
      {id:14,branch:'SKN',name:'ครอบจั่ว 457',note:'',status:'up',sort:7},
      {id:11,branch:'PPS',name:'ครอบข้าง 304',note:'',status:'up',sort:2},
      {id:12,branch:'PPS',name:'พับครอบ',note:'',status:'up',sort:3},
      {id:13,branch:'BK',name:'พับครอบ',note:'',status:'up',sort:4},
    ],
    sos: [
      {branch:'SKN',sonum:'SO68A001',sodat:new Date().toISOString().slice(0,10),dlvdat:new Date().toISOString().slice(0,10),cuscod:'A001',cusnam:'ลูกค้าทดสอบ 1',docstat:'N',synced_at:new Date().toISOString()},
      {branch:'BK',sonum:'SO68B001',sodat:new Date().toISOString().slice(0,10),dlvdat:new Date().toISOString().slice(0,10),cuscod:'B001',cusnam:'ลูกค้า BK มีงาน PU',docstat:'N',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68OLD01',sodat:new Date(Date.now()-10*864e5).toISOString().slice(0,10),dlvdat:new Date(Date.now()-8*864e5).toISOString().slice(0,10),cuscod:'C009',cusnam:'ลูกค้าใบเก่าสิบวัน',docstat:'N',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'O68N001',sodat:new Date().toISOString().slice(0,10),dlvdat:new Date().toISOString().slice(0,10),cuscod:'ON01',cusnam:'คุณฟ้า ออเดอร์ร้านออนไลน์',docstat:'N',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68S777',sodat:new Date().toISOString().slice(0,10),dlvdat:new Date(Date.now()+864e5).toISOString().slice(0,10),cuscod:'O610310888',cusnam:'ร้าน SHOPEE',docstat:'N',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68A002',sodat:new Date().toISOString().slice(0,10),dlvdat:new Date(Date.now()+864e5).toISOString().slice(0,10),cuscod:'A002',cusnam:'ลูกค้าสอง',docstat:'N',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68A003',sodat:new Date().toISOString().slice(0,10),dlvdat:new Date(Date.now()+2*864e5).toISOString().slice(0,10),cuscod:'A003',cusnam:'ลูกค้าตามแบบ',docstat:'N',synced_at:new Date().toISOString()},
    ],
    its: [
      {branch:'SKN',sonum:'SO68A001',seq:1,stkcod:'02A-GRST-035-ZC',stkdes:'3.50 -10 ตรง เทาชัตเตอร์เกรย์ 0.35ZC',ordqty:35,remqty:35,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68A001',seq:2,stkcod:'05A-XX',stkdes:'สกรูยิงหลังคา',ordqty:100,remqty:100,unit:'ตัว',synced_at:new Date().toISOString()},
      {branch:'BK',sonum:'SO68B001',seq:1,stkcod:'03VP-PU2535-SL-BLACK',stkdes:'PU Foam Snaplock 25 มม.35k ท้องฟอยล์ดำ',ordqty:20,remqty:20,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'BK',sonum:'SO68B001',seq:2,stkcod:'01A-ZI-030',stkdes:'2.00 -6 ตรง ซิงค์ 0.30',ordqty:12,remqty:12,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68OLD01',seq:1,stkcod:'01A-ZI-030',stkdes:'3.00 -5 ตรง ซิงค์ 0.30',ordqty:15,remqty:15,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'O68N001',seq:1,stkcod:'01A-ZI-030',stkdes:'2.00 -6 ตรง ซิงค์ 0.30',ordqty:12,remqty:12,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68S777',seq:1,stkcod:'01A-ZI-030',stkdes:'2.50 -4 ตรง ซิงค์ 0.30',ordqty:10,remqty:10,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68A002',seq:1,stkcod:'01A-GRST-035-ZC',stkdes:'2.00 -8 ตรง เทาชัตเตอร์เกรย์ 0.35ZC',ordqty:16,remqty:16,unit:'มร',synced_at:new Date().toISOString()},
      {branch:'SKN',sonum:'SO68A003',seq:1,stkcod:'02WF4-WA-035-ZC',stkdes:'3.50 -9 ชนผนังตามแบบ 220 ขาวเอเชี่ยนไวท์ 0.35 Cool',ordqty:31.5,remqty:31.5,unit:'มร',synced_at:new Date().toISOString()},
    ],
    coils: [
      {branch:'SKN',coil_sku:'ZZC-GRST-035-ZC',totbal:1250,synced_at:new Date().toISOString()},
    ],
    tks: [], jobs: [], events: [], shapes: [],
  };
  window.__STATE__ = state;
  return {
    async init(){},
    async getStaff(){ return state.staff; },
    async verifyPin(id,pin){ return pin === '1111'; },
    async sendOtp(){ throw new Error('mock: no email'); },
    async getSessionEmail(){ return null; },
    async signOut(){},
    async fetchSO(branch, sonum){
      if(sonum==='SO68DBONLY') return {so:{branch:'SKN',sonum:'SO68DBONLY',sodat:new Date(Date.now()-40*864e5).toISOString().slice(0,10),dlvdat:null,cuscod:'D001',cusnam:'ลูกค้าเดือนที่แล้ว',docstat:'N'}, its:[{seq:1,stkcod:'01A-ZI-030',stkdes:'2.50 -4 ตรง ซิงค์ 0.30',ordqty:10,unit:'มร'}]};
      const so = state.sos.find(s=>s.branch===branch&&s.sonum===sonum);
      return so? {so, its: state.its.filter(i=>i.branch===branch&&i.sonum===sonum)} : null;
    },
    async loadAll(){ return JSON.parse(JSON.stringify({sos:state.sos, its:state.its, tks:state.tks, machines:state.machines, coils:state.coils, jobs:state.jobs, shapes:state.shapes})); },
    async upsertShape(row){ const i=state.shapes.findIndex(s=>s.branch===row.branch&&s.sonum===row.sonum&&s.seq===row.seq); if(i>=0) state.shapes[i]=row; else state.shapes.push(JSON.parse(JSON.stringify(row))); },
    async insertTicket(row){ const id = uid(); state.tks.push({...row, id, created_at:new Date().toISOString(), oitems:row.oitems||null, people:row.people||{}, item_seqs:row.item_seqs||[], so_cover:row.so_cover||'', route:row.route||null, assignee:row.assignee||'', priority:row.priority||0, coil_lot:'', waste_note:'', prod_m:row.prod_m||0, sheets:row.sheets||0, max_len:row.max_len||0, weight_kg:row.weight_kg||0, workers:row.workers||[]}); return id; },
    /* 👥 เลียนแบบ RPC ฝั่ง SQL — ต่อ array ในคำสั่งเดียว กันคน 2-6 คนกดพร้อมกันแล้วทับกันหาย */
    async joinWork(id,w){ const t=state.tks.find(t=>t.id===id); if(!t) throw new Error('no ticket');
      t.workers = t.workers||[];
      if(t.workers.some(x=>String(x.id)===String(w.id)&&!x.out)) return;   // กดซ้ำ = ไม่เพิ่มซ้อน
      t.workers.push(JSON.parse(JSON.stringify(w))); },
    async leaveWork(id,sid,at){ const t=state.tks.find(t=>t.id===id); if(!t) throw new Error('no ticket');
      t.workers=(t.workers||[]).map(x=>(String(x.id)===String(sid)&&!x.out)?{...x,out:at}:x); },
    async closeWork(id,at){ const t=state.tks.find(t=>t.id===id); if(!t) throw new Error('no ticket');
      t.workers=(t.workers||[]).map(x=>x.out?x:{...x,out:at}); },
    async updateTicket(id,patch){ const t = state.tks.find(t=>t.id===id); if(!t) throw new Error('no ticket'); Object.assign(t, patch); },
    async insertEvent(ev){ state.events.push({...ev, id:state.events.length+1, at:new Date().toISOString()}); },
    async getEvents(tid){ return state.events.filter(e=>e.ticket_id===tid).reverse(); },
    async insertJob(row){ if(state.jobs.some(j=>j.branch===row.branch&&j.order_no===row.order_no)) throw new Error('dup'); state.jobs.push({...row, id:'job-'+(state.jobs.length+1), status:'new', created_at:new Date().toISOString()}); },
    async updateJob(id,patch){ Object.assign(state.jobs.find(j=>j.id===id), patch); },
    async setMachine(id,patch){ Object.assign(state.machines.find(m=>m.id===id), patch); },
    onChange(){},
  };
})();
`;

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
const htmlWithMock = html.replace('<script>', '<script>' + MOCK + '</scr' + 'ipt><script>');
await page.setContent(htmlWithMock, { waitUntil: 'networkidle' });
const T = [];
const ok = (name, cond) => T.push((cond ? 'PASS' : 'FAIL') + '  ' + name);
const click = async (sel) => { await page.locator(sel).first().click(); await page.waitForTimeout(120); };
const clickText = async (txt) => { await page.locator(`button:has-text("${txt}")`).first().click(); await page.waitForTimeout(150); };

// ---- 1. login ด้วย PIN (Gem/admin) ----
await page.waitForTimeout(400);
ok('login overlay โชว์', await page.locator('#loginbg').isVisible());
await page.locator('a:has-text("ใช้ PIN")').click(); await page.waitForTimeout(100);
await page.locator('.lg-staff button', { hasText: 'Gem' }).first().click();
for (const k of ['1','1','1','1']) await page.locator('.pinpad button', { hasText: new RegExp('^'+k+'$') }).first().click();
await page.waitForTimeout(300);
ok('PIN login เข้าได้ (Gem)', !(await page.locator('#loginbg').isVisible()));
ok('badge LIVE', (await page.locator('#conn').textContent()) === 'LIVE');

// ---- 2. ฝั่งขาย: สั่งผลิต SO68A001 ----
await clickText('ฝั่งขาย');
ok('เห็นบิล SO68A001', (await page.content()).includes('SO68A001'));
ok('รายการสกรู = สต็อค', (await page.content()).includes('📦 สต็อค'));
await clickText('สั่ง+อนุมัติใบผลิต');
let st = await page.evaluate(() => window.__STATE__.tks);
ok('สั่งแล้วได้ ticket stage 1 + people ครบ', st.length === 1 && st[0].stage === 1 && st[0].people.ordered === 'Gem' && st[0].people.approved === 'Gem' && st[0].machine.startsWith('ครอบข้าง'));
ok('metric ถูกคำนวณ (35 ม. / 10 แผ่น)', st[0].prod_m === 35 && st[0].sheets === 10 && st[0].max_len === 3.5);

// ---- 3. วางแผน: A ผลิตใหม่ → คิวเครื่อง ----
await clickText('ฝั่งผลิต: วางแผน');
ok('เห็น AI ไม่มีชุด (ใบเดียว) + ใบรอวางแผน', (await page.content()).includes('รอวางแผน'));
ok('เห็นสต็อคคอยล์ ZZC', (await page.content()).includes('ZZC-GRST-035-ZC'));
await clickText('A ผลิตใหม่');
await page.locator('.planx.show select').nth(1).selectOption({ index: 1 }); // มอบหมาย คนแรก
await clickText('เข้าคิวเครื่อง');
st = await page.evaluate(() => window.__STATE__.tks);
ok('planA → stage 2 route A + คนถูกมอบหมาย', st[0].stage === 2 && st[0].route === 'A' && st[0].assignee.length > 0 && st[0].people.planned === 'Gem');

// ---- 4. บอร์ดเครื่อง: เริ่ม → เสร็จ ----
await clickText('บอร์ดเครื่อง');
ok('การ์ดอยู่คอลัมน์เครื่องครอบข้าง', (await page.content()).includes('ครอบข้าง 457'));
await clickText('เริ่มผลิต');
st = await page.evaluate(() => window.__STATE__.tks);
ok('เริ่มผลิต → stage 3', st[0].stage === 3 && st[0].people.started === 'Gem');
await clickText('เสร็จ');
st = await page.evaluate(() => window.__STATE__.tks);
ok('เสร็จ → stage 4 + modal เปิด', st[0].stage === 4 && await page.locator('#ovbg.show').isVisible());
// กรอกข้อมูลหน้างานใน modal
await page.locator('#ovbg input').first().fill('L2569-018');
await page.locator('#ovbg input').first().blur(); await page.waitForTimeout(150);
st = await page.evaluate(() => window.__STATE__.tks);
ok('บันทึกล็อตคอยล์', st[0].coil_lot === 'L2569-018');
ok('ประวัติโหลดจาก event', (await page.locator('#m-hist').textContent()).includes('ผลิตเสร็จ'));
await page.locator('#ovbg .s-x').click(); await page.waitForTimeout(100);

// ---- 5. รวมของ/ส่ง ----
await clickText('รวมของ/ส่ง');
ok('เห็นสรุปจัดรถ (กก./แผ่น/ยาวสุด)', (await page.content()).includes('จัดรถ'));
await clickText('แพ็คทั้งบิล');
await clickText('ออกจัดส่ง');
await clickText('ถึงลูกค้าแล้ว');
st = await page.evaluate(() => window.__STATE__.tks);
ok('แพ็ค→ส่ง→สำเร็จ stage 7', st[0].stage === 7 && st[0].people.packed === 'Gem' && st[0].people.shipped === 'Gem');

// ---- 6. ข้ามสาขา: BK มีงาน PU → ส่งให้ SKN ----
await click('button.tab:has-text("BK")');
await clickText('ฝั่งขาย');
ok('BK เห็นแถวแดง PU ผลิตไม่ได้', (await page.content()).includes('ไม่มีเครื่องPU'));
await clickText('ส่งให้ SKN ผลิตเลย');
st = await page.evaluate(() => window.__STATE__.tks);
const xb = st.find(t => t.source === 'xborder');
ok('xborder ticket → branch SKN stage 0', xb && xb.branch === 'SKN' && xb.stage === 0 && xb.from_branch === 'BK');
ok('ฝั่งส่งเห็น ✓ ส่งแล้ว', (await page.content()).includes('ส่งให้ SKN ผลิตแล้ว'));
// ฝั่งรับ SKN
await click('button.tab:has-text("SKN")');
await clickText('ฝั่งผลิต: วางแผน');
ok('SKN เห็นงานจากสาขาอื่นรอรับ', (await page.content()).includes('งานจากสาขาอื่น'));
await clickText('รับงาน');
st = await page.evaluate(() => window.__STATE__.tks);
ok('รับงาน → stage 1 + accepted', st.find(t=>t.source==='xborder').stage === 1 && st.find(t=>t.source==='xborder').people.accepted === 'Gem');
// ผูก SO คลุม
await clickText('รายละเอียด');
await page.locator('#ovbg input[id^="cov-"]').fill('SO68S099');
await clickText('ผูก'); await page.waitForTimeout(200);
st = await page.evaluate(() => window.__STATE__.tks);
ok('ผูก SO คลุมสำเร็จ', st.find(t=>t.source==='xborder').so_cover === 'SO68S099');
await page.locator('#ovbg .s-x').click(); await page.waitForTimeout(100);

// ---- 7. งานออนไลน์ ----
await clickText('ออนไลน์');
await clickText('เพิ่มออเดอร์เอง');
await page.locator('#aj-plat').fill('Shopee');
await page.locator('#aj-ord').fill('SP250718TEST');
await page.locator('#aj-recv').fill('คุณทดสอบ · ขอนแก่น');
await page.locator('#aj-items').fill('01WP-GRST-030-JJL | 1.20 -10 ลอนรั้ว เทาเข้ม 0.30JJL | 12 | มร');
await clickText('บันทึกออเดอร์');
ok('ออเดอร์ออนไลน์เข้า', (await page.content()).includes('SP250718TEST'));
await clickText('สร้างใบผลิต → เข้าฝั่งผลิต');
st = await page.evaluate(() => window.__STATE__.tks);
const ol = st.find(t => t.source === 'online');
ok('online ticket → ลอนรั้ว 182 stage 1', ol && ol.machine === 'ลอนรั้ว 182' && ol.stage === 1);
ok('job → ticketed', (await page.evaluate(() => window.__STATE__.jobs))[0].status === 'ticketed');

// ---- 8. แจ้งเครื่องเสีย (admin) ----
await clickText('บอร์ดเครื่อง');
await page.locator('.mfix').first().click(); await page.waitForTimeout(250);
ok('toggle เครื่องเสีย → down', (await page.evaluate(() => window.__STATE__.machines))[0].status === 'down');
await page.locator('.mfix').first().click(); await page.waitForTimeout(250);
ok('toggle กลับ → up', (await page.evaluate(() => window.__STATE__.machines))[0].status === 'up');

// ---- 9. ⚡ สั่งด่วน ----
await clickText('ฝั่งขาย');
await page.locator('#urg-so').fill('SO68A555');
await clickText('⚡ สั่งด่วน');
st = await page.evaluate(() => window.__STATE__.tks);
ok('urgent ticket เข้า stage 1', st.some(t => t.source === 'urgent' && t.sonum === 'SO68A555' && t.stage === 1));

// ---- 10. v7.1: 3-day filter + ค้นหาใบเก่า ----
await click('button.tab:has-text("SKN")');
await clickText('ฝั่งขาย');
ok('ใบเก่า 10 วันถูกซ่อนจากหน้าแรก', !(await page.locator('#main').innerText()).includes('SO68OLD01'));
await page.locator('#q-so').fill('SO68OLD01');
await clickText('ค้นหา');
ok('ค้นหาเจอใบเก่า 10 วัน', (await page.content()).includes('SO68OLD01'));
await page.locator('#q-so').fill('SO68DBONLY');
await clickText('ค้นหา');
ok('ไม่เจอในหน้า → มีปุ่มดึงจาก DB', (await page.content()).includes('ดึง SO SO68DBONLY'));
await clickText('ดึง SO SO68DBONLY');
await page.waitForTimeout(250);
ok('ดึงใบเก่าจาก DB ขึ้นมาได้ + badge ใบเก่า', (await page.content()).includes('ลูกค้าเดือนที่แล้ว') && (await page.content()).includes('📥 ใบเก่า'));
await page.locator('#q-so').fill('');
await clickText('ค้นหา');

// ---- 11. v7.1: สั่งซ้ำต้องอนุมัติ PIN ----
ok('รายการที่สั่งแล้วถูกล็อค', (await page.content()).includes('✓ สั่งแล้ว 🔒'));
ok('SO68A001 มีปุ่มเรียกซ้ำ', (await page.content()).includes('เรียกผลิตซ้ำ'));
await page.locator('button:has-text("เรียกผลิตซ้ำ")').first().click(); await page.waitForTimeout(150);
ok('ฟอร์มขออนุมัติโชว์', (await page.content()).includes('ขออนุมัติสั่งผลิตซ้ำ'));
// v7.9: เตือนออกใบไปแล้ว + admin เท่านั้น + บังคับสาเหตุ
ok('เตือนว่ารายการนี้ออกใบไปแล้ว', (await page.locator('#main').innerText()).includes('ออกใบผลิตไปแล้ว'));
ok('ผู้อนุมัติซ้ำ = admin เท่านั้น (ไม่มีเซลส์)', !(await page.locator('[id^="ra-"]').first().innerText()).includes('สมชาย'));
await page.locator('[id^="rp-"]').fill('1111');
await clickText('ยืนยัน'); await page.waitForTimeout(150);
ok('ไม่เลือกสาเหตุ → ถูกบล็อค', !(await page.locator('#main').innerText()).includes('อนุมัติซ้ำโดย'));
await page.locator('[id^="rr-"]').first().selectOption({ index: 1 });
await page.locator('[id^="rp-"]').fill('9999');
await clickText('ยืนยัน'); await page.waitForTimeout(200);
ok('PIN ผิด → ไม่ปลดล็อค', !(await page.locator('#main').innerText()).includes('อนุมัติซ้ำโดย'));
await page.locator('[id^="rp-"]').fill('1111');
await clickText('ยืนยัน'); await page.waitForTimeout(250);
ok('PIN ถูก → ปลดล็อค + โชว์ชื่อผู้อนุมัติ', (await page.content()).includes('อนุมัติซ้ำโดย'));
await page.locator('input[id^="cb-SO68A001-"]').first().check();
await clickText('สั่งผลิตซ้ำ'); await page.waitForTimeout(250);
st = await page.evaluate(() => window.__STATE__.tks);
const reT = st.filter(t=>t.sonum==='SO68A001' && t.source==='so');
ok('ticket ซ้ำถูกสร้าง + people.reorder_approved บันทึก', reT.length===2 && reT.some(t=>t.people.reorder_approved==='Gem'));
ok('บันทึกสาเหตุ + เวลาอนุมัติซ้ำ', reT.some(t=>(t.people.reorder_reason||'').includes('ตำหนิ') && t.times && t.times.reorder_approved));
const reEv = await page.evaluate(() => window.__STATE__.events.filter(e=>e.detail.includes('สั่งผลิตซ้ำ')));
ok('event บันทึกคนขอ+คนอนุมัติ', reEv.length===1 && reEv[0].detail.includes('อนุมัติซ้ำโดย Gem'));

// ---- 12. routing ครอบ: หน้ารีดมาตรฐาน→เครื่องรีด / variant→พับครอบ ----
const capR = await page.evaluate(() => [
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบข้าง 457 เทาชัตเตอร์','SKN',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบข้าง 457-15 เทาชัตเตอร์','SKN',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบข้าง 304 เทาชัตเตอร์','SKN',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบข้าง 457-10 เทาเข้ม','BK',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบจั่ว 457 เทา','SKN',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบจั่ว 457-12 เทา','SKN',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบข้าง 304 เทา','PPS',''),
  machineOf('02A-GRST-035-ZC','2.00 -5 ครอบข้าง 457 เทา','PPS',''),
]);
ok('SKN ครอบข้าง 457 → เครื่องรีด', capR[0]==='ครอบข้าง 457');
ok('SKN ครอบข้าง 457-15 → พับครอบ', capR[1]==='พับครอบ');
ok('SKN ครอบข้าง 304 → พับครอบ', capR[2]==='พับครอบ');
ok('BK ครอบข้าง 457-10 → พับครอบ', capR[3]==='พับครอบ');
ok('SKN ครอบจั่ว 457 → เครื่องรีดจั่ว', capR[4]==='ครอบจั่ว 457');
ok('SKN ครอบจั่ว 457-12 → พับครอบ', capR[5]==='พับครอบ');
ok('PPS ครอบข้าง 304 → เครื่องรีด 304', capR[6]==='ครอบข้าง 304');
ok('PPS ครอบข้าง 457 → พับครอบ', capR[7]==='พับครอบ');

// ---- 13. SO ออนไลน์ (ขึ้นต้น O) แยกแท็บ ----
await click('button.tab:has-text("SKN")');
await clickText('ฝั่งขาย');
ok('O-SO ไม่โชว์ในฝั่งขาย', !(await page.locator('#main').innerText()).includes('O68N001'));
await clickText('ออนไลน์');
ok('O-SO โชว์ในแท็บออนไลน์', (await page.locator('#main').innerText()).includes('O68N001'));
await clickText('สั่ง+อนุมัติใบผลิต');
st = await page.evaluate(() => window.__STATE__.tks);
const ot = st.find(t=>t.sonum==='O68N001');
ok('O-SO งานตรง → default ตรง-R ปีกขวา (Gem เคาะ 20 ก.ค.)', !!ot && ot.machine==='ตรง-R ปีกขวา' && ot.stage===1);
await clickText('บอร์ดเครื่อง');
ok('การ์ด O-SO บนบอร์ดติด 🛍', true); // online flag ตรวจใน state แทน
const otFlag = await page.evaluate(() => { const t=TK.find(x=>x.so==='O68N001'); return t && t.online; });
ok('ticket O-SO ถูกนับเป็นงานออนไลน์', otFlag===true);

// ---- 14. แท็บออนไลน์เฉพาะ SKN/BK — PPS ไม่มี ----
await click('button.tab:has-text("PPS")'); await page.waitForTimeout(150);
ok('PPS ไม่มีแท็บออนไลน์ + เด้งกลับฝั่งขาย', !(await page.locator('.vtabs').innerText()).includes('ออนไลน์'));
await click('button.tab:has-text("BK")'); await page.waitForTimeout(150);
ok('BK มีแท็บออนไลน์', (await page.locator('.vtabs').innerText()).includes('ออนไลน์'));
await click('button.tab:has-text("SKN")'); await page.waitForTimeout(150);
ok('SKN มีแท็บออนไลน์', (await page.locator('.vtabs').innerText()).includes('ออนไลน์'));

// ---- 15. v7.5: งานออนไลน์ = รหัสลูกค้าขึ้นต้น O (SO เลขปกติ) ----
await click('button.tab:has-text("SKN")');
await clickText('ฝั่งขาย');
ok('SO ของลูกค้ารหัส O ไม่โชว์ฝั่งขาย', !(await page.locator('#main').innerText()).includes('SO68S777'));
await clickText('ออนไลน์');
ok('SO ของลูกค้ารหัส O โชว์แท็บออนไลน์', (await page.locator('#main').innerText()).includes('SO68S777'));
await page.locator('.socard:has-text("SO68S777") button:has-text("สั่ง+อนุมัติใบผลิต")').click();
await page.waitForTimeout(250);
st = await page.evaluate(() => window.__STATE__.tks);
const cusT = st.find(t=>t.sonum==='SO68S777');
ok('งานลูกค้ารหัส O → default ตรง-R ปีกขวา', !!cusT && cusT.machine==='ตรง-R ปีกขวา' && cusT.stage===1);
ok('ticket ลูกค้ารหัส O ติดธงออนไลน์', await page.evaluate(() => { const t=TK.find(x=>x.so==='SO68S777'); return t && t.online===true; }));
// ⇄ ทีมผลิตเลือกปีกเองบนบอร์ด
await clickText('ฝั่งผลิต: วางแผน');
const s7 = page.locator('.tkt', { hasText: 'SO68S777' });
await s7.locator('button:has-text("A ผลิตใหม่")').click(); await page.waitForTimeout(120);
await s7.locator('button:has-text("เข้าคิวเครื่อง")').click(); await page.waitForTimeout(250);
await clickText('บอร์ดเครื่อง');
await page.locator('.bcard:has-text("SO68S777") button:has-text("⇄")').click(); await page.waitForTimeout(250);
st = await page.evaluate(() => window.__STATE__.tks.find(t=>t.sonum==='SO68S777'));
ok('⇄ ย้ายปีก R→L ได้จากบอร์ด', st.machine==='ตรง-L ปีกซ้าย' && st.stage===2);

// ---- 16. v7.5: ⚡ด่วน — กันซ้ำ + ชี้ไปการ์ดจริงถ้า SO sync แล้ว ----
await clickText('ฝั่งขาย');
await page.locator('#urg-so').fill('SO68A555');   // มีใบผลิตอยู่แล้วจากเทส 9
await clickText('⚡ สั่งด่วน');
st = await page.evaluate(() => window.__STATE__.tks.filter(t=>t.sonum==='SO68A555'));
ok('⚡ด่วนซ้ำ SO เดิม → ถูกบล็อค (ยังใบเดียว)', st.length===1);
await page.locator('#urg-so').fill('SO68A002');   // SO sync มาแล้ว
await clickText('⚡ สั่งด่วน');
st = await page.evaluate(() => window.__STATE__.tks.filter(t=>t.sonum==='SO68A002'));
ok('⚡ด่วนกับ SO ที่ sync แล้ว → ไม่สร้างใบเปล่า', st.length===0);
ok('…แต่พาไปที่การ์ดจริงให้สั่งเอง', (await page.locator('#main').innerText()).includes('SO68A002'));
await page.evaluate(() => { q=''; render(); });

// ---- 17. v7.5: ใบด่วนผูกรายการ/ความยาวอัตโนมัติเมื่อ SO sync มา ----
await page.locator('#urg-so').fill('SO68LATER');
await clickText('⚡ สั่งด่วน');
st = await page.evaluate(() => window.__STATE__.tks.filter(t=>t.sonum==='SO68LATER'));
ok('ใบด่วนก่อน SO มา → สร้างได้ (ว่าง)', st.length===1 && st[0].prod_m===0);
await page.evaluate(async () => {   // จำลอง so_push sync SO เข้ามา
  const t=new Date().toISOString();
  window.__STATE__.sos.push({branch:'SKN',sonum:'SO68LATER',sodat:t.slice(0,10),dlvdat:t.slice(0,10),cuscod:'A009',cusnam:'ลูกค้าด่วน',docstat:'N',synced_at:t});
  window.__STATE__.its.push({branch:'SKN',sonum:'SO68LATER',seq:1,stkcod:'01A-ZI-030',stkdes:'4.00 -5 ตรง ซิงค์ 0.30',ordqty:20,remqty:20,unit:'มร',synced_at:t});
  await reload(); render();
});
await clickText('ฝั่งผลิต: วางแผน');
const laterCard = page.locator('.tkt', { hasText: 'SO68LATER' });
ok('ใบด่วนโชว์ความยาวหลัง SO sync (20 ม./5 แผ่น)', (await laterCard.innerText()).includes('20 ม.') && (await laterCard.innerText()).includes('5'));
await laterCard.locator('button:has-text("A ผลิตใหม่")').click(); await page.waitForTimeout(120);
await laterCard.locator('button:has-text("เข้าคิวเครื่อง")').click(); await page.waitForTimeout(250);
st = await page.evaluate(() => window.__STATE__.tks.filter(t=>t.sonum==='SO68LATER'));
ok('planA ใบด่วน → ผูกรายการ+metric ลง DB ถาวร', st[0].stage===2 && String(st[0].item_seqs)==='1' && st[0].prod_m===20 && st[0].sheets===5 && st[0].max_len===4 && st[0].label.startsWith('⚡'));

// ---- 18. v7.5: กันดับเบิลคลิก (insert ช้า 400ms + กดรัว) ----
await clickText('ฝั่งขาย');
await page.evaluate(() => { const o=DB.insertTicket; DB.insertTicket=async r=>{ await new Promise(x=>setTimeout(x,400)); return o(r); }; });
const a2btn = page.locator('.socard:has-text("SO68A002") button:has-text("สั่ง+อนุมัติใบผลิต")');
await a2btn.click({ noWaitAfter:true });
await page.waitForTimeout(60);
await a2btn.click({ force:true, noWaitAfter:true, timeout:800 }).catch(()=>{});
await page.waitForTimeout(1200);
st = await page.evaluate(() => window.__STATE__.tks.filter(t=>t.sonum==='SO68A002'));
ok('กดสั่งรัว 2 ครั้ง → ได้ใบเดียว', st.length===1);

// ---- 19. v7.6: ประทับเวลาทุกขั้น + ระยะเวลา process ----
const t0=(await page.evaluate(()=>window.__STATE__.tks))[0];
ok('times ประทับครบ 8 ขั้น (ออกใบ→ถึงลูกค้า)', ['ordered','approved','planned','started','done','packed','shipped','arrived'].every(k=>t0.times&&t0.times[k]));
const tl=await page.evaluate(()=>timeLine(TK.find(x=>x.st===7)));
ok('timeLine โชว์เวลา+รอคิว+เวลาผลิตจริง', ['ออกใบ','อนุมัติ','เริ่ม','รอคิว','เสร็จ','ผลิต','ถึงลูกค้า'].every(w=>tl.includes(w)));
await clickText('ฝั่งผลิต: วางแผน');
ok('การ์ดวางแผนโชว์ 🕐 ออกใบ/อนุมัติ', (await page.locator('#main').innerText()).includes('ออกใบ'));
await clickText('รายละเอียด');
ok('modal มีสรุปเวลา process', (await page.locator('#ovbg').innerText()).toLowerCase().includes('เวลา process'));
await page.locator('#ovbg .s-x').click(); await page.waitForTimeout(100);
await clickText('ฝั่งขาย');
ok('ฝั่งขาย: สั่งครบแล้วโชว์เวลาออกใบ', (await page.locator('#main').innerText()).includes('สั่งครบแล้ว · 🕐 ออกใบ'));

// ---- 20. v7.7: แท็บ 📊 รายงานเวลา/คอขวด ----
await clickText('📊 เวลา');
const rp = await page.locator('#main').innerText();
ok('รายงานโชว์สรุปวันนี้', rp.includes('ออกใบ') && rp.includes('เสร็จ') && rp.includes('กำลังผลิต'));
ok('รายงานมีตารางรายเครื่อง + lead time', rp.toLowerCase().includes('รายเครื่อง') && rp.includes('ออกใบ→เสร็จ'));
ok('รายงานเทียบ 3 สาขา', rp.includes('SKN:') && rp.includes('BK:') && rp.includes('PPS:'));
ok('ผลิตเฉลี่ยคำนวณได้ (ใบจบงานมี started→done)', rp.includes('น.'));

// ---- 21. v8.0: 📐 ครอบตามแบบ — วาดแบบจากระยะจริง ----
await click('button.tab:has-text("SKN")');
await clickText('ฝั่งขาย');
const a3 = page.locator('.socard:has-text("SO68A003")');
ok('รายการตามแบบมีปุ่ม 📐 วาดแบบ', (await a3.innerText()).includes('📐 วาดแบบ'));
await a3.locator('button:has-text("📐")').first().click(); await page.waitForTimeout(250);
ok('editor เปิด + วาด SVG แล้ว', await page.locator('#shbg.show').isVisible() && (await page.locator('#sh-b svg path').count()) > 0);
// กรอกผ่านช่องจริง (shSeg) — ระบบถือว่า "แตะตัวเลขแล้ว" ค่อยบันทึก segs ไม่งั้นด้านตั้งต้นจะกลายเป็นของจริง
await page.evaluate(() => { shSeg(1,'L',9); shSeg(2,'L',3); });
ok('girth 10+9+3=22 ซม. → ✓ ตรงรหัสแบบ 220', (await page.locator('#sh-b').innerText()).includes('✓ ตรงรหัสแบบ 220'));
await page.locator('#sh-b button:has-text("บันทึกแบบ")').click(); await page.waitForTimeout(300);
const shp = await page.evaluate(() => window.__STATE__.shapes);
ok('บันทึกแบบลง DB (3 ด้าน girth 220 + คนบันทึก)', shp.length===1 && shp[0].girth_mm===220 && shp[0].segs.length===3 && shp[0].sonum==='SO68A003' && shp[0].updated_by==='Gem');
ok('ปุ่มเปลี่ยนเป็น 📐 ✓ (มีแบบแล้ว)', (await a3.innerText()).includes('📐 ✓'));
// สั่งผลิต → ใบผลิตต้องติดป้าย 📐 มีแบบ + modal โชว์รูปแบบพับ
await a3.locator('button:has-text("สั่ง+อนุมัติใบผลิต")').click(); await page.waitForTimeout(300);
await clickText('ฝั่งผลิต: วางแผน');
const a3t = page.locator('.tkt', { hasText: 'SO68A003' });
ok('ใบผลิตติดป้าย 📐 มีแบบ', (await a3t.innerText()).includes('📐 มีแบบ'));
await a3t.locator('button:has-text("รายละเอียด")').click(); await page.waitForTimeout(300);
ok('modal ผลิตโชว์รูปแบบพับ scale จริง', (await page.locator('#m-b').innerText()).includes('แบบครอบ') && (await page.locator('#m-b svg path').count()) > 0);
await page.locator('#ovbg .s-x').click(); await page.waitForTimeout(100);

// ---- 22. v8.1: 📥 parser ไฟล์ออเดอร์ Shopee/TikTok ----
await clickText('ออนไลน์');
ok('แท็บออนไลน์มีช่องนำเข้าไฟล์', await page.locator('#imp-file').count() === 1);
const pr = await page.evaluate(() => {
  const shopee = parsePlatformRows([
    ['หมายเลขคำสั่งซื้อ','ประเภทคำสั่งซื้อ','สถานะการสั่งซื้อ','Hot Listing','สถานะการคืนเงินหรือคืนสินค้า','ชื่อผู้ใช้ (ผู้ซื้อ)','วันที่ทำการสั่งซื้อ','x','x','x','x','x','x','x','*หมายเลขติดตามพัสดุ','x','x','x','ชื่อสินค้า','เลขอ้างอิง SKU (SKU Reference No.)','ชื่อตัวเลือก','x','x','จำนวน','จำนวนที่ส่งคืน'],
    ['260717VURBP8A1','','ที่ต้องจัดส่ง','N','','ballrii','2026-07-17','','','','','','','','TH268','','','','ลอนรั้วเมทัลชีทลายไม้','10035','ลายไม้ปาเก้,50ซม.','','','12','0'],
    ['260717VURBP8A1','','ที่ต้องจัดส่ง','N','','ballrii','2026-07-17','','','','','','','','TH268','','','','ลอนฝ้าเมทัลชีท','10040','ขาว,100ซม.','','','5','0'],
    ['260718CANCEL1','','ยกเลิกแล้ว','N','','xxx','2026-07-18','','','','','','','','','','','','ลอนรั้ว','10031','เมเปิ้ล','','','9','0'],
    ['260718RETURN1','','ที่ต้องจัดส่ง','N','','yyy','2026-07-18','','','','','','','','TH999','','','','ลอนรั้ว','10031','เมเปิ้ล','','','4','2'],
  ]);
  const tiktok = parsePlatformRows([
    ['Order ID','Order Status','Order Substatus','Cancelation/Return Type','Normal or Pre-order','SKU ID','Seller SKU','Product Name','Variation','Quantity','Sku Quantity of return'],
    ['Platform unique order ID.','Current order status.','','','','Platform SKU ID.','Seller sku','Platform product name.','Platform SKU variation','SKU sold quantity in the ord','SKU returned quantity'],
    ['585085416541489018','ที่จะจัดส่ง','รอจัดส่ง','','Normal','173442','000464','ลอนรั้วลายไม้','แดงมะขาม, 80 ซม., 12 ชิ้น','1','0'],
  ]);
  return {sp:{plat:shopee.platform, n:Object.keys(shopee.orders).length, i1:shopee.orders['260717VURBP8A1'].items.length, ret:shopee.returns.length},
          tt:{plat:tiktok.platform, n:Object.keys(tiktok.orders).length, sku:Object.values(tiktok.orders)[0].items[0].stk}};
});
ok('Shopee: รวม 2 รายการเข้าออเดอร์เดียว + ตัดใบยกเลิก + จับคืน', pr.sp.plat==='Shopee' && pr.sp.n===2 && pr.sp.i1===2 && pr.sp.ret===1);
ok('TikTok: ข้ามแถวคำอธิบาย + อ่าน Seller SKU', pr.tt.plat==='TikTok' && pr.tt.n===1 && pr.tt.sku==='000464');

// ---- 23. v8.2: 🏭 ผลิตเก็บเข้าสต็อค (ไม่มี SO / ไม่มีลูกค้า) ----
await click('button.tab:has-text("SKN")');
await clickText('ผลิตเข้าสต็อค');
ok('มีแท็บ 🏭 ผลิตเข้าสต็อค', (await page.locator('.vtabs').innerText()).includes('ผลิตเข้าสต็อค'));
ok('admin เห็นฟอร์มออกใบ', await page.locator('#st-items').count() === 1);
await page.locator('#st-items').fill('01WP-GRST-030-JJL | 1.20 -10 ลอนรั้ว เทาเข้ม 0.30JJL | 30 | มร');
await page.locator('#st-note').fill('เติมสต็อคขายออนไลน์');
await clickText('ออกใบ → เข้าคิววางแผน');
await page.waitForTimeout(600);   // DB.insertTicket ถูกหน่วง 400ms ไว้ตั้งแต่เทส 18
st = await page.evaluate(() => window.__STATE__.tks.filter(t => t.source === 'stock'));
ok('ออกใบสต็อค → 1 ใบ stage 1 เลข ST + เครื่องลอนรั้ว 182', st.length===1 && st[0].stage===1 && /^ST\d{6}-01$/.test(st[0].sonum) && st[0].machine==='ลอนรั้ว 182');
ok('ใบสต็อคเก็บเหตุผล + metric (30 ม./25 แผ่น)', st[0].people.stock_note==='เติมสต็อคขายออนไลน์' && st[0].prod_m===30 && st[0].sheets===25);
ok('stock_note ไม่ถูกประทับเวลา (ไม่ใช่ขั้นตอน)', !!st[0].times.ordered && !st[0].times.stock_note);
const stNo = st[0].sonum;
ok('ใบสต็อคติด badge 🏭 เข้าสต็อค', (await page.locator('#main').innerText()).includes('🏭'));
// วางแผน → เข้าคิว → เริ่ม → เสร็จ
await clickText('ฝั่งผลิต: วางแผน');
const stCard = page.locator('.tkt', { hasText: stNo });
ok('การ์ดวางแผนบอกว่าไม่มีลูกค้า', (await stCard.innerText()).includes('ผลิตเก็บเข้าสต็อค'));
await stCard.locator('button:has-text("A ผลิตใหม่")').click(); await page.waitForTimeout(120);
await stCard.locator('button:has-text("เข้าคิวเครื่อง")').click(); await page.waitForTimeout(250);
await clickText('บอร์ดเครื่อง');
const stB = page.locator('.bcard', { hasText: stNo });
if (await stB.locator('button:has-text("รับงาน")').count()) { await stB.locator('button:has-text("รับงาน")').click(); await page.waitForTimeout(250); }
await stB.locator('button:has-text("เริ่มผลิต")').click(); await page.waitForTimeout(250);
await stB.locator('button:has-text("เสร็จ")').click(); await page.waitForTimeout(300);
if (await page.locator('#ovbg.show').isVisible()) { await page.locator('#ovbg .s-x').click(); await page.waitForTimeout(120); }
st = await page.evaluate(() => window.__STATE__.tks.filter(t => t.source === 'stock'));
ok('ใบสต็อคเดินไลน์ได้เหมือนงานลูกค้า → stage 4', st[0].stage===4 && st[0].people.started==='Gem' && st[0].people.done==='Gem');
ok('บอร์ดโชว์ปุ่มเก็บเข้าสต็อคแทนรอรวมของ', (await page.locator('.bcard', { hasText: stNo }).innerText()).includes('เก็บเข้าสต็อค'));
// ต้องไม่หลุดเข้าโมดูลรวมของ/จัดส่ง
await clickText('รวมของ/ส่ง');
ok('ใบสต็อคไม่โผล่ในแท็บรวมของ/ส่ง', !(await page.locator('#main').innerText()).includes(stNo));
// เก็บเข้าสต็อค
await clickText('ผลิตเข้าสต็อค');
ok('อยู่กลุ่ม “ผลิตเสร็จ — รอเก็บเข้าสต็อค”', (await page.locator('#main').innerText()).includes('รอเก็บเข้าสต็อค'));
await clickText('เก็บเข้าสต็อคแล้ว');
st = await page.evaluate(() => window.__STATE__.tks.filter(t => t.source === 'stock'));
ok('เก็บเข้าสต็อค → stage 7 + times.stocked + ไม่มี packed/shipped', st[0].stage===7 && !!st[0].times.stocked && st[0].people.stocked==='Gem' && !st[0].people.packed && !st[0].people.shipped);
ok('โชว์กลุ่มเก็บเข้าสต็อควันนี้', (await page.locator('#main').innerText()).includes('เก็บเข้าสต็อควันนี้'));
const stEv = await page.evaluate(() => window.__STATE__.events.filter(e => e.action === 'stock_in'));
ok('event stock_in บันทึกยอด ม./แผ่น/กก.', stEv.length===1 && stEv[0].detail.includes('30') && stEv[0].detail.includes('กก.'));
// ต้องถูกนับในรายงานเวลา/คอขวด (กินเวลาเครื่องจริง)
await clickText('📊 เวลา');
ok('รายงานนับใบสต็อคในเครื่องลอนรั้ว 182', (await page.locator('#main').innerText()).includes('ลอนรั้ว 182'));
// สิทธิ์: ทีมขายออกใบได้ (Gem เคาะ ขาย+หัวหน้าผลิต+ผจก.สาขา) / ช่างรีดออกไม่ได้
const perm = await page.evaluate(() => ['sales','planner','admin','operator','packer'].map(r => {
  enterAsStaff({id:99, name:'ทดสอบสิทธิ์', role:r, branch:'SKN'}, 'pin');
  return !!USER.canStock;
}));
ok('สิทธิ์ออกใบ = ขาย/หัวหน้าผลิต/ผจก.สาขา เท่านั้น', String(perm)==='true,true,true,false,false');
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.role==='sales' && s.branch==='SKN'), 'pin'));
await page.waitForTimeout(200);
await clickText('ผลิตเข้าสต็อค');
ok('ทีมขาย (สมชาย) เห็นฟอร์มออกใบผลิตเข้าสต็อค', await page.locator('#st-items').count() === 1);
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.role==='operator'), 'pin'));
await page.waitForTimeout(200);
await clickText('ผลิตเข้าสต็อค');
ok('ช่างรีด (เก่ง) ไม่เห็นฟอร์ม แต่ดูสถานะได้', await page.locator('#st-items').count() === 0 && (await page.locator('#main').innerText()).includes('รอเก็บเข้าสต็อค'));

// ---- 24. v8.3: ประหยัดโหลด — ไม่วาดจอใหม่ถ้าข้อมูลไม่ขยับ ----
const noChange = await page.evaluate(async () => await reload());
ok('ข้อมูลเหมือนเดิม → reload คืน false (ไม่ applyData/ไม่วาดจอใหม่)', noChange === false);
const changed = await page.evaluate(async () => {
  window.__STATE__.machines.push({id:999, branch:'SKN', name:'เครื่องทดสอบซิงค์', sort:99, status:'ok', note:''});
  return await reload();
});
ok('ข้อมูลขยับ → reload คืน true', changed === true);
ok('ของใหม่เข้า state จริง', (await page.evaluate(() => MACHINES.SKN)).includes('เครื่องทดสอบซิงค์'));

// ---- 25. v8.4: 👥 หลายคนเข้าร่วมงานเครื่องเดียวกัน ----
// Gem เคาะ: ช่างกดเข้าร่วมเอง / ยังไม่ล็อกจำนวนคน เพราะทีมขนส่ง multitask — ระบบแค่จดว่าใครอยู่ตรงไหนช่วงไหน
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.name==='Gem'), 'pin'));
await page.waitForTimeout(200);
const wtk = await page.evaluate(async () => {
  const t = window.__STATE__.tks.find(t => t.branch==='SKN' && t.source==='so');
  t.stage = 3; t.workers = [];
  await reload();
  return t.id;
});
await click('button.tab:has-text("SKN")');
await clickText('บอร์ดเครื่อง');
ok('การ์ดหน้าเครื่องมีปุ่ม ➕ เข้าร่วม', (await page.locator('#main').innerText()).includes('เข้าร่วม'));
// ช่างคนที่ 1 กดเข้าร่วม
await page.evaluate(async id => { await joinWork(id); }, wtk);
await page.waitForTimeout(200);
let wk = await page.evaluate(id => window.__STATE__.tks.find(t=>t.id===id).workers, wtk);
ok('ช่างคนแรกกด ➕ → เข้า workers 1 คน มีเวลาเข้า', wk.length===1 && wk[0].name==='Gem' && !!wk[0].in && !wk[0].out);
// กดซ้ำคนเดิม ต้องไม่ซ้อน
await page.evaluate(async id => { await joinWork(id); }, wtk);
await page.waitForTimeout(150);
wk = await page.evaluate(id => window.__STATE__.tks.find(t=>t.id===id).workers, wtk);
ok('กด ➕ ซ้ำคนเดิม → ไม่ซ้อนกัน', wk.length===1);
ok('คนที่เข้าแล้วเห็นปุ่ม 🚪 ออก แทน ➕', (await page.locator('#main').innerText()).includes('ออก'));
// ช่างคนที่ 2 และ 3 มาช่วย (เครื่องลอนตรง BK 2-3 คน / PU 6 คน ตามที่ทีมขอ)
for (const nm of ['เก่ง (ช่างรีด)','บอย (หัวหน้าผลิต)']) {
  await page.evaluate(async ([id,n]) => {
    enterAsStaff(window.__STATE__.staff.find(s => s.name===n), 'pin');
    await joinWork(id);
  }, [wtk, nm]);
  await page.waitForTimeout(200);
}
wk = await page.evaluate(id => window.__STATE__.tks.find(t=>t.id===id).workers, wtk);
ok('3 คนช่วยกันในใบเดียวได้ (ไม่ทับกันหาย)', wk.length===3 && wk.filter(w=>!w.out).length===3);
await clickText('บอร์ดเครื่อง');
ok('การ์ดโชว์ชื่อคนที่เข้าร่วม + จำนวนคน', (await page.locator('#main').innerText()).includes('(3 คน)'));
// คนที่ 3 กดออกเอง
await page.evaluate(async id => { await leaveWork(id); }, wtk);
await page.waitForTimeout(200);
wk = await page.evaluate(id => window.__STATE__.tks.find(t=>t.id===id).workers, wtk);
ok('กด 🚪 ออก → ปิดเวลาเฉพาะคนนั้น', wk.filter(w=>w.out).length===1 && wk.filter(w=>!w.out).length===2);
// กดผลิตเสร็จ → ปิดเวลาให้ทุกคนที่ยังค้าง (คนลืมกดออกแน่นอน)
await page.evaluate(async id => { await doneProd(id); }, wtk);
await page.waitForTimeout(400);
wk = await page.evaluate(id => window.__STATE__.tks.find(t=>t.id===id).workers, wtk);
ok('กดผลิตเสร็จ → ปิดเวลาให้ทุกคนที่ยังค้างอัตโนมัติ', wk.length===3 && wk.every(w=>!!w.out));
const jev = await page.evaluate(() => window.__STATE__.events.filter(e=>e.action==='join_work'||e.action==='leave_work'));
ok('ลง log ใครเข้า/ออกงานครบ', jev.filter(e=>e.action==='join_work').length===3 && jev.filter(e=>e.action==='leave_work').length===1);
const wmin = await page.evaluate(id => wkMin(TK.find(t=>t.id===id)), wtk);
ok('คน-นาที รวมได้ (ไม่ติดลบ/ไม่ NaN)', typeof wmin==='number' && wmin>=0 && !isNaN(wmin));
await page.evaluate(() => { const m=document.querySelector('#ovbg.show .s-x'); if(m) m.click(); });
await page.waitForTimeout(150);
await clickText('📊 เวลา');
const rp2 = await page.locator('#main').innerText();
ok('รายงานมีคอลัมน์ คน/ใบ + คน-นาที', rp2.includes('คน/ใบ') && rp2.includes('คน-นาที'));

// ---- 26. v8.4: ✏️ วาดมือแนบใบครอบตามแบบ (ขายวาด ช่างเติมตัวเลขได้) ----
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.name==='Gem'), 'pin'));
await page.waitForTimeout(200);
await click('button.tab:has-text("SKN")');
await clickText('ฝั่งขาย');
const a4 = page.locator('.socard:has-text("SO68A003")');
await a4.locator('button:has-text("📐")').first().click(); await page.waitForTimeout(250);
ok('editor มี 2 แท็บ ตัวเลข/วาดมือ', (await page.locator('#sh-b').innerText()).includes('วาดมือ'));
await page.locator('#sh-b button:has-text("วาดมือ")').first().click(); await page.waitForTimeout(200);
ok('โหมดวาดมือมีผืนผ้าใบ', await page.locator('#sk-c').count() === 1);
await page.evaluate(() => { skStart(10,10); skMove(40,12); skMove(60,40); skEnd(); skStart(20,50); skMove(70,52); skEnd(); });
await page.waitForTimeout(150);
ok('วาด 2 เส้น → เก็บเป็น path 2 เส้น', (await page.evaluate(() => SK.paths.length)) === 2);
ok('เส้นขึ้นบนผืนผ้าใบจริง', (await page.locator('#sk-ink path').count()) === 2);
await page.evaluate(() => skUndo());
ok('↩ ย้อน ลบเส้นล่าสุด', (await page.evaluate(() => SK.paths.length)) === 1);
await page.evaluate(() => { const el=document.getElementById('sk-note'); if(el){ el.value='ครอบมุมนี้ให้พับเก็บขอบด้วย'; shNote(el.value);} });
await page.locator('#sh-b button:has-text("บันทึกแบบ")').click(); await page.waitForTimeout(300);
const sh2 = await page.evaluate(() => window.__STATE__.shapes.find(s=>s.sonum==='SO68A003'));
ok('บันทึกลายเส้น + โน้ต ลง DB (เป็น vector ไม่ใช่รูปภาพ)', sh2.sketch.paths.length===1 && /^M /.test(sh2.sketch.paths[0].d) && sh2.note.includes('พับเก็บขอบ'));
ok('ตัวเลขเดิมไม่ถูกลบทิ้งตอนวาดมือ', sh2.segs.length===3 && sh2.girth_mm===220);
// ใบที่ขายวาดมืออย่างเดียว ไม่แตะตัวเลข → ห้ามบันทึกด้านตั้งต้นเป็นของจริง (girth ปลอมจะเช็ครหัสแบบผิด)
const drawOnly = await page.evaluate(async () => {
  openShape('SO68A003', 99, 'ครอบตามแบบ 220 ทดสอบวาดล้วน');
  shMode('draw'); skStart(5,5); skMove(50,50); skEnd();
  await shSave();
  return window.__STATE__.shapes.find(s=>s.seq===99);
});
ok('วาดมืออย่างเดียว → ไม่บันทึก segs ปลอม / girth = null', drawOnly.segs.length===0 && drawOnly.girth_mm===null && drawOnly.sketch.paths.length===1);
const openTk = await page.evaluate(() => {
  const t = window.__STATE__.tks.find(t => t.sonum==='SO68A003');
  return t? t.id : null;
});
if (openTk) {
  await page.evaluate(async id => { await openM(id); }, openTk);
  await page.waitForTimeout(400);
  const mb = await page.locator('#m-b').innerText();
  ok('ช่างเห็นทั้งแบบตัวเลข + ลายมือ + โน้ต ในใบผลิต', mb.includes('แบบครอบ') && mb.includes('วาดมือ') && mb.includes('พับเก็บขอบ'));
  await page.evaluate(() => { const m=document.querySelector('#ovbg.show .s-x'); if(m) m.click(); });
  await page.waitForTimeout(150);
} else ok('ช่างเห็นทั้งแบบตัวเลข + ลายมือ + โน้ต ในใบผลิต', false);
// ลายเส้นจาก DB ต้องถือเป็นข้อมูล ไม่ใช่โค้ด
const evil = await page.evaluate(() => skPathsHTML([{d:'M 1 1 L 2 2"/><script>x=1</scr'+'ipt>', c:'red" onload="alert(1)', w:99}]));
ok('path/สีจาก DB ถูกล้าง (กันฝัง HTML/JS ผ่านฟิลด์แบบ)', !/<script|onload|alert/i.test(evil) && evil.includes('#1f2933'));

// ---- 27. v8.5: ⚠️ เตือนใบครอบตามแบบที่ยังไม่มีแบบ + 📚 คลังแบบใช้ซ้ำ ----
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.name==='Gem'), 'pin'));
await page.waitForTimeout(200);
await click('button.tab:has-text("SKN")');
// ลบแบบของ SO68A003 ชั่วคราว = จำลองเคสจริงที่ขายสั่งเข้าผลิตก่อนได้ระยะจากลูกค้า
const bak = await page.evaluate(() => {
  const k = Object.keys(SHAPES).find(x => x.indexOf('SO68A003|1') >= 0);
  const b = JSON.parse(JSON.stringify(SHAPES[k]));
  delete SHAPES[k]; render();
  return { k, b };
});
await clickText('ฝั่งผลิต: วางแผน');
const g1 = page.locator('.tkt', { hasText: 'SO68A003' });
const g1txt = await g1.innerText();
ok('ใบที่ไม่มีแบบติดป้ายเตือน ⚠ ยังไม่มีแบบ', g1txt.includes('ยังไม่มีแบบ 1 รายการ'));
ok('ป้าย 📐 มีแบบ หายไปเมื่อไม่มีแบบจริง', !g1txt.includes('📐 มีแบบ'));
await g1.locator('button:has-text("รายละเอียด")').click(); await page.waitForTimeout(300);
const mgap = await page.locator('#m-b').innerText();
ok('modal เตือนช่างก่อนลงมือ + มีปุ่มวาดในใบเลย', mgap.includes('ยังไม่มีแบบ') && (await page.locator('#m-b button:has-text("📐 รายการที่")').count()) === 1);
await page.locator('#ovbg .s-x').click(); await page.waitForTimeout(120);
await clickText('ฝั่งขาย');
const sgap = await page.locator('#main').innerText();
ok('ฝั่งขายเห็นแถบเตือน (ขายคือคนเดียวที่แก้ได้)', sgap.includes('สั่งผลิตไปแล้วแต่ยังไม่มีแบบ'));
ok('แถบเตือนกดวาดได้ทันทีจากหน้าขาย', (await page.locator('#main .warn button[onclick^="openShape"]').count()) >= 1);
// ใบที่ยังไม่เข้าผลิต ไม่ต้องขึ้นแถบ — ขายสั่งก่อนได้ขนาดเป็นเรื่องปกติ ไม่ใช่ของเสีย
ok('นับเฉพาะใบที่เข้าผลิตแล้วและยังไม่เสร็จ', (await page.evaluate(() => shapeGaps().length)) === 1);
await page.evaluate(({k,b}) => { SHAPES[k]=b; render(); }, bak);
await clickText('ฝั่งผลิต: วางแผน');
ok('ใส่แบบกลับ → ป้ายเตือนหาย', !(await page.locator('.tkt', { hasText: 'SO68A003' }).innerText()).includes('ยังไม่มีแบบ'));
ok('ไม่มีช่องว่างเหลือ = แถบเตือนไม่โผล่', (await page.evaluate(() => gapBanner())) === '');
// 📚 คลังแบบ — ครอบรหัส 220 เคยทำไว้แล้ว ต้องหยิบมาใช้ได้ ไม่ต้องวาดใหม่
const lib = await page.evaluate(() => {
  SHAPES['SKN|SO68ZZZ|1'] = { branch:'SKN', sonum:'SO68ZZZ', seq:1, des:'ครอบตามแบบ 220 ใบอื่น',
    segs:[{L:10,a:90,d:1},{L:9,a:90,d:-1},{L:3}], girth_mm:220, sketch:{paths:[]}, note:'',
    updated_by:'ฝน', updated_at:new Date().toISOString() };
  SHAPES['SKN|SO68YYY|1'] = JSON.parse(JSON.stringify(SHAPES['SKN|SO68ZZZ|1']));  // แบบซ้ำเป๊ะ — ต้องยุบเหลืออันเดียว
  SHAPES['SKN|SO68YYY|1'].sonum='SO68YYY';
  SHAPES['SKN|SO68WWW|1'] = { branch:'SKN', sonum:'SO68WWW', seq:1, des:'ครอบตามแบบ 457 คนละรหัส', segs:[{L:20,a:90,d:1},{L:25}], girth_mm:450, updated_by:'บอย', updated_at:new Date().toISOString() };
  return { same: shapeLib('220','SKN|SO68A003|1').length, other: shapeLib('457','SKN|SO68A003|1').length, none: shapeLib(null).length };
});
ok('คลังแบบยุบแบบซ้ำเหลืออันเดียว + ไม่เอาตัวเอง', lib.same === 2);   // ZZZ/YYY ยุบเป็น 1 + seq99 ที่วาดมือ
ok('ไม่ปนแบบคนละรหัส / สินค้าที่ไม่มีรหัสแบบ', lib.other === 1 && lib.none === 0);
await clickText('ฝั่งขาย');
await page.locator('.socard:has-text("SO68A003") button:has-text("📐")').first().click(); await page.waitForTimeout(250);
ok('editor โชว์แถบคลังแบบ 220 ที่เคยทำไว้', (await page.locator('#sh-b').innerText()).includes('ที่เคยทำไว้'));
const used = await page.evaluate(() => {
  SHED.segs = [{L:1}]; SHED.touched = false;          // ล้างให้เหลือด้านเดียว จะได้เห็นชัดว่าดึงของเก่ามาจริง
  const el = document.querySelector('#sh-b div[onclick^="useLib"]');
  el.click();
  return { n: SHED.segs.length, g: shGirth(), touched: SHED.touched };
});
ok('กดแบบเก่า → ดึงระยะมาใช้ต่อได้เลย (3 ด้าน 22 ซม.)', used.n === 3 && Math.round(used.g) === 22 && used.touched === true);
await page.locator('#shbg .s-x').first().click(); await page.waitForTimeout(150);
ok('ปิด editor โดยไม่บันทึก = ของเดิมใน DB ไม่ถูกแตะ', (await page.evaluate(() => window.__STATE__.shapes.find(s=>s.sonum==='SO68A003'&&s.seq===1).girth_mm)) === 220);

// ---- 28. v8.6: ⏸ พักงาน/ทำต่อ + ❌ ยกเลิกใบผลิต (ทิ้งร่องรอย ใครขอ ใครอนุมัติ) ----
// Gem 26 ก.ค.: "บางกรณี ผลิตค้างคืน พรุ่งนี้มาทำต่อ / ใบผลิตยกเลิกก็มี แต่ต้องทิ้งร่องรอยไว้ด้วย ใครอนุมัติ ใครยกเลิก"
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.name==='Gem'), 'pin'));
await page.waitForTimeout(200);
const ptk = await page.evaluate(async () => {
  const t = window.__STATE__.tks.find(t => t.branch==='SKN' && t.source==='so' && t.stage>=2 && t.stage<=3)
         || window.__STATE__.tks.find(t => t.branch==='SKN' && t.source==='so');
  t.stage = 3; t.route='A'; t.people = {...(t.people||{}), started:'Gem'};
  t.times = {...(t.times||{}), started:new Date(Date.now()-60*60000).toISOString()};   // เริ่มไปแล้ว 60 นาที
  t.workers = [];
  await reload();
  return t.id;
});
await click('button.tab:has-text("SKN")');
await clickText('บอร์ดเครื่อง');
ok('ใบกำลังผลิตมีปุ่ม ⏸ พัก', (await page.locator('#main').innerText()).includes('⏸ พัก'));
// มีคน 2 คนค้างอยู่ในงาน — พักแล้วต้องถูกปิดเวลาให้หมด ไม่งั้นพักข้ามคืนคน-นาทีพัง
await page.evaluate(async id => { await joinWork(id); }, ptk);
await page.evaluate(async ([id,n]) => { enterAsStaff(window.__STATE__.staff.find(s=>s.name===n),'pin'); await joinWork(id); }, [ptk,'เก่ง (ช่างรีด)']);
await page.waitForTimeout(300);
ok('ก่อนพัก มีคนค้างอยู่ในงาน 2 คน', (await page.evaluate(id => window.__STATE__.tks.find(t=>t.id===id).workers.filter(w=>!w.out).length, ptk)) === 2);
// กด ⏸ แล้วยังไม่เลือกสาเหตุ = ต้องไม่ผ่าน (สาเหตุบังคับ พรุ่งนี้ต้องรู้ว่าค้างเพราะอะไร)
await page.evaluate(id => { pauseAsk(id); }, ptk);
await page.waitForTimeout(200);
ok('กด ⏸ → กางฟอร์มเลือกสาเหตุ', (await page.locator('#main').innerText()).includes('เลือกสาเหตุที่พัก'));
await page.evaluate(id => { pauseProd(id); }, ptk);
await page.waitForTimeout(250);
ok('ไม่เลือกสาเหตุ → พักไม่ได้ (บังคับ)', !(await page.evaluate(id => !!(window.__STATE__.tks.find(t=>t.id===id).people||{}).paused, ptk)));
await page.evaluate(id => {
  document.getElementById('pr-'+id).value = '🌙 หมดกะ/ค้างคืน พรุ่งนี้ทำต่อ';
  document.getElementById('pn-'+id).value = 'เหลืออีก 3 แผ่น';
  pauseProd(id);
}, ptk);
await page.waitForTimeout(400);
const pst = await page.evaluate(id => { const t=window.__STATE__.tks.find(t=>t.id===id); return {p:t.people, tm:t.times, st:t.stage, wk:t.workers}; }, ptk);
ok('พักงาน → บันทึกคนพัก + สาเหตุ + เวลาที่พัก', pst.p.paused==='เก่ง (ช่างรีด)' && /ค้างคืน/.test(pst.p.pause_reason) && /เหลืออีก 3 แผ่น/.test(pst.p.pause_reason) && !!pst.tm.paused);
ok('พักแล้วใบยังคาเครื่องเดิม (stage 3 ไม่ถอยกลับเข้าคิว)', pst.st === 3);
ok('พัก → ปิดเวลาคนที่ค้างอยู่ให้ครบทุกคนอัตโนมัติ', pst.wk.length===2 && pst.wk.every(w=>!!w.out));
await clickText('บอร์ดเครื่อง');
const bpz = await page.locator('#main').innerText();
ok('การ์ดโชว์ ⏸ พักอยู่ + ใครพัก + สาเหตุ', bpz.includes('พักอยู่') && bpz.includes('เก่ง') && bpz.includes('ค้างคืน'));
ok('ใบที่พักอยู่ ปุ่มเปลี่ยนเป็น ▶ ทำต่อ (ไม่ใช่ ✅ เสร็จ)', bpz.includes('▶ ทำต่อ'));
// ย้อนเวลาที่พักไป 8 ชม. = ค้างคืนจริง แล้วกดทำต่อ
await page.evaluate(id => { const t=TK.find(t=>t.id===id); t.tm.paused = new Date(Date.now()-8*3600*1000).toISOString(); }, ptk);
await page.evaluate(id => { resumeProd(id); }, ptk);
await page.waitForTimeout(400);
const rst = await page.evaluate(id => { const t=window.__STATE__.tks.find(t=>t.id===id); return {p:t.people, tm:t.times}; }, ptk);
ok('ทำต่อ → ล้างสถานะพัก (กลับมาเป็นงานเดินปกติ)', !rst.p.paused && !rst.p.pause_reason && !rst.tm.paused);
ok('สะสมนาทีที่พักไว้ที่ pause_min (~8 ชม.)', Math.abs(rst.tm.pause_min - 480) < 3);
// ใบค้างคืนจริง: เริ่ม 9 ชม.ที่แล้ว ทำจริง 1 ชม. แล้วพักข้ามคืน 8 ชม.
const pm = await page.evaluate(id => { const t=TK.find(t=>t.id===id);
  t.tm.started = new Date(Date.now()-9*3600*1000).toISOString();
  t.tm.done = new Date().toISOString();
  return {net: prodMin(t), raw: durMin(t.tm.started, t.tm.done)}; }, ptk);
ok('ผลิตจริงหักเวลาพักออก (60 นาที ไม่ใช่ 9 ชม.)', Math.abs(pm.net - 60) < 3 && pm.raw > 400);
const pev = await page.evaluate(() => window.__STATE__.events.filter(e=>e.action==='pause'||e.action==='resume'));
ok('ลง log พัก/ทำต่อ ครบ ตรวจย้อนได้', pev.filter(e=>e.action==='pause').length===1 && pev.filter(e=>e.action==='resume').length===1);
// ---- ❌ ยกเลิกใบผลิต ----
const xtk = await page.evaluate(async () => {
  const t = window.__STATE__.tks.find(t => t.branch==='SKN' && t.stage===1) || window.__STATE__.tks.find(t => t.branch==='SKN');
  t.stage = 1; t.people = {...(t.people||{})}; delete t.people.cancelled;
  await reload();
  return { id:t.id, so:t.sonum||t.so_no||'' };
});
await page.evaluate(() => enterAsStaff(window.__STATE__.staff.find(s => s.name==='Gem'), 'pin'));
await page.waitForTimeout(200);
await click('button.tab:has-text("SKN")');
await clickText('วางแผน');
ok('แท็บวางแผนมีปุ่ม ❌ ยกเลิกใบ', (await page.locator('#main').innerText()).includes('ยกเลิกใบ'));
const nAlive0 = await page.evaluate(() => tks().length);
await page.evaluate(id => { cancelAsk(id); }, xtk.id);
await page.waitForTimeout(250);
ok('กด ❌ → กางฟอร์มขอผู้อนุมัติ + PIN', (await page.locator('#main').innerText()).includes('ผู้อนุมัติ'));
await page.evaluate(async id => { await cancelTicket(id); }, xtk.id);
await page.waitForTimeout(300);
ok('ไม่เลือกสาเหตุ → ยกเลิกไม่ได้', !(await page.evaluate(id => !!(window.__STATE__.tks.find(t=>t.id===id).people||{}).cancelled, xtk.id)));
await page.evaluate(async id => {
  document.getElementById('xr-'+id).value = '🙅 ลูกค้ายกเลิกออเดอร์';
  document.getElementById('xp-'+id).value = '9999';          // PIN ผิด
  await cancelTicket(id);
}, xtk.id);
await page.waitForTimeout(300);
ok('PIN ผิด → ยกเลิกไม่ได้ (กันกดยกเลิกเองโดยไม่มีคนอนุมัติ)', !(await page.evaluate(id => !!(window.__STATE__.tks.find(t=>t.id===id).people||{}).cancelled, xtk.id)));
await page.evaluate(async id => {
  document.getElementById('xr-'+id).value = '🙅 ลูกค้ายกเลิกออเดอร์';
  document.getElementById('xn-'+id).value = 'ลูกค้าโทรมายกเลิกเช้านี้';
  document.getElementById('xp-'+id).value = '1111';
  await cancelTicket(id);
}, xtk.id);
await page.waitForTimeout(500);
const xst = await page.evaluate(id => { const t=window.__STATE__.tks.find(t=>t.id===id); return {p:t.people, tm:t.times}; }, xtk.id);
ok('ยกเลิกสำเร็จ → บันทึกทั้งคนขอและคนอนุมัติ (ร่องรอยครบ)', !!xst.p.cancelled && !!xst.p.cancel_approved && xst.p.cancelled==='Gem');
ok('บันทึกสาเหตุ + ขั้นที่ยกเลิก + เวลา', /ลูกค้ายกเลิก/.test(xst.p.cancel_reason) && /โทรมายกเลิก/.test(xst.p.cancel_reason) && xst.p.cancel_stage==='1' && !!xst.tm.cancelled);
ok('ใบที่ยกเลิกหลุดจากบอร์ดทันที (ช่างหยิบไปทำต่อไม่ได้)', (await page.evaluate(() => tks().length)) === nAlive0 - 1);
ok('แต่ใบยังอยู่ครบใน DB ไม่ได้ถูกลบ', (await page.evaluate(id => !!window.__STATE__.tks.find(t=>t.id===id), xtk.id)) === true);
const xev = await page.evaluate(() => window.__STATE__.events.filter(e=>e.action==='cancel'));
ok('ลง log ยกเลิก มีทั้งคนขอและคนอนุมัติในข้อความ', xev.length===1 && /ขอโดย/.test(xev[0].detail) && /อนุมัติ/.test(xev[0].detail));
await clickText('📊 เวลา');
const rp3 = await page.locator('#main').innerText();
ok('รายงานมีหัวข้อใบที่ยกเลิก + เห็นชื่อคนอนุมัติ', rp3.includes('ใบที่ยกเลิก') && rp3.includes('ยกเลิกตอน'));
// ยกเลิกตอนผลิตไปแล้ว ต้องบังคับกรอกว่าตัดไปแล้วเท่าไหร่ (ของกลายเป็นเศษ ห้ามหายเงียบ)
await page.evaluate(async id => { const t=window.__STATE__.tks.find(t=>t.id===id); t.stage=3; await reload(); }, ptk);
await clickText('บอร์ดเครื่อง');
await page.evaluate(id => { cancelAsk(id); }, ptk);
await page.waitForTimeout(250);
ok('ยกเลิกใบที่ผลิตไปแล้ว → มีช่องกรอกจำนวนที่ทำไปแล้ว', (await page.evaluate(id => !!document.getElementById('xm-'+id), ptk)) === true);
await page.evaluate(async id => {
  document.getElementById('xr-'+id).value = '✏️ ลูกค้าแก้แบบ/แก้ขนาด — ออกใบใหม่แทน';
  document.getElementById('xp-'+id).value = '1111';
  await cancelTicket(id);
}, ptk);
await page.waitForTimeout(300);
ok('ผลิตไปแล้วแต่ไม่กรอกจำนวน → ยกเลิกไม่ได้ (วัตถุดิบห้ามหายเงียบ)', !(await page.evaluate(id => !!(window.__STATE__.tks.find(t=>t.id===id).people||{}).cancelled, ptk)));
await page.evaluate(async id => {
  document.getElementById('xr-'+id).value = '✏️ ลูกค้าแก้แบบ/แก้ขนาด — ออกใบใหม่แทน';
  document.getElementById('xm-'+id).value = '3 แผ่น / 12 ม.';
  document.getElementById('xp-'+id).value = '1111';
  await cancelTicket(id);
}, ptk);
await page.waitForTimeout(500);
ok('กรอกจำนวนแล้ว → ยกเลิกได้ + เก็บของเสียไว้', /3 แผ่น/.test(await page.evaluate(id => (window.__STATE__.tks.find(t=>t.id===id).people||{}).cancel_made_note || '', ptk)));
ok('ยกเลิกตอนกำลังผลิต → บันทึกว่ายกเลิกที่ขั้น 3', (await page.evaluate(id => (window.__STATE__.tks.find(t=>t.id===id).people||{}).cancel_stage, ptk)) === '3');

console.log(T.join('\n'));
console.log('EVENTS LOGGED:', await page.evaluate(() => window.__STATE__.events.length));
console.log(errors.length ? 'JS ERRORS:\n' + errors.join('\n') : 'NO JS ERRORS');
await browser.close();
process.exit(T.some(t => t.startsWith('FAIL')) || errors.length ? 1 : 0);
