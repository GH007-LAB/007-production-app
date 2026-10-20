-- Fleet007 รถบริษัท: ทะเบียนรถ + วันครบกำหนด พรบ./ประกัน/ภาษี/ตรวจสภาพ/อื่น ๆ + แจ้งเตือนอีเมล
-- รันครั้งเดียวบน Supabase กลาง · idempotent · ทุกตาราง fleet_* เปิด RLS ไม่มี policy = service role (/api/fleet/*) เท่านั้น
-- ผู้ใช้: แอดมิน · HR · จัดซื้อ (เช็คตำแหน่งที่ API + ต้องติ๊กสิทธิ์แอป fleet007 ใน app_access)

-- 1) รถ
create table if not exists public.fleet_vehicle (
  id          bigserial primary key,
  plate       text not null,                  -- ทะเบียน เช่น "1กข 1234"
  province    text,                           -- จังหวัดบนป้าย
  brand       text,                           -- ยี่ห้อ
  model       text,                           -- รุ่น
  vtype       text,                           -- กระบะ / เก๋ง / รถบรรทุก 6 ล้อ / รถยก / มอเตอร์ไซค์ ...
  year        int,
  branch      text,                           -- สาขาที่ใช้รถ BK / SKN / PPS / สำนักงานใหญ่
  driver      text,                           -- ผู้รับผิดชอบ/คนขับประจำ
  chassis_no  text,
  note        text,
  active      boolean not null default true,  -- false = ขาย/เลิกใช้ (ไม่แจ้งเตือนแล้ว)
  updated_by  text,
  updated_at  timestamptz not null default now(),
  created_at  timestamptz not null default now()
);
create unique index if not exists fleet_vehicle_plate on public.fleet_vehicle (plate, coalesce(province, '')) where active;

-- 2) รายการที่ต้องต่ออายุ/แจ้งเตือน (ต่อคัน)
create table if not exists public.fleet_item (
  id           bigserial primary key,
  vehicle_id   bigint not null references public.fleet_vehicle(id) on delete cascade,
  kind         text not null,                 -- พรบ. · ประกันภัย · ภาษีรถยนต์ · ตรวจสภาพรถ · เปลี่ยนถ่ายน้ำมันเครื่อง · อื่น ๆ (ชื่อเอง)
  due_date     date not null,                 -- วันหมดอายุ/ครบกำหนด
  remind_days  int[] not null default '{60,30,15,7,1}',   -- เตือนล่วงหน้ากี่วัน (เกินกำหนดแล้วเตือนทุก 7 วัน)
  provider     text,                          -- บริษัทประกัน / ผู้ให้บริการ
  policy_no    text,                          -- เลขกรมธรรม์ / เลขเอกสาร
  amount       numeric,                       -- เบี้ย/ค่าใช้จ่ายล่าสุด
  note         text,
  active       boolean not null default true,
  updated_by   text,
  updated_at   timestamptz not null default now()
);
create index if not exists fleet_item_due on public.fleet_item (active, due_date);

-- 3) ประวัติการต่ออายุ (กด "ต่ออายุแล้ว" → เก็บรอบเดิม แล้วเลื่อน due_date)
create table if not exists public.fleet_renewal (
  id          bigserial primary key,
  item_id     bigint not null references public.fleet_item(id) on delete cascade,
  old_due     date,
  new_due     date not null,
  provider    text,
  policy_no   text,
  amount      numeric,
  note        text,
  renewed_by  text,
  renewed_at  timestamptz not null default now()
);

-- 4) log อีเมลแจ้งเตือน — กันส่งซ้ำ (รายการเดียวกัน · รอบ due เดียวกัน · ขั้นเดียวกัน = ส่งครั้งเดียว)
create table if not exists public.fleet_alert_log (
  id        bigserial primary key,
  ts        timestamptz not null default now(),
  item_id   bigint,
  due_date  date,
  stage     text,                             -- "30" = เหลือ 30 วัน · "overdue-14" = เกิน 14 วัน · "test"
  sent_to   text,
  ok        boolean not null default true,
  error     text
);
create unique index if not exists fleet_alert_once on public.fleet_alert_log (item_id, due_date, stage) where ok;

do $$ declare t text; p record; begin
  foreach t in array array['fleet_vehicle','fleet_item','fleet_renewal','fleet_alert_log'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
  for p in select policyname, tablename from pg_policies where schemaname = 'public' and tablename like 'fleet\_%' loop
    execute format('drop policy %I on public.%I', p.policyname, p.tablename);
  end loop;
end $$;

-- 5) ลงทะเบียนแอปใน hub — ติ๊กสิทธิ์ให้ แอดมิน / HR / จัดซื้อ ที่ app.007metals.com/admin/access
insert into public.apps (code, name_th, url, icon, description, sort, active)
values ('fleet007', 'Fleet007 · รถบริษัท', 'https://production.007metals.com/fleet007',
        'truck', 'ทะเบียนรถ · พรบ. · ประกัน · ภาษี · ตรวจสภาพ · แจ้งเตือนอีเมล', 12, true)
on conflict (code) do nothing;
