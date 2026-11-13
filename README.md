# Mini Market Terminal

A small Bloomberg-style market dashboard, built twice: as a Python terminal app and as a single-file web app.

- **Terminal app** (`mini_market_terminal.py`): Python and `curses`, standard library only.
- **Web app** (`docs/index.html`): vanilla HTML, CSS and JavaScript. Live demo: https://YOUR-USERNAME.github.io/mini-market-terminal/

> By default, prices are **simulated** with a seeded random walk. They are not real market data.

## Features

- Watchlist with last price, change and sparklines, updating every second
- Index strip: Nifty 50, Sensex, S&P 500, Nasdaq 100
- Area chart for the selected symbol, with open, high, low and volume
- Command line: `add`, `rm`, `chart`, `sort`, `pause`, `resume`, `help`, `quit`
- Watchlist saved between sessions
- Optional real prices from Yahoo Finance with `--live`

## Run the terminal app

```bash
python mini_market_terminal.py          # simulated prices, no installs
pip install -r requirements.txt
python mini_market_terminal.py --live   # real prices via yfinance
```

Needs Python 3.8+ and a terminal of at least 80x20. On Windows, `pip install -r requirements.txt` also installs `windows-curses`.

In live mode, use Yahoo tickers for Indian stocks, for example `add TCS.NS`.

## Commands

| Command | What it does |
| --- | --- |
| `add SYM [price]` | Add a symbol to the watchlist |
| `rm SYM` | Remove a watchlist symbol |
| `chart SYM` | Show a symbol in the chart (Tab also cycles) |
| `sort sym\|px\|chg\|off` | Sort the watchlist |
| `pause` / `resume` | Stop or restart the feed |
| `quit` | Exit |

## How it works

- `Quote` holds a rolling window of 120 prices per symbol.
- `Market` owns all quotes. In simulated mode each tick applies a Gaussian return to the last price. In live mode a background thread polls yfinance every 10 seconds and ticks use the latest price.
- The UI loop redraws about five times a second, reads keys without blocking, and never touches the data layer directly.

## Ideas for next steps

- Candlestick view and moving averages
- Portfolio tracker with profit and loss
- News panel
- Unit tests for the simulator and command parser

## License

MIT
