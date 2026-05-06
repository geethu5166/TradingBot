"""
Advanced Indian Market Trading Bot v2.0
- Gemini 1.5 Flash multi-agent signal engine
- NSE Indices + Top F&O stocks
- Telegram alerts to YOUR private chat only (locked to your chat_id)
- Market hours aware (NSE 9:15 AM - 3:30 PM IST, Mon-Fri)
- Per-symbol cooldown (no duplicate spam)
- Daily summary alert at 3:35 PM IST
- Structured logging to console + bot.log
- DigitalOcean / Docker ready
"""

import os
import re
import json
import time
import logging
import requests
import traceback
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from typing import Optional

import pandas as pd
import yfinance as yf
import google.generativeai as genai
from dotenv import load_dotenv
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, ADXIndicator, SMAIndicator, EMAIndicator, CCIIndicator
from ta.volatility import AverageTrueRange, BollingerBands

# ──────────────────────────────────────────────────────────
# BOOTSTRAP
# ──────────────────────────────────────────────────────────
load_dotenv()

IST = ZoneInfo("Asia/Kolkata")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("TradingBot")

# ──────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")   # your personal chat ID - locked

INTERVAL        = "15m"
SCAN_PERIOD     = "5d"
LOOP_SLEEP_SEC  = 900          # 15 minutes
MIN_CONFIDENCE  = 72           # alert only if AI confidence >= this
COOLDOWN_MIN    = 60           # don't re-alert same symbol within N minutes
MARKET_OPEN     = dt_time(9, 15)
MARKET_CLOSE    = dt_time(15, 30)
SUMMARY_TIME    = dt_time(15, 35)

SYMBOLS: dict[str, str] = {
    # Indices
    "NIFTY 50":     "^NSEI",
    "BANK NIFTY":   "^NSEBANK",
    "MIDCAP 50":    "^NSEMDCP50",
    # Top F&O Stocks
    "RELIANCE":     "RELIANCE.NS",
    "TCS":          "TCS.NS",
    "INFOSYS":      "INFY.NS",
    "HDFC BANK":    "HDFCBANK.NS",
    "ICICI BANK":   "ICICIBANK.NS",
    "WIPRO":        "WIPRO.NS",
    "ADANIENT":     "ADANIENT.NS",
    "TATAMOTORS":   "TATAMOTORS.NS",
    "BAJFINANCE":   "BAJFINANCE.NS",
    "AXISBANK":     "AXISBANK.NS",
}

# ──────────────────────────────────────────────────────────
# STATE
# ──────────────────────────────────────────────────────────
last_alert_time: dict[str, float] = {}
daily_signals:   list[dict]       = []
summary_sent_today: bool          = False

# ──────────────────────────────────────────────────────────
# MARKET HOURS
# ──────────────────────────────────────────────────────────
def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE

def is_summary_time() -> bool:
    now = datetime.now(IST)
    t   = now.time()
    return SUMMARY_TIME <= t <= dt_time(15, 40) and now.weekday() < 5

# ──────────────────────────────────────────────────────────
# INDICATORS
# ──────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> Optional[pd.Series]:
    if len(df) < 50:
        return None
    try:
        close = df["Close"].squeeze()
        high  = df["High"].squeeze()
        low   = df["Low"].squeeze()

        df["ema9"]    = EMAIndicator(close, window=9).ema_indicator()
        df["ema21"]   = EMAIndicator(close, window=21).ema_indicator()
        df["sma50"]   = SMAIndicator(close, window=50).sma_indicator()
        df["sma200"]  = SMAIndicator(close, window=200).sma_indicator()

        df["rsi"]     = RSIIndicator(close).rsi()
        macd_obj      = MACD(close)
        df["macd"]    = macd_obj.macd()
        df["macd_sig"]= macd_obj.macd_signal()
        df["macd_dif"]= macd_obj.macd_diff()
        stoch         = StochasticOscillator(high, low, close)
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()
        df["cci"]     = CCIIndicator(high, low, close).cci()

        df["atr"]     = AverageTrueRange(high, low, close).average_true_range()
        bb            = BollingerBands(close)
        df["bb_upper"]= bb.bollinger_hband()
        df["bb_lower"]= bb.bollinger_lband()
        df["bb_width"]= bb.bollinger_wband()

        adx           = ADXIndicator(high, low, close)
        df["adx"]     = adx.adx()
        df["adx_pos"] = adx.adx_pos()
        df["adx_neg"] = adx.adx_neg()

        df["vol_avg20"] = df["Volume"].rolling(20).mean()
        df["vol_ratio"] = df["Volume"] / df["vol_avg20"]

        row = df.iloc[-1].copy()
        row["prev_close"] = float(df["Close"].iloc[-2])
        return row
    except Exception as e:
        log.error(f"Indicator error: {e}")
        return None

# ──────────────────────────────────────────────────────────
# GEMINI AI
# ──────────────────────────────────────────────────────────
def ai_analysis(symbol: str, d: pd.Series) -> Optional[dict]:
    try:
        model  = genai.GenerativeModel("gemini-1.5-flash")
        change = ((float(d["Close"]) - float(d["prev_close"])) / float(d["prev_close"])) * 100

        prompt = f"""
You are the Chief Investment Officer of a quantitative hedge fund running 1,000 specialised AI agents
on the NSE Indian market. Your agents have completed their analysis and report the following data.

INSTRUMENT : {symbol}
PRICE      : Rs.{float(d['Close']):.2f}  ({change:+.2f}% vs prev close)
TIMEFRAME  : 15-minute candles

--- TREND SQUAD ---
EMA9={float(d['ema9']):.2f}  EMA21={float(d['ema21']):.2f}
SMA50={float(d['sma50']):.2f}  SMA200={float(d['sma200']):.2f}
ADX={float(d['adx']):.1f} (+DI={float(d['adx_pos']):.1f} / -DI={float(d['adx_neg']):.1f})

--- MOMENTUM SQUAD ---
RSI={float(d['rsi']):.1f}  CCI={float(d['cci']):.1f}
MACD Hist={float(d['macd_dif']):.4f}  Signal={float(d['macd_sig']):.4f}
Stoch %K={float(d['stoch_k']):.1f}  %D={float(d['stoch_d']):.1f}

--- VOLATILITY SQUAD ---
ATR={float(d['atr']):.2f}
BB Upper={float(d['bb_upper']):.2f}  Lower={float(d['bb_lower']):.2f}  Width={float(d['bb_width']):.2f}

--- VOLUME SQUAD ---
Volume Ratio vs 20-day avg = {float(d['vol_ratio']):.2f}x

INSTRUCTIONS:
1. Synthesise ALL agent reports above into a single trade decision.
2. Entry must be based on current price plus or minus 0.1%.
3. Stop-Loss must be exactly 1.5x ATR from entry.
4. Target must give at least 2:1 reward-to-risk.
5. Confidence must reflect CONFLUENCE of signals (multiple agreeing = higher).
6. If trend is weak (ADX < 20) or signals conflict badly, set signal to HOLD.

Return ONLY a valid JSON object. No markdown, no extra text:
{{
  "signal":     "BUY",
  "confidence": 85,
  "entry":      1234.56,
  "sl":         1210.00,
  "tp":         1284.00,
  "rationale":  "One concise sentence."
}}
"""
        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        return json.loads(raw)

    except json.JSONDecodeError as e:
        log.warning(f"[{symbol}] JSON parse failed: {e}")
    except Exception as e:
        log.error(f"[{symbol}] Gemini error: {e}")
    return None

# ──────────────────────────────────────────────────────────
# TELEGRAM — locked to YOUR chat_id only
# ──────────────────────────────────────────────────────────
def _tg_post(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials missing.")
        return False
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

def send_signal_alert(symbol: str, sig: dict):
    emoji = "\U0001f680" if sig["signal"] == "BUY" else "\U0001f53b"
    rr    = abs(sig["tp"] - sig["entry"]) / max(abs(sig["sl"] - sig["entry"]), 0.01)
    text  = (
        f"{emoji} *{sig['signal']} SIGNAL \u2014 {symbol}*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4cd *Entry :* `Rs.{sig['entry']:.2f}`\n"
        f"\U0001f6d1 *Stop Loss :* `Rs.{sig['sl']:.2f}`\n"
        f"\U0001f3af *Target :* `Rs.{sig['tp']:.2f}`\n"
        f"\u2696\ufe0f *R:R :* `1 : {rr:.1f}`\n"
        f"\U0001f4ca *Confidence :* `{sig['confidence']}%`\n"
        f"\U0001f4dd *Rationale :* {sig['rationale']}\n"
        f"\U0001f550 *Time :* {datetime.now(IST).strftime('%d %b %Y  %H:%M IST')}\n"
        f"\u26a0\ufe0f _Not financial advice. Trade responsibly._"
    )
    if _tg_post(text):
        log.info(f"[{symbol}] Alert sent \u2192 {sig['signal']} @ Rs.{sig['entry']:.2f}")

def send_daily_summary():
    if not daily_signals:
        _tg_post("\U0001f4cb *Daily Summary* \u2014 No actionable signals today.")
        return
    buys  = [s for s in daily_signals if s["signal"] == "BUY"]
    sells = [s for s in daily_signals if s["signal"] == "SELL"]
    lines = [
        f"\U0001f4cb *Daily Summary \u2014 {datetime.now(IST).strftime('%d %b %Y')}*",
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"Total Signals : {len(daily_signals)}   \U0001f680 BUY: {len(buys)}   \U0001f53b SELL: {len(sells)}",
        "",
    ]
    for s in daily_signals:
        e = "\U0001f680" if s["signal"] == "BUY" else "\U0001f53b"
        lines.append(f"{e} {s['symbol']} | Entry Rs.{s['entry']:.2f} | Conf {s['confidence']}%")
    _tg_post("\n".join(lines))
    log.info("Daily summary sent.")

# ──────────────────────────────────────────────────────────
# COOLDOWN
# ──────────────────────────────────────────────────────────
def is_on_cooldown(symbol: str) -> bool:
    last = last_alert_time.get(symbol, 0)
    return (time.time() - last) < (COOLDOWN_MIN * 60)

# ──────────────────────────────────────────────────────────
# SCAN ONE SYMBOL
# ──────────────────────────────────────────────────────────
def scan_symbol(name: str, ticker: str):
    try:
        df = yf.download(ticker, period=SCAN_PERIOD, interval=INTERVAL,
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            log.warning(f"[{name}] Insufficient data ({len(df)} rows)")
            return

        data = compute_indicators(df)
        if data is None:
            return

        sig = ai_analysis(name, data)
        if sig is None:
            return

        log.info(f"[{name}] {sig['signal']} | Conf={sig['confidence']}%")

        if sig["signal"] == "HOLD":
            return
        if sig["confidence"] < MIN_CONFIDENCE:
            log.info(f"[{name}] Skipped \u2014 confidence {sig['confidence']}% below {MIN_CONFIDENCE}%")
            return
        if is_on_cooldown(name):
            log.info(f"[{name}] Skipped \u2014 cooldown active")
            return

        send_signal_alert(name, sig)
        last_alert_time[name] = time.time()
        sig["symbol"] = name
        daily_signals.append(sig)

    except Exception:
        log.error(f"[{name}] Unhandled exception:\n{traceback.format_exc()}")

# ──────────────────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────────────────
def main():
    global summary_sent_today, daily_signals

    if not GEMINI_API_KEY:
        log.critical("GEMINI_API_KEY not set in .env \u2014 exiting.")
        raise SystemExit(1)

    genai.configure(api_key=GEMINI_API_KEY)

    log.info("=" * 55)
    log.info("  TradingBot v2.0 \u2014 started")
    log.info(f"  Symbols     : {len(SYMBOLS)}")
    log.info(f"  Scan every  : {LOOP_SLEEP_SEC // 60} minutes")
    log.info(f"  Min Conf    : {MIN_CONFIDENCE}%  |  Cooldown: {COOLDOWN_MIN} min")
    log.info("=" * 55)

    _tg_post(
        f"\u2705 *TradingBot v2.0 Online*\n"
        f"Scanning *{len(SYMBOLS)} instruments* every {LOOP_SLEEP_SEC // 60} min\n"
        f"Market hours: 09:15 \u2013 15:30 IST (Mon\u2013Fri)\n"
        f"Min confidence threshold: {MIN_CONFIDENCE}%"
    )

    while True:
        now_ist = datetime.now(IST)

        # Reset daily state at midnight
        if now_ist.hour == 0 and now_ist.minute < 15:
            daily_signals      = []
            summary_sent_today = False

        # Send end-of-day summary once
        if is_summary_time() and not summary_sent_today:
            send_daily_summary()
            summary_sent_today = True

        if not is_market_open():
            log.info(f"Market closed ({now_ist.strftime('%H:%M IST')}) \u2014 sleeping {LOOP_SLEEP_SEC // 60} min")
            time.sleep(LOOP_SLEEP_SEC)
            continue

        log.info(f"\u2500\u2500 Scan cycle @ {now_ist.strftime('%H:%M IST')} \u2500\u2500")
        for name, ticker in SYMBOLS.items():
            scan_symbol(name, ticker)
            time.sleep(2)    # gentle pacing between symbols

        log.info(f"\u2500\u2500 Cycle done. Sleeping {LOOP_SLEEP_SEC // 60} min \u2500\u2500")
        time.sleep(LOOP_SLEEP_SEC)


if __name__ == "__main__":
    main()
