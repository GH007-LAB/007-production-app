-- RPC หา staff จาก line_id สำหรับ LINE login (p3-2 fix)
-- เหตุผล: ตาราง staff ให้ SELECT แก่ anon/authenticated แบบ column-level เท่านั้น
--   (อ่าน email/pin/line_id ไม่ได้) การ query .from("staff").eq("line_id",...) จึงโดน 42501
-- วิธีแก้: ใช้ SECURITY DEFINER RPC (แนวเดียวกับ verify_pin) คืนทุกคอลัมน์ยกเว้น pin
-- รันบน Supabase production (dbbhg) แล้ว 2026-08-06

create or replace function public.staff_by_line_id(p_line_id text)
returns table(id bigint, branch text, name text, role text,
              can_approve boolean, email text, active boolean, line_id text)
language sql
security definer
set search_path = public
as $func$
  select s.id, s.branch, s.name, s.role, s.can_approve, s.email, s.active, s.line_id
  from public.staff s
  where s.line_id = p_line_id and s.active = true
$func$;

revoke all on function public.staff_by_line_id(text) from public;
-- ⚠️ 5 ต.ค. 69 (C1): เชื่อพารามิเตอร์ + เปิดให้ anon = ใครก็ดึงแถว staff จาก line_id ได้
--   ปิดสิทธิ์ client ทั้งหมดแล้วใน ~/SP-TT-dashboard/db/c1_line_id_app_metadata.sql
--   (prod_enter อ่านตัวตนจาก JWT ครอบหน้าที่นี้แล้ว · index.html เลิกเรียก) — ห้าม grant กลับ
revoke all on function public.staff_by_line_id(text) from public, anon, authenticated;
