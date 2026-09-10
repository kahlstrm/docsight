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


def test_channel_rollover_preserves_growth_and_observation_time():
    readings = [snapshot(0, 4294967290, [channel(1, 4294967290)]),
                snapshot(1, 5, [channel(1, 5)]),
                snapshot(2, 8, [channel(1, 8)])]
    result = period_counter_growth(readings)
    assert result['total']['uncorr_errors'] == 14
    assert result['observed_seconds']['uncorr_errors'] == 7200
    assert list(result['samples'].values()) == [None, 11, 3]
    assert readings[1]['ds_channels'][0]['uncorrectable_errors'] == 5


@pytest.mark.parametrize('with_channels', [False, True])
def test_duplicate_counter_readings_ignore_signal_and_health_changes(with_channels):
    readings = [snapshot(i, 100 + i * 10, [channel(1, 100 + i * 10)] if with_channels else None)
                for i in range(3)]
    duplicate = {**readings[1], 'summary': {**readings[1]['summary'], 'health': 'marginal', 'ds_snr_avg': 30}}
    if with_channels:
        duplicate['ds_channels'] = [{**readings[1]['ds_channels'][0], 'snr': 30}]
    result = period_counter_growth([*readings, duplicate])
    assert result == period_counter_growth(readings)


@pytest.mark.parametrize('utc_stamp, local_stamp', [
    ('2026-09-09T21:00:00Z', '2026-09-10 00:00'),
    ('2026-01-09T22:00:00Z', '2026-01-10 00:00'),
    ('2026-03-29T00:30:00Z', '2026-03-29 02:30'),
    ('2026-03-29T01:30:00Z', '2026-03-29 04:30'),
])
def test_comparison_evidence_uses_selected_timezone(utc_stamp, local_stamp):
    from app.modules.reports.report import _format_comparison_evidence
    evidence = _format_comparison_evidence({
        'timezone': 'Europe/Helsinki',
        'period_a': {'from': utc_stamp, 'to': utc_stamp},
        'period_b': {'from': utc_stamp, 'to': utc_stamp},
    }, {})
    assert f'Compared {local_stamp} to {local_stamp} against {local_stamp} to {local_stamp}.' in evidence


@pytest.mark.parametrize('with_channels', [False, True])
@pytest.mark.parametrize('conflicting_field, affected, unaffected', [
    ('correctable_errors', 'corr_errors', 'uncorr_errors'),
    ('uncorrectable_errors', 'uncorr_errors', 'corr_errors'),
])
def test_duplicate_conflicts_only_interrupt_the_affected_counter(
    with_channels, conflicting_field, affected, unaffected,
):
    readings = [snapshot(i, 100 + i * 10) for i in range(4)]
    if with_channels:
        for i, reading in enumerate(readings):
            reading['ds_channels'] = [{
                **channel(1, 100 + i * 10), 'correctable_errors': 100 + i * 10,
            }]
    duplicate = {**readings[1], 'summary': {
        **readings[1]['summary'], 'ds_' + conflicting_field: 111,
    }}
    if with_channels:
        duplicate['ds_channels'] = [{
            **readings[1]['ds_channels'][0], conflicting_field: 111,
        }]

    result = period_counter_growth([*readings, duplicate])
    assert result['total'][unaffected] == 30
    assert result['observed_seconds'][unaffected] == 10800
    assert result['errors_per_hour'][unaffected] == 10
    assert result['total'][affected] == 10
    assert result['observed_seconds'][affected] == 3600
    assert result['errors_per_hour'][affected] == 10
    expected_samples = [None, 10, 10, 10] if unaffected == 'uncorr_errors' else [None, None, None, 10]
    assert list(result['samples'].values()) == expected_samples
    assert period_counter_growth([duplicate, *reversed(readings)]) == result
