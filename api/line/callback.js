// GET /api/line/callback
// ตรวจ state (CSRF) → แลก code เป็น token → ดึงโปรไฟล์ LINE
// → สร้าง/หา user ใน Supabase (ผูก line_id ใน user_metadata)
// → ออก magic-link hashed_token แล้ว redirect กลับหน้าแอปเป็น #lt=<token>
//   ให้ฝั่ง client (static app) เอาไป sb.auth.verifyOtp เองเพื่อเปิด session
const { createClient } = require("@supabase/supabase-js");

// อ่านค่า cookie ตัวเดียวจาก header (เลี่ยง dependency เพิ่ม)
function readCookie(cookieHeader, name) {
  if (!cookieHeader) return null;
  const parts = cookieHeader.split(";");
  for (const p of parts) {
    const idx = p.indexOf("=");
    if (idx === -1) continue;
    const k = p.slice(0, idx).trim();
    if (k === name) return p.slice(idx + 1).trim();
  }
  return null;
}

module.exports = async function handler(req, res) {
  const origin = `https://${req.headers.host}`;

  // helper: redirect กลับหน้าแอป (ลบ cookie state ทิ้งเสมอ)
  const back = (hashOrQuery) => {
    res.setHeader("Set-Cookie", [
      `line_oauth_state=; HttpOnly; Secure; SameSite=Lax; Max-Age=0; Path=/`,
    ]);
    res.statusCode = 302;
    res.setHeader("Location", `${origin}/${hashOrQuery}`);
    res.end();
  };

  if (req.method !== "GET") {
    res.status(405).json({ error: "method-not-allowed" });
    return;
  }

  const code = req.query && req.query.code;
  const state = req.query && req.query.state;
  const cookieState = readCookie(req.headers.cookie, "line_oauth_state");

  // ตรวจ state ป้องกัน CSRF; ผู้ใช้กดยกเลิกที่ LINE ก็จะไม่มี code เช่นกัน
  if (!code || !state || !cookieState || state !== cookieState) {
    back("?lineerror=1");
    return;
  }

  const channelId = process.env.LINE_CHANNEL_ID;
  const channelSecret = process.env.LINE_CHANNEL_SECRET;
  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!channelId || !channelSecret || !supabaseUrl || !serviceKey) {
    back("?lineerror=1");
    return;
  }

  try {
    const redirectUri = `${origin}/api/line/callback`;

    // 1) แลก authorization code → access token
    const tokenRes = await fetch("https://api.line.me/oauth2/v2.1/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
        client_id: channelId,
        client_secret: channelSecret,
      }).toString(),
    });
    if (!tokenRes.ok) throw new Error("token-exchange-failed");
    const tokens = await tokenRes.json();

    // 2) ดึงโปรไฟล์ LINE → userId ใช้เป็น line_id
    const profRes = await fetch("https://api.line.me/v2/profile", {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    if (!profRes.ok) throw new Error("profile-failed");
    const profile = await profRes.json();
    const lineId = profile.userId;
    if (!lineId) throw new Error("no-line-id");

    // 3) Supabase admin (service role) — อีเมลสังเคราะห์คงที่ต่อ 1 LINE user
    const admin = createClient(supabaseUrl, serviceKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const email = `line_${lineId}@line.007metals.local`;

    // สร้าง user ครั้งแรก (ครั้งถัดไปจะได้ error ว่ามีอยู่แล้ว → ข้ามได้)
    await admin.auth.admin.createUser({
      email,
      email_confirm: true,
      user_metadata: {
        line_id: lineId,
        display_name: profile.displayName,
        provider: "line",
      },
    });

    // 4) ออก magic link (ใช้ได้ทั้ง user ใหม่และเก่า) → เอา hashed_token
    const { data: link, error: linkErr } = await admin.auth.admin.generateLink({
      type: "magiclink",
      email,
    });
    if (linkErr || !link || !link.properties || !link.properties.hashed_token) {
      throw new Error("generate-link-failed");
    }

    // 5) ส่ง token กลับใน URL fragment (ไม่ถูกส่งไป server, client อ่านเองแล้ว verifyOtp)
    back(`#lt=${encodeURIComponent(link.properties.hashed_token)}`);
  } catch (e) {
    // log ฝั่ง server เท่านั้น ไม่ส่งรายละเอียดออก client
    console.error("LINE callback error:", e && e.message ? e.message : e);
    back("?lineerror=1");
  }
};
