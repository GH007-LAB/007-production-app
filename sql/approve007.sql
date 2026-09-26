-- Approve007 (P-17 เฟส 1) — รันครั้งเดียวบน Supabase กลาง (syvfdbvmwaeyokytckwb) · idempotent
-- ทุกตาราง approve_* เปิด RLS และ "ไม่มี policy" = anon/authenticated อ่าน-เขียนไม่ได้เลย
-- เข้าถึงได้เฉพาะ service role จาก /api/approve/* บน Vercel (ทุนห้ามถึงเครื่องเซล)

-- 1) snapshot จาก Mac mini: ทุน (costbook_rules) · Rate 1 · รายการสินค้า · ช่วงราคา — เก็บ 5 ชุดล่าสุด
create table if not exists public.approve_snapshot (
  id          bigserial primary key,
  created_at  timestamptz not null default now(),
  payload     jsonb not null
);

-- 2) บรรทัดบิล SO พร้อมราคา (ย้อนหลัง 60 วัน) — แยกจาก so_item_live ที่อ่านได้สาธารณะและไม่มีราคา
create table if not exists public.approve_so_line (
  branch     text not null,
  sonum      text not null,
  seq        int  not null,
  sodat      date,
  stkcod     text,
  stkdes     text,
  qty        numeric,
  price      numeric,
  value      numeric,
  tfactor    numeric default 1,
  cusnam     text,
  synced_at  timestamptz not null default now(),
  primary key (branch, sonum, seq)
);
create index if not exists approve_so_line_sonum on public.approve_so_line (sonum);
create index if not exists approve_so_line_date  on public.approve_so_line (branch, sodat);

-- 3) log ทุกการเช็ค (ไม่มีทุน/GP) — กันไล่ราคา + ส่งผล < 75% เข้า approval_requests.jsonl
create table if not exists public.approve_check_log (
  id           bigserial primary key,
  ts           timestamptz not null default now(),
  employee_id  text,
  name         text,
  role         text,
  branch       text,
  layer        text,
  key          text,
  sonum        text,
  total        numeric,
  grade        text,
  chance       int,
  coverage     int,
  blocked      boolean not null default false
);
create index if not exists approve_check_log_chase on public.approve_check_log (employee_id, key, ts);

alter table public.approve_snapshot  enable row level security;
alter table public.approve_so_line   enable row level security;
alter table public.approve_check_log enable row level security;
-- ตั้งใจไม่สร้าง policy ใด ๆ · ถ้าเคยมีให้ลบทิ้ง
do $$ declare p record; begin
  for p in select policyname, tablename from pg_policies
           where schemaname = 'public' and tablename in ('approve_snapshot','approve_so_line','approve_check_log') loop
    execute format('drop policy %I on public.%I', p.policyname, p.tablename);
  end loop;
end $$;
revoke all on public.approve_snapshot, public.approve_so_line, public.approve_check_log from anon, authenticated;

-- 4) ลงทะเบียนแอปใน hub — แล้วติ๊กสิทธิ์รายคนที่ app.007metals.com/admin/access
--    ⚠️ ตรวจชื่อคอลัมน์ของตาราง apps ก่อนรัน (อ้างจาก /api/line/enter ที่ใช้ apps.code)
insert into public.apps (code, name)
select 'approve007', 'Approve007 · ขายได้เลยไหม'
where not exists (select 1 from public.apps where code = 'approve007');
