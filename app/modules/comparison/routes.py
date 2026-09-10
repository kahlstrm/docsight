"""Before/After Comparison module routes."""

from app.runtime import current_runtime
from flask import Blueprint, jsonify, request

from app.aggregation import (
    ThresholdContext,
    Window,
    aggregate_snapshot_period,
)
from app.analyzer import threshold_snapshot
from app.web_auth import require_auth
from .counters import period_counter_growth

bp = Blueprint("comparison_module", __name__)


def _get_storage():
    return current_runtime().storage


def _comparison_view(aggregate, snapshots):
    """Map the shared aggregate to the established comparison response shape."""
    totals = aggregate["totals"]
    growth = period_counter_growth(snapshots)
    return {
        "snapshots": aggregate["snapshot_count"],
        "avg": {
            key: (round(value, 2) if value is not None else None)
            for key, value in aggregate["averages"].items()
        },
        "total": growth["total"],
        "observed_seconds": growth["observed_seconds"],
        "errors_per_hour": growth["errors_per_hour"],
        "errors_supported": totals["errors_supported"],
        "corr_errors_supported": totals["correctable_supported"],
        "uncorr_errors_supported": totals["uncorrectable_supported"],
        "health_distribution": aggregate["health_distribution"],
        "timeseries": [
            {**sample, "uncorr_errors": growth["samples"].get(sample["timestamp"])}
            for sample in aggregate["samples"]
        ],
    }


def _compute_delta(period_a, period_b):
    """Compute delta between two aggregated periods."""
    a_avg = period_a["avg"]
    b_avg = period_b["avg"]

    def diff(key):
        a_val = a_avg.get(key)
        b_val = b_avg.get(key)
        if a_val is None or b_val is None:
            return None
        return round(b_val - a_val, 2)

    ds_power_d = diff("ds_power")
    ds_snr_d = diff("ds_snr")
    us_power_d = diff("us_power")
    if period_a["total"].get("uncorr_errors") is not None and period_b["total"].get("uncorr_errors") is not None:
        uncorr_d = period_b["total"]["uncorr_errors"] - period_a["total"]["uncorr_errors"]
    else:
        uncorr_d = None

    a_rate = period_a["errors_per_hour"]["uncorr_errors"]
    b_rate = period_b["errors_per_hour"]["uncorr_errors"]
    rate_delta = b_rate - a_rate if a_rate is not None and b_rate is not None else None

    # Normalize error growth by observed time so unequal windows are comparable.
    score = 0
    if ds_snr_d is not None:
        if ds_snr_d > 1:
            score += 1
        elif ds_snr_d < -1:
            score -= 1
    if rate_delta is not None:
        if rate_delta > 10:
            score -= 1
        elif rate_delta < 0:
            score += 1

    enough_samples = all(len({sample["timestamp"] for sample in period["timeseries"]}) >= 2
                         for period in (period_a, period_b))
    if not enough_samples or (ds_snr_d is None and rate_delta is None):
        verdict = "insufficient_data"
    elif score > 0:
        verdict = "improved"
    elif score < 0:
        verdict = "degraded"
    else:
        verdict = "unchanged"

    return {
        "ds_power": ds_power_d,
        "ds_snr": ds_snr_d,
        "us_power": us_power_d,
        "uncorr_errors": uncorr_d,
        "uncorr_errors_per_hour": rate_delta,
        "verdict": verdict,
    }


def compare_periods(storage, from_a, to_a, from_b, to_b):
    """Load and compare two periods from snapshot storage."""
    snapshots_a = storage.get_range_data(from_a, to_a)
    snapshots_b = storage.get_range_data(from_b, to_b)

    thresholds = ThresholdContext.from_analyzer_snapshot(threshold_snapshot())
    aggregate_a = aggregate_snapshot_period(
        snapshots_a,
        window=Window(from_a, to_a),
        thresholds=thresholds,
    )
    aggregate_b = aggregate_snapshot_period(
        snapshots_b,
        window=Window(from_b, to_b),
        thresholds=thresholds,
    )
    period_a = _comparison_view(aggregate_a, snapshots_a)
    period_b = _comparison_view(aggregate_b, snapshots_b)
    period_a["from"] = from_a
    period_a["to"] = to_a
    period_b["from"] = from_b
    period_b["to"] = to_b

    return {
        "period_a": period_a,
        "period_b": period_b,
        "delta": _compute_delta(period_a, period_b),
    }


@bp.route("/api/comparison")
@require_auth
def api_compare():
    """Compare signal quality between two time periods."""
    from_a = request.args.get("from_a")
    to_a = request.args.get("to_a")
    from_b = request.args.get("from_b")
    to_b = request.args.get("to_b")

    if not all([from_a, to_a, from_b, to_b]):
        return jsonify({"error": "from_a, to_a, from_b, to_b required"}), 400

    storage = _get_storage()
    if not storage:
        return jsonify({"error": "storage not available"}), 503

    return jsonify(compare_periods(storage, from_a, to_a, from_b, to_b))
