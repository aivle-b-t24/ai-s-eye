from datetime import datetime, timedelta, timezone

import pytest

from app.cleanup_store_states import retention_cutoff


def test_retention_cutoff_uses_configured_days() -> None:
    now = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)

    cutoff = retention_cutoff(7, now)

    assert cutoff == now - timedelta(days=7)


def test_retention_cutoff_rejects_non_positive_days() -> None:
    with pytest.raises(ValueError):
        retention_cutoff(0)
