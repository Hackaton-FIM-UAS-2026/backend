-- Correcciones del revisor de seguridad de Supabase (aplicadas al proyecto el 25 nov).
alter function public.tocar_updated_at() set search_path = public;
-- Solo la usa el trigger de auth.users; nadie debe llamarla por la API.
revoke execute on function public.alta_usuaria() from public, anon, authenticated;
-- Métricas: solo con sesión (además valida rol adentro).
revoke execute on function public.metricas() from public, anon;
grant execute on function public.metricas() to authenticated;
-- rol_actual() se deja ejecutable: las políticas RLS la llaman (incluida la del catálogo
-- público para anon) y solo revela el rol de quien pregunta.
