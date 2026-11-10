"""Catálogo aprobado de eventos (`event-schemas.json`) y su validación, sin dependencias nuevas.

`event-schemas.json` es una **copia exacta** de `docs/telemetry/event-schemas.json` (la imagen Docker solo incluye
`services/api/app`); `tests/test_telemetry_contract.py` falla si las dos copias se separan.

El plan (§18.1) deja dos opciones para validar en Python: añadir `jsonschema` (dependencia que hay que aprobar) o
modelos equivalentes. Aquí se valida contra el propio JSON Schema con un validador mínimo que entiende exactamente las
palabras clave que usa el catálogo (Draft-07): `$ref`, `allOf`, `anyOf`, `if`/`then`/`else`, `type`, `enum`, `const`,
`pattern`, `format` (`date-time`, `date`), límites numéricos y de longitud, `required`, `properties`,
`additionalProperties`, `items`, `minItems`, `maxItems` y `uniqueItems`. Si el catálogo empieza a usar otra, el test de
cobertura de palabras clave falla en lugar de aceptarla en silencio.

Los mensajes de error solo nombran la ruta del campo y la regla incumplida, **nunca el valor** recibido: un valor que
no valida podría ser un dato personal enviado por error.
"""

import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("event-schemas.json")

# Palabras clave que entiende `_Validator`. Las de anotación (`title`, `description`, `examples`, `x-…`) se ignoran.
SUPPORTED_KEYWORDS = frozenset(
    {
        "$ref", "allOf", "anyOf", "if", "then", "else", "type", "enum", "const", "pattern", "format", "minimum",
        "maximum", "minLength", "maxLength", "required", "properties", "additionalProperties", "items", "minItems",
        "maxItems", "uniqueItems",
    }
)
ANNOTATION_KEYWORDS = frozenset({"title", "description", "examples", "default", "$schema", "$id"})


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def catalog_version() -> str:
    return load_schema()["x-catalogVersion"]


def event_types() -> tuple[str, ...]:
    return tuple(load_schema()["x-eventTypes"])


def event_definition(event_type: str) -> dict[str, Any] | None:
    """Esquema de un `event_type` del catálogo, o `None` si no existe."""
    if event_type not in event_types():
        return None
    return load_schema()["definitions"][event_type]


def allowed_sources(event_type: str) -> tuple[str, ...]:
    definition = event_definition(event_type)
    return tuple(definition["x-sources"]) if definition else ()


def schema_version(event_type: str) -> str | None:
    """`schemaVersion` que exige el catálogo para ese `event_type`."""
    definition = event_definition(event_type)
    if definition is None:
        return None
    for part in definition.get("allOf", []):
        version = part.get("properties", {}).get("schemaVersion", {}).get("const")
        if version:
            return version
    return None


def _ecma_pattern(pattern: str) -> re.Pattern[str]:
    # En ECMAScript (el dialecto de JSON Schema) `$` es el final del texto; en Python también acepta un `\n` final.
    return re.compile(re.sub(r"(?<!\\)\$", r"\\Z", pattern))


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _matches_type(value: Any, expected: str) -> bool:
    actual = _json_type(value)
    if expected == "number":
        return actual in ("integer", "number")
    if expected == "integer":
        # Draft-07: un entero es un número sin parte decimal (5.0 también lo es).
        return actual == "integer" or (actual == "number" and float(value).is_integer())
    return actual == expected


def _valid_format(value: str, kind: str) -> bool:
    try:
        if kind == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif kind == "date":
            date.fromisoformat(value)
    except ValueError:
        return False
    return True


class _Validator:
    def __init__(self, root: dict[str, Any]) -> None:
        self.root = root
        self.patterns: dict[str, re.Pattern[str]] = {}

    def _resolve(self, ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise ValueError(f"Referencia no soportada: {ref}")
        node: Any = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def _pattern(self, pattern: str) -> re.Pattern[str]:
        if pattern not in self.patterns:
            self.patterns[pattern] = _ecma_pattern(pattern)
        return self.patterns[pattern]

    def errors(self, value: Any, schema: dict[str, Any], path: str) -> list[str]:
        where = path or "(evento)"
        found: list[str] = []

        if "$ref" in schema:
            found += self.errors(value, self._resolve(schema["$ref"]), path)
        for part in schema.get("allOf", []):
            found += self.errors(value, part, path)
        if "anyOf" in schema and not any(not self.errors(value, option, path) for option in schema["anyOf"]):
            found.append(f"{where}: no cumple ninguna de las formas permitidas")
        if "if" in schema and not self.errors(value, schema["if"], path):
            if "then" in schema:
                found += self.errors(value, schema["then"], path)
        elif "if" in schema and "else" in schema:
            found += self.errors(value, schema["else"], path)

        if "type" in schema:
            expected = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_matches_type(value, kind) for kind in expected):
                found.append(f"{where}: tipo no válido (se espera {' o '.join(expected)})")
                return found
        if "const" in schema and value != schema["const"]:
            found.append(f"{where}: valor no permitido")
        if "enum" in schema and value not in schema["enum"]:
            found.append(f"{where}: valor no permitido")

        if isinstance(value, str):
            if "pattern" in schema and not self._pattern(schema["pattern"]).search(value):
                found.append(f"{where}: formato no válido")
            if "format" in schema and not _valid_format(value, schema["format"]):
                found.append(f"{where}: formato {schema['format']} no válido")
            if "minLength" in schema and len(value) < schema["minLength"]:
                found.append(f"{where}: demasiado corto")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                found.append(f"{where}: demasiado largo")

        if _json_type(value) in ("integer", "number"):
            if "minimum" in schema and value < schema["minimum"]:
                found.append(f"{where}: por debajo del mínimo")
            if "maximum" in schema and value > schema["maximum"]:
                found.append(f"{where}: por encima del máximo")

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                found.append(f"{where}: demasiados pocos elementos")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                found.append(f"{where}: demasiados elementos")
            if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
                found.append(f"{where}: elementos repetidos")
            if "items" in schema:
                for index, item in enumerate(value):
                    found += self.errors(item, schema["items"], f"{path}[{index}]")

        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    found.append(f"{self._child(path, name)}: obligatorio")
            declared = schema.get("properties", {})
            for name, item in value.items():
                child = self._child(path, name)
                if name in declared:
                    found += self.errors(item, declared[name], child)
                elif schema.get("additionalProperties") is False:
                    # El nombre de la clave tampoco se repite: lo decide quien envía y podría ser cualquier cosa.
                    found.append(f"{where}: propiedad no permitida por la allowlist")
                elif isinstance(schema.get("additionalProperties"), dict):
                    found += self.errors(item, schema["additionalProperties"], child)
        return found

    @staticmethod
    def _child(path: str, name: str) -> str:
        return f"{path}.{name}" if path else name


@lru_cache(maxsize=1)
def _validator() -> _Validator:
    return _Validator(load_schema())


def validate_event(event: dict[str, Any]) -> list[str]:
    """Errores del evento frente a su esquema del catálogo (lista vacía = válido). Sin valores en los mensajes."""
    event_type = event.get("event_type")
    if not isinstance(event_type, str) or event_definition(event_type) is None:
        return ["event_type: no está en el catálogo aprobado"]
    return _validator().errors(event, event_definition(event_type), "")


def unsupported_keywords() -> set[str]:
    """Palabras clave del catálogo que este validador no entiende (debe estar vacío; lo comprueba un test)."""
    found: set[str] = set()

    def walk(node: Any, in_properties: bool) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, False)
        elif isinstance(node, dict):
            for key, child in node.items():
                if not in_properties and key not in SUPPORTED_KEYWORDS and key not in ANNOTATION_KEYWORDS:
                    if not key.startswith("x-"):
                        found.add(key)
                # Dentro de `properties` las claves son nombres de propiedad; dentro de `examples`, datos.
                if key in ("examples", "default", "const", "enum"):
                    continue
                walk(child, key == "properties")

    walk(load_schema()["definitions"], True)
    return found
