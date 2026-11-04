"""`TTLCache` (`app/cache.py`) sin HTTP: aciertos y fallos, TTL, invalidación, copias inmutables y errores.

Ejecutar desde services/api: uv run pytest tests/test_cache.py
"""

import logging

import pytest
from pydantic import BaseModel

from app.cache import TTLCache


class Item(BaseModel):
    name: str
    tags: list[str]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Loader:
    """Cuenta cuántas veces se leen los datos «de verdad»."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(clock) -> TTLCache:
    return TTLCache("test.items", ttl_seconds=30, response_type=list[Item], clock=clock)


def items(*names: str) -> list[Item]:
    return [Item(name=name, tags=["a"]) for name in names]


def test_first_read_is_a_miss_and_the_second_a_hit(cache):
    load = Loader(items("uno", "dos"))
    assert cache.get_or_load(("k",), load) == items("uno", "dos")
    assert cache.get_or_load(("k",), load) == items("uno", "dos")
    assert load.calls == 1
    stats = cache.stats()
    assert (stats.hits, stats.misses, stats.entries) == (1, 1, 1)
    assert stats.hit_ratio == 0.5


def test_each_hit_returns_new_objects_that_can_be_modified_safely(cache):
    cache.get_or_load(("k",), Loader(items("uno")))
    first = cache.get_or_load(("k",), Loader(None))
    first[0].name = "cambiado"
    first[0].tags.append("b")
    first.append(Item(name="intruso", tags=[]))

    assert cache.get_or_load(("k",), Loader(None)) == items("uno")


def test_modifying_the_value_returned_by_a_miss_does_not_change_the_cache(cache):
    value = items("uno")
    cache.get_or_load(("k",), Loader(value))
    value[0].name = "cambiado"
    assert cache.get_or_load(("k",), Loader(None)) == items("uno")


def test_entry_expires_after_the_ttl(cache, clock):
    load = Loader(items("uno"))
    cache.get_or_load(("k",), load)
    clock.advance(29.9)
    cache.get_or_load(("k",), load)
    assert load.calls == 1

    clock.advance(0.1)  # justo al cumplirse el TTL ya no vale
    cache.get_or_load(("k",), load)
    assert load.calls == 2


def test_different_keys_do_not_collide(cache):
    cache.get_or_load(("k", "LA"), Loader(items("la")))
    cache.get_or_load(("k", None), Loader(items("todos")))
    assert cache.get_or_load(("k", "LA"), Loader(None)) == items("la")
    assert cache.get_or_load(("k", None), Loader(None)) == items("todos")


def test_invalidate_forgets_every_entry(cache):
    load = Loader(items("uno"))
    cache.get_or_load(("a",), load)
    cache.get_or_load(("b",), load)
    cache.invalidate()
    assert cache.stats().entries == 0
    assert cache.stats().invalidations == 1
    cache.get_or_load(("a",), load)
    assert load.calls == 3


def test_a_load_error_is_propagated_and_nothing_is_cached(cache):
    def failing():
        raise RuntimeError("la base no responde")

    with pytest.raises(RuntimeError):
        cache.get_or_load(("k",), failing)
    assert cache.stats().entries == 0

    load = Loader(items("uno"))
    assert cache.get_or_load(("k",), load) == items("uno")
    assert load.calls == 1


def test_a_write_during_the_read_discards_the_result(cache):
    """Lectura que empezó antes de una escritura: su resultado puede ser viejo y no se guarda."""

    def load_while_someone_writes():
        cache.invalidate()  # otra petición escribe mientras se leen los datos
        return items("viejo")

    assert cache.get_or_load(("k",), load_while_someone_writes) == items("viejo")
    assert cache.stats().entries == 0

    load = Loader(items("nuevo"))
    assert cache.get_or_load(("k",), load) == items("nuevo")
    assert load.calls == 1


def test_a_failure_reading_the_cache_falls_back_to_the_data(cache, monkeypatch, caplog):
    cache.get_or_load(("k",), Loader(items("uno")))

    def broken(_key):
        raise RuntimeError("caché rota")

    monkeypatch.setattr(cache, "_lookup", broken)
    load = Loader(items("fresco"))
    with caplog.at_level(logging.ERROR, logger="trackflow.api.cache"):
        assert cache.get_or_load(("k",), load) == items("fresco")
    assert load.calls == 1
    assert "no se pudo leer" in caplog.text


def test_a_failure_storing_does_not_break_the_response(cache, monkeypatch, caplog):
    def broken(*_args):
        raise MemoryError

    monkeypatch.setattr(cache, "_store", broken)
    with caplog.at_level(logging.ERROR, logger="trackflow.api.cache"):
        assert cache.get_or_load(("k",), Loader(items("uno"))) == items("uno")
    assert "no se pudo guardar" in caplog.text


def test_max_entries_evicts_the_entry_that_expires_first(clock):
    cache = TTLCache("test.small", ttl_seconds=30, response_type=list[Item], max_entries=2, clock=clock)
    cache.get_or_load(("a",), Loader(items("a")))
    clock.advance(1)
    cache.get_or_load(("b",), Loader(items("b")))
    clock.advance(1)
    cache.get_or_load(("c",), Loader(items("c")))

    assert cache.stats().entries == 2
    load_a = Loader(items("a"))
    cache.get_or_load(("a",), load_a)
    assert load_a.calls == 1  # «a» era la que caducaba antes: salió


def test_reset_clears_entries_and_counters(cache):
    cache.get_or_load(("k",), Loader(items("uno")))
    cache.get_or_load(("k",), Loader(None))
    cache.reset()
    stats = cache.stats()
    assert (stats.hits, stats.misses, stats.invalidations, stats.entries) == (0, 0, 0, 0)


@pytest.mark.parametrize("ttl", [0, -1])
def test_a_cache_without_expiry_is_rejected(ttl):
    with pytest.raises(ValueError, match="TTL"):
        TTLCache("test.forever", ttl_seconds=ttl, response_type=list[Item])
