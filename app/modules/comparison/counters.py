"""Observed counter growth within a comparison window, excluding reset intervals."""

from datetime import datetime
from itertools import groupby
from math import isfinite

from app.aggregation.window import canonical_utc_timestamp
from app.error_counters import observed_counter_increase, observed_counter_values


def _summary_counter(snapshot, field):
    summary = snapshot.get("summary") or {}
    value = summary.get("ds_" + field)
    if summary.get("errors_supported") is False or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if isfinite(number) and number >= 0 and number.is_integer() else None


def _increase(previous, current, field):
    if any((snapshot.get("summary") or {}).get("errors_supported") is False
           for snapshot in (previous, current)):
        return None
    before, after = previous.get("ds_channels"), current.get("ds_channels")
    if before or after:
        return observed_counter_increase(before or [], after or [], field)
    # Older snapshots may contain only aggregate counters.
    a, b = _summary_counter(previous, field), _summary_counter(current, field)
    return b - a if a is not None and b is not None and b >= a else None


def _counter_projection(snapshot):
    summary = snapshot.get("summary") or {}
    if summary.get("errors_supported") is False:
        return None
    channels = snapshot.get("ds_channels")
    fields = ("correctable_errors", "uncorrectable_errors")
    if channels:
        return tuple(observed_counter_values(channels, field) for field in fields)
    return tuple(_summary_counter(snapshot, field) for field in fields)


def period_counter_growth(snapshots):
    def timestamp(snapshot):
        return canonical_utc_timestamp(snapshot.get("timestamp"))

    totals = {"corr_errors": None, "uncorr_errors": None}
    seconds = dict.fromkeys(totals, 0)
    samples = {}
    previous = None
    previous_time = None
    for stamp, group in groupby(sorted(snapshots, key=timestamp), key=timestamp):
        readings = list(group)
        current = readings[0]
        # Conflicting readings at the same instant cannot establish a baseline.
        if any(_counter_projection(reading) != _counter_projection(current)
               for reading in readings[1:]):
            previous = None
            samples[stamp] = None
            continue
        try:
            time = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            previous = None
            samples[stamp] = None
            continue
        samples[stamp] = None
        if previous is not None:
            elapsed = (time - previous_time).total_seconds()
            for key, field in (("corr_errors", "correctable_errors"),
                               ("uncorr_errors", "uncorrectable_errors")):
                increase = _increase(previous, current, field)
                if increase is not None and elapsed > 0:
                    totals[key] = (totals[key] or 0) + increase
                    seconds[key] += elapsed
                    if key == "uncorr_errors":
                        samples[stamp] = increase
        previous, previous_time = current, time
    rates = {key: total * 3600 / seconds[key] if seconds[key] else None
             for key, total in totals.items()}
    return {"total": totals, "observed_seconds": seconds, "errors_per_hour": rates,
            "samples": samples}
