import lzma
import struct
from datetime import datetime, timedelta, timezone

import pytest

from scripts.compare_dukascopy_ig_recent_spreads import decode_bi5_ticks, dukascopy_hour_url


def test_dukascopy_url_uses_zero_based_month():
    timestamp = datetime(2026, 7, 10, 20, tzinfo=timezone.utc)

    url = dukascopy_hour_url("USDJPY", timestamp)

    assert url.endswith("/USDJPY/2026/06/10/20h_ticks.bi5")


def test_decode_bi5_ticks_for_usdjpy_prices():
    hour = datetime(2026, 7, 10, 20, tzinfo=timezone.utc)
    raw = struct.pack(">IIIff", 1_500, 160_352, 160_342, 1.5, 2.5)
    content = lzma.compress(raw)

    ticks = decode_bi5_ticks(content, hour, "USDJPY")

    assert len(ticks) == 1
    row = ticks[0]
    assert row["timestamp_utc"] == hour + timedelta(milliseconds=1_500)
    assert row["symbol"] == "USDJPY"
    assert row["bid"] == pytest.approx(160.342)
    assert row["ask"] == pytest.approx(160.352)
    assert row["mid"] == pytest.approx(160.347)
    assert row["spread_pips"] == pytest.approx(1.0)
    assert row["bid_vol"] == pytest.approx(2.5)
    assert row["ask_vol"] == pytest.approx(1.5)
