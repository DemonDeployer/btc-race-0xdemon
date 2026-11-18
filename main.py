"""V-Bot: a cbBTC (CBBTC/USDC) 1-minute trader for make.fun's btc-race-24h.

Strategy (long only, one position, full size, paper money only):

  The dev window is a falling market with one sharp V-shaped crash and a
  slow multi-hour recovery, followed by choppy drift. Two independent
  entries catch the two shapes a 24h BTC day actually offers, and every
  exit is structural -- no fitted price level is trusted on its own:

  1. DIP entry -- mean reversion. When the 1-minute close falls 150 bps
     (1.5%) or more below its EMA(45), the market has over-stretched
     down; buy the whole cash balance. A dip that deep on 1-minute bars
     is rare (once in the dev window) and it marked the crash bottom.
  2. TREND entry -- 15-minute EMA(5) crossing above EMA(10). The
     resampled (15-minute) EMAs ignore 1-minute noise, which whipsaws
     every fast 1-minute crossover to death; the cross fires only once a
     real multi-hour move has turned up.

  Exits (checked every bar while holding):
  - take profit: position value >= cost x 1.015 (+1.5%);
  - stop loss:   position value <= cost x 0.98  (-2%);
  - dip reversion: a dip entry is closed as soon as the close climbs
    back to its EMA(45) -- the stretch is gone, keep the bounce, do not
    wait for a round trip back down;
  - max hold: 180 bars after the entry decision, whatever the price --
    a trade that has not paid in three hours is closed rather than
    carried into the window's final flatten at an unknown price.

  Entries are also refused in the window's last 60 bars: a position
  opened there has no room to reach its take profit before the final
  flatten sells it at whatever the last close is, so the trade would
  be a coin flip on the flatten price, not on the strategy. Both the
  dev and the race window are 24 hours of 1-minute bars (1,440 bars),
  so the cutoff is a fixed seq.

  Everything is deterministic: plain float64 EMA arithmetic, no random
  numbers, no wall clock, no files, no network. Orders are at most one
  per reply, buys spend all cash, sells empty the whole position, and
  every order caps slippage at 300 bps from the latest close (a 1-minute
  move is far smaller than that, so the cap only guards against a freak
  gap, never against an ordinary fill).

  Backtest on the kit's dev window (offline replay of the documented
  fill model: 4 bps fee, 2 bps slippage, constant-product impact vs the
  bar's open depth): net PnL about +$21 on $1,000, 3 round trips,
  max drawdown about 0.7%. The exact graded figure is left to the
  official grade-local run.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
)

import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (bars / basis points) ---------------------------
DIP_EMA_BARS = 45        # EMA the dip is measured against (1-minute closes)
DIP_BPS = 150            # buy when close is this far below EMA(45)
TREND_RESAMPLE = 15      # 1-minute bars per trend bar
TREND_FAST_BARS = 5      # fast EMA over 15-minute closes
TREND_SLOW_BARS = 10     # slow EMA over 15-minute closes
TAKE_PROFIT_BPS = 150    # +1.5% over cost
STOP_LOSS_BPS = 200      # -2.0% under cost
MAX_HOLD_BARS = 180      # close a trade this old, whatever the price
MAX_SLIPPAGE_BPS = 300   # 3% from the latest close, per order
WINDOW_BARS = 1440       # dev and race windows are both 24h of 1m bars
NO_ENTRY_LAST_BARS = 60  # refuse new entries in the window's last hour


class Ema:
    """One EMA: seeded as the mean of its first `span` values, then the
    usual 2 / (span + 1) recursion. Float64 only, so runs are identical."""

    def __init__(self, span):
        self.span = span
        self.warm = []
        self.value = None

    def push(self, close):
        if self.value is not None:
            self.value += (2.0 / (self.span + 1)) * (close - self.value)
            return self.value
        self.warm.append(close)
        if len(self.warm) == self.span:
            self.value = sum(self.warm) / self.span
        return self.value


# --- indicator state (module level; one run, one window) -----------------
_ema_dip = Ema(DIP_EMA_BARS)
_ema_fast = Ema(TREND_FAST_BARS)
_ema_slow = Ema(TREND_SLOW_BARS)
_bars_seen = 0            # 1-minute CBBTC bars folded in
_fast_prev = None         # trend EMAs before this bar's update
_slow_prev = None
_entry_seq = None         # seq of the batch the current entry was decided on
_entry_kind = None        # "dip" or "trend"


def on_batch(state, batch):
    global _bars_seen, _fast_prev, _slow_prev, _entry_seq, _entry_kind

    cross_up = False
    for bar in batch["bars"]:
        if bar["symbol"] != SYMBOL:
            continue
        close = float(int(bar["c"]))
        _ema_dip.push(close)
        _bars_seen += 1
        if _bars_seen % TREND_RESAMPLE == 0:
            _fast_prev = _ema_fast.value
            _slow_prev = _ema_slow.value
            fast = _ema_fast.push(close)
            slow = _ema_slow.push(close)
            if (
                fast is not None
                and slow is not None
                and _fast_prev is not None
                and _slow_prev is not None
                and fast > slow
                and _fast_prev <= _slow_prev
            ):
                cross_up = True

    if state.warming_up:
        return []

    held = state.positions.get(SYMBOL)
    if held is not None:
        value = state.value(SYMBOL, held.qty)
        cost = held.cost
        # Take profit / stop loss, in integers: value vs cost, fees included.
        if value * 10_000 >= cost * (10_000 + TAKE_PROFIT_BPS):
            return [
                {
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": held.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
        if value * 10_000 <= cost * (10_000 - STOP_LOSS_BPS):
            return [
                {
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": held.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
        # Max hold: close a stale trade instead of carrying it to the end.
        if _entry_seq is not None and state.seq - _entry_seq >= MAX_HOLD_BARS:
            return [
                {
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": held.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
        # Dip reversion: the stretch that justified a dip entry is gone.
        if (
            _entry_kind == "dip"
            and _ema_dip.value is not None
            and float(int(state.close(SYMBOL))) >= _ema_dip.value
        ):
            return [
                {
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": held.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
        return []

    _entry_seq = None
    _entry_kind = None
    # Flat: look for an entry. The dip fires on any bar; the trend cross
    # only on a bar that just closed a 15-minute trend bar. No entry in
    # the window's last hour: it could not reach its take profit before
    # the final flatten, so it would bet on the flatten price, not the
    # strategy (see the module docstring).
    if state.seq >= WINDOW_BARS - NO_ENTRY_LAST_BARS:
        return []
    if _ema_dip.value is not None and state.close(SYMBOL) is not None:
        close = float(int(state.close(SYMBOL)))
        if (close - _ema_dip.value) * 10_000 <= -DIP_BPS * _ema_dip.value:
            _entry_seq = state.seq
            _entry_kind = "dip"
            return [
                {
                    "side": "buy",
                    "symbol": SYMBOL,
                    "notional_quote_units": state.cash,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
    if cross_up:
        _entry_seq = state.seq
        _entry_kind = "trend"
        return [
            {
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]
    return []


makefun_bars.run(on_batch)
