from datetime import UTC

import pytest

from fintracker.normalizer.hash import eb_dedup_hash as _dedup_hash
from fintracker.normalizer.normalize import _is_internal, normalize


class TestDedupHash:
    def test_deterministic(self):
        h1 = _dedup_hash("2024-01-15", -25.50, "Coffee Shop", "EUR")
        h2 = _dedup_hash("2024-01-15", -25.50, "Coffee Shop", "EUR")
        assert h1 == h2

    def test_uses_absolute_amount(self):
        assert _dedup_hash("2024-01-15", -25.50, "shop", "EUR") == _dedup_hash(
            "2024-01-15", 25.50, "shop", "EUR"
        )

    def test_case_insensitive_description(self):
        assert _dedup_hash("2024-01-15", 10.0, "Coffee Shop", "EUR") == _dedup_hash(
            "2024-01-15", 10.0, "COFFEE SHOP", "EUR"
        )

    def test_only_date_prefix_used(self):
        assert _dedup_hash("2024-01-15T12:30:00Z", 10.0, "shop", "EUR") == _dedup_hash(
            "2024-01-15", 10.0, "shop", "EUR"
        )

    def test_sha256_length(self):
        assert len(_dedup_hash("2024-01-15", 10.0, "shop", "EUR")) == 64

    def test_different_amounts_differ(self):
        assert _dedup_hash("2024-01-15", 10.00, "shop", "EUR") != _dedup_hash(
            "2024-01-15", 10.01, "shop", "EUR"
        )

    def test_different_currencies_differ(self):
        assert _dedup_hash("2024-01-15", 10.0, "shop", "EUR") != _dedup_hash(
            "2024-01-15", 10.0, "shop", "USD"
        )


class TestInternalPatterns:
    @pytest.mark.parametrize(
        "desc",
        [
            "Top-Up by bank transfer",
            "top up by SEPA",
            "Exchanged from EUR to USD",
            "Exchange to GBP",
            "Savings Vault deposit",
            "Transfer to vault",
            "from vault: savings",
            "Balance migration",
            "Revolut @username",
            "Crypto exchange",
            "Crypto purchase BTC",
            "Cryptocurrency swap",
        ],
    )
    def test_matches_internal(self, desc):
        assert _is_internal(desc), f"Expected internal: {desc!r}"

    @pytest.mark.parametrize(
        "desc",
        [
            "Amazon.it",
            "ESSELUNGA SPA",
            "Netflix.com",
            "Airbnb",
            "Uber *trip",
            "Decathlon store",
            "Spotify Premium",
            "ATM withdrawal",
            "Caffè Vergnano",
        ],
    )
    def test_does_not_match_real(self, desc):
        assert not _is_internal(desc), f"Incorrectly flagged as internal: {desc!r}"


class TestNormalize:
    def _tx(
        self,
        amount="25.50",
        currency="EUR",
        date="2024-01-15",
        indicator="DBIT",
        creditor="Coffee Shop",
        status="BOOK",
    ):
        return {
            "booking_date": date,
            "transaction_amount": {"amount": amount, "currency": currency},
            "credit_debit_indicator": indicator,
            "creditor": {"name": creditor} if indicator == "DBIT" else None,
            "debtor": {"name": creditor} if indicator == "CRDT" else None,
            "remittance_information": ["Dankort-køb", creditor],
            "status": status,
        }

    def test_debit_is_negative(self):
        txs = normalize([self._tx(indicator="DBIT")], "acc1", ecb_rates={})
        assert txs[0].amount == -25.50

    def test_credit_is_positive(self):
        txs = normalize([self._tx(indicator="CRDT")], "acc1", ecb_rates={})
        assert txs[0].amount == 25.50

    def test_basic(self):
        from datetime import datetime

        txs = normalize([self._tx()], "acc1", ecb_rates={})
        assert len(txs) == 1
        t = txs[0]
        assert t.currency == "EUR"
        assert t.eur_amount == -25.50
        assert t.booking_date == datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        assert t.account_id == "acc1"
        assert not t.is_internal
        assert len(t.dedup_hash) == 64
        assert t.status == "verified"
        assert t.source == "enable_banking"

    def test_skips_missing_date(self):
        raw = [{"transaction_amount": {"amount": "10", "currency": "EUR"}, "status": "BOOK"}]
        assert normalize(raw, "acc1", ecb_rates={}) == []

    def test_skips_pending(self):
        raw = [self._tx(status="PDNG")]
        assert normalize(raw, "acc1", ecb_rates={}) == []

    def test_skips_info(self):
        raw = [self._tx(status="INFO")]
        assert normalize(raw, "acc1", ecb_rates={}) == []

    def test_fx_conversion(self):
        raw = [self._tx(amount="108", currency="USD")]
        txs = normalize(raw, "acc1", ecb_rates={"USD": 1.08})
        assert abs(txs[0].eur_amount - (-100.0)) < 0.01

    def test_internal_flagged(self):
        # Real Revolut top-up: remittance_information starts with the marker
        raw = [
            {
                "booking_date": "2024-01-15",
                "transaction_amount": {"amount": "500", "currency": "EUR"},
                "credit_debit_indicator": "CRDT",
                "debtor": {"name": "My Bank"},
                "remittance_information": ["Top-Up by SEPA transfer"],
                "status": "BOOK",
            }
        ]
        txs = normalize(raw, "acc1", ecb_rates={})
        assert txs[0].is_internal

    def test_merchant_from_creditor(self):
        raw = [self._tx(creditor="STARBUCKS IT")]
        txs = normalize(raw, "acc1", ecb_rates={})
        assert txs[0].merchant_name == "STARBUCKS IT"

    def test_dedup_hash_idempotent(self):
        raw = [self._tx()]
        h1 = normalize(raw, "acc1", ecb_rates={})[0].dedup_hash
        h2 = normalize(raw, "acc1", ecb_rates={})[0].dedup_hash
        assert h1 == h2


class TestEcbCacheTtl:
    def _reset(self, mod):
        mod._ecb_cache.clear()
        mod._ecb_fetched_at = 0.0

    def test_fresh_cache_skips_refetch(self):
        import time
        from unittest.mock import patch

        import fintracker.normalizer.normalize as mod

        self._reset(mod)
        mod._ecb_cache.update({"USD": 1.1})
        mod._ecb_fetched_at = time.monotonic()
        with patch("fintracker.normalizer.normalize.httpx.get") as mock_get:
            rates = mod.fetch_ecb_rates()
        mock_get.assert_not_called()
        assert rates == {"USD": 1.1}
        self._reset(mod)

    def test_expired_cache_refetches_and_keeps_stale_on_failure(self):
        import time
        from unittest.mock import patch

        import fintracker.normalizer.normalize as mod

        self._reset(mod)
        mod._ecb_cache.update({"USD": 1.1})
        mod._ecb_fetched_at = time.monotonic() - mod._ECB_TTL_SECONDS - 1
        with patch(
            "fintracker.normalizer.normalize.httpx.get", side_effect=Exception("net down")
        ) as mock_get:
            rates = mod.fetch_ecb_rates()
        mock_get.assert_called_once()
        assert rates == {"USD": 1.1}
        self._reset(mod)
