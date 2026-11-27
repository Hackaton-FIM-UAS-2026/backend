-- 0006 · «Mis datos»: RFC y dirección de la usuaria (la CURP ya existía y es única).
alter table public.perfiles add column if not exists rfc text;
alter table public.perfiles add column if not exists direccion text;
alter table public.perfiles add constraint perfiles_rfc_len check (rfc is null or length(rfc) between 12 and 13);
