-- ============================================================
-- PPP v8.4 — 👥 หลายคนเข้าร่วมงานเครื่องจักร + ✏️ วาดแบบครอบด้วยมือ
-- รันใน Supabase → SQL Editor → New query → วางทั้งหมด → Run
-- รันซ้ำได้ ไม่พัง (ใช้ if not exists / create or replace)
-- ============================================================

-- 1) คอลัมน์ใหม่ -------------------------------------------------
-- workers: [{id, name, in, out}] — ใครลงมือทำใบนี้บ้าง เข้าเมื่อไหร่ ออกเมื่อไหร่
alter table production_ticket
  add column if not exists workers jsonb not null default '[]'::jsonb;

-- sketch: {paths:[{d,c,w}]} — ลายเส้น vector (ไม่ใช่รูปภาพ จะได้ไม่กินโควต้า)
-- note  : โน้ตข้อความถึงช่าง
alter table shape_drawing
  add column if not exists sketch jsonb,
  add column if not exists note   text;


-- 2) RPC เข้าร่วม/ออก/ปิดงาน ------------------------------------
-- ทำไมต้องเป็น RPC ไม่ใช่ update ตรงจากแอป:
-- ช่าง 2-6 คนกด ➕ พร้อมกันได้จริง (PU 6 คน) ถ้าให้แอปอ่าน array → แก้ → เขียนกลับ
-- คนที่กดทีหลังจะเขียนทับคนแรกหาย ต่อ array ในคำสั่ง SQL เดียว = ใครกดก็ติดครบทุกคน

create or replace function join_work(p_ticket uuid, p_staff jsonb)
returns void
language sql
security definer
set search_path = public
as $$
  update production_ticket
     set workers = coalesce(workers,'[]'::jsonb) || jsonb_build_array(p_staff)
   where id = p_ticket
     -- กันกดซ้ำ: ถ้าคนนี้ยังอยู่ในงาน (ยังไม่มี out) ไม่ต้องเพิ่มซ้อน
     and not exists (
       select 1 from jsonb_array_elements(coalesce(workers,'[]'::jsonb)) w
        where w->>'id' = p_staff->>'id' and (w->'out') is null
     );
$$;

create or replace function leave_work(p_ticket uuid, p_id text, p_at text)
returns void
language sql
security definer
set search_path = public
as $$
  update production_ticket
     set workers = (
       select coalesce(jsonb_agg(
                case when w->>'id' = p_id and (w->'out') is null
                     then w || jsonb_build_object('out', p_at)
                     else w end
              ), '[]'::jsonb)
         from jsonb_array_elements(coalesce(workers,'[]'::jsonb)) w
     )
   where id = p_ticket
     -- jsonb_agg บน array ว่างคืน NULL — กันไว้ไม่ให้ล้าง workers เป็น null
     and jsonb_array_length(coalesce(workers,'[]'::jsonb)) > 0;
$$;

-- ปิดเวลาให้ทุกคนที่ยังค้างอยู่ ตอนกด "ผลิตเสร็จ"
-- (คนลืมกด 🚪 ออก แน่นอน ถ้าไม่ปิดให้ ตัวเลขคน-นาทีจะบวมจนใช้วางแผนไม่ได้)
create or replace function close_work(p_ticket uuid, p_at text)
returns void
language sql
security definer
set search_path = public
as $$
  update production_ticket
     set workers = (
       select coalesce(jsonb_agg(
                case when (w->'out') is null
                     then w || jsonb_build_object('out', p_at)
                     else w end
              ), '[]'::jsonb)
         from jsonb_array_elements(coalesce(workers,'[]'::jsonb)) w
     )
   where id = p_ticket
     and jsonb_array_length(coalesce(workers,'[]'::jsonb)) > 0;
$$;


-- 3) สิทธิ์เรียกใช้ ---------------------------------------------
grant execute on function join_work(uuid, jsonb)  to anon, authenticated;
grant execute on function leave_work(uuid, text, text) to anon, authenticated;
grant execute on function close_work(uuid, text)  to anon, authenticated;


-- 4) เช็คว่าลงครบ ------------------------------------------------
select
  (select count(*) from information_schema.columns
    where table_name='production_ticket' and column_name='workers')            as col_workers,
  (select count(*) from information_schema.columns
    where table_name='shape_drawing' and column_name in ('sketch','note'))     as col_shape,
  (select count(*) from pg_proc
    where proname in ('join_work','leave_work','close_work'))                  as rpc_count;
-- ต้องได้ col_workers=1 · col_shape=2 · rpc_count=3


-- ═══════════════════════════════════════════════════════════════
-- 5) ✏️ เปลี่ยนชื่อเครื่องตรง สาขาสกลนคร ให้มี "สีตัวเครื่อง" อยู่ในชื่อ
--    หน้างานเรียกเครื่องด้วยสี ไม่ได้เรียก L/R → ชื่อบนบอร์ดต้องตรงกับที่ปากคนพูด
--      ตรง-L = เครื่องเขียว = ปีกซ้าย
--      ตรง-R = เครื่องแดง  = ปีกขวา
--    ⚠️ ต้องอัปเดต production_ticket.machine ด้วย เพราะใบผลิตอ้างเครื่อง "ด้วยชื่อ"
--       ถ้าเปลี่ยนแต่ตาราง machine ใบที่ค้างอยู่จะหลุดหายจากคอลัมน์บอร์ดทันที
--    รันซ้ำได้ (ไม่มีอะไรเกิดขึ้นถ้าเปลี่ยนไปแล้ว)
-- ---------------------------------------------------------------
update production_ticket set machine = 'ตรง-L เขียว ปีกซ้าย'
  where branch='SKN' and machine='ตรง-L ปีกซ้าย';
update production_ticket set machine = 'ตรง-R แดง ปีกขวา'
  where branch='SKN' and machine='ตรง-R ปีกขวา';

update machine set name='ตรง-L เขียว ปีกซ้าย', updated_at=now()
  where branch='SKN' and name='ตรง-L ปีกซ้าย';
update machine set name='ตรง-R แดง ปีกขวา',  updated_at=now()
  where branch='SKN' and name='ตรง-R ปีกขวา';

-- เช็คผล: ต้องเห็น 2 แถว ชื่อใหม่ และ orphan = 0
select name, sort from machine where branch='SKN' and name like 'ตรง-%' order by sort;
select count(*) as orphan_tickets
  from production_ticket t
 where t.branch='SKN' and t.machine like 'ตรง-%'
   and not exists (select 1 from machine m where m.branch=t.branch and m.name=t.machine);


-- ═══════════════════════════════════════════════════════════════
-- 6) ❌ ทีมขายยกเลิก SO เองได้ (v8.7)
--    เหตุผล: ใบ SO ค้างบนหน้าจอเยอะเกินไปจนลายตา หาใบที่ต้องทำจริงไม่เจอ
--    ขอบเขต: ยกเลิก "ทั้งใบ" ไม่ใช่รายบรรทัด — เพราะ so_item_live ถูก
--            ลบ-แล้ว-ใส่ใหม่ทุกครั้งที่ so_push.py sync (ทุก 2 นาที)
--            ธงที่เก็บรายบรรทัดจะโดนล้างทิ้ง ส่วน so_live ใช้ upsert
--            merge-duplicates → คอลัมน์ที่ไม่ได้อยู่ใน payload รอดชีวิต
--    สิทธิ์: ขายกดเองได้เลย ไม่ต้องรออนุมัติ และกดคืนได้ 1 คลิก
--            (ต่างจากยกเลิกใบผลิต ที่เผาวัตถุดิบไปแล้วย้อนไม่ได้)
--    เงื่อนไข: ถ้า SO นั้นมีใบผลิตที่ยังเดินอยู่ → แอปบล็อกไว้ ให้ไป
--             ยกเลิกใบผลิตก่อน (จุดนั้นคือจุดที่เริ่มกินวัตถุดิบจริง)
--    รันซ้ำได้
-- ---------------------------------------------------------------
alter table so_live add column if not exists cancelled_at   timestamptz;
alter table so_live add column if not exists cancelled_by   text not null default '';
alter table so_live add column if not exists cancel_reason  text not null default '';

-- ใบที่ถูกยกเลิกมีน้อยกว่าใบปกติมาก → partial index พอ
create index if not exists so_live_cancelled_idx
  on so_live (branch, cancelled_at) where cancelled_at is not null;

-- เช็คผล: ต้องได้ col_socancel = 3
select count(*) as col_socancel from information_schema.columns
 where table_name='so_live'
   and column_name in ('cancelled_at','cancelled_by','cancel_reason');


-- ═══════════════════════════════════════════════════════════════
-- 7) 🖐 โต๊ะ "งานพับมือ" ทุกสาขา (v9.4 — feedback รุ้ง+เมย์ 2 ส.ค.)
--    เคสจริง: บิลช่างประเสริฐ — สกลไม่มีเครื่องผลิตบานเกล็ดระบาย 304/457
--    ต้องพับมือ แต่ระบบสั่งไม่ได้ งานเลยหลุดออกนอกระบบ ไม่ถูกนับเวลา/คิว
--    เพิ่มเป็น "เครื่อง" หนึ่งตัวต่อสาขา → ขายเลือก "ผลิตแบบพับมือ" ได้
--    แล้วใบไหลตาม วางแผน→บอร์ด→แพ็ค→ส่ง ปกติทุกขั้น
--    (คู่กันในแอป: เครื่องเสียก็สั่ง "เข้าคิวรอซ่อม" ได้แล้ว — ไม่ต้องแก้ DB)
--    รันซ้ำได้
-- ---------------------------------------------------------------
insert into machine (branch, name, note, sort) values
  ('SKN','งานพับมือ','งานที่เครื่องรีดทำไม่ได้ เช่น บานเกล็ดระบาย 304/457',90),
  ('BK' ,'งานพับมือ','งานที่เครื่องรีดทำไม่ได้ — พับมือหน้างาน',90),
  ('PPS','งานพับมือ','งานที่เครื่องรีดทำไม่ได้ — พับมือหน้างาน',90)
on conflict (branch, name) do nothing;

-- เช็คผล: ต้องได้ 3 แถว
select branch, name from machine where name='งานพับมือ' order by branch;


-- ═══════════════════════════════════════════════════════════════
-- 8) 🧾 เลข IV คู่กับ SO (v9.7 — Gem 2 ส.ค.: จะปล่อยรถส่งของ ดู SO
--    อย่างเดียวไม่พอ ต้องเห็น IV คู่กัน)
--    so_push.py เวอร์ชันใหม่จะอ่านบิลขายจาก DBF แล้วเติมเลข IV มาให้
--    (หลายใบคั่นด้วย ,) — คอลัมน์นี้รอดจาก sync เพราะ upsert
--    merge-duplicates แตะเฉพาะคอลัมน์ใน payload
--    รันซ้ำได้
-- ---------------------------------------------------------------
alter table so_live add column if not exists ivnum text not null default '';

-- เช็คผล: ต้องได้ 1
select count(*) as col_ivnum from information_schema.columns
 where table_name='so_live' and column_name='ivnum';


-- ═══════════════════════════════════════════════════════════════
-- 9) 🔧 เพิ่มเครื่องที่มีจริงหน้างานแต่ไม่มีในระบบ (v9.9 — FB คุณหย่อย SKN 4 ส.ค.)
--    เคสจริง: ครอบข้าง 304 อยู่ในใบผลิตแต่ระบบมองไม่เห็น — กติกา routing
--    มีอยู่แล้วว่า ครอบหน้ากว้าง 304 (เครื่องรีด SKN เป็น 457) ต้องไป
--    "พับครอบ" แต่ตาราง machine ไม่มีเครื่องนี้ → ใบเลยไม่มีคอลัมน์ให้อยู่
--    เครื่องย้ำกันสาด ก็มีจริงแต่ไม่เคยถูกใส่ในระบบ
--    รันซ้ำได้
-- ---------------------------------------------------------------
insert into machine (branch, name, note, sort) values
  ('SKN','พับครอบ','ครอบหน้ากว้างไม่ตรงเครื่องรีด (304/ครอบพับ/ตามแบบ)',6),
  ('SKN','ย้ำกันสาด','งานย้ำกันสาด',7)
on conflict (branch, name) do nothing;

-- เช็คผล: ต้องเห็นทั้ง 2 เครื่อง
select name, sort from machine where branch='SKN' and name in ('พับครอบ','ย้ำกันสาด') order by sort;
