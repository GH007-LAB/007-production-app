// GET /api/line/start
// เริ่มล็อกอิน LINE: สร้าง state กัน CSRF → set cookie → redirect ไปหน้ายินยอมของ LINE
const crypto = require("crypto");

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.status(405).json({ error: "method-not-allowed" });
    return;
  }

  const channelId = process.env.LINE_CHANNEL_ID;
  if (!channelId) {
    // อย่ารั่วรายละเอียด env ออกฝั่ง client
    res.status(500).json({ error: "server-misconfigured" });
    return;
  }

  // origin ของ deployment (Vercel ให้ host มาใน header เสมอ, บังคับ https)
  const origin = `https://${req.headers.host}`;
  const redirectUri = `${origin}/api/line/callback`;

  const state = crypto.randomUUID();

  // เก็บ state ไว้ใน cookie HttpOnly เพื่อเทียบตอน callback
  res.setHeader("Set-Cookie", [
    `line_oauth_state=${state}; HttpOnly; Secure; SameSite=Lax; Max-Age=600; Path=/`,
  ]);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: channelId,
    redirect_uri: redirectUri,
    state,
    scope: "profile openid",
  });

  res.statusCode = 302;
  res.setHeader("Location", `https://access.line.me/oauth2/v2.1/authorize?${params.toString()}`);
  res.end();
};
