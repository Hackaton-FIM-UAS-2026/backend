# Empoderate · backend

API de Empoderate, la plataforma que hicimos con la Secretaría de las Mujeres de Ahome (SEMujeres) para el
2do Hackathon FIM-UAS 2026. Recibe el test de cada usuaria, le arma su ruta (empleo, capacitación o
emprendimiento), le recomienda recursos reales del catálogo y, si lo pide, la canaliza con jurídico o
psicología sin que nadie más vea su caso.

**Stack:** FastAPI, Supabase (Auth, Postgres con RLS, pgvector), Claude para redactar y conversar, y Gemini
para los embeddings del catálogo.

- Frontend: https://github.com/Hackaton-FIM-UAS-2026/frontend
- Documentación de endpoints (local): http://localhost:8000/docs
- Datos de la demo y cómo pasarlos a reales: [`data/README.md`](data/README.md)

## Estructura

```
app/
  dominio/          lógica pura y probada: diccionario, motor de ruta, requisitos, fusión, matching
    pesos_ruta.json   pesos del motor (se ajustan sin tocar código)
  ia/               Claude (tool use + JSON Schema), embeddings de Gemini, plantillas del flujo sensible
  routers/          público, usuaria (/me), chat y canalización, panel (/admin)
  modulos/          un módulo por carpeta; cada router.py se registra solo
    asistente/        chat, canalización y visitas
    caminos/          caminos de la usuaria, puentes y catálogo
    perfil/           Mis datos y entrevista dinámica
    expediente/       expediente único, solicitudes, casos, citas y permisos por área
    recepcion/        visitas previstas y llegada
    empresas/         registro, vacantes, candidatas y revisión
    portada/          empresas aliadas para el sitio público
  servicios.py      lee con RLS, aplica el dominio y escribe con service role
  sensible.py       cifrado y bitácora de lo sensible
  auth.py  db.py  config.py  main.py
supabase/migrations/  0001 a 0007, en orden
data/               catálogo, empresas y demo (todo ficticio)
scripts/            cargar catálogo, crear la demo, etiquetar recursos
tests/              pruebas por módulo
```

## 1. Crear el proyecto de Supabase

1. En [supabase.com](https://supabase.com) crea un proyecto nuevo en la región más cercana (West US o East US)
   y guarda la contraseña de la base.
2. En **SQL Editor** corre las migraciones de `supabase/migrations/` **en orden**, empezando por
   `0001_esquema.sql` y `0001b_endurecer_funciones.sql`, hasta `0007_citas.sql`. Cada una debe terminar sin
   errores.
3. En **Authentication → Sign In / Providers → Email** deja Email activo y apaga **Confirm email** para la
   demo. El SMTP que trae Supabase manda muy pocos correos por hora y un registro en vivo se puede trabar.
4. En **Project Settings → API Keys** copia la `anon` y la `service_role`. Si ves las llaves nuevas
   (`sb_publishable_…` / `sb_secret_…`), usa la pestaña **Legacy API keys**, que son las que tenemos probadas
   con `supabase-py`.
5. La URL del proyecto está en **Project Settings → Data API** (`https://xxxx.supabase.co`).

> La `service_role` se salta RLS. Va solo en el `.env` del backend y en las variables de Vercel, nunca en el
> front ni en git.

## 2. Correr en local

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # va en SENSIBLE_KEY
uvicorn app.main:app --reload
```

Llena el `.env` con los datos del paso anterior. `ANTHROPIC_API_KEY` y `GEMINI_API_KEY` son opcionales: sin
ellas el asistente responde con su respaldo por palabras clave y el matching usa similitud neutra. La llave de
Anthropic tiene que ser de un workspace (Console → Settings → Workspaces → empoderate → API Keys) y la cuenta
necesita saldo.

### Cargar datos

Todos los datos son ficticios.

```bash
python -m scripts.cargar_catalogo      # empresas y recursos (y embeddings si hay GEMINI_API_KEY)
python -m scripts.crear_demo           # cuentas <alias>@demo.example (2 por rol), casos y visitas
python -m scripts.etiquetar_catalogo   # etiqueta con Claude solo los recursos que no tienen etiquetas
```

- La contraseña de las cuentas de demo es `DEMO_PASSWORD`.
- `crear_demo` también sirve para **restaurar la demo**: deja casos, visitas y actividad como al inicio.
- No uses `etiquetar_catalogo --todos`, porque pisa las etiquetas que ya curamos a mano.

## 3. Desplegar en Vercel

El backend vive en el proyecto `empoderate-api` (FastAPI con `index.py` y `vercel.json`):

```bash
npx vercel deploy --prod --yes
```

- Las variables de producción se manejan con `npx vercel env ls | add | rm`, nunca en el código.
- `render.yaml` tiene que seguir en `.vercelignore`; si no, Vercel lo confunde con servicios.
- Vercel solo despliega si el último commit es de alguien del equipo en Vercel. Si no, la dueña del proyecto
  hace un commit encima (o se agrega a esa persona al equipo) y se vuelve a desplegar.
- Si una migración cambia opciones del test (escolaridad, por ejemplo), **primero se despliega el backend y
  después el front**. El front nuevo manda valores que el backend viejo rechaza.

## 4. Pruebas

```bash
python -m unittest discover -s tests -v
```

`test_dominio.py` revisa los casos base de la demo: María va a Emprendimiento con puente de Capacitación,
Lucía a Empleabilidad y Rosa de Capacitación a Emprendimiento. También cubre la fusión del expediente, los
requisitos, el matching y el respaldo de señales sensibles. Si alguien mueve `pesos_ruta.json` y estas fallan,
cambió la demo.

El resto (`test_m*.py`) prueba cada módulo: asistente, caminos, expediente y permisos por área, recepción,
empresas, portada y perfil. Usan `tests/catalogo_prueba.json`, así que editar el catálogo real no las rompe.

## Endpoints

La lista completa, con ejemplos, está en `/docs`. Estos son los principales.

**Públicos y de la usuaria**

| Método | Ruta | Qué hace |
| --- | --- | --- |
| GET | `/salud` | despierta el servidor |
| GET | `/diccionario` | test base, preguntas de entrevista y etiquetas |
| GET | `/recursos`, `/catalogo` | catálogo publicado |
| GET | `/emergencia` | 911 y líneas de apoyo, sin sesión |
| GET | `/publico/empresas-aliadas` | logos para el sitio público |
| POST | `/me/registro` | guarda el consentimiento (conserva la fecha del primero) |
| GET / PATCH | `/me/expediente` | leer o fusionar campos, cada uno con su `fuente` |
| GET / PATCH | `/me/datos` | Mis datos: nombre, teléfono, CURP, RFC y dirección |
| POST | `/me/entrevista/siguiente` | la siguiente pregunta según lo que ya contestó |
| GET | `/me/ruta`, `/me/caminos` | ruta principal, puente y explicación |
| GET | `/me/recomendaciones` | top 10 con requisitos evaluados |
| GET | `/me/recursos/{id}` | detalle, preguntas que faltan y «¡Cumples!» |
| POST | `/me/recursos/{id}/accion` | aplicar o guardar |
| GET | `/me/seguimiento` | avance y línea de tiempo |
| POST | `/chat`, `/asistente/mensaje` | conversación con detección de señales (solo propone) |
| POST | `/asistente/canalizar`, `/asistente/visita` | pedir apoyo o agendar visita |
| POST / GET | `/me/canalizaciones` | crear con consentimiento o ver el estado |
| DELETE | `/me/expediente-sensible` | borra todo lo sensible |

**Personal de SEMujeres**

| Método | Ruta | Quién | Qué hace |
| --- | --- | --- | --- |
| GET | `/admin/yo` | personal | rol de quien entra |
| GET | `/panel/resumen` | por área | resumen del área |
| GET | `/panel/solicitudes`, POST `/{folio}/asignar` | trabajo social | solicitudes nuevas y asignación |
| GET | `/panel/casos`, PATCH `/casos/{folio}/cita` | especialistas | casos propios y citas |
| GET / POST | `/panel/expedientes`, `/{id}` | por área | expediente único; cada área ve solo lo suyo |
| POST | `/panel/expedientes/{id}/notas`, `/derivar` | por área | notas y derivar a otra área |
| GET / PATCH | `/panel/visitas`, POST `/llegada` | recepción | visitas previstas y llegadas sin cita (pasan a trabajo social) |
| GET / POST | `/panel/revision/…` | asesora, coordinación | revisar empresas y vacantes |
| GET / POST | `/admin/recursos`, PATCH `/{id}/publicacion` | asesora, coordinación | editar, publicar o pausar recursos |
| GET / PATCH | `/admin/canalizaciones`, `/{folio}` | especialistas | bandeja por urgencia y caso descifrado |
| GET | `/admin/metricas` | personal | conteos (la asesora no ve los del flujo sensible) |
| GET | `/admin/bitacora` | coordinación | quién leyó qué |

**Empresas:** `/empresas/registro`, `/empresas/yo`, `/empresas/vacantes` y
`/empresas/vacantes/{id}/candidatas`. Ninguna vacante se publica sin que SEMujeres la revise.

## Decisiones de diseño

- **La ruta la decide el código**, no la IA (`dominio/motor_ruta.py` + `pesos_ruta.json`). Claude solo la
  redacta, y si tarda más de 6 s se usa una plantilla.
- **La IA no inventa recursos.** El chat solo recibe el top 10 de la usuaria y los IDs que regresa se filtran
  contra esa lista. Las preguntas solo pueden ser de campos del diccionario, con sus opciones.
- **«¿Qué me falta?» es una resta.** `dominio/requisitos.py` marca cada requisito como cumple, no cumple o
  falta el dato.
- **Expediente vivo.** Cada campo guarda `fuente`, `confianza` y `fecha`, con historial en
  `expediente_eventos`. Si el personal contradice lo que dijo ella, queda en `conflictos` y no se sobrescribe.
- **Cada área ve lo suyo.** `modulos/expediente/permisos.py` define qué lee cada rol. Lo confidencial de otra
  área aparece como texto público («En atención jurídica desde 26 nov») o con candado.
- **Lo sensible va aparte.** `expedientes_sensibles` está cifrado con Fernet, RLS solo deja verlo a ella y a la
  especialista que la atiende, cada lectura queda en `bitacora_accesos`, y la conversación no se guarda ni se
  escribe en logs.
- **La seguridad está en la base, no en los botones.** Las lecturas usan el JWT de quien pide y el navegador
  no puede escribir en ninguna tabla.

## Pendientes

- Teléfono y horario oficiales del área jurídica de la Secretaría de las Mujeres de Sinaloa, en
  `app/ia/plantillas.py` (`CONTACTO_EMERGENCIA`). Falta también confirmar el número vigente de la Línea de la
  Vida.
- Validar con SEMujeres las plantillas del flujo sensible.
- Que la usuaria pueda autorizar que su asesora vea su caso sensible (hoy la separación es total).
- Desempate de rutas con LLM. Por ahora, en un empate gana el orden fijo.
