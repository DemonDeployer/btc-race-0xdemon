# btc-race-0xdemon

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/DemonDeployer/btc-race-0xdemon/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/DemonDeployer/btc-race-0xdemon/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

V-Bot: a long-only cbBTC trader that buys sharp dips below EMA(45) and 15-minute EMA trend turns, and exits on take-profit, stop-loss, dip reversion, or a 180-bar max hold. Paper money only — no real funds are traded.

## Run it

```sh
python3 -P -s main.py
```

The bot speaks `agent-fun/bars-replay/v1` (NDJSON on stdin/stdout) using the kit's Python SDK shim, vendored byte-identical under `vendor/`. Standard library only, deterministic: no clock, no network, no files outside the repo.

---

<sub>Entered on [make.fun](https://make.fun/?ref=qamf9tkx&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
