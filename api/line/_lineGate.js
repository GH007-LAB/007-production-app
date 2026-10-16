// ด่านทะเบียนก่อนสร้างผู้ใช้ LINE (17 ต.ค. 69) — คู่กับ hub SP-TT-dashboard/lib/lineGate.ts
// ไฟล์ขึ้นต้น "_" = Vercel ไม่ทำเป็น route
// ออก session ให้เฉพาะ LINE ที่ผูกทะเบียนแล้ว (ตรงกับ is_current_user_allowed ฝั่ง DB)
//   1) employees.active และ employees.line_id ตรง
//   2) allowed_line_ids.active (allowlist เดิมที่ hub /api/line/approve เขียน)
// ที่เหลือ = ยังไม่ได้รับอนุมัติ → ไม่สร้าง user · ส่งไปล็อกอินที่ hub ซึ่งมีฟอร์มขอสิทธิ์

const LINE_ID_RE = /^U[0-9a-f]{32}$/;

// admin = client service role · error → โยนออก (ปฏิเสธล็อกอิน) ไม่ปล่อยผ่าน
async function isRegisteredLine(admin, lineId) {
  if (typeof lineId !== "string" || !LINE_ID_RE.test(lineId)) return false;
  const emp = await admin.from("employees").select("id").eq("line_id", lineId).eq("active", true).limit(1);
  if (emp.error) throw new Error("check-employees-failed");
  if ((emp.data || []).length > 0) return true;
  const allow = await admin.from("allowed_line_ids").select("line_id").eq("line_id", lineId).eq("active", true).limit(1);
  if (allow.error) throw new Error("check-allowlist-failed");
  return (allow.data || []).length > 0;
}

// โดเมนองค์กร → ล็อกอินที่ hub (มีฟอร์มขอสิทธิ์) · dev/preview → กลับหน้าแอปพร้อม ?lineerror=notreg
function notRegisteredLocation(origin) {
  const host = new URL(origin).hostname;
  if (host.endsWith("007metals.com")) return "https://app.007metals.com/auth/line/start";
  return `${origin}/?lineerror=notreg`;
}

module.exports = { isRegisteredLine, notRegisteredLocation };
