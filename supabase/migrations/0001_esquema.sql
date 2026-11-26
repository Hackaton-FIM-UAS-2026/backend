-- =====================================================================
-- Esquema inicial · Agente de canalización económica para mujeres
-- Pegar completo en Supabase → SQL Editor → Run (o `supabase db push`).
--
-- Modelo de seguridad:
--   * El navegador SOLO lee (con la llave anon + JWT de la usuaria) y
--     RLS filtra por dueña o por rol del personal.
--   * Toda escritura pasa por FastAPI (service role) DESPUÉS de que el
--     backend comprobó, leyendo con el JWT de quien pide, que RLS le
--     deja ver ese registro. Nadie escribe directo a las tablas desde
--     el frontend.
--   * El personal económico no puede ver ni contar expedientes sensibles.
-- =====================================================================

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------
-- Personal de CEMujeres y su rol
-- ---------------------------------------------------------------------
create table public.personal (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  nombre     text not null,
  rol        text not null check (rol in (
               'asesora_economica', 'especialista_juridica',
               'especialista_psicologica', 'coordinacion')),
  activo     boolean not null default true,
  created_at timestamptz not null default now()
);

-- Rol de quien hace la petición (null = usuaria o anónimo).
create or replace function public.rol_actual()
returns text
language sql stable security definer
set search_path = public
as $$
  select rol from public.personal where user_id = auth.uid() and activo
$$;

-- ---------------------------------------------------------------------
-- Perfil de la usuaria (datos de contacto, NO el expediente)
-- ---------------------------------------------------------------------
create table public.perfiles (
  usuaria_id          uuid primary key references auth.users (id) on delete cascade,
  nombre              text,
  correo              text,
  telefono            text,
  medio_contacto      text,
  horario_contacto    text,
  municipio           text,
  estado_seguimiento  text not null default 'Nueva',
  acepto_privacidad_at timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Expediente económico vivo (un solo registro con versión + historial)
-- ---------------------------------------------------------------------
create table public.expedientes (
  usuaria_id        uuid primary key references public.perfiles (usuaria_id) on delete cascade,
  campos            jsonb not null default '{}'::jsonb,   -- {campo: {valor, fuente, confianza, fecha, por_confirmar}}
  ruta              jsonb,                                -- {principal, puente, puntajes, factores, manual?}
  conflictos        jsonb not null default '[]'::jsonb,   -- choques personal vs. usuaria
  version           integer not null default 0,
  embedding         extensions.vector(768),
  embedding_version integer,
  updated_at        timestamptz not null default now()
);

create table public.expediente_eventos (
  id             bigint generated always as identity primary key,
  usuaria_id     uuid not null references public.perfiles (usuaria_id) on delete cascade,
  version        integer not null,
  campo          text,
  valor_anterior jsonb,
  valor_nuevo    jsonb,
  fuente         text not null,
  texto          text not null,            -- frase legible para la línea de tiempo
  autor          uuid,                      -- personal que lo registró (si aplica)
  created_at     timestamptz not null default now()
);
create index on public.expediente_eventos (usuaria_id, created_at desc);

-- ---------------------------------------------------------------------
-- Catálogo curado de recursos
-- ---------------------------------------------------------------------
create table public.recursos (
  id            text primary key,
  titulo        text not null,
  proveedor     text not null,
  tipo          text not null check (tipo in ('curso','vacante','beca','apoyo','financiamiento')),
  rutas         text[] not null check (rutas <@ array['empleabilidad','emprendimiento','capacitacion']),
  modalidad     text,            -- Presencial | En línea | Híbrida
  horario       text,            -- Mañanas | Tardes | Noches | Fines de semana | Flexible
  horas_semana  integer,
  costo         text,
  ubicacion     text,
  municipios    text[] not null default '{}',  -- vacío = cualquiera
  fecha_cierre  date,
  requisitos    jsonb not null default '[]'::jsonb,  -- [{campo, op, valor, duro, label}]
  descripcion   text,
  url_accion    text,
  embedding     extensions.vector(768),
  verificado_el text,            -- '2026-11'
  publicada     boolean not null default true,
  creada_el     timestamptz not null default now(),
  actualizada_el timestamptz not null default now()
);
create index on public.recursos using hnsw (embedding extensions.vector_cosine_ops);

-- Lo que la usuaria hizo con cada recurso
create table public.recursos_usuaria (
  usuaria_id uuid not null references public.perfiles (usuaria_id) on delete cascade,
  recurso_id text not null references public.recursos (id) on delete cascade,
  estado     text not null check (estado in ('guardado','aplicado','inscrita','terminado','contratada')),
  updated_at timestamptz not null default now(),
  primary key (usuaria_id, recurso_id)
);

-- ---------------------------------------------------------------------
-- Canalización sensible (jurídica / psicológica)
-- ---------------------------------------------------------------------
create sequence public.folio_canalizacion start 15;

create table public.canalizaciones (
  id          uuid primary key default gen_random_uuid(),
  folio       text not null unique default ('C-' || lpad(nextval('public.folio_canalizacion')::text, 3, '0')),
  usuaria_id  uuid not null references auth.users (id) on delete cascade,
  tipo        text not null check (tipo in ('juridica','psicologica','ambas')),
  urgencia    text not null default 'pronta' check (urgencia in ('inmediata','pronta','informativa')),
  estado      text not null default 'nueva' check (estado in ('nueva','contactada','en atención','cerrada')),
  asignada_a  uuid references public.personal (user_id),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Contacto seguro + resumen aprobado, CIFRADOS por el backend (Fernet).
-- Nunca se guarda la conversación ni diagnósticos.
create table public.expedientes_sensibles (
  usuaria_id       uuid primary key references auth.users (id) on delete cascade,
  datos_cifrados   text not null,
  version          integer not null default 1,
  consentimiento_at timestamptz not null,
  updated_at       timestamptz not null default now()
);

create table public.canalizacion_notas (
  id              bigint generated always as identity primary key,
  canalizacion_id uuid not null references public.canalizaciones (id) on delete cascade,
  autor           uuid not null references public.personal (user_id),
  nota_cifrada    text not null,
  created_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Bitácora de accesos (solo se inserta; nunca se edita)
-- ---------------------------------------------------------------------
create table public.bitacora_accesos (
  id         bigint generated always as identity primary key,
  actor      uuid,
  rol        text,
  accion     text not null,        -- listar | leer | actualizar | crear | borrar
  tabla      text not null,
  registro   text,
  usuaria_id uuid,
  created_at timestamptz not null default now()
);
create index on public.bitacora_accesos (created_at desc);

-- ---------------------------------------------------------------------
-- Alta automática de perfil + expediente al registrarse
-- (el personal se crea con user_metadata.es_personal = true y no la recibe)
-- ---------------------------------------------------------------------
create or replace function public.alta_usuaria()
returns trigger
language plpgsql security definer
set search_path = public
as $$
begin
  if coalesce(new.raw_user_meta_data ->> 'es_personal', 'false') = 'true' then
    return new;
  end if;
  insert into public.perfiles (usuaria_id, correo, telefono, nombre)
  values (new.id, new.email, new.phone, new.raw_user_meta_data ->> 'nombre')
  on conflict do nothing;
  insert into public.expedientes (usuaria_id) values (new.id) on conflict do nothing;
  return new;
end $$;

create trigger al_crear_usuario
after insert on auth.users
for each row execute function public.alta_usuaria();

-- updated_at automático
create or replace function public.tocar_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

create trigger t_perfiles   before update on public.perfiles             for each row execute function public.tocar_updated_at();
create trigger t_exp        before update on public.expedientes          for each row execute function public.tocar_updated_at();
create trigger t_canal      before update on public.canalizaciones       for each row execute function public.tocar_updated_at();
create trigger t_sensible   before update on public.expedientes_sensibles for each row execute function public.tocar_updated_at();

-- =====================================================================
-- RLS
-- =====================================================================
alter table public.personal              enable row level security;
alter table public.perfiles              enable row level security;
alter table public.expedientes           enable row level security;
alter table public.expediente_eventos    enable row level security;
alter table public.recursos              enable row level security;
alter table public.recursos_usuaria      enable row level security;
alter table public.canalizaciones        enable row level security;
alter table public.expedientes_sensibles enable row level security;
alter table public.canalizacion_notas    enable row level security;
alter table public.bitacora_accesos      enable row level security;

-- Personal: cada quien se ve a sí misma; coordinación ve a todo el equipo.
create policy personal_select on public.personal for select to authenticated
  using (user_id = auth.uid() or public.rol_actual() = 'coordinacion');

-- Perfil y expediente económico: ella + asesoras económicas + coordinación (perfil).
create policy perfiles_select on public.perfiles for select to authenticated
  using (usuaria_id = auth.uid() or public.rol_actual() in ('asesora_economica','coordinacion'));

create policy expedientes_select on public.expedientes for select to authenticated
  using (usuaria_id = auth.uid() or public.rol_actual() = 'asesora_economica');

create policy eventos_select on public.expediente_eventos for select to authenticated
  using (usuaria_id = auth.uid() or public.rol_actual() = 'asesora_economica');

create policy recursos_usuaria_select on public.recursos_usuaria for select to authenticated
  using (usuaria_id = auth.uid() or public.rol_actual() = 'asesora_economica');

-- Catálogo: lo publicado es público; el personal ve también lo pausado.
create policy recursos_publicos on public.recursos for select to anon, authenticated
  using (publicada or public.rol_actual() is not null);

-- Canalizaciones: ella + la especialista del tipo correspondiente.
-- Asesoras económicas y coordinación NO las ven (coordinación solo conteos vía metricas()).
create policy canal_select on public.canalizaciones for select to authenticated
  using (
    usuaria_id = auth.uid()
    or (public.rol_actual() = 'especialista_juridica'    and tipo in ('juridica','ambas'))
    or (public.rol_actual() = 'especialista_psicologica' and tipo in ('psicologica','ambas'))
  );

create policy sensible_select on public.expedientes_sensibles for select to authenticated
  using (
    usuaria_id = auth.uid()
    or exists (
      select 1 from public.canalizaciones c
      where c.usuaria_id = expedientes_sensibles.usuaria_id
        and ((public.rol_actual() = 'especialista_juridica'    and c.tipo in ('juridica','ambas'))
          or (public.rol_actual() = 'especialista_psicologica' and c.tipo in ('psicologica','ambas')))
    )
  );

create policy notas_select on public.canalizacion_notas for select to authenticated
  using (exists (select 1 from public.canalizaciones c where c.id = canalizacion_id
                 and public.rol_actual() in ('especialista_juridica','especialista_psicologica')));

create policy bitacora_select on public.bitacora_accesos for select to authenticated
  using (public.rol_actual() = 'coordinacion');

-- (Sin políticas de insert/update/delete: desde el navegador nadie escribe.
--  El backend escribe con la service role, que ignora RLS.)

-- =====================================================================
-- Funciones RPC
-- =====================================================================

-- Similitud semántica (pgvector). security invoker → respeta RLS de recursos.
create or replace function public.match_recursos(query_embedding extensions.vector(768), match_count int default 60)
returns table (id text, similitud float)
language sql stable
set search_path = public, extensions
as $$
  select r.id, 1 - (r.embedding <=> query_embedding) as similitud
  from public.recursos r
  where r.embedding is not null
  order by r.embedding <=> query_embedding
  limit match_count
$$;

-- Métricas agregadas (sin contenido sensible, solo conteos).
create or replace function public.metricas()
returns jsonb
language plpgsql stable security definer
set search_path = public
as $$
begin
  if public.rol_actual() is null then
    raise exception 'sin permiso';
  end if;
  return jsonb_build_object(
    'usuarias_por_ruta', (select coalesce(jsonb_object_agg(k, n), '{}'::jsonb) from (
        select coalesce(ruta ->> 'principal', 'sin_ruta') k, count(*) n from expedientes group by 1) t),
    'usuarias_por_estado', (select coalesce(jsonb_object_agg(estado_seguimiento, n), '{}'::jsonb) from (
        select estado_seguimiento, count(*) n from perfiles group by 1) t),
    'acciones', (select coalesce(jsonb_object_agg(estado, n), '{}'::jsonb) from (
        select estado, count(*) n from recursos_usuaria group by 1) t),
    -- El personal económico no ve ni conteos del flujo sensible.
    'canalizaciones_por_estado', case when public.rol_actual() = 'asesora_economica' then null else
        (select coalesce(jsonb_object_agg(estado, n), '{}'::jsonb) from (
          select estado, count(*) n from canalizaciones group by 1) t) end
  );
end $$;

revoke all on function public.metricas() from anon;
