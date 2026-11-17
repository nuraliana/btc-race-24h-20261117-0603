"""RangeFade: a long-only mean-reversion bot for the make.fun BTC race
btc-race-24h-20261117-0603.

What this race's dev window taught us
--------------------------------------
This race's dev window (24 h, 1,440 one-minute bars of CBBTC/USDC, 0 gaps)
is calm and range-bound, unlike the falling window of the previous race:
it ends only +49 bps from where it started, its 1-minute returns are
narrow (sd ~6.4 bps, extremes +45/-34 bps), its widest close-to-close
drawdown is 212 bps, and it mean-reverts hard in both directions. A
20-bar rise of 100 bps reverses to a median -144 bps over the next 60
bars (0% of such rises are still up then), while a 20-bar drop of 100-120
bps bounces to a median +107/+114 bps over the next 120 bars (100% of
them up). The previous race's dip-sniper (drop 120 bps over 20 bars,
take-profit 200 bps, hold 180 bars) still passes this window but only
finds one round trip (+5.08 USDC): its trigger is too rare and its
profit target too far for a 200 bps-wide range.

So this bot fades the range instead of chasing one deep dip:

  * It buys only near the bottom of the range: the close must sit
    within LOW_BAND_BPS of the lowest close of the last RANGE_WIN bars
    AND have fallen at least DROP_BPS over the last DROP_WIN bars, so a
    small pullback in the middle of the range does not trigger it.
    A 210-bar range (3.5 hours) works best: it is the market's own
    swing length here, so the rolling low is a real swing low rather
    than a 2-hour wobble, and a 25-bar drop window waits for the slide
    to finish instead of catching the knife mid-fall.
  * It sells back near the top of the range: the close within
    HIGH_BAND_BPS of the highest close of the last RANGE_WIN bars is an
    exit, because rises here reverse within the hour. A take-profit
    (+TP_BPS over cost) and a stop-loss (-SL_BPS) bound the same trade,
    and a maximum hold (MAX_HOLD_BARS) closes it if the range never
    gives the exit back. On this window both winning trades exit on
    the take-profit, not on the range-top exit: the tighter 20 bps
    top band lets the bounce run to +120 bps instead of cutting it
    at the first touch of the old high.
  * After any exit it waits COOLDOWN_BARS before the next entry, so a
    quick take-profit cannot churn straight back into the same swing
    and pay the ~26 bps round-trip cost twice for one move.
  * It never enters after scored bar 1380: a fresh position there would
    pay a round trip for no time to earn it back.

Costs: a full-size round trip costs ~26 bps (4 bps fee + 2 bps slippage
+ ~7 bps impact per side), so the bot only trades when the move it
fades is several times that cost. All decisions use exact integer
cross-multiplication on integer closes: no floats, no clock, no
environment, no randomness -- two runs give byte-identical orders.

Verified grade of THIS file (grade-local, new kit, process driver):
net PnL +21.451566 USDC (+2.15%), 4 trades (2 round trips, win rate
100%), max drawdown 0.66% (limit 25%), fees 1.617071 USDC, net PnL at
2x fees +19.821219 USDC, 0 rejected orders. The two trades buy the
window's two V-bottoms (scored bars ~369 and ~563) and exit on the
take-profit (~509 and ~674). Dev gate (net PnL > 0) passes with margin.

Robustness (grade-local on the new dev window, full harness engine,
62 parameter combinations across 4 sweep rounds): the winning point is
a plateau, not a spike -- every neighbour is also positive: range
window 180/210/240/270 bars gives +16.63/+20.69/+20.69/+20.69 USDC;
drop window 20/25 bars gives +20.69/+21.45; drop 70/80 bps gives
+19.95/+21.45; take-profit 100/120/150 bps gives +17.82/+21.45/+15.90;
hold 180/240 bars gives +21.45/+20.69; low band 40/60 bps gives
+21.45/+20.16; stop-loss 150/200 bps gives +20.69/+21.45. The range
filter is what makes it work: the same entry without it (RANGE_ON=0)
loses 0.02 USDC, and a 90-bar range window halves the result. Too
strict is the only failure mode nearby: a 90 bps drop trigger or a
30 bps low band finds one trade or none.

Security note (agentic-bug-hunter 7-question gate): this bot runs in the
grader's sandbox with no network, no secrets, no user data and no
writes outside its own reply; there is no attacker, no real user and no
real money it could harm, so there is no finding to report.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"
RANGE_WIN = 210          # bars of the rolling range (low/high)
RANGE_ON = 1             # 1: entry needs near-low + exit on near-high; 0: dip-only
LOW_BAND_BPS = 40        # enter when close within 40 bps above rolling low
DROP_WIN = 25            # bars over which the entry drop is measured
DROP_BPS = 80            # enter when the close fell >= 80 bps
TAKE_PROFIT_BPS = 120    # exit: position value >= cost + 120 bps
HIGH_BAND_BPS = 20       # exit when close within 20 bps below rolling high
STOP_LOSS_BPS = 200      # exit: position value <= cost - 200 bps
MAX_HOLD_BARS = 180      # exit: sell after 180 bars held (3 hours)
COOLDOWN_BARS = 30       # bars to wait after an exit before re-entering
ENTRY_CUTOFF_BAR = 1380  # scored-window bars after which no new entry
MAX_SLIPPAGE_BPS = 100   # bound on the move from the latest close
MIN_CASH_QUOTE_UNITS = 1_000_000  # 1 USDC, in quote units


def _sell_all(held_qty):
    """One order: sell the whole position, slippage-bounded."""
    return [{"side": "sell", "symbol": SYMBOL, "qty": held_qty,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def _buy_all(cash):
    """One order: buy with all cash, slippage-bounded."""
    return [{"side": "buy", "symbol": SYMBOL,
             "notional_quote_units": cash,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


class RangeFade:
    """Keeps the close history, the entry bar and the last exit bar.

    The SDK state only remembers the latest bar, so the bot tracks its
    own closes (oldest first), the batch sequence where the position
    first appeared, and the sequence of the last exit for the cooldown.
    """

    def __init__(self):
        self.closes = []
        self.entry_seq = None
        self.last_exit_seq = None

    def note_bar(self, state):
        bar = state.latest.get(SYMBOL)
        if bar is not None:
            self.closes.append(int(bar["c"]))

    def _range(self):
        """(low, high) of the last RANGE_WIN closes, or None if too few."""
        if len(self.closes) < RANGE_WIN + 1:
            return None
        window = self.closes[-RANGE_WIN:]
        return min(window), max(window)

    def dropped_enough(self):
        """True when the close fell >= DROP_BPS over DROP_WIN bars."""
        if len(self.closes) < DROP_WIN + 1:
            return False
        now = self.closes[-1]
        then = self.closes[-1 - DROP_WIN]
        return now * 10_000 <= then * (10_000 - DROP_BPS)

    def near_low(self):
        """True when the close is within LOW_BAND_BPS of the rolling low."""
        r = self._range()
        if r is None:
            return False
        low, _high = r
        return self.closes[-1] * 10_000 <= low * (10_000 + LOW_BAND_BPS)

    def near_high(self):
        """True when the close is within HIGH_BAND_BPS of the rolling high."""
        r = self._range()
        if r is None:
            return False
        _low, high = r
        return self.closes[-1] * 10_000 >= high * (10_000 - HIGH_BAND_BPS)

    def exit_order(self, state, held):
        """Sell order if any exit fires, else None.

        Take-profit and stop-loss compare the marked value against the
        position cost with exact integer arithmetic; the time exit counts
        bars held since the fill, not since the decision.
        """
        if self.entry_seq is None:
            self.entry_seq = state.seq
        value = state.value(SYMBOL, held.qty)
        cost = held.cost
        if value * 10_000 >= cost * (10_000 + TAKE_PROFIT_BPS):
            return _sell_all(held.qty)
        if value * 10_000 <= cost * (10_000 - STOP_LOSS_BPS):
            return _sell_all(held.qty)
        if RANGE_ON and self.near_high():
            return _sell_all(held.qty)
        if state.seq - self.entry_seq >= MAX_HOLD_BARS:
            return _sell_all(held.qty)
        return None

    def on_batch(self, state, batch):
        self.note_bar(state)
        if state.warming_up:
            return []

        held = state.positions.get(SYMBOL)
        if held is not None:
            order = self.exit_order(state, held)
            if order is not None:
                self.entry_seq = None
                self.last_exit_seq = state.seq
                return order
            return []

        self.entry_seq = None
        if state.seq - state.warmup_bars > ENTRY_CUTOFF_BAR:
            return []
        if (self.last_exit_seq is not None
                and state.seq - self.last_exit_seq < COOLDOWN_BARS):
            return []
        if not self.dropped_enough():
            return []
        if RANGE_ON and not self.near_low():
            return []
        if state.cash >= MIN_CASH_QUOTE_UNITS:
            return _buy_all(state.cash)
        return []


makefun_bars.run(RangeFade().on_batch)
