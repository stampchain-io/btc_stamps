# Operational alerting

The indexer emits structured alerts for incident patterns it detects but
cannot recover from autonomously (stuck rollback loops, critical failures,
silent hangs). Alerts are routed to AWS SNS — the topic ARN and subscriber
list are operator-managed and never committed to this repo.

## Configuration

| Env var | Default | Effect |
| --- | --- | --- |
| `OPS_ALERT_SNS_TOPIC_ARN` | unset | When set, alerts are published to this SNS topic. When unset, alerts are logged at WARNING level only — safe default for dev/CI. |
| `OPS_ALERT_DEDUP_WINDOW_SEC` | `3600` | Minimum interval between repeats of the same alert (by `dedup_key`). Prevents paging storms during sustained incidents. |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `us-east-1` | Region for the SNS client. |

The indexer process must have IAM permission `sns:Publish` on the
configured topic (the AWS credentials it already uses for S3 uploads,
QuickNode keys, etc.).

## What triggers an alert

| Detector | Fires when | Severity |
| --- | --- | --- |
| `CriticalFailureHandler` integration | Any `handle_critical_failure(...)` invocation: rollback-loop limit exceeded, consensus mismatch in non-FORCE mode, DB corruption, etc. — i.e. **before** the process exits. | critical |
| `StuckRollbackDetector` (early warning) | Same target block has been rolled back ≥3 times within 30 minutes. Catches the CP/BTC hash-divergence loop **before** the existing kill-the-process threshold trips. | critical |
| `ProgressWatchdog` | Main indexer loop hasn't ticked (no block processed) for ≥30 minutes. Catches the May-23 silent-hang pattern (process alive in `futex_wait_queue`, systemd reports active, but no log output). | critical |
| `fallback_monitor` session age | A Counterparty fallback session is open and the block being indexed is ≥ `CP_FALLBACK_ALERT_AFTER_BLOCKS` (default 6) blocks past the session start. Every block in the session lacks its stamp issuances until the recovery rollback runs (issue #957: a session stayed open for five weeks unnoticed). Repeats once per dedup window while the session is open. | critical |
| `fallback_monitor` session cap | The session reached `CP_FALLBACK_MAX_SESSION_BLOCKS` and the indexer halted rather than making the session unrecoverable by rollback. | critical |
| `fallback_monitor` CP behind tip | Counterparty answers health checks but has not served the tip block for ≥ `CP_BEHIND_ALERT_AFTER_SEC` (default 30 min). The indexer is waiting, not falling back. | critical |
| `fallback_monitor` startup | At startup the reprocessing queue holds a fallback session that is more than 1000 blocks behind the indexer. The startup rollback will refuse it and the indexer cannot start until an operator closes it with `tools/drain_fallback_queue.py`. | critical |
| `fallback_monitor` recovered | The recovery rollback ran and a fallback session was closed. | info |

## Adding a new alert

```python
from index_core.ops_alerter import notify

notify(
    severity="warning",          # critical | warning | info
    title="Short subject",       # included in SNS Subject (truncated to 100 chars)
    body="Multi-line detail",    # included in SNS Message
    dedup_key="stable-key",      # repeats suppressed within OPS_ALERT_DEDUP_WINDOW_SEC
)
```

`dedup_key` should encode the *thing* being alerted on, not the time —
e.g. `f"stuck-rollback-{target_block}"` not `f"alert-{time.time()}"`.
