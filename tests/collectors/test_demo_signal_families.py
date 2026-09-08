"""Tests for demo history signal-family trend fields."""

import pytest

from app.analyzer import _build_signal_family_summary
from app.collectors.demo import DemoCollector


def test_demo_historical_analysis_populates_signal_family_trend_keys():
    collector = object.__new__(DemoCollector)

    analysis = collector._generate_historical_analysis(
        index=1,
        diurnal=0.0,
        seasonal=0.0,
        bad_period=False,
        hour=12,
        day_of_year=120,
    )

    summary = analysis["summary"]
    families = summary["signal_families"]

    assert set(families["downstream"]["families"]) == {"sc_qam", "ofdm"}
    assert set(families["upstream"]["families"]) == {"sc_qam", "ofdma"}
    assert summary["ds_scqam_snr_avg"] is not None
    assert summary["ds_ofdm_mer_avg"] is not None
    assert summary["us_scqam_power_avg"] is not None
    assert summary["us_ofdma_power_avg"] is not None


@pytest.mark.parametrize("hour", [0, 4, 12, 20])
@pytest.mark.parametrize("bad_period", [False, True])
def test_demo_family_shortcut_matches_channel_classification(hour, bad_period):
    collector = object.__new__(DemoCollector)
    analysis = collector._generate_historical_analysis(
        index=123, diurnal=0.2, seasonal=-0.1,
        bad_period=bad_period, hour=hour, day_of_year=10,
    )

    assert analysis["summary"]["signal_families"] == _build_signal_family_summary(
        analysis["ds_channels"], analysis["us_channels"],
    )
    assert all("channel_family" not in ch for ch in analysis["ds_channels"] + analysis["us_channels"])
