-- 0005 · Ajustes del test base y limpieza de eventos duplicados
--
-- 1. Escolaridad: Preparatoria → Media superior, Universidad → Licenciatura
--    (en expedientes y en los requisitos de recursos, incluidas vacantes de empresas).
-- 2. Documentos: se quita «Cuenta bancaria»; el campo tiene_cuenta_bancaria deja de existir.
-- 3. «Aplicó a «…»» / «Guardó «…»» repetidos: se conserva el primero por usuaria y texto.
--
-- Verificación (correr antes y después; después todo debe dar 0):
--   select count(*) from public.expedientes where campos#>>'{escolaridad,valor}' in ('Preparatoria','Universidad');
--   select count(*) from public.expedientes where campos ? 'tiene_cuenta_bancaria' or campos#>'{documentos,valor}' ? 'Cuenta bancaria';
--   select count(*) from public.recursos where requisitos::text ~ 'Preparatoria|Universidad|Cuenta bancaria|tiene_cuenta_bancaria';
--   select count(*) - count(distinct (usuaria_id, texto)) from public.expediente_eventos
--     where texto like 'Aplicó a «%' or texto like 'Guardó «%';

begin;

-- ---------- Expedientes ----------
update public.expedientes
set campos = jsonb_set(campos, '{escolaridad,valor}',
  to_jsonb(case campos#>>'{escolaridad,valor}' when 'Preparatoria' then 'Media superior' else 'Licenciatura' end))
where campos#>>'{escolaridad,valor}' in ('Preparatoria', 'Universidad');

update public.expedientes
set campos = jsonb_set(campos, '{documentos,valor}', (campos#>'{documentos,valor}') - 'Cuenta bancaria')
where jsonb_typeof(campos#>'{documentos,valor}') = 'array' and campos#>'{documentos,valor}' ? 'Cuenta bancaria';

update public.expedientes
set campos = campos - 'tiene_cuenta_bancaria'
where campos ? 'tiene_cuenta_bancaria';

-- ---------- Requisitos de recursos ----------
update public.recursos r
set requisitos = coalesce((
  select jsonb_agg(nuevo order by i)
  from (
    select i,
      case
        when e->>'campo' = 'escolaridad' then
          e || jsonb_build_object('valor',
                 case e->>'valor' when 'Preparatoria' then 'Media superior' when 'Universidad' then 'Licenciatura' else e->>'valor' end)
            || case when e ? 'label' then jsonb_build_object('label',
                 replace(replace(e->>'label', 'Preparatoria terminada', 'Media superior terminada'),
                         'Universidad terminada', 'Licenciatura terminada'))
               else '{}'::jsonb end
        when e->>'campo' = 'documentos' and jsonb_typeof(e->'valor') = 'array' then
          e || jsonb_build_object('valor', (e->'valor') - 'Cuenta bancaria')
            || case when e ? 'label' then jsonb_build_object('label',
                 replace(replace(e->>'label', ', Cuenta bancaria', ''), 'Cuenta bancaria, ', ''))
               else '{}'::jsonb end
        else e
      end as nuevo
    from jsonb_array_elements(r.requisitos) with ordinality as t(e, i)
    where e->>'campo' is distinct from 'tiene_cuenta_bancaria'
  ) x
  -- un requisito de documentos que se quedó sin documentos ya no pide nada
  where not (nuevo->>'campo' = 'documentos' and jsonb_typeof(nuevo->'valor') = 'array' and jsonb_array_length(nuevo->'valor') = 0)
), '[]'::jsonb)
where requisitos::text ~ 'Preparatoria|Universidad|Cuenta bancaria|tiene_cuenta_bancaria';

update public.recursos
set etiquetas = jsonb_set(etiquetas, '{pide}', (etiquetas->'pide') - 'tiene_cuenta_bancaria')
where etiquetas->'pide' ? 'tiene_cuenta_bancaria';

-- ---------- Eventos repetidos de Aplicar / Guardar ----------
delete from public.expediente_eventos e
using public.expediente_eventos k
where e.usuaria_id = k.usuaria_id
  and e.texto = k.texto
  and e.id > k.id
  and (e.texto like 'Aplicó a «%' or e.texto like 'Guardó «%');

commit;
