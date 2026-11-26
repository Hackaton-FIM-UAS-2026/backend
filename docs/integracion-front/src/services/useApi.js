// src/services/useApi.js — hook mínimo para pasar de lecturas síncronas (localStorage) a la API.
//
//   const { datos, cargando, error } = useApi(api.recomendaciones);
//
import { useEffect, useState } from "react";

export function useApi(fn, deps = []) {
  const [estado, setEstado] = useState({ datos: null, cargando: true, error: null });
  useEffect(() => {
    let vivo = true;
    setEstado((e) => ({ ...e, cargando: true }));
    fn()
      .then((datos) => vivo && setEstado({ datos, cargando: false, error: null }))
      .catch((error) => vivo && setEstado({ datos: null, cargando: false, error }));
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return estado;
}
