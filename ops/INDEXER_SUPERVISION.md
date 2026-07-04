# Indexer supervision

The `btc-stamps-indexer.service` systemd unit owns and supervises the
`poetry run indexer` process. It replaces the previous workflow of running
the indexer manually inside a tmux session — which had the side-effect
that closing or losing the tmux session killed the indexer with no
automatic restart. Under systemd, the indexer is restarted automatically
on crash and on host reboot, and the tmux session becomes a purely
read-only log viewer.

This directory contains the unit file, the `indexer-logs` companion
script, and this runbook.

```
ops/
├── INDEXER_SUPERVISION.md           ← you are here
├── systemd/
│   └── btc-stamps-indexer.service   ← systemd unit (owns the process)
└── bin/
    └── indexer-logs                 ← tmux + journalctl log viewer
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ systemd (PID 1)                                                  │
│   └─ btc-stamps-indexer.service                                  │
│        └─ /home/ubuntu/.local/bin/poetry run indexer  ← actual   │
│             └─ Python: index_core.server etc.            process │
│                                                                  │
│   logs → journald                                                │
└────────────────────────────────────────┬─────────────────────────┘
                                         │
                                         ▼
                         (read-only)
                ┌────────────────────────────┐
                │ indexer-logs (tmux session)│
                │   journalctl -u … -f       │
                └────────────────────────────┘
                  attach/detach freely;
                  closing it does NOT stop the indexer
```

## Initial install — one-time cutover

> **Important:** the indexer is currently running inside a manual tmux
> session named `indexer`. That manual process must be stopped first,
> otherwise both the old manual indexer and the new systemd-supervised
> indexer would compete for the same DB pool slots.

```bash
# 1. Copy the unit file + helper script into place
sudo cp ops/systemd/btc-stamps-indexer.service /etc/systemd/system/
sudo cp ops/bin/indexer-logs                  /usr/local/bin/
sudo chmod +x /usr/local/bin/indexer-logs

# 2. Tell systemd about the new unit
sudo systemctl daemon-reload

# 3. Stop the manual tmux indexer (one-time cutover) — graceful: lets the
#    indexer flush uploads and close cleanly before the next process takes
#    over.
tmux send-keys -t indexer C-c
# wait a few seconds for clean shutdown messages, then:
tmux kill-session -t indexer

# 4. Enable + start the systemd-supervised indexer
sudo systemctl enable --now btc-stamps-indexer

# 5. Verify it's running and tail the logs
sudo systemctl status btc-stamps-indexer       # expect: active (running)
indexer-logs                                    # opens tmux log viewer
#  Inside the tmux session: Ctrl-b d to detach (indexer keeps running)
```

## Branch switch protocol

The systemd unit's `WorkingDirectory` is `/home/ubuntu/btc_stamps/indexer`
— it always runs whatever branch is checked out. To switch:

```bash
sudo systemctl stop btc-stamps-indexer
cd /home/ubuntu/btc_stamps
git checkout <branch>     # e.g., dev, main, fix/foo
git pull
cd indexer
poetry install            # rebuild .venv if dependencies changed
sudo systemctl start btc-stamps-indexer
indexer-logs              # tail the new run
```

## Daily operations

```bash
# Live log tail (attach to tmux session)
indexer-logs

# Historical
journalctl -u btc-stamps-indexer --since '1 hour ago'
journalctl -u btc-stamps-indexer --since '2026-05-19 23:00' --until '2026-05-19 23:30'

# Status
sudo systemctl status btc-stamps-indexer

# Manual restart
sudo systemctl restart btc-stamps-indexer

# Stop (e.g. for maintenance)
sudo systemctl stop btc-stamps-indexer
sudo systemctl start btc-stamps-indexer

# After a restart-burst lockout (StartLimitBurst exceeded)
sudo systemctl reset-failed btc-stamps-indexer
sudo systemctl start btc-stamps-indexer
```

## Restart semantics

| Setting | Value | Effect |
|---|---|---|
| `Restart` | `always` | Restarts on ANY exit (clean exit, crash, OOM, signal). |
| `RestartSec` | `30s` | Wait 30s after exit before restarting. Lets transient issues clear. |
| `StartLimitBurst` | `5` | At most 5 restarts within `StartLimitIntervalSec`. |
| `StartLimitIntervalSec` | `300s` | The 5-restart window. |
| `KillSignal` | `SIGTERM` | Graceful shutdown signal — indexer catches via `server.shutdown_flag`. |
| `TimeoutStopSec` | `120s` | If cleanup hangs past 120s, SIGKILL. |

If the indexer crashes 5 times in 5 minutes, systemd marks the unit as
failed and stops restarting. Use `systemctl reset-failed` to clear after
fixing the underlying cause.

## Troubleshooting

**Unit fails to start, status shows `failed`:**

```bash
journalctl -u btc-stamps-indexer --since '10 min ago' | tail -50
```
Look for Python tracebacks, missing env vars, DB connect errors. The
indexer's first ~30 seconds of startup logs are usually the diagnostic.

**Restart loop / circuit-breaker tripped:**

```bash
systemctl status btc-stamps-indexer
# look for: "start request repeated too quickly" / "scheduled restart job failed"
sudo systemctl reset-failed btc-stamps-indexer
sudo systemctl start btc-stamps-indexer
indexer-logs    # observe what fails on the next attempt
```

**Long graceful shutdown — adjusting `TimeoutStopSec`:**

If `systemctl stop` consistently times out and SIGKILLs the indexer, the
async upload worker (or some other cleanup path) needs more than 120s to
drain. Measure with:

```bash
time sudo systemctl stop btc-stamps-indexer
```

If you observe `real > 120s`, edit
`/etc/systemd/system/btc-stamps-indexer.service`, raise `TimeoutStopSec`,
then `sudo systemctl daemon-reload`. Update this file in the repo to
match.

**Reverting to manual tmux operation (emergency):**

```bash
sudo systemctl disable --now btc-stamps-indexer
cd /home/ubuntu/btc_stamps/indexer
tmux new-session -d -s indexer 'poetry run indexer 2>&1 | tee -a /tmp/indexer.log'
tmux attach -t indexer
```

## Notifications (deferred)

The unit file contains a commented `OnFailure=btc-stamps-indexer-alert.service`
hook for future telegram-bot notification. To enable when ready:

1. Write the alert sender (small bash one-liner using `curl` to
   `https://api.telegram.org/bot<token>/sendMessage`).
2. Create `/etc/systemd/system/btc-stamps-indexer-alert.service` as a
   `Type=oneshot` that invokes the sender.
3. Uncomment the `OnFailure=` line in the indexer unit.
4. `sudo systemctl daemon-reload`.

This is out of scope for the initial supervision PR.

## What this design intentionally does NOT include

- **Auto-pull on branch change.** Branch switches stay manual (stop, git,
  install, start) — unattended `git pull` on a running production indexer
  is unsafe.
- **Health check endpoint / HTTP probe.** The indexer has no health
  endpoint today. Could be added as a separate observability PR.
- **Container deployment.** Counterparty and bitcoind already run in
  containers on this host, but the indexer itself runs against the local
  Python venv. systemd is simpler than containerizing for this use case;
  branch switches don't require image rebuilds.
