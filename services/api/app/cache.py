"""Caché en memoria con TTL para respuestas de lectura compartidas por todos los usuarios autenticados.

Decisiones (detalle en `CACHING_REPORT.md`, en la raíz del repo):

- **Solo datos no personalizados.** Se cachea lo que es idéntico para cualquier usuario autenticado (proveedores,
  incidencias, listado de SKUs). La autenticación sigue ocurriendo en cada petición, **antes** de leer la caché: los
  routers la exigen con `dependencies=[Depends(get_current_user)]`. Nada que dependa de la identidad, del rol o de la
  sesión (`/auth/me`, `/profiles/me`, `/users`) pasa por aquí.
- **Instantáneas inmutables.** Se guarda el JSON (`bytes`) del valor, generado con el `TypeAdapter` del
  `response_model`, y cada acierto lo convierte en objetos nuevos (`validate_json`): nadie puede modificar por
  accidente lo que está en la caché. Las funciones del router siguen devolviendo sus modelos y FastAPI los serializa
  como antes, así que el contrato de la API (y las pruebas que llaman a esas funciones directamente) no cambia.
- **Claves deterministas.** Una tupla con el origen de los datos (ruta del fichero o URL de la base) y los parámetros
  ya validados (enums o `None`). Las claves no se escriben en el log.
- **TTL por caché**, nunca infinito, e **invalidación explícita** tras cada escritura que cambia los datos. Cada
  invalidación sube una generación: una lectura que empezó antes de la escritura no guarda su resultado (ya viejo).
- **Un fallo de la caché no tumba el endpoint.** Si consultar o guardar en la caché falla, se registra y se responde
  con los datos recién leídos. Un error al leer los datos se propaga como siempre (404, 500…) y no se cachea.
- **Alcance: un proceso.** Con varios workers de uvicorn cada uno tiene su caché y la invalidación solo llega al
  worker que hizo la escritura; los demás pueden servir datos viejos hasta su TTL. La API se despliega con un worker
  (`docs/despliegue-api.md`). Los cambios hechos por otros procesos (p. ej. los seeders) también tardan hasta el TTL.
"""

import logging
import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter

logger = logging.getLogger("trackflow.api.cache")


@dataclass(frozen=True)
class _Entry:
    snapshot: bytes
    expires_at: float


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    invalidations: int
    entries: int

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class TTLCache:
    """Caché con caducidad de un tipo de respuesta. `response_type` es el `response_model` del endpoint.

    `clock` existe para que los tests puedan adelantar el tiempo sin esperar al TTL.
    """

    def __init__(
        self,
        name: str,
        ttl_seconds: float,
        response_type: Any,
        max_entries: int = 64,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("El TTL debe ser positivo: no hay cachés sin caducidad.")
        self.name = name
        self.ttl_seconds = ttl_seconds
        self.adapter: TypeAdapter[Any] = TypeAdapter(response_type)
        self.max_entries = max_entries
        self.clock = clock
        self._entries: dict[Hashable, _Entry] = {}
        self._lock = threading.Lock()
        self._generation = 0
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

    def get_or_load(self, key: Hashable, load: Callable[[], Any]) -> Any:
        """Valor de `key`: una copia nueva de la instantánea si sigue vigente; si no, `load()` y se guarda."""
        try:
            snapshot = self._lookup(key)
            if snapshot is not None:
                return self.adapter.validate_json(snapshot)
        except Exception:
            logger.exception("Caché %s: no se pudo leer; se consultan los datos", self.name)

        with self._lock:
            self._misses += 1
            generation = self._generation
        value = load()  # un error al leer los datos se propaga y no se cachea nada
        try:
            self._store(key, self.adapter.dump_json(value), generation)
        except Exception:
            logger.exception("Caché %s: no se pudo guardar; se responde sin cachear", self.name)
        return value

    def invalidate(self) -> None:
        """Olvida todas las entradas tras una escritura. Las lecturas en curso no guardarán su resultado."""
        with self._lock:
            self._entries.clear()
            self._generation += 1
            self._invalidations += 1

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(self._hits, self._misses, self._invalidations, len(self._entries))

    def reset(self) -> None:
        """Vacía la caché y sus contadores (tests y mediciones)."""
        with self._lock:
            self._entries.clear()
            self._generation += 1
            self._hits = self._misses = self._invalidations = 0

    def _lookup(self, key: Hashable) -> bytes | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self.clock():
                del self._entries[key]
                return None
            self._hits += 1
            return entry.snapshot

    def _store(self, key: Hashable, snapshot: bytes, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return  # hubo una escritura mientras se leían los datos: el resultado puede estar viejo
            if key not in self._entries and len(self._entries) >= self.max_entries:
                # Límite de memoria: sale la entrada que caduca antes.
                oldest = min(self._entries, key=lambda existing: self._entries[existing].expires_at)
                del self._entries[oldest]
            self._entries[key] = _Entry(snapshot, self.clock() + self.ttl_seconds)


# Registro de todas las cachés de la API, para vaciarlas a la vez (tests y mediciones).
_registry: dict[str, TTLCache] = {}


def register(cache: TTLCache) -> TTLCache:
    if cache.name in _registry:
        raise ValueError(f"Ya existe una caché llamada {cache.name!r}")
    _registry[cache.name] = cache
    return cache


def all_caches() -> dict[str, TTLCache]:
    return dict(_registry)


def reset_all() -> None:
    for cache in _registry.values():
        cache.reset()
