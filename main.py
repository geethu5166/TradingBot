import os
import time
import json
import logging
import requests
import traceback
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from dotenv import load_dotenv
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, ADXIndicator, SMAIndicator, EMAIndicator, CCIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

# ─── LOGGING ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("TradingBot")

# ─── ENV ────────────────────────────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY")
BOT_TOKEN         = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID           = os.getenv("TELEGRAM_CHAT_ID")
INTERVAL          = os.getenv("INTERVAL", "15m")
SLEEP_SECONDS     = int(os.getenv("SLEEP_SECONDS", "900"))
CONFIDENCE_THRESH = int(os.getenv("CONFIDENCE_THRESHOLD", "70"))

genai.configure(api_key=GEMINI_API_KEY)

# ─── SYMBOLS ────────────────────────────────────────────────────────────────
SYMBOLS = {
    "NIFTY 50":   "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "MIDCAP 50":  "^NSEMDCP50",
    "SENSEX":     "^BSESN",
    "FINNIFTY":   "^CNXFIN",
}

# ─── MARKET HOURS CHECK ─────────────────────────────────────────────────────
def is_market_open() -> bool:
    """Returns True if NSE is currently open (Mon–Fri 09:15–15:30 IST)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.weekday() >= 5:
        return False
    open_time  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_time <= now <= close_time

# ─── INDICATORS ─────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> dict:
    """Returns a dict of the latest indicator values."""
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    adx  = ADXIndicator(high, low, close)
    macd = MACD(close)
    bb   = BollingerBands(close)
    sto  = StochasticOscillator(high, low, close)
    obv  = OnBalanceVolumeIndicator(close, vol)

    df["rsi"]      = RSIIndicator(close).rsi()
    df["adx"]      = adx.adx()
    df["adx_pos"]  = adx.adx_pos()
    df["adx_neg"]  = adx.adx_neg()
    df["macd"]     = macd.macd()
    df["macd_sig"] = macd.macd_signal()
    df["macd_dif"] = macd.macd_diff()
    df["atr"]      = AverageTrueRange(high, low, close).average_true_range()
    df["sma50"]    = SMAIndicator(close, window=50).sma_indicator()
    df["sma200"]   = SMAIndicator(close, window=200).sma_indicator()
    df["ema20"]    = EMAIndicator(close, window=20).ema_indicator()
    df["ema9"]     = EMAIndicator(close, window=9).ema_indicator()
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_pct"]   = bb.bollinger_pband()
    df["stoch_k"]  = sto.stoch()
    df["stoch_d"]  = sto.stoch_signal()
    df["obv"]      = obv.on_balance_volume()
    df["cci"]      = CCIIndicator(high, low, close).cci()

    row = df.iloc[-1].to_dict()

    row["trend_bull"]     = row["ema9"] > row["ema20"] > row["sma50"]
    row["golden_cross"]   = row["sma50"] > row["sma200"]
    row["macd_bull"]      = row["macd_dif"] > 0
    row["rsi_oversold"]   = row["rsi"] < 35
    row["rsi_overbought"] = row["rsi"] > 65

    last3 = df["Close"].iloc[-3:]
    row["momentum_up"]   = bool(all(last3.diff().dropna() > 0))
    row["momentum_down"] = bool(all(last3.diff().dropna() < 0))

    return row

# ─── AI ANALYSIS ─────────────────────────────────────────────────────────────
def ai_analysis(symbol: str, d: dict):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
You are a senior quantitative analyst and CIO of a multi-strategy trading firm.
Analyze the following real-time indicator snapshot for {symbol} and return a precise trade decision.

=== SNAPSHOT ===
Price:       {d["Close"]:.2f}
ADX:         {d["adx"]:.2f}  (+DI {d["adx_pos"]:.2f} / -DI {d["adx_neg"]:.2f})
RSI(14):     {d["rsi"]:.2f}
MACD Diff:   {d["macd_dif"]:.4f}  (MACD {d["macd"]:.4f} / Signal {d["macd_sig"]:.4f})
ATR:         {d["atr"]:.2f}
EMA9:        {d["ema9"]:.2f} | EMA20: {d["ema20"]:.2f}
SMA50:       {d["sma50"]:.2f} | SMA200: {d["sma200"]:.2f}
BB %B:       {d["bb_pct"]:.2f}  (Upper {d["bb_upper"]:.2f} / Lower {d["bb_lower"]:.2f})
Stoch K/D:   {d["stoch_k"]:.2f} / {d["stoch_d"]:.2f}
CCI:         {d["cci"]:.2f}
OBV Trend:   Rising={d["obv"] > 0}
Trend Flags: Bullish EMA Stack={d["trend_bull"]} | Golden Cross={d["golden_cross"]}
             MACD Bullish={d["macd_bull"]} | RSI Oversold={d["rsi_oversold"]} | RSI Overbought={d["rsi_overbought"]}
             3-Candle Momentum Up={d["momentum_up"]} | Down={d["momentum_down"]}

=== TASKS ===
1. Trend Squad:    Evaluate EMA stack, ADX strength (>25=strong), SMA crossovers.
2. Momentum Squad: Confirm MACD, RSI, Stoch, CCI alignment.
3. Volatility Squad: Use ATR to set dynamic Stop Loss (1.5x ATR from entry). Assess BB squeeze vs expansion.
4. Volume Squad:  Confirm OBV trend matches price direction.
5. Risk Squad:    Calculate R:R ratio. Reject if < 1.5.

=== OUTPUT ===
Return ONLY a valid JSON object (no markdown, no explanation):
{{
  "signal": "BUY" or "SELL" or "HOLD",
  "confidence": integer 0-100,
  "entry": float,
  "sl": float,
  "tp1": float,
  "tp2": float,
  "rr_ratio": float,
  "regime": "TRENDING" or "RANGING" or "VOLATILE",
  "timeframe": "Intraday" or "Swing",
  "rationale": "two sentence explanation"
}}
"""
    try:
        resp = model.generate_content(prompt)
        raw  = resp.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        log.warning(f"AI parse error for {symbol}: {e}")
        return None

# ─── TELEGRAM ────────────────────────────────────────────────────────────────
def send_telegram(text: str, parse_mode: str = "Markdown") -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

def format_alert(name: str, price: float, sig: dict) -> str:
    emoji  = "\U0001f680" if sig["signal"] == "BUY" else "\U0001f53b" if sig["signal"] == "SELL" else "\u23f8"
    regime = {"TRENDING": "\U0001f4c8 Trending", "RANGING": "\u2194\ufe0f Ranging", "VOLATILE": "\u26a1 Volatile"}.get(sig.get("regime",""), "")
    ts     = datetime.now().strftime("%d %b %Y  %H:%M IST")
    return (
        f"{emoji} *{sig['signal']} SIGNAL \u2014 {name}*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f550 *Time:*       {ts}\n"
        f"\U0001f4b0 *Price:*      `{price:.2f}`\n"
        f"\U0001f4cd *Entry:*      `{sig['entry']:.2f}`\n"
        f"\U0001f6d1 *Stop Loss:*  `{sig['sl']:.2f}`\n"
        f"\U0001f3af *Target 1:*   `{sig['tp1']:.2f}`\n"
        f"\U0001f3af *Target 2:*   `{sig['tp2']:.2f}`\n"
        f"\u2696\ufe0f *R:R Ratio:*  `{sig.get('rr_ratio',0):.2f}`\n"
        f"\U0001f4ca *Confidence:* `{sig['confidence']}%`\n"
        f"\U0001f310 *Regime:*     {regime}\n"
        f"\u23f1 *Timeframe:*  {sig.get('timeframe','Intraday')}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4dd {sig['rationale']}\n"
        f"\u26a0\ufe0f _Not financial advice. Trade responsibly._"
    )

# ─── HEALTH PING ─────────────────────────────────────────────────────────────
last_health_ping = datetime.min

def health_ping():
    global last_health_ping
    now = datetime.now()
    if (now - last_health_ping) >= timedelta(hours=6):
        send_telegram("\U0001f916 *TradingBot Heartbeat* \u2014 Running normally \u2705")
        last_health_ping = now

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────
def run():
    log.info("TradingBot v2 started.")
    send_telegram("\U0001f916 *TradingBot v2 Started* \u2014 Monitoring NSE indices \U0001f4e1")

    while True:
        try:
            health_ping()

            if not is_market_open():
                log.info("Market closed. Sleeping 15 min...")
                time.sleep(900)
                continue

            cycle_start = datetime.now()
            log.info(f"--- Scan cycle at {cycle_start.strftime('%H:%M:%S')} ---")

            for name, ticker in SYMBOLS.items():
                try:
                    df = yf.download(ticker, period="10d", interval=INTERVAL, progress=False, auto_adjust=True)
                    if df.empty or len(df) < 50:
                        log.warning(f"{name}: insufficient data ({len(df)} rows)")
                        continue

                    indicators = compute_indicators(df)
                    analysis   = ai_analysis(name, indicators)

                    if not analysis:
                        log.info(f"{name}: AI returned no result")
                        continue

                    log.info(f"{name}: {analysis['signal']} conf={analysis['confidence']}% R:R={analysis.get('rr_ratio',0):.2f}")

                    if (
                        analysis["signal"] != "HOLD"
                        and analysis["confidence"] >= CONFIDENCE_THRESH
                        and analysis.get("rr_ratio", 0) >= 1.5
                    ):
                        alert = format_alert(name, indicators["Close"], analysis)
                        ok = send_telegram(alert)
                        log.info(f"Alert sent for {name}: {ok}")

                except Exception as e:
                    log.error(f"Error processing {name}: {e}\n{traceback.format_exc()}")

            elapsed = (datetime.now() - cycle_start).total_seconds()
            sleep_for = max(0, SLEEP_SECONDS - elapsed)
            log.info(f"Cycle done in {elapsed:.1f}s. Next scan in {sleep_for:.0f}s.")
            time.sleep(sleep_for)

        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            send_telegram("\U0001f916 *TradingBot* \u2014 Stopped by user \U0001f6d1")
            break
        except Exception as e:
            log.critical(f"Outer loop error: {e}\n{traceback.format_exc()}")
            time.sleep(60)

if __name__ == "__main__":
    run()
