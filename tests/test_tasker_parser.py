import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.tasker_parser import parse_tasker_payload
from src.models.tasker import TaskerPayload


def _payload(**kwargs) -> TaskerPayload:
    defaults = {
        "raw_text": "Hai pagato €12,50 a Esselunga",
        "amount": "12.50",
        "currency": "EUR",
        "merchant": "Esselunga",
        "direction": "debit",
        "device_timestamp": datetime(2026, 6, 7, 14, 32, 0, tzinfo=timezone.utc),
        "parse_status": "ok",
    }
    defaults.update(kwargs)
    return TaskerPayload(**defaults)


class TestParseTaskerPayload:
    def test_debit_is_negative(self):
        tx = parse_tasker_payload(_payload(direction="debit", amount="12.50"))
        assert tx.amount == -12.50

    def test_credit_is_positive(self):
        tx = parse_tasker_payload(_payload(direction="credit", amount="50.00"))
        assert tx.amount == 50.00

    def test_status_is_pending(self):
        tx = parse_tasker_payload(_payload())
        assert tx.status == "pending"

    def test_source_is_tasker(self):
        tx = parse_tasker_payload(_payload())
        assert tx.source == "tasker"

    def test_currency_and_merchant(self):
        tx = parse_tasker_payload(_payload(currency="EUR", merchant="Esselunga"))
        assert tx.currency == "EUR"
        assert tx.merchant_name == "Esselunga"

    def test_dedup_hash_is_64_chars(self):
        tx = parse_tasker_payload(_payload())
        assert len(tx.dedup_hash) == 64

    def test_dedup_hash_deterministic(self):
        p = _payload()
        assert parse_tasker_payload(p).dedup_hash == parse_tasker_payload(p).dedup_hash

    def test_parse_failed_produces_none_amount(self):
        p = _payload(parse_status="failed", amount=None, merchant=None, direction=None)
        tx = parse_tasker_payload(p)
        assert tx.amount == 0.0
        assert tx.merchant_name is None
        assert tx.status == "pending"

    def test_booking_date_from_device_timestamp(self):
        ts = datetime(2026, 6, 7, 14, 32, 0, tzinfo=timezone.utc)
        tx = parse_tasker_payload(_payload(device_timestamp=ts))
        assert tx.booking_date == ts

    def test_is_internal_false(self):
        tx = parse_tasker_payload(_payload(merchant="Esselunga"))
        assert not tx.is_internal

    def test_eur_amount_equals_amount_for_eur(self):
        tx = parse_tasker_payload(_payload(currency="EUR", amount="12.50", direction="debit"))
        assert tx.eur_amount == -12.50
