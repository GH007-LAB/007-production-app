-- RPC ทางเข้าแอพระบบผลิตจากล็อกอินกลาง (แก้พนักงานติดหน้า "ผูกบัญชี LINE")
-- ปัญหา: ตาราง staff เป็นชื่อตัวอย่าง ไม่มี email/line_id — พนักงานจริงล็อกอินกลาง
--   ด้วย LINE แล้วหา staff ไม่เจอ เลยติดหน้าผูกตลอด (ผูกก็ไม่ผ่านเพราะอีเมลไม่มีในตาราง)
-- วิธีแก้: หาใน staff ก่อน (คนที่ผูกแล้ว เช่น ปอนด์/Gem) → ไม่เจอค่อยหาพนักงานกลาง
--   (employees.line_id / email) → เช็กสิทธิ์แอพ production ใน app_access →
--   map ตำแหน่ง → role ผลิต → สร้าง/ผูกแถว staff ให้อัตโนมัติ (FK created_by/staff_id
--   ชี้เข้า staff(id) จึงต้องมีแถวจริงเสมอ)
-- รันบน Supabase syvfdbvmwaeyokytckwb แล้ว 2026-08-25

create or replace function public.prod_enter(p_line_id text default null, p_email text default null)
returns table(id bigint, branch text, name text, role text,
              can_approve boolean, email text, active boolean, line_id text)
language plpgsql
security definer
set search_path = public
as $func$
declare
  emp record;
  st_id bigint;
  v_role text;
begin
  -- 1) staff เดิมที่ผูกแล้ว
  if p_line_id is not null then
    select s.id into st_id from staff s where s.line_id = p_line_id and s.active limit 1;
  end if;
  if st_id is null and p_email is not null then
    select s.id into st_id from staff s
     where lower(s.email) = lower(p_email) and s.active limit 1;
  end if;

  -- 2) ไม่เจอ → พนักงานกลาง
  if st_id is null then
    select e.* into emp from employees e
     where e.active
       and ((p_line_id is not null and e.line_id = p_line_id)
         or (p_email  is not null and lower(e.email) = lower(p_email)))
     limit 1;
    if not found then return; end if;

    -- 3) ต้องมีสิทธิ์แอพ production (รปภ. ไม่มี → ไม่ผ่าน)
    if not exists (
      select 1 from app_access aa join apps a on a.id = aa.app_id
      where aa.employee_id = emp.id and a.code = 'production'
    ) then return; end if;

    -- 4) ตำแหน่ง → role ของแอพผลิต
    v_role := case
      when emp.is_admin or emp.position = 'ผู้จัดการสาขา' then 'admin'
      when emp.position in ('หัวหน้าฝ่ายผลิตและจัดส่ง','โฟร์แมน') then 'planner'
      when emp.position in ('หัวหน้าฝ่ายขาย','พนักงานขาย','พนักงานขายออนไลน์','พนักงานไลฟ์สด') then 'sales'
      when emp.position in ('พนักงานขับรถ','สต๊อก') then 'packer'
      else 'operator'
    end;

    -- 5) มีแถว staff อีเมลตรงอยู่แล้ว → ผูก line_id ให้ / ไม่มี → สร้างใหม่
    select s.id into st_id from staff s
     where emp.email is not null and lower(s.email) = lower(emp.email) and s.active limit 1;
    if st_id is not null then
      update staff s set line_id = coalesce(s.line_id, emp.line_id, p_line_id)
       where s.id = st_id;
    else
      insert into staff(branch, name, role, line_id, email, active, can_approve)
      values (emp.branch, emp.nickname, v_role,
              coalesce(emp.line_id, p_line_id),
              coalesce(emp.email, p_email),
              true, v_role in ('admin','planner'))
      returning staff.id into st_id;
    end if;
  end if;

  return query
    select s.id, s.branch, s.name, s.role, s.can_approve, s.email, s.active, s.line_id
    from staff s where s.id = st_id;
end
$func$;

revoke all on function public.prod_enter(text, text) from public;
-- เฉพาะคนที่มี session แล้วเท่านั้น (ต่างจาก staff_by_line_id เดิมที่ให้ anon ด้วย)
grant execute on function public.prod_enter(text, text) to authenticated;
