-- 0003 · La línea de tiempo confidencial (canalizaciones y notas) no se lee con la sesión
-- de la usuaria ni de la asesora económica: solo el backend (service role) la arma por área.
drop policy eventos_select on public.expediente_eventos;
create policy eventos_select on public.expediente_eventos for select to authenticated
  using (
    area in ('general', 'economico') and fuente <> 'nota'
    and (usuaria_id = auth.uid() or public.rol_actual() = 'asesora_economica')
  );
