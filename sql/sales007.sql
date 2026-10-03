-- Sales007 รายงานขายประจำวันแบบ live (salesreport007 v6) — รันครั้งเดียวบน Supabase กลาง · idempotent
-- ทุกตาราง sales_* เปิด RLS และ "ไม่มี policy" = anon/authenticated อ่าน-เขียนไม่ได้
-- เข้าถึงได้เฉพาะ service role ผ่าน /api/sales/* บน Vercel (ยอดเงินห้ามถึงเครื่องสาขาโดยตรง)

-- 1) เอกสารจาก Express (IV · AI · SR · HS · RE) — sales_push.py บนเครื่องสาขาส่งมาทุก 1 นาที
create table if not exists public.sales_doc (
  branch         text not null,
  doc_no         text not null,
  type           text not null,                 -- IV AI SR HS RE
  doc_date       date not null,
  cuscod         text,
  customer       text,
  total          numeric not null default 0,    -- ยอดรวม VAT ตาม Express
  remain         numeric,                       -- IV: ยอดค้าง (ถ้า Express มี)
  refs           jsonb not null default '[]',   -- RE: เลข IV ที่ตัดชำระ (ARRCPIT)
  active         boolean not null default true, -- false = ถูกลบ/ยกเลิกใน Express
  first_seen_at  timestamptz not null default now(),   -- เวลาที่ระบบเห็นครั้งแรก → ใช้แบ่งรอบ (ไม่ส่งใน upsert)
  updated_at     timestamptz not null default now(),
  report_date    date,                          -- ประทับตอนล็อกรายงาน = เอกสารนี้อยู่ในรายงานวันไหน
  primary key (branch, doc_no)
);
create index if not exists sales_doc_open on public.sales_doc (branch, report_date, first_seen_at);
create index if not exists sales_doc_day  on public.sales_doc (branch, doc_date, type);

-- 2) ช่องทางที่พนักงานเลือก (แยกจากข้อมูล Express — feeder เขียนทับ sales_doc ได้โดยไม่ลบตัวเลือก)
create table if not exists public.sales_choice (
  branch      text not null,
  doc_no      text not null,
  channel     text not null,                    -- RE/AI/HS: cash | transfer | qr · SR: deduct | refund_cash
  set_by      text,
  set_at      timestamptz not null default now(),
  primary key (branch, doc_no)
);
create table if not exists public.sales_choice_log (
  id bigserial primary key, ts timestamptz not null default now(),
  branch text, doc_no text, channel text, set_by text
);

-- 3) รายจ่ายประจำวัน (จ่ายจากลิ้นชักเงินสด) — รูปบิลเก็บใน storage bucket sales007 (private)
create table if not exists public.sales_expense (
  id           bigserial primary key,
  branch       text not null,
  report_date  date not null,
  category     text not null,
  item         text not null,
  payee        text,
  amount       numeric not null check (amount > 0),
  bill_no      text,
  receipt_path text,                            -- ว่าง = ไม่มีรูปบิล → ไม่นับเป็นรายจ่าย
  created_by   text,
  created_at   timestamptz not null default now(),
  deleted      boolean not null default false
);
create index if not exists sales_expense_day on public.sales_expense (branch, report_date);

-- 4) รายงานต่อสาขาต่อวัน — snapshot ณ เวลาล็อก = หลักฐาน (แก้หลังจากนี้ไม่นับ)
create table if not exists public.sales_report (
  branch        text not null,
  report_date   date not null,
  status        text not null default 'locked',  -- locked (ส่งแล้ว หรือ ล็อกอัตโนมัติ)
  lock_reason   text,                            -- submit | deadline | manual
  cash_counted  numeric,
  preparer      text,
  submitted_at  timestamptz,
  locked_at     timestamptz not null default now(),
  float         numeric not null default 0,
  summary       jsonb not null,
  snapshot      jsonb not null,
  primary key (branch, report_date)
);

-- 5) สถานะ feeder ต่อสาขา (หน้าแอปโชว์ "อัปเดตจาก Express ล่าสุด")
create table if not exists public.sales_feed (
  branch       text primary key,
  last_push_at timestamptz not null default now(),
  info         jsonb
);

do $$ declare t text; p record; begin
  foreach t in array array['sales_doc','sales_choice','sales_choice_log','sales_expense','sales_report','sales_feed'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
  for p in select policyname, tablename from pg_policies where schemaname = 'public' and tablename like 'sales\_%' loop
    execute format('drop policy %I on public.%I', p.policyname, p.tablename);
  end loop;
end $$;

-- 6) bucket รูปบิล (private — เปิดดูผ่าน signed URL จาก API เท่านั้น)
insert into storage.buckets (id, name, public) values ('sales007', 'sales007', false) on conflict (id) do nothing;

-- 7) ลงทะเบียนแอปใน hub — แล้วติ๊กสิทธิ์รายคนที่ app.007metals.com/admin/access
insert into public.apps (code, name_th, url, icon, description, sort, active)
values ('sales007', 'Sales007 · รายงานขายประจำวัน', 'https://production.007metals.com/sales007',
        'receipt', 'IV/RE live จาก Express · เลือกช่องทางรับเงิน · รายจ่ายประจำวัน · ปิดยอด', 11, true)
on conflict (code) do nothing;
