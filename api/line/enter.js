// POST /api/line/enter
// ทางเข้าแอพระบบผลิตจากล็อกอินกลาง — ไม่ต้องรัน SQL/ไม่ต้องให้แอดมินกรอก staff ล่วงหน้า
//
// ปัญหาเดิม: ตาราง staff ของแอพผลิตเป็นชื่อตัวอย่าง ไม่มี email/line_id พนักงานจริง
//   ล็อกอินกลางด้วย LINE เข้ามาแล้วหา staff ไม่เจอ → ติดหน้า "ผูกบัญชี LINE" ตลอด
//   (กรอกอีเมลก็ไม่ผ่าน เพราะ /api/line/link หาแต่ในตาราง staff ซึ่งไม่มีอีเมลใครเลย)
//
// วิธีแก้: ให้ฝั่งเซิร์ฟเวอร์ (service role) เทียบกับ "ทะเบียนพนักงานกลาง" แทน
//   1) staff เดิมที่ผูก line_id ไว้แล้ว → เข้าเลย
//   2) ไม่เจอ → หา employees จาก line_id (อัตโนมัติ) หรือจากอีเมลบริษัทที่กรอก
//   3) ต้องมีสิทธิ์แอพ production ใน app_access (รปภ./คนที่แอดมินไม่ได้ติ๊ก → ไม่ผ่าน)
//   4) map ตำแหน่ง → role ของแอพผลิต แล้วสร้าง/ผูกแถว staff ให้อัตโนมัติ
//      (FK created_by/staff_id ชี้เข้า staff(id) จึงต้องมีแถวจริงเสมอ)
//
// Authorization: Bearer <supabase access_token> ของ session กลาง (ต้องเป็นล็อกอิน LINE)
// body (ไม่บังคับ): { email } — ใช้เฉพาะกรณี employees.line_id ยังว่าง
const { createClient } = require("@supabase/supabase-js");

const APP_CODE = "production";

// ตำแหน่งในทะเบียนกลาง → role ของแอพผลิต
function roleFromEmployee(emp) {
  const pos = (emp.position || "").trim();
  if (emp.is_admin || pos === "ผู้จัดการสาขา") return "admin";
  if (pos === "หัวหน้าฝ่ายผลิตและจัดส่ง" || pos === "โฟร์แมน") return "planner";
  if (
    pos === "หัวหน้าฝ่ายขาย" ||
    pos === "พนักงานขาย" ||
    pos === "พนักงานขายออนไลน์" ||
    pos === "พนักงานไลฟ์สด"
  )
    return "sales";
  if (pos === "พนักงานขับรถ" || pos === "สต๊อก") return "packer";
  return "operator";
}

async function readJsonBody(req) {
  if (req.body) {
    if (typeof req.body === "object") return req.body;
    if (typeof req.body === "string") {
      try { return JSON.parse(req.body); } catch { return null; }
    }
  }
  const chunks = [];
  for await (const c of req) chunks.push(c);
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch { return null; }
}

const STAFF_COLS = "id,branch,name,role,can_approve,email,active,line_id";

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method-not-allowed" });
    return;
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    res.status(500).json({ error: "server-misconfigured" });
    return;
  }

  const authz = req.headers.authorization || "";
  const token = authz.startsWith("Bearer ") ? authz.slice(7).trim() : null;
  if (!token) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }

  const body = await readJsonBody(req);
  if (body === null) {
    res.status(400).json({ error: "bad-request" });
    return;
  }
  let claimedEmail = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (claimedEmail && (claimedEmail.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(claimedEmail))) {
    res.status(400).json({ error: "invalid-email" });
    return;
  }

  const admin = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    const { data: userData, error: userErr } = await admin.auth.getUser(token);
    const user = userData && userData.user;
    if (userErr || !user) {
      res.status(401).json({ error: "unauthorized" });
      return;
    }
    const lineId = (user.user_metadata && user.user_metadata.line_id) || null;
    // อีเมล session ของ LINE เป็นอีเมลสังเคราะห์ (line_<id>@line.007metals.local) — ใช้เทียบไม่ได้
    const realEmail =
      user.email && !/@line\.007metals\.local$/i.test(user.email)
        ? user.email.toLowerCase()
        : null;
    if (!lineId && !realEmail) {
      res.status(401).json({ error: "unauthorized" });
      return;
    }

    // 1) staff เดิมที่ผูกไว้แล้ว
    if (lineId) {
      const { data: rows, error } = await admin
        .from("staff").select(STAFF_COLS).eq("active", true).eq("line_id", lineId).limit(1);
      if (error) throw error;
      if (rows && rows.length) { res.status(200).json({ staff: rows[0], via: "staff-line" }); return; }
    }
    if (realEmail) {
      const { data: rows, error } = await admin
        .from("staff").select(STAFF_COLS).eq("active", true).ilike("email", realEmail).limit(1);
      if (error) throw error;
      if (rows && rows.length) { res.status(200).json({ staff: rows[0], via: "staff-email" }); return; }
    }

    // 2) ทะเบียนพนักงานกลาง — line_id ก่อน (อัตโนมัติ) แล้วค่อยอีเมลที่กรอก/อีเมล session
    const empCols = "id,nickname,full_name,branch,position,is_admin,email,line_id,active";
    let emp = null;
    if (lineId) {
      const { data, error } = await admin
        .from("employees").select(empCols).eq("active", true).eq("line_id", lineId).limit(1);
      if (error) throw error;
      if (data && data.length) emp = data[0];
    }
    const lookupEmail = claimedEmail || realEmail;
    if (!emp && lookupEmail) {
      const { data, error } = await admin
        .from("employees").select(empCols).eq("active", true).ilike("email", lookupEmail).limit(2);
      if (error) throw error;
      if (data && data.length > 1) { res.status(409).json({ error: "email-ambiguous" }); return; }
      if (data && data.length) {
        // กันสวมสิทธิ์: อีเมลที่ผูก LINE อื่นไว้แล้ว ห้ามคนอื่นมาอ้าง
        if (data[0].line_id && lineId && data[0].line_id !== lineId) {
          res.status(409).json({ error: "already-linked" });
          return;
        }
        emp = data[0];
      }
    }
    if (!emp) {
      res.status(404).json({ error: lookupEmail ? "employee-not-found" : "need-email" });
      return;
    }

    // 3) สิทธิ์แอพระบบผลิต (ติ๊กที่ app.007metals.com/admin/access)
    const { data: appRows, error: appErr } = await admin
      .from("apps").select("id").eq("code", APP_CODE).limit(1);
    if (appErr) throw appErr;
    if (!appRows || !appRows.length) { res.status(500).json({ error: "app-missing" }); return; }
    const { data: accRows, error: accErr } = await admin
      .from("app_access").select("app_id").eq("employee_id", emp.id).eq("app_id", appRows[0].id).limit(1);
    if (accErr) throw accErr;
    if (!accRows || !accRows.length) { res.status(403).json({ error: "no-app-access" }); return; }

    // 4) map ตำแหน่ง → role
    const role = roleFromEmployee(emp);
    const empEmail = emp.email ? emp.email.toLowerCase() : lookupEmail || null;

    // 5) มีแถว staff อีเมลตรงอยู่แล้ว → ผูก line_id ให้ / ไม่มี → สร้างใหม่
    let staffRow = null;
    if (empEmail) {
      const { data, error } = await admin
        .from("staff").select(STAFF_COLS).eq("active", true).ilike("email", empEmail).limit(1);
      if (error) throw error;
      if (data && data.length) staffRow = data[0];
    }
    if (staffRow) {
      if (!staffRow.line_id && lineId) {
        const { data, error } = await admin
          .from("staff").update({ line_id: lineId }).eq("id", staffRow.id).select(STAFF_COLS).maybeSingle();
        if (error && error.code === "23505") { res.status(409).json({ error: "line-already-used" }); return; }
        if (error) throw error;
        if (data) staffRow = data;
      }
    } else {
      const { data, error } = await admin
        .from("staff")
        .insert({
          branch: emp.branch,
          name: emp.nickname || emp.full_name || empEmail,
          role,
          line_id: lineId,
          email: empEmail,
          active: true,
          can_approve: role === "admin" || role === "planner",
        })
        .select(STAFF_COLS)
        .maybeSingle();
      if (error && error.code === "23505") { res.status(409).json({ error: "line-already-used" }); return; }
      if (error) throw error;
      staffRow = data;
    }

    if (!staffRow) { res.status(500).json({ error: "server-error" }); return; }
    res.status(200).json({ staff: staffRow, via: "employees" });
  } catch (e) {
    console.error("LINE enter error:", e && e.message ? e.message : e);
    res.status(500).json({ error: "server-error" });
  }
};
