# MT5 → Telegram Signal Bot

A production-ready trading **signal** bot for MetaTrader 5. It scans
**BTCUSD, ETHUSD, and XAUUSD** on the **M5** and **M15** timeframes using a
confluence strategy (VWAP + Market Structure + Volume + Candlestick
Confirmation) and sends formatted alerts to Telegram.

> ⚠️ **This bot never places trades.** It only analyzes the market and
> sends you a Telegram message. You decide whether to execute the trade
> manually in your own MT5 terminal.

---

## 1. How the strategy works

A signal is only sent when **every** rule below passes, and the combined
confidence score is **≥ 80%** (configurable):

**BUY**
- Price is above VWAP (bonus if it recently pulled back toward VWAP)
- Market structure is bullish (Higher Highs + Higher Lows), ideally with a
  fresh Break of Structure
- Current candle's tick volume is above `1.2×` the 20-candle average
  (configurable)
- A bullish candlestick pattern confirms (Bullish Engulfing, Hammer, or a
  strong bullish rejection wick)
- The higher timeframe (M15 confirms M5 by default) agrees with the
  direction

**SELL** — every condition mirrored.

**Take Profit** is always set so the trade's realized risk:reward is
exactly **2.6**:

```
risk = |entry - stop_loss|
TP (buy)  = entry + risk * 2.6
TP (sell) = entry - risk * 2.6
```

Stop Loss is derived from the most recent swing low/high plus a small
ATR buffer.

### Confidence score weighting

| Condition    | Weight |
|--------------|-------:|
| VWAP         | 20     |
| Structure    | 25     |
| Volume       | 20     |
| Candlestick  | 20     |
| Trend        | 15     |

All weights and the 80% threshold are configurable in `.env`.

---

## 2. Project structure

```
mt5-telegram-signal-bot/
├── main.py                  # Entry point
├── scanner.py                # Continuous scan loop (never crashes, auto-reconnects)
├── config.py                  # Loads and validates all settings from .env
├── requirements.txt
├── .env.example
├── core/
│   ├── vwap.py                 # Manual VWAP calculation
│   ├── market_structure.py     # HH/HL/LH/LL, BOS, CHoCH detection
│   ├── candlestick.py          # Engulfing, Hammer, Shooting Star, Rejection patterns
│   ├── volume.py                # Tick-volume confirmation
│   ├── risk.py                  # Entry/SL/TP calculation (2.6 R:R)
│   ├── sessions.py               # London / New York session filter
│   └── signal_engine.py          # Combines everything into a confidence score
├── data/
│   └── mt5_client.py             # MT5 connection, reconnection, candle fetching
├── storage/
│   ├── signal_store.py            # JSON-backed duplicate-signal protection
│   └── csv_logger.py               # CSV signal history
├── telegram_bot/
│   ├── client.py                    # Telegram Bot API (requests-based)
│   ├── formatter.py                  # Message templates
│   └── commands.py                    # /status /pairs /lastsignal /today /help
└── utils/
    ├── logger.py                       # Rotating file + console logging
    └── retry.py                         # Exponential backoff decorator
```

---

## 3. Requirements

- **Windows** (the `MetaTrader5` Python package only works on Windows,
  because it talks to the local MT5 terminal process)
- Python 3.11+
- A MetaTrader 5 terminal installed and logged into a broker account
  (demo or live — this bot works with either since it never trades)
- A Telegram account

---

## 4. Installation

```powershell
# 1. Clone the repository
git clone https://github.com/<your-username>/mt5-telegram-signal-bot.git
cd mt5-telegram-signal-bot

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the environment template
copy .env.example .env
```

Now open `.env` in a text editor and fill in your values (see sections
below for MT5 and Telegram setup).

---

## 5. MT5 setup

1. Install [MetaTrader 5](https://www.metatrader5.com/en/download) and log
   into any account (demo is fine — no trades are ever placed).
2. Leave the terminal **open** while the bot runs. `MetaTrader5.initialize()`
   attaches to the already-running terminal.
3. In `.env`:
   - If you're already logged into the terminal manually, you can leave
     `MT5_LOGIN`, `MT5_PASSWORD`, and `MT5_SERVER` blank.
   - If you want the bot to log in itself (useful for a VPS running
     headless), fill in all three plus `MT5_TERMINAL_PATH` (the full path
     to `terminal64.exe`).
4. Make sure BTCUSD, ETHUSD, and XAUUSD (or your broker's equivalent
   symbol names, e.g. `XAUUSDm`) are visible in Market Watch. If your
   broker uses different symbol names, update `SYMBOLS` in `.env`.

---

## 6. Telegram setup

### Creating a bot with BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and a unique
   username ending in `bot`).
3. BotFather will reply with an API token that looks like
   `123456789:AAExampleTokenString`. Copy it into `TELEGRAM_BOT_TOKEN` in
   `.env`.

### Finding your Chat ID

1. Send any message to your new bot (search for its username and press
   Start).
2. Visit this URL in your browser, replacing `<TOKEN>` with your bot
   token:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Look for `"chat":{"id":123456789,...}` in the JSON response — that
   number is your `TELEGRAM_CHAT_ID`.
4. For a group chat, add the bot to the group first, send a message in
   the group, then repeat step 2 — group chat IDs are negative numbers.

---

## 7. Running the bot

### Locally (Windows, foreground)

```powershell
venv\Scripts\activate
python main.py
```

You should see log output in the console and receive a "🚀 Bot started"
message in Telegram.

### Running in the background on Windows

Use `pythonw.exe` to run without a console window, or use
[NSSM](https://nssm.cc/) to install it as a Windows service:

```powershell
nssm install MT5SignalBot "C:\path\to\venv\Scripts\python.exe" "C:\path\to\main.py"
nssm start MT5SignalBot
```

### Running on a VPS later

Most Forex/crypto VPS providers offer a Windows Server image with MT5
pre-installable. Steps are identical to the local setup above — install
Python, clone the repo, install MT5, configure `.env`, then run `main.py`
under NSSM (or Task Scheduler) so it restarts automatically if the VPS
reboots.

---

## 8. Telegram bot commands

| Command       | Description                              |
|---------------|-------------------------------------------|
| `/status`     | Bot & MT5 connection status, active signal count |
| `/pairs`      | List monitored pairs and timeframes        |
| `/lastsignal` | Show the most recent signal sent           |
| `/today`      | Show every signal sent today                |
| `/help`       | List all commands                           |

The bot also sends:
- A **heartbeat** message every 6 hours (configurable) confirming it's
  still online.
- A **daily performance summary** at a configured UTC hour.

---

## 9. Duplicate signal protection

Every signal is keyed by `(symbol, timeframe, direction)`. Once sent, no
new signal for that exact key is emitted until one of:

- Take Profit is hit
- Stop Loss is hit
- Market structure flips direction
- The cooldown period expires (default 30 minutes, `SIGNAL_COOLDOWN_MINUTES`)

State is persisted to `signals/active_signals.json`, so it survives
restarts.

---

## 10. Signal history (CSV)

Every signal sent is appended to `signals/signal_history.csv` with columns:
`date, time, pair, timeframe, entry, sl, tp, confidence, direction,
signal_number, result`. The `result` column is left blank for you (or a
future add-on) to fill in once a trade closes.

---

## 11. Configuration reference

All settings live in `.env` — see `.env.example` for the full list with
inline comments, including:

- Symbols & timeframes (`SYMBOLS`, `TIMEFRAMES`, `CONFIRMATION_TIMEFRAME`)
- Strategy tuning (`RISK_REWARD_RATIO`, `VOLUME_LOOKBACK`,
  `VOLUME_MULTIPLIER`, `MIN_CONFIDENCE_SCORE`, confidence weights)
- Session filter (`SESSION_FILTER=LONDON|NEWYORK|BOTH|OFF`)
- Scanner behavior (`SCAN_INTERVAL_SECONDS`, reconnect settings)
- Logging (`LOG_FILE`, `LOG_LEVEL`, rotation size/backups)

---

## 12. Testing instructions

1. **Config validation** — run `python -c "from config import config; print(config)"`.
   It should print your loaded settings without raising `ConfigError`.
2. **MT5 connectivity** — with the MT5 terminal open, run:
   ```powershell
   python -c "from data.mt5_client import mt5_client; mt5_client.connect(); print(mt5_client.get_candles('BTCUSD','M5',10))"
   ```
   You should see a 10-row DataFrame of recent candles.
3. **Telegram connectivity** — run:
   ```powershell
   python -c "from telegram_bot.client import telegram_client; telegram_client.send_message('Test message from bot')"
   ```
   You should receive "Test message from bot" in Telegram within seconds.
4. **Full run** — `python main.py` and watch `logs/bot.log` for scan
   cycles every `SCAN_INTERVAL_SECONDS`.

---

## 13. Final checklist

- [x] Connects to MT5 (`data/mt5_client.py`, auto-reconnect with backoff)
- [x] Scans BTCUSD, ETHUSD, XAUUSD on M5 + M15 (configurable in `.env`)
- [x] Detects setups via VWAP + Structure + Volume + Candlestick confluence
- [x] Calculates TP/SL with an exact 2.6 risk:reward ratio
- [x] Sends formatted, emoji-rich Telegram signals
- [x] Prevents duplicate signals (JSON-backed cooldown + TP/SL/structure clearing)
- [x] Runs continuously, reconnects automatically, never crashes the main loop
- [x] Never places a trade — signal-only, always

---

## 14. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `mt5.initialize() failed` | MT5 terminal not open, or wrong path | Open the terminal manually first, or set `MT5_TERMINAL_PATH` |
| `Symbol 'X' not found` | Broker uses a different symbol name/suffix | Check Market Watch for the exact name (e.g. `XAUUSDm`) and update `SYMBOLS` |
| No Telegram messages arrive | Wrong token/chat ID, or bot not started with `/start` | Re-check `.env`, message the bot once, re-fetch `getUpdates` |
| Bot logs "No rate data returned" | Symbol not selected / market closed | Ensure the symbol is enabled in Market Watch |
| Too few / too many signals | Strategy thresholds too strict/loose | Tune `MIN_CONFIDENCE_SCORE`, `VOLUME_MULTIPLIER`, or the confidence weights in `.env` |
| `ModuleNotFoundError: MetaTrader5` | Running on macOS/Linux | The `MetaTrader5` package is Windows-only; run this bot on Windows or a Windows VPS |
