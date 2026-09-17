from __future__ import annotations

from pathlib import Path

from quantnifty import learning_store


def test_filesystem_paper_trade_lock_is_exclusive(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(learning_store, "_database_url", lambda: "")
    monkeypatch.setattr(learning_store, "_root", lambda: tmp_path)
    assert learning_store.claim_paper_trade_lock("2026-09-17", "T1") is True
    assert learning_store.claim_paper_trade_lock("2026-09-17", "T2") is False
    assert learning_store.release_paper_trade_lock("2026-09-17", "T2") is False
    assert learning_store.release_paper_trade_lock("2026-09-17", "T1") is True
    assert learning_store.claim_paper_trade_lock("2026-09-17", "T2") is True


def test_stale_filesystem_lock_can_be_reconciled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(learning_store, "_database_url", lambda: "")
    monkeypatch.setattr(learning_store, "_root", lambda: tmp_path)
    assert learning_store.claim_paper_trade_lock("2026-09-17", "T1") is True
    learning_store.reconcile_paper_trade_lock("2026-09-17", set())
    assert learning_store.claim_paper_trade_lock("2026-09-17", "T2") is True
