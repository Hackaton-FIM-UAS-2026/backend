-- 0004 · El identificador interno de la fuente «personal» usa el nombre correcto de la institución.
update public.expediente_eventos set fuente = 'personal_semujeres' where fuente = 'personal_cemujeres';
update public.expedientes
   set campos = replace(campos::text, '"personal_cemujeres"', '"personal_semujeres"')::jsonb,
       conflictos = replace(conflictos::text, '"personal_cemujeres"', '"personal_semujeres"')::jsonb
 where campos::text like '%personal_cemujeres%' or conflictos::text like '%personal_cemujeres%';
