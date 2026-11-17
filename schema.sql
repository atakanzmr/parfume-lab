-- =====================================================================
--  PARFÜM LAB · veritabanı kurulumu
--  Supabase > SQL Editor > New query > bu dosyanın tamamını yapıştır > Run
--  Tekrar çalıştırmak güvenlidir: var olan kayıtları silmez, değiştirmez.
-- =====================================================================

-- ---------- Malzemeler: hammadde, çözücü, çözelti ----------
create table if not exists public.materials (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  kind        text not null check (kind in ('raw','solvent','dilution')),
  short       text,
  maker       text,
  supplier    text,
  family      text,
  note        text check (note in ('top','heart','base')),
  descriptor  text,
  cas         text,
  ifra_max    numeric check (ifra_max >= 0),
  density     numeric check (density > 0),
  base_id     uuid references public.materials(id),
  solvent_id  uuid references public.materials(id),
  strength    numeric check (strength > 0 and strength <= 100),
  archived    boolean not null default false,
  notes       text,
  created_at  timestamptz not null default now(),
  constraint dilution_fields check (kind <> 'dilution' or (base_id is not null and strength is not null))
);

-- ---------- Stok hareketleri: silinmez, ters kayıtla düzeltilir ----------
create table if not exists public.movements (
  id          uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials(id),
  qty         numeric not null,
  cost        numeric,
  type        text not null check (type in ('purchase','prep_in','prep_out','production','adjust','loss','sample','reversal')),
  ref_kind    text,
  ref_id      uuid,
  reverses    uuid references public.movements(id),
  note        text,
  at          timestamptz not null default now(),
  created_at  timestamptz not null default now()
);
create index if not exists movements_material_idx on public.movements(material_id);
create index if not exists movements_ref_idx on public.movements(ref_id);
create unique index if not exists movements_reverses_uq on public.movements(reverses) where reverses is not null;

-- ---------- Hammadde koku notları ----------
create table if not exists public.material_notes (
  id          uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials(id) on delete cascade,
  at          timestamptz not null default now(),
  strength    numeric,
  surface     text,
  body        text,
  created_at  timestamptz not null default now()
);

-- ---------- Denediklerim ----------
create table if not exists public.perfumes (
  id            uuid primary key default gen_random_uuid(),
  brand         text,
  name          text not null,
  concentration text,
  year          int,
  perfumer      text,
  accords       text,
  status        text,
  notes         text,
  created_at    timestamptz not null default now()
);
create table if not exists public.perfume_reviews (
  id          uuid primary key default gen_random_uuid(),
  perfume_id  uuid not null references public.perfumes(id) on delete cascade,
  at          timestamptz not null default now(),
  surface     text,
  weather     text,
  opening     text,
  heart       text,
  base        text,
  sillage     numeric,
  longevity   numeric,
  rating      numeric,
  comment     text,
  created_at  timestamptz not null default now()
);
create index if not exists perfume_reviews_perfume_idx on public.perfume_reviews(perfume_id);

-- ---------- Formüller, versiyonlar, satırlar ----------
create table if not exists public.formulas (
  id                uuid primary key default gen_random_uuid(),
  code              text,
  name              text not null,
  style             text,
  target_perfume_id uuid references public.perfumes(id) on delete set null,
  notes             text,
  archived          boolean not null default false,
  created_at        timestamptz not null default now()
);
create table if not exists public.formula_versions (
  id          uuid primary key default gen_random_uuid(),
  formula_id  uuid not null references public.formulas(id) on delete cascade,
  no          int not null,
  parent_id   uuid references public.formula_versions(id) on delete set null,
  title       text,
  conc        numeric not null default 20 check (conc > 0 and conc <= 100),
  status      text not null default 'draft' check (status in ('draft','locked')),
  notes       text,
  created_at  timestamptz not null default now(),
  unique (formula_id, no)
);
create table if not exists public.formula_lines (
  id          uuid primary key default gen_random_uuid(),
  version_id  uuid not null references public.formula_versions(id) on delete cascade,
  material_id uuid not null references public.materials(id),
  amount      numeric not null default 0 check (amount >= 0),
  pos         int not null default 0,
  note        text,
  created_at  timestamptz not null default now()
);
create index if not exists formula_lines_version_idx on public.formula_lines(version_id);

-- ---------- Üretimler ve değerlendirmeler ----------
create table if not exists public.productions (
  id          uuid primary key default gen_random_uuid(),
  version_id  uuid not null references public.formula_versions(id),
  code        text,
  final_g     numeric,
  conc        numeric,
  solvent_id  uuid references public.materials(id),
  at          timestamptz not null default now(),
  rest_days   int not null default 30,
  cancelled   boolean not null default false,
  notes       text,
  created_at  timestamptz not null default now()
);
create table if not exists public.production_lines (
  id            uuid primary key default gen_random_uuid(),
  production_id uuid not null references public.productions(id) on delete cascade,
  material_id   uuid not null references public.materials(id),
  planned       numeric,
  actual        numeric not null,
  strength      numeric,
  pos           int not null default 0,
  created_at    timestamptz not null default now()
);
create table if not exists public.evaluations (
  id            uuid primary key default gen_random_uuid(),
  production_id uuid not null references public.productions(id) on delete cascade,
  at            timestamptz not null default now(),
  surface       text,
  weather       text,
  opening       text,
  heart         text,
  base          text,
  sillage       numeric,
  longevity     numeric,
  rating        numeric,
  next_change   text,
  comment       text,
  created_at    timestamptz not null default now()
);

-- ---------- Erişim: yalnızca giriş yapmış kullanıcı ----------
do $$
declare t text;
begin
  foreach t in array array['materials','movements','material_notes','perfumes','perfume_reviews',
                           'formulas','formula_versions','formula_lines','productions','production_lines','evaluations'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists sahip on public.%I', t);
    execute format('create policy sahip on public.%I for all to authenticated using (true) with check (true)', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;

-- ---------- Toplu kayıt: ya hepsi yazılır ya hiçbiri ----------
create or replace function public.commit_ops(ops jsonb)
returns void
language plpgsql
security invoker
set search_path = public
as $$
declare
  op   jsonb;
  t    text;
  k    text;
  r    jsonb;
  cols text;
  sets text;
  n    int;
  can_insert constant text[] := array['materials','movements','material_notes','perfumes','perfume_reviews',
                                      'formulas','formula_versions','formula_lines','productions','production_lines','evaluations'];
  can_update constant text[] := array['materials','material_notes','perfumes','perfume_reviews',
                                      'formulas','formula_versions','formula_lines','productions','evaluations'];
  can_delete constant text[] := array['materials','material_notes','perfumes','perfume_reviews',
                                      'formulas','formula_versions','formula_lines','evaluations'];
begin
  if jsonb_typeof(ops) <> 'array' then
    raise exception 'ops bir dizi olmalı';
  end if;

  for op in select value from jsonb_array_elements(ops) loop
    t := op->>'t';
    k := op->>'op';
    r := coalesce(op->'row', '{}'::jsonb);

    if k = 'insert' then
      if not (t = any(can_insert)) then raise exception 'izin yok: % %', k, t; end if;
      select string_agg(quote_ident(key), ', ') into cols from jsonb_object_keys(r) as key;
      if cols is null then raise exception 'boş kayıt: %', t; end if;
      execute format('insert into public.%I (%s) select %s from jsonb_populate_record(null::public.%I, $1)',
                     t, cols, cols, t) using r;

    elsif k = 'update' then
      if not (t = any(can_update)) then raise exception 'izin yok: % %', k, t; end if;
      select string_agg(format('%I = x.%I', key, key), ', ') into sets
        from jsonb_object_keys(r) as key where key not in ('id','created_at');
      if sets is null then continue; end if;
      execute format('update public.%I as d set %s from jsonb_populate_record(null::public.%I, $1) as x where d.id = $2',
                     t, sets, t) using r, (op->>'id')::uuid;
      get diagnostics n = row_count;
      if n = 0 then raise exception 'kayıt bulunamadı: % %', t, op->>'id'; end if;

    elsif k = 'delete' then
      if not (t = any(can_delete)) then raise exception 'izin yok: % %', k, t; end if;
      execute format('delete from public.%I where id = $1', t) using (op->>'id')::uuid;
      get diagnostics n = row_count;
      if n = 0 then raise exception 'kayıt bulunamadı: % %', t, op->>'id'; end if;

    else
      raise exception 'bilinmeyen işlem: %', k;
    end if;
  end loop;
end $$;

revoke all on function public.commit_ops(jsonb) from public, anon;
grant execute on function public.commit_ops(jsonb) to authenticated;

-- ---------- Uyanık tutma: ücretsiz plan bir hafta işlemsiz kalırsa durur ----------
create or replace function public.ping()
returns timestamptz
language sql
stable
as $$ select now() $$;

grant execute on function public.ping() to anon, authenticated;

-- ---------- Başlangıç verisi: Hammeyd siparişi (38 kalem) ----------
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('141e907a-3659-546e-8430-49a440f6b736', 'Dipropilen Glikol (DPG)', 'solvent', 'DPG', null, 'Hammeyd', null, null, null, null, null, 1.02, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('6780e334-4cc6-5b42-a83a-9849a7565566', 'Parfüm Bazı (96,6°)', 'solvent', 'Alkol', null, 'Hammeyd', null, null, null, null, null, 0.806, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('6a2de896-47a0-5db7-b85f-b62b1d422704', 'Hedione HC', 'raw', null, 'Firmenich', 'Hammeyd', 'Çiçeksi', 'heart', 'Yasemin, ışıltılı, havadar', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('994071d7-8469-5b51-ade5-b8a7f0f572cd', 'Hedione', 'raw', null, 'Firmenich', 'Hammeyd', 'Çiçeksi', 'heart', 'Yasemin, taze, narenciyemsi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('60c7faa2-5598-54c1-b819-8e648316c7cd', 'Iso E Super', 'raw', null, 'IFF', 'Hammeyd', 'Odunsu', 'base', 'Kadifemsi odunsu-amber, sedir', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('7422aee3-a31e-5546-b873-bdf41d2bc270', 'Fleur de Cuir', 'raw', null, 'Payan Bertrand', 'Hammeyd', 'Deri', 'base', 'Çiçeksi deri', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('81e8dcb7-cc9b-5d28-9be0-7f7b10e18708', 'Dihydro Ionone Beta', 'raw', null, null, 'Hammeyd', 'Odunsu', 'heart', 'Odunsu, iris-menekşe, amber', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('f61f2e1e-8811-5c55-ae28-4b67b6864905', 'Suederal', 'raw', null, 'IFF', 'Hammeyd', 'Deri', 'base', 'Süet, yumuşak deri', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('f9999810-8d4a-5cf0-b6e5-b8d94c9d30bd', 'Helvetolide', 'raw', null, 'Firmenich', 'Hammeyd', 'Misk', 'base', 'Misk, armutsu meyvemsi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('e0568316-43aa-5864-b241-b0ff3d07d0e0', 'Cashmeran', 'raw', null, 'IFF', 'Hammeyd', 'Odunsu', 'base', 'Misk-odunsu, baharatlı, kadifemsi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('da51bd63-b80f-5496-add9-ec866cfac6f3', 'Sandalore', 'raw', null, 'Givaudan', 'Hammeyd', 'Odunsu', 'base', 'Sandal ağacı', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('4cef813f-a6ba-5708-9210-d06db18aca4e', 'Juniper Berry Oil', 'raw', null, null, 'Hammeyd', 'Aromatik', 'top', 'Ardıç, reçinemsi, cin', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('a2b52d98-f9c4-5c32-9ba9-1add95f9a674', 'Cardamom Oil', 'raw', null, null, 'Hammeyd', 'Baharatlı', 'top', 'Taze baharat, okaliptüsümsü', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('958bc0fa-2eb9-5e8c-a02f-05b6d652a5b6', 'Bergamot Oil (Bergapten Free)', 'raw', null, null, 'Hammeyd', 'Narenciye', 'top', 'Bergamot, taze narenciye', null, null, null, null, null, null, false, 'Renksiz', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('ea3b20ea-7ab8-5cde-a19a-3d57d28a247f', 'Coumarin', 'raw', null, null, 'Hammeyd', 'Tatlı', 'base', 'Tonka, saman, tatlı', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('9ec8d4d3-8727-56b7-89ba-e7d99d011c69', 'Damascenone', 'raw', null, 'Firmenich', 'Hammeyd', 'Meyvemsi', 'heart', 'Gül, erik, tütünümsü; çok güçlü', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('c320f8be-4aba-577e-8f4c-1a130150053b', 'Ambrox Super', 'raw', null, 'Firmenich', 'Hammeyd', 'Amber', 'base', 'Ambergris, odunsu amber', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('0d4c0e53-bacc-5c16-b265-44bb1fccabf8', 'Tobacarol', 'raw', null, null, 'Hammeyd', 'Tütün', 'base', 'Tütün yaprağı, kuru', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('90d20c38-593b-5302-8bc8-d5df232d2609', 'Grisalva', 'raw', null, 'IFF', 'Hammeyd', 'Amber', 'base', 'Ambergris, hayvansı amber', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('fddff194-e085-5d68-816b-cb1cac13c339', 'Polysantol', 'raw', null, 'Firmenich', 'Hammeyd', 'Odunsu', 'base', 'Kremsi sandal ağacı; güçlü', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('768a40ee-b672-5123-a4fd-2ae2fc85a2c5', 'Hydroxycitronellal', 'raw', null, null, 'Hammeyd', 'Çiçeksi', 'heart', 'Müge, tatlı çiçeksi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('11cd008d-fd3e-5830-9112-9081c296ec78', 'Floralozone', 'raw', null, 'IFF', 'Hammeyd', 'Ozonik', 'top', 'Ozonik, deniz, taze', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('ea041d76-2d91-52a7-88e6-71c9c3ab1fad', 'Ambrettolide', 'raw', null, 'IFF', 'Hammeyd', 'Misk', 'base', 'Misk, ambrette tohumu, meyvemsi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('2068856d-5248-509a-b941-e2e13863f190', 'Timbersilk', 'raw', null, 'IFF', 'Hammeyd', 'Odunsu', 'base', 'Kuru odunsu-amber', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('eb0aed69-afbb-5cc8-8e75-d11eb9f30f0f', 'Vanillin', 'raw', null, null, 'Hammeyd', 'Tatlı', 'base', 'Vanilya', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('576f3d47-d087-52e2-84dc-7cb6aee2afb4', 'Kephalis', 'raw', null, 'Givaudan', 'Hammeyd', 'Tütün', 'base', 'Tütün, odunsu, amber', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('a6ea17f5-f2d6-5ca2-bc49-d44fba367d4b', 'Ethylene Brassylate', 'raw', null, null, 'Hammeyd', 'Misk', 'base', 'Tatlı, pudralı misk', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('e082615a-2236-5d00-befb-2b4f203d4b49', 'Ionone Beta', 'raw', null, null, 'Hammeyd', 'Çiçeksi', 'heart', 'Menekşe, odunsu, meyvemsi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('72f53e6f-c8bd-5964-ae38-b54d4c4cf56c', 'Guaiacwood Oil', 'raw', null, null, 'Hammeyd', 'Odunsu', 'base', 'Dumanlı odunsu, çay gülü', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('fc6834bf-bf9c-5db3-98c9-f16a1abdd6d5', 'Benzoin Resinoid Siam', 'raw', null, null, 'Hammeyd', 'Reçine', 'base', 'Balsamik, vanilyamsı', null, null, null, null, null, null, false, '%100, seyreltilmemiş', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('d9689eda-9376-53dd-bbdb-4f49ecd4654e', 'Aurantiol', 'raw', null, null, null, 'Çiçeksi', 'heart', 'Portakal çiçeği, tatlı çiçeksi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('4c2b8483-55c3-5a5a-9f68-6f5c452cf83d', 'Cinnamon Bark Ceylon Oil', 'raw', null, 'Payan Bertrand', 'Hammeyd', 'Baharatlı', 'heart', 'Tarçın kabuğu, sıcak baharat', null, null, null, null, null, null, false, '"Supreme" kalite', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('f2a51461-c11a-5f45-af33-7d72440a3a58', 'Labdanum Absolute', 'raw', null, null, 'Hammeyd', 'Amber', 'base', 'Reçinemsi amber, deri, hayvansı', null, null, null, null, null, null, false, '%100', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('9435d43a-3dbb-5ea2-82b5-7c67a620ad19', 'Linalool', 'raw', null, 'BASF', 'Hammeyd', 'Çiçeksi', 'top', 'Taze çiçeksi, lavanta-bergamot', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('3f42c18f-75ec-5a00-bab4-d5040822a261', 'Methyl Ionone Gamma Coeur', 'raw', null, 'IFF', 'Hammeyd', 'Pudralı', 'heart', 'İris, menekşe, pudralı', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('c3eff6c6-1e6a-5576-b7f4-6c3c59749ded', 'Benzyl Salicylate', 'raw', null, null, 'Hammeyd', 'Çiçeksi', 'base', 'Hafif balsamik çiçeksi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('4c9fdccd-1120-5229-b7d8-7669744d8c6d', 'Bicyclononalactone', 'raw', null, 'IFF', 'Hammeyd', 'Tatlı', 'base', 'Tonka, kumarinimsi, kremsi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('c0dd888d-637d-5fa0-812c-22171c5f6d95', 'Geraniol', 'raw', null, null, 'Hammeyd', 'Çiçeksi', 'heart', 'Gül, çiçeksi', null, null, null, null, null, null, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.materials (id, name, kind, short, maker, supplier, family, note, descriptor, cas, ifra_max, density, base_id, solvent_id, strength, archived, notes, created_at) values ('0fc1d9c2-fcb0-5c89-83fe-3e02fc67bc6a', 'Aurantiol %50 DPG', 'dilution', null, null, 'Hammeyd', 'Çiçeksi', 'heart', null, null, null, null, 'd9689eda-9376-53dd-bbdb-4f49ecd4654e', '141e907a-3659-546e-8430-49a440f6b736', 50, false, null, '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('8a66273d-5d12-5b03-95c6-7522140d9acc', '141e907a-3659-546e-8430-49a440f6b736', 102.0, 300, 'purchase', null, null, null, 'İlk sipariş · 100 ml', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('bdd510ac-66c9-552b-9cc2-48b0cbe52541', '6780e334-4cc6-5b42-a83a-9849a7565566', 806.0, 450, 'purchase', null, null, null, 'İlk sipariş · 1000 ml', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('de31c90e-c129-5286-bd08-f33ec2fcdf3d', '6a2de896-47a0-5db7-b85f-b62b1d422704', 10, 300, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('186bff7e-685e-5065-9b2b-c006afbf58ad', '994071d7-8469-5b51-ade5-b8a7f0f572cd', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('d35877a9-906e-5fdb-951c-6b44f7e0ecc6', '60c7faa2-5598-54c1-b819-8e648316c7cd', 30, 420, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('0254bd08-2deb-5453-8052-5b3fbc8ffa4e', '7422aee3-a31e-5546-b873-bdf41d2bc270', 1, 360, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('d1f25bf8-2077-58d9-a671-d2a8f7d8b46b', '81e8dcb7-cc9b-5d28-9be0-7f7b10e18708', 5, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('50a860ca-cc06-554f-9c41-b1052e8781e7', 'f61f2e1e-8811-5c55-ae28-4b67b6864905', 5, 180, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('b4c95255-fb8b-5b7d-bc04-7ad481a5d146', 'f9999810-8d4a-5cf0-b6e5-b8d94c9d30bd', 5, 360, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('48cdd491-afc9-5909-9dd5-36d47dd61005', 'e0568316-43aa-5864-b241-b0ff3d07d0e0', 5, 180, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('9b02f007-f5e0-57a0-b839-df07bb83db0a', 'da51bd63-b80f-5496-add9-ec866cfac6f3', 10, 240, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('289e757c-0cf8-5ffd-916c-ac25055519bf', '4cef813f-a6ba-5708-9210-d06db18aca4e', 5, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('13768435-ed2e-5700-bf23-c8e5c06c1e2c', 'a2b52d98-f9c4-5c32-9ba9-1add95f9a674', 5, 280, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('97908840-c20a-53f4-a4d9-507072ce8c31', '958bc0fa-2eb9-5e8c-a02f-05b6d652a5b6', 10, 360, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('ba1a5cea-01f1-58e0-9002-d990e353fca2', 'ea3b20ea-7ab8-5cde-a19a-3d57d28a247f', 5, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('6049878d-cdde-5a9a-9b6e-40a343c94c62', '9ec8d4d3-8727-56b7-89ba-e7d99d011c69', 1, 320, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('77785301-8009-5047-80a5-bb6f1c1426e7', 'c320f8be-4aba-577e-8f4c-1a130150053b', 1, 280, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('96a5a2a8-ab52-5db2-ac7e-d1d32ad5d228', '0d4c0e53-bacc-5c16-b265-44bb1fccabf8', 5, 320, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('a0042f7b-4ae6-5368-8d21-e20f9b47a1b5', '90d20c38-593b-5302-8bc8-d5df232d2609', 1, 350, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('126e8b55-97bb-5f4e-83ba-8db6698fe671', 'fddff194-e085-5d68-816b-cb1cac13c339', 5, 280, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('124da44f-8f2d-5348-a80d-df3e0f2119d9', '768a40ee-b672-5123-a4fd-2ae2fc85a2c5', 10, 180, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('31c0ea99-ede4-5ed0-9a22-aec85744b5e3', '11cd008d-fd3e-5830-9112-9081c296ec78', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('27572553-3289-573d-9e83-b46c05218f39', 'ea041d76-2d91-52a7-88e6-71c9c3ab1fad', 5, 600, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('ddf7d287-c6d1-5db9-9692-ee6d20d619ae', '2068856d-5248-509a-b941-e2e13863f190', 10, 220, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('e988c228-8cc4-558f-8f30-4fbcc61da1a6', 'eb0aed69-afbb-5cc8-8e75-d11eb9f30f0f', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('175023d7-1fdf-5aec-bbbc-1979d60f280b', '576f3d47-d087-52e2-84dc-7cb6aee2afb4', 10, 240, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('28856908-0362-56a4-9ee5-16fa0f6141f7', 'a6ea17f5-f2d6-5ca2-bc49-d44fba367d4b', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('03c692b0-d5d2-52c1-85db-d4be8278b94a', 'e082615a-2236-5d00-befb-2b4f203d4b49', 10, 240, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('de5397ba-a53b-551d-a83d-27462fed09b6', '72f53e6f-c8bd-5964-ae38-b54d4c4cf56c', 5, 260, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('31a0b04c-d638-5071-bcdf-1011df40c1e1', 'fc6834bf-bf9c-5db3-98c9-f16a1abdd6d5', 5, 360, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('54c06761-3aaf-5211-99fe-b8788635e128', '0fc1d9c2-fcb0-5c89-83fe-3e02fc67bc6a', 5, 240, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('6ae4c61c-f76e-585c-9d9d-6c1e9620092c', '4c2b8483-55c3-5a5a-9f68-6f5c452cf83d', 5, 180, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('088bc7b1-d8a9-529b-91fa-fab2e20bc08d', 'f2a51461-c11a-5f45-af33-7d72440a3a58', 5, 620, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('4b820dd4-4416-56db-8605-73b6fb8dab68', '9435d43a-3dbb-5ea2-82b5-7c67a620ad19', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('7080c58d-72f6-5d4e-b128-0296fb079b13', '3f42c18f-75ec-5a00-bab4-d5040822a261', 5, 180, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('f6a33747-a643-5843-9866-106d2d9ecaf5', 'c3eff6c6-1e6a-5576-b7f4-6c3c59749ded', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('86635aee-4c64-5029-891d-7e6414c64059', '4c9fdccd-1120-5229-b7d8-7669744d8c6d', 5, 180, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;
insert into public.movements (id, material_id, qty, cost, type, ref_kind, ref_id, reverses, note, at, created_at) values ('1f9dea5b-d255-5152-ba1f-4ca79ae6410d', 'c0dd888d-637d-5fa0-812c-22171c5f6d95', 10, 150, 'purchase', null, null, null, 'İlk sipariş', '2026-11-16T20:40:00.000Z', '2026-11-16T20:40:00.000Z') on conflict (id) do nothing;

notify pgrst, 'reload schema';
