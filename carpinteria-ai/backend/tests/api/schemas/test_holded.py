import pytest
from pydantic import ValidationError
from api.schemas.holded import HoldedItem, HoldedEstimate

def test_holded_item_defaults():
    item = HoldedItem(name="Mesa", units=2.5, subtotal=150.0)
    assert item.tax == 21

def test_holded_estimate_valid():
    item = HoldedItem(name="Silla", units=4.0, subtotal=200.0)
    estimate = HoldedEstimate(contactId="123", date=1672531200, items=[item])
    assert estimate.contactId == "123"
    assert len(estimate.items) == 1

def test_holded_estimate_empty_items():
    with pytest.raises(ValidationError) as exc:
        HoldedEstimate(contactId="123", date=1672531200, items=[])
    assert "items cannot be empty" in str(exc.value)

def test_holded_estimate_clean_json():
    item = HoldedItem(name="Silla", units=4.0, subtotal=200.0)
    estimate = HoldedEstimate(contactId="123", date=1672531200, items=[item])
    json_data = estimate.model_dump_json_clean()
    assert "123" in json_data
    assert "Silla" in json_data
