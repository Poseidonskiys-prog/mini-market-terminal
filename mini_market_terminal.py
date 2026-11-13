#!/usr/bin/env python3
"""Mini Market Terminal: a curses market dashboard.

Standard library only. Run `python mini_market_terminal.py` for simulated prices,
or `python mini_market_terminal.py --live` for real prices (needs `pip install yfinance`).
On Windows, first run `pip install windows-curses`.
"""
import argparse
import curses
import json
import locale
import random
import threading
import time
import zlib
from collections import deque
from datetime import datetime
from pathlib import Path

N = 120  # points of history kept per symbol
BARS = "▁▂▃▄▅▆▇█"

# (symbol, name, base price, volatility per tick, yfinance ticker)
INDICES = [
    ("NIFTY", "Nifty 50", 24500, .0006, "^NSEI"),
    ("SENSEX", "BSE Sensex", 80500, .0006, "^BSESN"),
    ("SPX", "S&P 500", 5900, .0005, "^GSPC"),
    ("NDX", "Nasdaq 100", 20800, .0007, "^NDX"),
]
WATCH = [
    ("AAPL", "Apple", 228, .0012, "AAPL"),
    ("MSFT", "Microsoft", 425, .0010, "MSFT"),
    ("NVDA", "Nvidia", 140, .0020, "NVDA"),
    ("TSLA", "Tesla", 250, .0025, "TSLA"),
    ("RELIANCE", "Reliance Industries", 2900, .0010, "RELIANCE.NS"),
    ("TCS", "Tata Consultancy", 4100, .0009, "TCS.NS"),
    ("INFY", "Infosys", 1850, .0010, "INFY.NS"),
    ("HDFCBANK", "HDFC Bank", 1720, .0009, "HDFCBANK.NS"),
]
HELP = [
    "add SYM [price]  add a symbol (live mode: use the Yahoo ticker, e.g. TCS.NS)",
    "rm SYM           remove a watchlist symbol",
    "chart SYM        show a symbol in the chart (Tab also cycles)",
    "sort sym|px|chg|off   sort the watchlist",
    "pause / resume   stop or restart the feed",
    "quit             exit",
]


class Quote:
    def __init__(self, sym, name, base, vol, yf, index=False):
        self.sym, self.name, self.vol, self.yf, self.index = sym, name, vol, yf, index
        self.hist = deque(maxlen=N)
        self.prev = base
        rnd = random.Random(zlib.crc32(sym.encode()))
        self.volume = int(base * 1000 * (.5 + rnd.random()))
        if base:  # simulated history: seeded random walk ending at `base`
            v, raw = 1.0, []
            for _ in range(N):
                v *= 1 + rnd.gauss(0, 1) * vol * 1.6
                raw.append(v)
            k = base / raw[-1]
            self.hist.extend(x * k for x in raw)
        self.open = self.hist[0] if self.hist else 0

    @property
    def last(self):
        return self.hist[-1] if self.hist else 0.0

    @property
    def chg(self):
        return self.last / self.open - 1 if self.open else 0.0

    def push(self, price):
        if not self.hist:  # first live price: start a flat history from it
            self.hist.extend([price] * N)
            self.open = price
        self.prev = self.last
        self.hist.append(price)
        self.volume += random.randint(0, 400)


class Market:
    def __init__(self, live=False):
        self.live, self.prices, self.error = live, {}, None
        self.q = {}
        self.file = Path.home() / f".mini_market_{'live' if live else 'sim'}.json"
        for r in INDICES:
            self.q[r[0]] = self._make(*r, index=True)
        for r in self._load() or WATCH:
            self.q[r[0]] = self._make(*r)
        if live:
            threading.Thread(target=self._poll, daemon=True).start()

    def _make(self, sym, name, base, vol, yf, index=False):
        return Quote(sym, name, 0 if self.live else base, vol, yf, index)

    def watch(self):
        return [q for q in self.q.values() if not q.index]

    def _load(self):
        try:
            return [tuple(r) for r in json.loads(self.file.read_text())]
        except Exception:
            return None

    def save(self):
        try:
            rows = [[q.sym, q.name, round(q.last, 2) or 100, q.vol, q.yf] for q in self.watch()]
            self.file.write_text(json.dumps(rows))
        except OSError:
            pass

    def _poll(self):
        import yfinance as yf  # imported lazily so simulated mode needs nothing
        while True:
            for q in list(self.q.values()):
                try:
                    self.prices[q.yf] = float(yf.Ticker(q.yf).fast_info["last_price"])
                    self.error = None
                except Exception as e:  # network or unknown ticker
                    self.error = f"{q.yf}: {e}"
            time.sleep(10)

    def tick(self):
        for q in self.q.values():
            if self.live:
                p = self.prices.get(q.yf)
                if p:
                    q.push(p)
            else:
                q.push(q.last * (1 + random.gauss(0, 1) * q.vol))

    def add(self, sym, price=None):
        base = price or 50 + zlib.crc32(sym.encode()) % 45000 / 100
        self.q[sym] = self._make(sym, sym if self.live else f"{sym} (simulated)", base, .0015, sym)
        self.save()

    def remove(self, sym):
        del self.q[sym]
        self.save()


def fmt(x):
    return f"{x:,.2f}"


def pct(x):
    return f"{x * 100:+.2f}%"


def spark(q, n=14):
    h = list(q.hist)[-30:]
    if len(h) < 2:
        return ""
    pts = [h[int(i * (len(h) - 1) / (n - 1))] for i in range(n)]
    lo, d = min(pts), (max(pts) - min(pts)) or 1
    return "".join(BARS[int((p - lo) / d * 7)] for p in pts)


class State:
    def __init__(self):
        self.sel, self.sort, self.paused = "NIFTY", None, False
        self.buf, self.log, self.hist, self.hi = "", deque(maxlen=5), [], 0


def command(line, mkt, st):
    """Run one command; return False to quit."""
    cmd, *a = line.split()
    cmd = cmd.lower()
    log = st.log.append
    sym = a[0].upper() if a else ""
    if cmd in ("quit", "exit", "q"):
        return False
    if cmd == "help":
        for h in HELP:
            log(h)
    elif cmd == "add":
        if not sym or len(sym) > 14:
            log("Usage: add SYM [price]")
        elif sym in mkt.q:
            log(f"{sym} is already on screen. Use chart {sym}.")
        else:
            try:
                price = float(a[1]) if len(a) > 1 else None
            except ValueError:
                return log("Price must be a number.") or True
            mkt.add(sym, price)
            st.sel = sym
            log(f"Added {sym}." + (" Waiting for the first live price." if mkt.live else ""))
    elif cmd == "rm":
        if sym in mkt.q and not mkt.q[sym].index:
            mkt.remove(sym)
            st.sel = "NIFTY" if st.sel == sym else st.sel
            log(f"Removed {sym}.")
        else:
            log("Usage: rm SYM (watchlist symbols only)")
    elif cmd == "chart":
        if sym in mkt.q:
            st.sel = sym
        else:
            log(f"Unknown symbol {sym or ''}. Try add {sym or 'SYM'}.")
    elif cmd == "sort":
        k = (a[0].lower() if a else "")
        if k in ("sym", "px", "chg", "off"):
            st.sort = None if k == "off" else k
            log(f"Sorted by {st.sort or 'default order'}.")
        else:
            log("Usage: sort sym|px|chg|off")
    elif cmd in ("pause", "resume"):
        st.paused = cmd == "pause"
        log("Feed paused." if st.paused else "Feed resumed.")
    else:
        log(f'Unknown command "{cmd}". Type help.')
    return True


def put(scr, y, x, s, attr=0):
    h, w = scr.getmaxyx()
    if 0 <= y < h and 0 <= x < w - 1:
        try:
            scr.addstr(y, x, s[: w - x - 1], attr)
        except curses.error:
            pass


def col(v):
    return curses.color_pair(1 if v >= 0 else 2)


def draw(scr, mkt, st):
    scr.erase()
    h, w = scr.getmaxyx()
    if h < 20 or w < 80:
        put(scr, 0, 0, "Resize the terminal to at least 80x20.")
        return scr.refresh()
    gold = curses.color_pair(3) | curses.A_BOLD
    put(scr, 0, 1, "Mini Market Terminal", gold)
    put(scr, 0, 24, "live data" if mkt.live else "simulated data", curses.color_pair(3))
    if st.paused:
        put(scr, 0, 42, "paused", curses.A_BOLD)
    put(scr, 0, w - 10, datetime.now().strftime("%H:%M:%S"))
    # index strip
    idx = [q for q in mkt.q.values() if q.index]
    cw = w // max(1, len(idx))
    for i, q in enumerate(idx):
        x = i * cw + 1
        on = curses.A_UNDERLINE if q.sym == st.sel else 0
        put(scr, 1, x, q.name, curses.A_BOLD | on)
        put(scr, 2, x, fmt(q.last) if q.hist else "...")
        put(scr, 2, x + 11, pct(q.chg), col(q.chg))
    bottom = h - 9
    lw = 48
    # watchlist
    put(scr, 3, 1, f"{'Symbol':<10}{'Last':>12}{'Chg':>9}  Trend", curses.A_DIM)
    rows = mkt.watch()
    keys = {"sym": lambda q: q.sym, "px": lambda q: -q.last, "chg": lambda q: -q.chg}
    if st.sort:
        rows = sorted(rows, key=keys[st.sort])
    for i, q in enumerate(rows):
        y = 4 + i
        if y >= bottom:
            break
        mark = curses.A_REVERSE if q.sym == st.sel else 0
        put(scr, y, 1, f"{q.sym:<10}{fmt(q.last) if q.hist else '...':>12}", mark)
        put(scr, y, 23, f"{pct(q.chg):>9}", col(q.chg) | mark)
        put(scr, y, 34, spark(q), col(q.chg))
    for y in range(3, bottom + 1):
        put(scr, y, lw, "│", curses.A_DIM)
    # chart panel
    q, x0 = mkt.q[st.sel], lw + 2
    put(scr, 3, x0, f"{q.sym} · {q.name}", curses.A_BOLD)
    put(scr, 4, x0, fmt(q.last) if q.hist else "waiting for price...", curses.A_BOLD)
    put(scr, 4, x0 + 14, pct(q.chg), col(q.chg))
    cols, top, ch = w - x0 - 12, 6, bottom - 8
    if q.hist and cols >= 10 and ch >= 3:
        data = list(q.hist)
        lo, hi = min(data), max(data)
        pad = (hi - lo) * .1 or 1
        lo, hi = lo - pad, hi + pad
        for i in range(cols):
            v = data[int(i * (len(data) - 1) / (cols - 1))]
            r = int((v - lo) / (hi - lo) * (ch - 1) + .5)
            y = top + ch - 1 - r
            put(scr, y, x0 + 10 + i, "█", col(q.chg))
            for yy in range(y + 1, top + ch):
                put(scr, yy, x0 + 10 + i, "░", curses.A_DIM)
        for k in range(3):
            put(scr, top + k * (ch - 1) // 2, x0, f"{fmt(hi - (hi - lo) * k / 2):>9}", curses.A_DIM)
        s = f"Open {fmt(q.open)}   High {fmt(max(data))}   Low {fmt(min(data))}   Vol {q.volume:,}"
        put(scr, bottom, x0, s)
    # log and prompt
    put(scr, h - 8, 0, "─" * (w - 1), curses.A_DIM)
    for i, line in enumerate(st.log):
        put(scr, h - 7 + i, 1, line, curses.A_DIM)
    if mkt.error:
        put(scr, h - 2, 1, "feed: " + mkt.error, curses.color_pair(2))
    put(scr, h - 1, 0, "> " + st.buf, gold)
    scr.move(h - 1, min(2 + len(st.buf), w - 2))
    scr.refresh()


def run(scr, mkt):
    curses.start_color()
    curses.use_default_colors()
    for i, c in enumerate((curses.COLOR_GREEN, curses.COLOR_RED, curses.COLOR_YELLOW), 1):
        curses.init_pair(i, c, -1)
    scr.keypad(True)
    scr.timeout(200)
    st, last_tick = State(), 0.0
    st.log.append("Prices are " + ("live from Yahoo Finance." if mkt.live else "simulated, not real market data."))
    st.log.append("Type help for commands. Tab cycles the chart.")
    while True:
        if not st.paused and time.time() - last_tick >= 1:
            mkt.tick()
            last_tick = time.time()
        draw(scr, mkt, st)
        ch = scr.getch()
        if ch in (10, 13, curses.KEY_ENTER):
            line, st.buf = st.buf.strip(), ""
            if line:
                st.hist.append(line)
                st.hi = len(st.hist)
                st.log.append("> " + line)
                if not command(line, mkt, st):
                    return
        elif ch in (127, 8, curses.KEY_BACKSPACE):
            st.buf = st.buf[:-1]
        elif ch == curses.KEY_UP and st.hi > 0:
            st.hi -= 1
            st.buf = st.hist[st.hi]
        elif ch == curses.KEY_DOWN:
            st.hi = min(st.hi + 1, len(st.hist))
            st.buf = st.hist[st.hi] if st.hi < len(st.hist) else ""
        elif ch == 9:
            keys = list(mkt.q)
            st.sel = keys[(keys.index(st.sel) + 1) % len(keys)]
        elif 32 <= ch <= 126:
            st.buf += chr(ch)


def main():
    ap = argparse.ArgumentParser(description="Mini Market Terminal")
    ap.add_argument("--live", action="store_true", help="use real prices via yfinance")
    args = ap.parse_args()
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(run, Market(live=args.live))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
