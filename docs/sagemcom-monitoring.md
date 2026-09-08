# Sagemcom monitoring

The Sagemcom XMO driver exposes modem uptime through
`docsight_device_uptime_seconds` and recognized connection state through
`docsight_docsis_online`. The FAST3896 DNA firmware reports uptime at
`Device/DeviceInfo/UpTime` and connection state at
`Device/Docsis/CableModem/Status`. `OPERATIONAL` and `ONLINE` map to 1;
`FORWARDING_DISABLED` maps to 0. Other, missing or unsupported values do not
produce an online-status sample. Unknown is not offline.

Three separate signals describe availability:

- Prometheus `up`: the exporter can be scraped.
- `docsight_modem_poll_success`: the most recent completed modem poll succeeded.
  It starts at 0, changes on success/failure, and is unchanged by a skipped poll.
- `docsight_docsis_online`: the modem's reported DOCSIS connection state.

`docsight_last_poll_timestamp_seconds` is the time of the last successful modem
poll (0 before the first success), independent of retry scheduling. A failed or
skipped poll never advances it. Retained channel measurements and metadata may
still be exported after a failure; gate channel/connection alerts on recent
successful collection. A zero-channel read is rejected rather than labelled
healthy. When no usable channel data can be collected, report a collection
failure even if optional status metadata is available.

`docsight_downstream_snr_valid` is 1 when the channel has a usable SNR measurement
and 0 otherwise. The Sagemcom driver treats zero, negative, non-finite, missing
and malformed SNR as unavailable. This is a conservative validity policy, not a
claim that a zero firmware value means a physical 0 dB signal. The channel and
codeword counters remain visible, and analysis reports `snr warning (unavailable)`.
Unlocked rows remain excluded from the existing active-channel contract; this
release does not expose a separate channel-lock metric.

## Scrape credentials

New API tokens default to `metrics` scope. They work only on `/metrics`, including
when another endpoint has no authentication decorator. Create them through
Settings → Security, or POST `/api/tokens` with a browser session and
`{"name":"prometheus","scope":"metrics"}`. Enable `metrics_require_token` to
require a token for scraping; that option remains opt-in for compatibility.

General integrations must explicitly select `api` scope. Existing database
tokens migrate to `api` scope to preserve their access; they do not become
restricted scraper tokens automatically. Scope is shown in the settings table
and token-list API. Revoke old scrape tokens and replace them with metrics-only
tokens. Backup, restore and server-side backup browsing require session
authentication when an admin password is configured, including for general API
tokens. Initial setup without an admin password remains available.

Keep management access restricted and configure an admin password. A restricted
token cannot secure an application whose management routes intentionally allow
unauthenticated access. Avoid exposing the general application to the scrape
network when a proxy can allow only `GET /metrics`.

Start with a 60-second polling interval. For alerts, distinguish an unreachable
exporter, failing/stale collection, confirmed offline state and decreasing modem
uptime. A missing metric is not evidence of an offline modem. Tune alert duration
and history retention for the installation.
