from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from fintracker.ingestion import fetch_transactions as ft


def _patch_get(monkeypatch, payload):
    monkeypatch.setattr(ft, "_get", lambda client, path, **params: payload)


def test_prefers_closing_booked_balance(monkeypatch):
    _patch_get(
        monkeypatch,
        {
            "balances": [
                {"balance_type": "ITAV", "balance_amount": {"currency": "EUR", "amount": "10.00"}},
                {"balance_type": "CLBD", "balance_amount": {"currency": "EUR", "amount": "42.50"}},
            ]
        },
    )
    assert ft.fetch_balances(MagicMock(), "acc-1") == Decimal("42.50")


def test_falls_back_to_first_balance(monkeypatch):
    _patch_get(
        monkeypatch,
        {
            "balances": [
                {"balance_type": "ITAV", "balance_amount": {"currency": "EUR", "amount": "7.10"}}
            ]
        },
    )
    assert ft.fetch_balances(MagicMock(), "acc-1") == Decimal("7.10")


def test_warns_on_non_eur_currency(monkeypatch, caplog):
    _patch_get(
        monkeypatch,
        {
            "balances": [
                {"balance_type": "CLBD", "balance_amount": {"currency": "USD", "amount": "5.00"}}
            ]
        },
    )
    with caplog.at_level("WARNING"):
        assert ft.fetch_balances(MagicMock(), "acc-1") == Decimal("5.00")
    assert "USD" in caplog.text


def test_empty_balances_raises(monkeypatch):
    _patch_get(monkeypatch, {"balances": []})
    with pytest.raises(ValueError):
        ft.fetch_balances(MagicMock(), "acc-1")
