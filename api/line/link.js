// POST /api/line/link
// ผูกบัญชี LINE เข้ากับ staff ครั้งแรก (self-service)
// - Authorization: Bearer <supabase access_token> (session LINE ที่ client เพิ่ง verifyOtp)
// - body JSON: { email }  (อีเมล staff ที่ต้องการผูก)
// ยืนยันตัวตนจาก token → เอา line_id ใน user_metadata → หา staff ตาม email → set line_id
const { createClient } = require("@supabase/supabase-js");

// รวม body เป็น JSON (รองรับทั้งกรณี Vercel parse ให้แล้ว และ raw stream)
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

  // ดึง access token จาก header
  const authz = req.headers.authorization || "";
  const token = authz.startsWith("Bearer ") ? authz.slice(7).trim() : null;
  if (!token) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }

  // อ่าน + validate body
  const body = await readJsonBody(req);
  if (!body || typeof body.email !== "string") {
    res.status(400).json({ error: "bad-request" });
    return;
  }
  const email = body.email.trim();
  if (!email || email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    res.status(400).json({ error: "invalid-email" });
    return;
  }

  const admin = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    // ยืนยัน token → ต้องเป็น user ที่มี line_id (มาจากล็อกอิน LINE เท่านั้น)
    const { data: userData, error: userErr } = await admin.auth.getUser(token);
    const lineId =
      userData && userData.user && userData.user.user_metadata
        ? userData.user.user_metadata.line_id
        : null;
    if (userErr || !lineId) {
      res.status(401).json({ error: "unauthorized" });
      return;
    }

    // หา staff ที่ active ตาม email (case-insensitive)
    const { data: staffRows, error: staffErr } = await admin
      .from("staff")
      .select("id,email,active,line_id")
      .eq("active", true)
      .ilike("email", email)
      .limit(2);
    if (staffErr) throw staffErr;

    if (!staffRows || staffRows.length === 0) {
      res.status(404).json({ error: "email-not-found" });
      return;
    }
    if (staffRows.length > 1) {
      // อีเมลซ้ำหลาย staff — ไม่เดา ให้แอดมินจัดการ
      res.status(409).json({ error: "email-ambiguous" });
      return;
    }

    const staff = staffRows[0];

    // ถ้า staff คนนี้เคยผูก LINE อื่นไว้แล้ว → กันเขียนทับ
    if (staff.line_id && staff.line_id !== lineId) {
      res.status(409).json({ error: "already-linked" });
      return;
    }

    // ผูก line_id (unique index กันกรณี line_id นี้ไปผูกกับ staff อื่นแล้ว)
    const { error: updErr } = await admin
      .from("staff")
      .update({ line_id: lineId })
      .eq("id", staff.id);
    if (updErr) {
      // ชน unique index = LINE นี้ผูกกับ staff อื่นอยู่
      if (updErr.code === "23505") {
        res.status(409).json({ error: "line-already-used" });
        return;
      }
      throw updErr;
    }

    res.status(200).json({ ok: true, staff_id: staff.id });
  } catch (e) {
    console.error("LINE link error:", e && e.message ? e.message : e);
    res.status(500).json({ error: "server-error" });
  }
};
