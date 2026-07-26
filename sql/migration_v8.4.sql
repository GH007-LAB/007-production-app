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
