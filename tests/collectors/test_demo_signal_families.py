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


def test_seeded_history_counters_are_cumulative_across_bad_windows(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from app.storage import SnapshotStorage
    from app.modules.comparison.counters import period_counter_growth

    monkeypatch.setattr('app.collectors.demo.DEMO_HISTORY_DAYS', 2)
    storage = SnapshotStorage(str(tmp_path / 'history.db'))
    collector = object.__new__(DemoCollector)
    collector._storage = storage
    collector._seed_history(datetime(2026, 1, 11, tzinfo=timezone.utc))
    snapshots = storage.get_range_data('2026-01-09T00:00:00Z', '2026-01-11T00:00:00Z')
    assert len(snapshots) == 192
    for before, after in zip(snapshots, snapshots[1:]):
        for a, b in zip(before['ds_channels'], after['ds_channels']):
            for field in ('correctable_errors', 'uncorrectable_errors'):
                assert b[field] >= a[field]
            if after['summary']['health'] == 'good':
                assert b['uncorrectable_errors'] == a['uncorrectable_errors']
    result = period_counter_growth(snapshots)
    assert result['observed_seconds']['uncorr_errors'] == 191 * 900
    assert result['total']['uncorr_errors'] == (
        snapshots[-1]['summary']['ds_uncorrectable_errors'] - snapshots[0]['summary']['ds_uncorrectable_errors']
    )
    collector._poll_count = 1
    monkeypatch.setattr('app.collectors.demo.random.random', lambda: 1)
    monkeypatch.setattr('app.collectors.demo.random.randint', lambda a, b: a)
    live = collector._generate_data()
    for ch in snapshots[-1]['ds_channels']:
        family = 'docsis30' if ch['docsis_version'] == '3.0' else 'docsis31'
        current = next(item for item in live['channelDs'][family] if item['channelID'] == ch['channel_id'])
        assert current['corrErrors'] == ch['correctable_errors']
        assert current['nonCorrErrors'] == ch['uncorrectable_errors']



def test_live_counters_preserve_growth_across_quiet_polls(monkeypatch):
    import copy
    from app.collectors.demo import _load_base_data
    from app.analyzer import analyze
    from app.modules.comparison.counters import period_counter_growth

    collector = DemoCollector(None, None, None, None, None, 300)
    original = copy.deepcopy(_load_base_data())
    snapshots = []
    for poll in range(4):
        active = poll in (0, 2)
        monkeypatch.setattr('app.collectors.demo.random.random', lambda: 0 if active else 1)
        monkeypatch.setattr('app.collectors.demo.random.randint', lambda a, b: b if active else a)
        collector._poll_count = poll + 1
        data = collector._generate_data()
        analysis = analyze(data)
        snapshots.append({**analysis, 'timestamp': f'2026-03-01T0{poll}:00:00Z'})

    for field, key in [('correctable_errors', 'corr_errors'), ('uncorrectable_errors', 'uncorr_errors')]:
        totals = [sum(ch[field] for ch in snapshot['ds_channels']) for snapshot in snapshots]
        assert totals[0] == totals[1] < totals[2] == totals[3]
        growth = period_counter_growth(snapshots)
        assert growth['total'][key] == totals[-1] - totals[0]
        assert growth['observed_seconds'][key] == 10800
    assert _load_base_data() == original
