-- เพิ่มคอลัมน์ line_id ให้ตาราง staff สำหรับผูกบัญชี LINE (p3-2)
-- รันเองใน Supabase SQL editor (โปรเจกต์ dbbhg) — Claude ไม่รันให้

alter table public.staff add column if not exists line_id text;

-- 1 LINE = 1 staff (กันผูกซ้ำ) แต่ยอมให้ line_id เป็น null ได้หลายแถว
create unique index if not exists staff_line_id_uk
  on public.staff (line_id)
  where line_id is not null;
