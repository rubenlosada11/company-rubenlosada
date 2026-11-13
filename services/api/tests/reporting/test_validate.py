"""Subflow validate: reglas de calidad (`app/reporting/validate.py`, PIPELINE_DESIGN.md §6.3).

Ejecutar desde services/api: uv run pytest tests/reporting/test_validate.py
"""

import pandas as pd
import pytest

from app.reporting.validate import VALID_COLUMNS, validate_events
from tests.reporting.helpers import DISCREPANCY, INBOUND, OUTBOUND, STOCKOUT, W2, at, event, frame


def test_valid_events_pass_with_their_dimensions():
    result = validate_events(
        frame(
            event(INBOUND, at(W2), quantity=40, order_id=1),
            event(OUTBOUND, at(W2), warehouse="zaragoza", client_id="electro-brand", quantity=2, order_id=7),
            event(STOCKOUT, at(W2)),
            event(DISCREPANCY, at(W2)),
        )
    )
    assert list(result.valid.columns) == VALID_COLUMNS
    assert len(result.valid) == 4 and result.rejected == {} and result.events_rejected == 0
    assert result.valid["warehouse"].tolist() == ["los_angeles", "zaragoza", "los_angeles", "los_angeles"]
    assert str(result.valid["timestamp"].dt.tz) == "UTC"
    # Solo la entrada conserva la cantidad: las demás nunca se suman.
    assert result.valid["quantity"].tolist() == [40, 0, 0, 0]


def test_events_read_counts_the_four_types_even_when_absent():
    result = validate_events(frame(event(OUTBOUND, at(W2)), event(OUTBOUND, at(W2))))
    assert result.events_read == {INBOUND: 0, OUTBOUND: 2, STOCKOUT: 0, DISCREPANCY: 0}


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (event(OUTBOUND, at(W2), warehouse="madrid"), "invalid_warehouse"),
        (event(OUTBOUND, at(W2), warehouse=None), "invalid_warehouse"),
        (event(OUTBOUND, at(W2), warehouse="LA"), "invalid_warehouse"),  # valor interno, no el del contrato
        (event(OUTBOUND, at(W2), client_id="Fashion Co"), "invalid_client_id"),
        (event(OUTBOUND, at(W2), client_id=None), "invalid_client_id"),
        (event(OUTBOUND, at(W2), client_id=7), "invalid_client_id"),
        (event(OUTBOUND, at(W2), client_id="a" * 65), "invalid_client_id"),
        (event(INBOUND, at(W2), quantity=None), "invalid_quantity"),
        (event(INBOUND, at(W2), quantity=0), "invalid_quantity"),
        (event(INBOUND, at(W2), quantity="5"), "invalid_quantity"),
        (event(INBOUND, at(W2), quantity=True), "invalid_quantity"),
        (event(INBOUND, at(W2), quantity=2.5), "invalid_quantity"),
        (event(INBOUND, at(W2), tags=None), "invalid_warehouse"),  # tags que no es un objeto
    ],
)
def test_each_rule_rejects_and_counts_by_type_and_reason(row, reason):
    result = validate_events(frame(row, event(OUTBOUND, at(W2), client_id="ok-client")))
    assert result.rejected == {row["event_type"]: {reason: 1}}
    assert result.events_rejected == 1
    assert result.valid["client_id"].tolist() == ["ok-client"]


def test_quantity_is_only_required_for_inbound_events():
    result = validate_events(frame(event(OUTBOUND, at(W2), quantity=None), event(STOCKOUT, at(W2), quantity=None)))
    assert result.rejected == {} and len(result.valid) == 2


def test_unparseable_timestamp_is_rejected():
    raw = frame(event(OUTBOUND, at(W2)))
    raw["timestamp"] = raw["timestamp"].astype(object)
    raw.loc[0, "timestamp"] = "no es una fecha"
    assert validate_events(raw).rejected == {OUTBOUND: {"invalid_timestamp": 1}}


def test_first_failing_rule_is_the_reason():
    row = event(INBOUND, at(W2), warehouse="madrid", client_id="MAL", quantity=0)
    assert validate_events(frame(row)).rejected == {INBOUND: {"invalid_warehouse": 1}}


def test_repeated_order_counts_once():
    first = event(OUTBOUND, at(W2, 9), order_id=5)
    repeated = event(OUTBOUND, at(W2, 10), order_id=5)  # mismo pedido, otro eventId
    other_warehouse = event(OUTBOUND, at(W2, 11), warehouse="zaragoza", order_id=5)  # otra base de órdenes
    inbound_same_id = event(INBOUND, at(W2, 12), order_id=5)  # stock_entries.id ≠ stock_exits.id
    result = validate_events(frame(first, repeated, other_warehouse, inbound_same_id))
    assert result.rejected == {OUTBOUND: {"duplicate_order": 1}}
    assert result.valid["id"].tolist() == [first["id"], other_warehouse["id"], inbound_same_id["id"]]


def test_events_without_order_id_are_never_duplicates():
    result = validate_events(frame(event(STOCKOUT, at(W2)), event(STOCKOUT, at(W2))))
    assert result.rejected == {} and len(result.valid) == 2


def test_invalid_row_does_not_hide_a_later_valid_copy_of_the_order():
    broken = event(OUTBOUND, at(W2, 9), client_id="MAL", order_id=5)
    good = event(OUTBOUND, at(W2, 10), order_id=5)
    result = validate_events(frame(broken, good))
    assert result.rejected == {OUTBOUND: {"invalid_client_id": 1}}
    assert result.valid["id"].tolist() == [good["id"]]


def test_empty_input_gives_empty_output_with_columns():
    result = validate_events(frame())
    assert result.valid.empty and list(result.valid.columns) == VALID_COLUMNS
    assert result.rejected == {} and sum(result.events_read.values()) == 0
    assert isinstance(result.valid, pd.DataFrame)
