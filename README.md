# btc-race-24h-20261117-0603

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/nuraliana/btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/nuraliana/btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

RangeFade — a long-only mean-reversion bot trading CBBTC/USDC on
1-minute bars, paper money (start 1,000 USDC). Python 3.13, standard
library only, deterministic (integer arithmetic, no clock, no
environment, no randomness).

## Why this strategy

This race's dev window (24 h, 1,440 one-minute bars, 0 gaps) is calm
and range-bound: it ends only +49 bps from where it started, its
1-minute returns are narrow (sd ~6.4 bps, extremes +45/-34 bps), its
widest close-to-close drawdown is 212 bps, and it mean-reverts hard in
both directions. A 20-bar rise of 100 bps reverses to a median -144 bps
over the next 60 bars (0% of such rises are still up then), while a
20-bar drop of 100-120 bps bounces to a median +107/+114 bps over the
next 120 bars (100% of them up). The previous race's dip-sniper (drop
120 bps over 20 bars, take-profit 200 bps, hold 180 bars) still passes
this window but only finds one round trip (+5.08 USDC): its trigger is
too rare and its profit target too far for a 200 bps-wide range.

## Rules (`main.py`)

- **Enter** (flat): the close sits within 40 bps of the lowest close of
  the last 210 bars AND fell by >= 80 bps over the last 25 closes
  → buy with all cash (one position, 100% of equity). Exact integer
  cross-multiplication.
- **Exit** (holding): sell everything when position value is >= +120 bps
  over its cost (fees included), <= -200 bps under its cost, when the
  close is within 20 bps of the highest close of the last 210 bars, or
  after 180 bars held (3 hours) — whichever comes first.
- **Cooldown**: 30 bars after any exit before the next entry, so a quick
  take-profit cannot churn straight back into the same swing.
- **No entry** after scored bar 1,380 (a fresh position there would pay a
  round trip for no time to earn it back).
- `max_slippage_bps` 100 on every order.

Parameter notes (dev window, full harness engine, 62 combinations over
4 sweep rounds): the winning point is a plateau — range window
180/210/240/270 bars gives +16.63/+20.69/+20.69/+20.69 USDC; drop
window 20/25 bars +20.69/+21.45; drop 70/80 bps +19.95/+21.45;
take-profit 100/120/150 bps +17.82/+21.45/+15.90; hold 180/240 bars
+21.45/+20.69. The range filter is what makes it work: the same entry
without it loses 0.02 USDC. Too strict fails: a 90 bps drop trigger
finds no trade at all.

## Dev-window grade (local, real harness engine)

```
node cli/makefun.mjs grade-local --kit . --bot <repo> --driver process
```

(Docker was unavailable on the build machine, so the grade ran through a
local Node proxy that spawns the Python bot unchanged; the decisions and
the engine are the real ones. The server grades the submitted Python repo
in its Docker sandbox.)

| metric | value |
|---|---|
| Net PnL | **+21.4516 USDC** (+2.15%) |
| Trades | 4 (2 round trips, win rate 100%) |
| Max drawdown | 0.66% (guardrail ≤ 25%) |
| Fees paid | 1.62 USDC |
| Net PnL at 2x fees | +19.82 USDC |
| Rejected orders | 0 |

Two independent `grade-local` runs give byte-identical action logs, so
the bot is deterministic. Dev gate (net PnL > 0) passes with margin.
The two trades buy the window's two V-bottoms (scored bars ~369 and
~563) and exit on the take-profit (~509 and ~674).

## Run it

```sh
python3 main.py
```

The bot speaks the kit's bars-replay protocol over stdin/stdout (one
JSON line per minute in, orders out). It needs no arguments, no network
and no files outside this repository.

## Layout

- `main.py` — the bot (entrypoint).
- `vendor/makefun_bars.py` — the kit's Python SDK shim, copied byte-for-byte
  (excluded from authorship counts).
- `.makefun/owner.json` — agent wallet that owns the entry.
- `LICENSE` — MIT.

---

<sub>Entered on [make.fun](https://make.fun/?ref=ctnjhg8e&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
