// ทดสอบด่านทะเบียน LINE ของ api/line/callback.js (17 ต.ค. 69) — รัน: node tests/line_gate.test.mjs
// เรียก handler จริงด้วย req/res ปลอม · mock fetch (LINE) + @supabase/supabase-js (ไม่ต้องติดตั้งแพ็กเกจ)
import { createRequire } from "module";
import Module from "module";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
let fails = 0, passes = 0;
const ok = (c, m) => { if (c) passes++; else { fails++; console.log("FAIL " + m); } };

const EMP = "U" + "a".repeat(32), ALLOW = "U" + "b".repeat(32), OUT = "U" + "c".repeat(32), GONE = "U" + "d".repeat(32);
const GONE_ALLOW = "U" + "e".repeat(32), REHIRE = "U" + "f".repeat(32);
const ROWS = {
  employees: [{ line_id: EMP, active: true }, { line_id: GONE, active: false }, { line_id: GONE_ALLOW, active: false },
              { line_id: REHIRE, active: false }, { line_id: REHIRE, active: true }],
  allowed_line_ids: [{ line_id: ALLOW, active: true }, { line_id: GONE_ALLOW, active: true }],
};
let calls, errTable;
const admin = {
  from(table) {
    const f = {};
    const b = {
      select() { return b; },
      eq(c, v) { f[c] = v; return b; },
      limit() {
        calls.push("from:" + table);
        if (errTable === table) return Promise.resolve({ data: null, error: { message: "x" } });
        return Promise.resolve({ data: (ROWS[table] || []).filter(r => Object.entries(f).every(([c, v]) => r[c] === v)), error: null });
      },
    };
    return b;
  },
  auth: { admin: {
    createUser: async (o) => { calls.push("createUser"); return { data: { user: { id: "u1" } }, error: null }; },
    generateLink: async ({ email }) => { calls.push("generateLink"); return { data: { user: { id: "u1", email, app_metadata: { line_id: email.slice(5, 38) } }, properties: { hashed_token: "HT" } }, error: null }; },
    updateUserById: async () => { calls.push("updateUserById"); return { error: null }; },
  } },
};
// mock @supabase/supabase-js
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, ...a) { return req === "@supabase/supabase-js" ? "@supabase/supabase-js" : origResolve.call(this, req, ...a); };
require.cache["@supabase/supabase-js"] = { id: "@supabase/supabase-js", filename: "@supabase/supabase-js", loaded: true, exports: { createClient: () => admin } };

const gate = require(path.join(root, "api/line/_lineGate.js"));
const handler = require(path.join(root, "api/line/callback.js"));
Object.assign(process.env, { LINE_CHANNEL_ID: "1", LINE_CHANNEL_SECRET: "s", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "k" });

async function login(lineId, host = "production.007metals.com") {
  calls = [];
  globalThis.fetch = async (url) => {
    if (String(url).includes("/oauth2/v2.1/token")) return { ok: true, json: async () => ({ access_token: "AT" }) };
    if (String(url).includes("/v2/profile")) return { ok: true, json: async () => ({ userId: lineId, displayName: "x" }) };
    throw new Error("unexpected fetch " + url);
  };
  const headers = {};
  const res = {
    statusCode: 200,
    setHeader(k, v) { headers[k.toLowerCase()] = v; },
    status(c) { this.statusCode = c; return this; },
    json() { this.end(); },
    end() {},
  };
  const req = { method: "GET", headers: { host, cookie: "line_oauth_state=ST" }, query: { code: "C", state: "ST" } };
  const logErr = console.error; console.error = () => {};
  try { await handler(req, res); } finally { console.error = logErr; }
  return { status: res.statusCode, location: headers.location || "", cookie: [].concat(headers["set-cookie"] || []).join(";") };
}

// ---- helper ----
calls = [];
ok(await gate.isRegisteredLine(admin, EMP) === true, "พนักงาน active = ลงทะเบียนแล้ว");
ok(await gate.isRegisteredLine(admin, ALLOW) === true, "allowed_line_ids active = ลงทะเบียนแล้ว");
ok(await gate.isRegisteredLine(admin, OUT) === false, "LINE คนนอก = ไม่ลงทะเบียน");
ok(await gate.isRegisteredLine(admin, GONE) === false, "พนักงานพ้นสภาพ = ไม่ลงทะเบียน");
calls = [];
ok(await gate.isRegisteredLine(admin, GONE_ALLOW) === false && !calls.includes("from:allowed_line_ids"), "พนักงานพ้นสภาพที่ค้างใน allowed_line_ids = ปฏิเสธ ไม่ไปเปิดทาง allowlist");
ok(await gate.isRegisteredLine(admin, REHIRE) === true, "มีแถวพ้นสภาพ + แถว active = ลงทะเบียนแล้ว");
calls = [];
ok(await gate.isRegisteredLine(admin, "U1' or '1'='1") === false && calls.length === 0, "line_id รูปแบบผิด → false ไม่ถาม DB");
ok(gate.notRegisteredLocation("https://production.007metals.com") === "https://app.007metals.com/auth/line/start", "โดเมนองค์กร → hub");
ok(gate.notRegisteredLocation("https://x.vercel.app") === "https://x.vercel.app/?lineerror=notreg", "preview → ?lineerror=notreg");

// ---- handler จริง ----
let r = await login(OUT);
ok(r.status === 302 && r.location === "https://app.007metals.com/auth/line/start", "LINE คนนอก → 302 ไป hub (ฟอร์มขอสิทธิ์)");
ok(!calls.includes("createUser") && !calls.includes("generateLink"), "LINE คนนอก → ไม่ createUser / ไม่ออก magic link");
ok(!r.location.includes("lt="), "LINE คนนอก → ไม่มี token ใน URL");
ok(/line_oauth_state=;.*Max-Age=0/.test(r.cookie), "ลบ cookie state เสมอ");

for (const id of [GONE, GONE_ALLOW]) {
  r = await login(id);
  ok(r.location.startsWith("https://app.007metals.com/") && !calls.includes("createUser") && !calls.includes("generateLink"), `พนักงานพ้นสภาพ${id === GONE_ALLOW ? " (ค้าง allowlist)" : ""} → ไม่ได้ session`);
}

r = await login(OUT, "prod-preview.vercel.app");
ok(r.location === "https://prod-preview.vercel.app/?lineerror=notreg" && !calls.includes("createUser"), "preview: LINE คนนอก → ?lineerror=notreg");

for (const id of [EMP, ALLOW]) {
  r = await login(id);
  ok(r.status === 302 && r.location === "https://production.007metals.com/#lt=HT", `ลงทะเบียนแล้ว (${id === EMP ? "พนักงาน" : "allowlist"}) → ได้ #lt= ตามเดิม`);
  ok(calls.indexOf("from:employees") < calls.indexOf("createUser") && calls.includes("generateLink"), "เช็คทะเบียนก่อน createUser");
}

errTable = "employees";
r = await login(EMP);
ok(r.location === "https://production.007metals.com/?lineerror=1" && !calls.includes("createUser"), "DB error ตอนเช็คทะเบียน → ปฏิเสธล็อกอิน (ไม่ปล่อยผ่าน)");
errTable = null;

console.log(`${passes} PASS` + (fails ? ` · ${fails} FAIL` : " · ALL PASS"));
process.exit(fails ? 1 : 0);
