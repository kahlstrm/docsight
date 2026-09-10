"""Regression tests for period error evidence, independent of modem lifetime totals."""

from app.modules.comparison.counters import period_counter_growth
from app.modules.comparison.routes import compare_periods
from unittest.mock import Mock
import pytest


def snapshot(hour, value, channels=None):
    return {"timestamp": f"2026-03-01T{hour:02d}:00:00Z",
            "summary": {"ds_correctable_errors": value, "ds_uncorrectable_errors": value},
            "ds_channels": channels or []}


@pytest.mark.parametrize("values, total, seconds", [
    ([55_800_000] * 16, 0, 15 * 3600),
    ([100, 110, 130], 30, 7200),
    ([100, 110, 3, 8], 15, 7200),
    ([100, None, 130], None, 0),
    ([100], None, 0),
    ([], None, 0),
])
def test_observed_increases(values, total, seconds):
    result = period_counter_growth([snapshot(i, value) for i, value in enumerate(values)])
    assert result["total"]["uncorr_errors"] == total
    assert result["observed_seconds"]["uncorr_errors"] == seconds
    assert result["errors_per_hour"]["uncorr_errors"] == (total * 3600 / seconds if seconds else None)


def test_order_and_duplicate_readings_do_not_change_growth():
    a, b = snapshot(0, 100), snapshot(1, 110)
    assert period_counter_growth([b, a, a]) == period_counter_growth([a, b])


def test_conflicting_timestamp_breaks_baseline():
    result = period_counter_growth([snapshot(0, 100), snapshot(1, 110), snapshot(1, 111), snapshot(2, 130)])
    assert result["total"]["uncorr_errors"] is None


def channel(id, value, frequency=500):
    return {"channel_id": id, "frequency": frequency, "uncorrectable_errors": value}


@pytest.mark.parametrize("after", [
    [channel(1, 10), channel(2, 300)],  # One reset masked by another channel's increase.
    [channel(1, 110)],
    [channel(1, 110, 501), channel(2, 110)],
    [channel(1, None), channel(2, 110)],
])
def test_resets_and_cohort_changes_are_unknown(after):
    result = period_counter_growth([snapshot(0, 200, [channel(1, 100), channel(2, 100)]),
                                    snapshot(1, 310, after)])
    assert result["total"]["uncorr_errors"] is None


def test_uncorrectable_only_channels_are_supported():
    result = period_counter_growth([snapshot(0, 100, [channel(1, 100)]),
                                    snapshot(1, 105, [channel(1, 105)])])
    assert result["total"] == {"corr_errors": None, "uncorr_errors": 5}


def test_verdict_compares_rates_in_unequal_windows():
    storage = Mock()
    storage.get_range_data.side_effect = [[snapshot(0, 100), snapshot(1, 120)],
                                          [snapshot(2, 200), snapshot(4, 240)]]
    result = compare_periods(storage, "2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04")
    assert result["delta"]["uncorr_errors"] == 20
    assert result["delta"]["uncorr_errors_per_hour"] == 0
    assert result["delta"]["verdict"] == "unchanged"


def test_report_preserves_insufficient_verdict_and_observation_duration():
    from app.modules.reports.report import _format_comparison_evidence
    storage = Mock()
    storage.get_range_data.side_effect = [[], [snapshot(0, 100), snapshot(1, 110)]]
    data = compare_periods(storage, "2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04")
    evidence = _format_comparison_evidence(data, {})
    assert 'Insufficient Data' in evidence
    assert 'Period A 0.0, Period B 1.0' in evidence
    assert 'per observed hour' in evidence


@pytest.mark.parametrize('value', [None, -1, True, 1.5, float('inf'), float('nan'), 'invalid'])
def test_invalid_channel_readings_do_not_become_observed_zeroes(value):
    result = period_counter_growth([snapshot(0, 100, [channel(1, 100)]),
                                    snapshot(1, 100, [channel(1, value)])])
    assert result['total']['uncorr_errors'] is None


def test_reset_interval_is_a_gap_in_the_chart():
    result = period_counter_growth([snapshot(0, 100), snapshot(1, 3), snapshot(2, 8)])
    assert list(result['samples'].values()) == [None, None, 5]


def test_missing_all_comparable_metrics_is_insufficient():
    storage = Mock()
    storage.get_range_data.side_effect = [[snapshot(0, None), snapshot(1, None)],
                                          [snapshot(2, None), snapshot(3, None)]]
    data = compare_periods(storage, '2026-03-01', '2026-03-02', '2026-03-03', '2026-03-04')
    assert data['delta']['verdict'] == 'insufficient_data'
