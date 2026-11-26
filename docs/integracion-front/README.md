# Conectar el front a la API

Copiar `src/lib/supabase.js`, `src/services/api.js` y `src/services/useApi.js` al repo del front, y luego:

```bash
npm i @supabase/supabase-js
```

`.env.local` del front (no se sube a git):

```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://TU-PROYECTO.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...   # la anon, NUNCA la service role
```

## Qué mock se reemplaza con qué

Las respuestas tienen **la misma forma** que los mocks, así que los componentes no cambian. Lo que cambia es que las páginas ahora leen de forma asíncrona (`useApi` o `await`).

| Hoy (mock) | Página | Ahora |
| --- | --- | --- |
| Registro sin auth | `Registro.jsx` | `entrar(correo, pass)` y luego `api.registro({ acepto_privacidad: true })` |
| `guardarCampos(resp, "test_base")` | `TestBase.jsx` | `await api.guardarCampos(resp, "test_base")` |
| `calcularRuta(valores(leerExpediente()))` | `Resultado.jsx` | `useApi(api.ruta)` → `{principal, puente, factores, explicacion}` |
| `leerCatalogoPublico()` + filtro por ruta | `Dashboard.jsx` | `useApi(api.recomendaciones)` → `datos.ruta`, `datos.recursos` (ya filtrados, top 10) |
| `leerCatalogoPublico().find(id)` | `RecursoDetalle.jsx` | `useApi(() => api.recurso(id), [id])` → trae `requisitos[].ok`, `preguntas`, `explicacion`, `cumple` |
| `resp[campo]` local en `ResourceDetail` | `ResourceDetail.jsx` | al contestar: `await api.guardarCampos({[campo]: valor}, "entrevista")` y volver a pedir `api.recurso(id)` |
| `window.open(url_accion)` | `RecursoDetalle.jsx` | `await api.accion(id, "aplicar")` y luego abrir `url_accion` |
| `leerExpediente()` | `Seguimiento.jsx` | `useApi(api.seguimiento)` → `version`, `datos_guardados`, `total`, `historial` |
| `SENALES` por palabras clave | `AgentChat.jsx` | `await api.chat(texto)` → mostrar `respuesta`; si `proponer_canalizacion`, mostrar botones; si `emergencia`, `EmergencyBanner` |
| `onDone({tipo, contacto})` | `Apoyo.jsx` | si no es null: `await api.canalizar({ tipo, contacto, consentimiento: true })` |
| `USUARIAS` | `AdminPanel.jsx` | `api.admin.usuarias()` |
| `CASOS_INICIALES` | `AdminPanel.jsx` | `api.admin.canalizaciones()` (solo especialistas; a la asesora le regresa 403: ocultar la pestaña) |
| `cambiarCaso(id, estado)` | `AdminPanel.jsx` | `api.admin.actualizarCaso(id, { estado })` (el `id` es el folio `C-015`) |
| `registrar(id, estado, nota)` | `AdminPanel.jsx` | `api.admin.situacion(id, { estado, nota })` |
| `registrarContacto(id, {...})` | `AdminPanel.jsx` | `api.admin.contacto(id, { medio, resultado, nota })` |
| `leerCatalogo / guardarOferta / cambiarPublicacion` | `AdminPanel.jsx` | `api.admin.recursos / guardarRecurso / publicar` |
| `TEST_BASE`, `DICCIONARIO_PREGUNTAS` | varios | pueden quedarse como están; `api.diccionario()` regresa lo mismo si quieren una sola fuente |
| `calcularRuta` en el front | — | **dejar de usarlo**: el backend agrega la regla de puente que pide el documento (María = Emprendimiento + puente Capacitación) |

## Ejemplo: detalle de recurso con preguntas del agente

```jsx
export default function RecursoDetalle() {
  const { id } = useParams();
  const [n, setN] = useState(0);                       // sube para volver a pedir
  const { datos: recurso, cargando, error } = useApi(() => api.recurso(id), [id, n]);

  const responder = async (campo, valor) => {
    await api.guardarCampos({ [campo]: valor }, "entrevista");
    setN((x) => x + 1);                                // el backend recalcula "¡Cumples!"
  };
  if (cargando) return <AppTemplate><p className="muted">Cargando…</p></AppTemplate>;
  if (error?.status === 404 || !recurso) return /* el estado vacío que ya tienen */;
  return <ResourceDetail recurso={recurso} onResponder={responder} onAction={...} />;
}
```

En `ResourceDetail`, `recurso.preguntas` ya viene lista (`[{campo, pregunta, opciones}]`) y `recurso.cumple` dice si mostrar "¡Cumples!". Ya no hace falta `DICCIONARIO_PREGUNTAS` ahí.

## Ejemplo: chat

```js
const r = await api.chat(texto);
setMsgs((m) => [...m, { from: "agente", text: r.respuesta }]);
setPropuesta(r.proponer_canalizacion);
setEmergencia(r.emergencia);   // si no es null: mostrar 911 sin formularios
```

## Cuentas de la demo

Después de `python -m scripts.crear_demo` en el backend: `maria@demo.example`, `lucia@…`, `rosa@…`, `asesora@…`, `juridica@…`, `psicologica@…`, `coordinacion@…`, todas con la contraseña `Demo2026!`.

## Errores esperables

- `401`: no hay sesión o expiró → mandar a `/registro`.
- `403`: el rol no tiene acceso (p. ej. la asesora pidiendo la bandeja) → ocultar esa sección.
- `422`: valor fuera del diccionario (p. ej. una opción con otro texto). El mensaje dice cuál.
- `ApiError(0)`: red lenta → mostrar "La conexión está lenta" y un botón de reintentar.
