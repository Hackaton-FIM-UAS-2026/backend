-- 0007 · Citas de Jurídico y Psicología con la usuaria.
alter table public.canalizaciones add column if not exists cita_at timestamptz;
alter table public.canalizaciones add column if not exists cita_modalidad text
  check (cita_modalidad in ('presencial', 'llamada', 'videollamada'));
alter table public.canalizaciones add column if not exists cita_nota text;
