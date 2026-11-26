-- =====================================================================
-- 0002 · Esquema para los módulos M1–M7 (prototipo 27 nov 2026)
-- Roles nuevos, CURP, áreas por canalización, empresas, revisión de
-- vacantes, etiquetas para caminos, visitas previstas y bucket de logos.
-- =====================================================================

-- ---------- Roles del personal ----------
alter table public.personal drop constraint personal_rol_check;
alter table public.personal add constraint personal_rol_check check (rol in (
  'asesora_economica', 'especialista_juridica', 'especialista_psicologica',
  'coordinacion', 'trabajo_social', 'recepcion'));

-- ---------- Perfil: CURP y colonia ----------
alter table public.perfiles add column curp text unique;
alter table public.perfiles add constraint perfiles_curp_len check (curp is null or length(curp) = 18);
alter table public.perfiles add column colonia text;

-- ---------- Canalizaciones: área asignada por Trabajo Social ----------
alter table public.canalizaciones drop constraint canalizaciones_estado_check;
alter table public.canalizaciones add constraint canalizaciones_estado_check
  check (estado in ('nueva', 'asignada', 'contactada', 'en atención', 'cerrada'));
alter table public.canalizaciones drop constraint canalizaciones_tipo_check;
alter table public.canalizaciones add constraint canalizaciones_tipo_check
  check (tipo in ('juridica', 'psicologica', 'ambas', 'no_se'));
alter table public.canalizaciones add column area_asignada text
  check (area_asignada in ('juridica', 'psicologica', 'ambas'));
alter table public.canalizaciones add column origen text not null default 'asistente'
  check (origen in ('asistente', 'persona', 'personal'));
alter table public.canalizaciones add column asignada_por uuid references public.personal (user_id);

-- ---------- Línea de tiempo por área ----------
alter table public.expediente_eventos add column area text not null default 'general'
  check (area in ('general', 'economico', 'trabajo_social', 'juridico', 'psicologia'));
alter table public.expediente_eventos add column texto_publico text;

-- ---------- Empresas ----------
create table public.empresas (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid unique references auth.users (id) on delete cascade,
  nombre          text not null,
  rfc             text not null,
  giro            text,
  contacto_nombre text,
  telefono        text,
  correo          text,
  logo_url        text,
  estado          text not null default 'pendiente' check (estado in ('pendiente', 'aprobada', 'rechazada')),
  motivo          text,
  revisada_por    uuid references public.personal (user_id),
  revisada_el     timestamptz,
  created_at      timestamptz not null default now()
);

-- ---------- Recursos: empresa, revisión humana y etiquetas ----------
alter table public.recursos add column empresa_id uuid references public.empresas (id) on delete cascade;
alter table public.recursos add column estado_revision text not null default 'aprobada'
  check (estado_revision in ('pendiente', 'aprobada', 'rechazada'));
alter table public.recursos add column motivo_revision text;
alter table public.recursos add column alerta_ia text;
alter table public.recursos add column sueldo text;
alter table public.recursos add column etiquetas jsonb not null default '{"pide": [], "da": [], "temas": []}'::jsonb;
alter table public.recursos add column revisada_por uuid references public.personal (user_id);
create index on public.recursos (empresa_id);

-- ---------- Visitas previstas ----------
create table public.visitas (
  id         bigint generated always as identity primary key,
  usuaria_id uuid not null references public.perfiles (usuaria_id) on delete cascade,
  fecha      date not null,
  franja     text not null check (franja in ('mañana', 'tarde')),
  modulo     text not null check (modulo in ('trabajo_social', 'juridico', 'psicologia', 'economico')),
  estado     text not null default 'por_llegar' check (estado in ('por_llegar', 'llego', 'no_vino')),
  origen     text not null check (origen in ('asistente', 'personal')),
  created_at timestamptz not null default now()
);
create index on public.visitas (fecha);

-- ---------- Alta automática: las empresas no reciben perfil de usuaria ----------
create or replace function public.alta_usuaria()
returns trigger
language plpgsql security definer
set search_path = public
as $$
begin
  if coalesce(new.raw_user_meta_data ->> 'es_personal', 'false') = 'true'
     or coalesce(new.raw_user_meta_data ->> 'es_empresa', 'false') = 'true' then
    return new;
  end if;
  insert into public.perfiles (usuaria_id, correo, telefono, nombre)
  values (new.id, new.email, new.phone, new.raw_user_meta_data ->> 'nombre')
  on conflict do nothing;
  insert into public.expedientes (usuaria_id) values (new.id) on conflict do nothing;
  return new;
end $$;
revoke execute on function public.alta_usuaria() from public, anon, authenticated;

-- =====================================================================
-- RLS
-- =====================================================================
alter table public.empresas enable row level security;
alter table public.visitas  enable row level security;

-- Canalizaciones: ella, Trabajo Social, y cada especialista solo lo asignado a su área.
drop policy canal_select on public.canalizaciones;
create policy canal_select on public.canalizaciones for select to authenticated
  using (
    usuaria_id = auth.uid()
    or public.rol_actual() = 'trabajo_social'
    or (public.rol_actual() = 'especialista_juridica'    and area_asignada in ('juridica', 'ambas'))
    or (public.rol_actual() = 'especialista_psicologica' and area_asignada in ('psicologica', 'ambas'))
  );

drop policy sensible_select on public.expedientes_sensibles;
create policy sensible_select on public.expedientes_sensibles for select to authenticated
  using (
    usuaria_id = auth.uid()
    or public.rol_actual() = 'trabajo_social'
    or exists (
      select 1 from public.canalizaciones c
      where c.usuaria_id = expedientes_sensibles.usuaria_id
        and ((public.rol_actual() = 'especialista_juridica'    and c.area_asignada in ('juridica', 'ambas'))
          or (public.rol_actual() = 'especialista_psicologica' and c.area_asignada in ('psicologica', 'ambas'))))
  );

drop policy notas_select on public.canalizacion_notas;
create policy notas_select on public.canalizacion_notas for select to authenticated
  using (exists (
    select 1 from public.canalizaciones c
    where c.id = canalizacion_notas.canalizacion_id
      and (public.rol_actual() = 'trabajo_social'
        or (public.rol_actual() = 'especialista_juridica'    and c.area_asignada in ('juridica', 'ambas'))
        or (public.rol_actual() = 'especialista_psicologica' and c.area_asignada in ('psicologica', 'ambas'))))
  );

-- Perfiles: también Trabajo Social y las especialistas (datos generales).
drop policy perfiles_select on public.perfiles;
create policy perfiles_select on public.perfiles for select to authenticated
  using (usuaria_id = auth.uid() or public.rol_actual() is not null);

-- Catálogo: lo publicado y aprobado es público; el personal ve todo.
drop policy recursos_publicos on public.recursos;
create policy recursos_publicos on public.recursos for select to anon, authenticated
  using ((publicada and estado_revision = 'aprobada') or public.rol_actual() is not null);

-- Empresas: la dueña y el personal.
create policy empresas_select on public.empresas for select to authenticated
  using (user_id = auth.uid() or public.rol_actual() is not null);

-- Visitas: ella y el personal.
create policy visitas_select on public.visitas for select to authenticated
  using (usuaria_id = auth.uid() or public.rol_actual() is not null);

-- ---------- Storage: logos públicos de empresas ----------
insert into storage.buckets (id, name, public)
values ('logos', 'logos', true)
on conflict (id) do nothing;

create policy logos_subir on storage.objects for insert to authenticated
  with check (bucket_id = 'logos');
