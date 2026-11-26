-- Ya aplicada en Supabase (versión 20261126013129, «endurecer_funciones»).
-- Se trae al repo para que el historial coincida con la base de datos.
alter function public.tocar_updated_at() set search_path = public;
-- Solo la usa el trigger de auth.users; nadie debe llamarla por la API.
revoke execute on function public.alta_usuaria() from public, anon, authenticated;
-- Métricas: solo con sesión (además valida rol adentro).
revoke execute on function public.metricas() from public, anon;
grant execute on function public.metricas() to authenticated;
