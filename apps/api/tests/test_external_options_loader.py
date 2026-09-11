from __future__ import annotations

import csv

import pytest

from quantnifty.external_options_loader import load_option_csv


def write_csv(path, rows):
    headers = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_loads_one_minute_ce_pe_rows_into_existing_snapshot_contract(tmp_path):
    path = tmp_path / "nifty_options.csv"
    write_csv(
        path,
        [
            {"timestamp": "2026-08-04 09:15:00", "expiry_date": "2026-08-04", "strike": "24500", "option_type": "CE", "close": "120.5", "volume": "1000", "open_interest": "5000", "spot_price": "24480"},
            {"timestamp": "2026-08-04 09:15:00", "expiry_date": "2026-08-04", "strike": "24500", "option_type": "PE", "close": "135.0", "volume": "1100", "open_interest": "5200", "spot_price": "24480"},
            {"timestamp": "2026-08-04 09:16:00", "expiry_date": "2026-08-04", "strike": "24500", "option_type": "CE", "close": "124.0", "volume": "1200", "open_interest": "5100", "spot_price": "24490"},
            {"timestamp": "2026-08-04 09:16:00", "expiry_date": "2026-08-04", "strike": "24500", "option_type": "PE", "close": "131.5", "volume": "1300", "open_interest": "5250", "spot_price": "24490"},
        ],
    )

    snapshots = load_option_csv(path)

    assert len(snapshots) == 2
    assert snapshots[0]["data_integrity"] == "RECORDED_HISTORICAL"
    assert snapshots[0]["historical_snapshot"] is True
    assert snapshots[0]["spot"] == 24480.0
    assert snapshots[0]["expiry"] == "2026-08-04"
    assert {row["side"] for row in snapshots[0]["option_chain"]} == {"CE", "PE"}
    assert all(row["oi"] > 0 and row["volume"] > 0 for row in snapshots[0]["option_chain"])
    assert snapshots[0]["option_chain"][0]["last_price"] > 0


def test_retains_optional_bid_ask_without_inventing_greeks(tmp_path):
    path = tmp_path / "quotes.csv"
    write_csv(
        path,
        [
            {"datetime": "2026-08-04 09:15:00", "expiry": "2026-08-04", "strike_price": "24500", "right": "C", "ltp": "120", "volume": "100", "oi": "1000", "bid": "119.5", "ask": "120.5", "spot": "24480"},
            {"datetime": "2026-08-04 09:15:00", "expiry": "2026-08-04", "strike_price": "24500", "right": "P", "ltp": "135", "volume": "110", "oi": "1200", "bid": "134.5", "ask": "135.5", "spot": "24480"},
        ],
    )

    snapshots = load_option_csv(path)
    rows = snapshots[0]["option_chain"]

    assert {row["bid"] for row in rows} == {119.5, 134.5}
    assert {row["ask"] for row in rows} == {120.5, 135.5}
    assert all("delta" not in row and "gamma" not in row for row in rows)


def test_rejects_missing_spot_or_expiry(tmp_path):
    path = tmp_path / "invalid.csv"
    write_csv(
        path,
        [{"timestamp": "2026-08-04 09:15:00", "strike": "24500", "option_type": "CE", "close": "120", "volume": "100", "oi": "1000", "spot": "0"}],
    )

    with pytest.raises(ValueError, match="missing option expiry"):
        load_option_csv(path)
