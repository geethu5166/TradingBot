"""
Advanced Multi-Market Trading Bot v3.1
- ALL Indian Indices (NIFTY, BANKNIFTY, SENSEX, FINNIFTY, MIDCAP, SMALLCAP etc.)
- Top 50 NSE F&O Stocks
- MCX Commodities (Gold, Silver, Crude, NatGas, Copper, Zinc, Lead, Aluminium, Nickel)
- Top 30 Crypto (BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC, DOT, AVAX...)
- Gemini 1.5 Flash AI with Why-This-Trade explanation
- Telegram alerts + commands (locked to YOUR chat_id)
- Market hours per segment | Cooldown | Daily summary

Telegram Commands:
  /start    - Help
  /status   - Uptime & stats
  /signals  - Today's signals
  /indices  - All Indian indices
  /stocks   - All NSE stocks
  /mcx      - MCX Commodities
  /crypto   - All crypto
  /market   - Market hours status
  /stop     - Stop bot
"""

import os
import re
import json
import time
import logging
import threading
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

# ────────────────────────────────────────────────────────
# BOOTSTRAP
# ────────────────────────────────────────────────────────
load_dotenv()
IST       = ZoneInfo("Asia/Kolkata")
BOT_START = datetime.now(IST)

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

# ────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

INTERVAL       = "15m"
SCAN_PERIOD    = "5d"
LOOP_SLEEP_SEC = 900
MIN_CONFIDENCE = 72
COOLDOWN_MIN   = 60
SUMMARY_TIME   = dt_time(15, 35)

NSE_OPEN  = dt_time(9, 15)
NSE_CLOSE = dt_time(15, 30)
MCX_OPEN  = dt_time(9, 0)
MCX_CLOSE = dt_time(23, 30)

# ────────────────────────────────────────────────────────
# ALL INDIAN INDICES
# ────────────────────────────────────────────────────────
NSE_INDICES: dict[str, str] = {
    "NIFTY 50":        "^NSEI",
    "BANK NIFTY":      "^NSEBANK",
    "SENSEX":          "^BSESN",
    "NIFTY IT":        "^CNXIT",
    "NIFTY PHARMA":    "^CNXPHARMA",
    "NIFTY AUTO":      "^CNXAUTO",
    "NIFTY FMCG":      "^CNXFMCG",
    "NIFTY METAL":     "^CNXMETAL",
    "NIFTY REALTY":    "^CNXREALTY",
    "NIFTY ENERGY":    "^CNXENERGY",
    "NIFTY INFRA":     "^CNXINFRA",
    "NIFTY MIDCAP 50": "^NSEMDCP50",
    "NIFTY SMALLCAP":  "^CNXSC",
    "NIFTY NEXT 50":   "^NSMIDCP",
    "INDIA VIX":       "^INDIAVIX",
}

# ────────────────────────────────────────────────────────
# TOP 50 NSE F&O STOCKS
# ────────────────────────────────────────────────────────
NSE_STOCKS: dict[str, str] = {
    # Banking & Finance
    "HDFC BANK":    "HDFCBANK.NS",
    "ICICI BANK":   "ICICIBANK.NS",
    "AXIS BANK":    "AXISBANK.NS",
    "SBI":          "SBIN.NS",
    "KOTAK BANK":   "KOTAKBANK.NS",
    "INDUSIND":     "INDUSINDBK.NS",
    "BAJFINANCE":   "BAJFINANCE.NS",
    "BAJAJFINSV":   "BAJAJFINSV.NS",
    "HDFCLIFE":     "HDFCLIFE.NS",
    "SBILIFE":      "SBILIFE.NS",
    # IT
    "TCS":          "TCS.NS",
    "INFOSYS":      "INFY.NS",
    "WIPRO":        "WIPRO.NS",
    "HCLTECH":      "HCLTECH.NS",
    "TECHM":        "TECHM.NS",
    "LTIM":         "LTIM.NS",
    "MPHASIS":      "MPHASIS.NS",
    # Energy & Oil
    "RELIANCE":     "RELIANCE.NS",
    "ONGC":         "ONGC.NS",
    "BPCL":         "BPCL.NS",
    "IOCL":         "IOC.NS",
    "NTPC":         "NTPC.NS",
    "POWERGRID":    "POWERGRID.NS",
    "ADANIGREEN":   "ADANIGREEN.NS",
    "ADANIPORTS":   "ADANIPORTS.NS",
    "ADANIENT":     "ADANIENT.NS",
    # Auto
    "TATAMOTORS":   "TATAMOTORS.NS",
    "MARUTI":       "MARUTI.NS",
    "M&M":          "M&M.NS",
    "EICHERMOT":    "EICHERMOT.NS",
    "HEROMOTOCO":   "HEROMOTOCO.NS",
    "BAJAJ-AUTO":   "BAJAJ-AUTO.NS",
    # Pharma
    "SUNPHARMA":    "SUNPHARMA.NS",
    "DRREDDY":      "DRREDDY.NS",
    "CIPLA":        "CIPLA.NS",
    "DIVISLAB":     "DIVISLAB.NS",
    # Metal & Mining
    "TATASTEEL":    "TATASTEEL.NS",
    "HINDALCO":     "HINDALCO.NS",
    "JSWSTEEL":     "JSWSTEEL.NS",
    "COALINDIA":    "COALINDIA.NS",
    "VEDL":         "VEDL.NS",
    # FMCG & Consumer
    "HINDUNILVR":   "HINDUNILVR.NS",
    "ITC":          "ITC.NS",
    "NESTLEIND":    "NESTLEIND.NS",
    "BRITANNIA":    "BRITANNIA.NS",
    # Others
    "LT":           "LT.NS",
    "ULTRACEMCO":   "ULTRACEMCO.NS",
    "ASIANPAINT":   "ASIANPAINT.NS",
    "TITAN":        "TITAN.NS",
    "ZOMATO":       "ZOMATO.NS",
    "PAYTM":        "PAYTM.NS",
}

# ────────────────────────────────────────────────────────
# MCX COMMODITIES
# ────────────────────────────────────────────────────────
MCX_COMMODITIES: dict[str, str] = {
    "GOLD MCX":        "GC=F",
    "SILVER MCX":      "SI=F",
    "CRUDE OIL MCX":   "CL=F",
    "NATURAL GAS MCX": "NG=F",
    "COPPER MCX":      "HG=F",
    "ZINC MCX":        "ZC=F",
    "LEAD MCX":        "PA=F",
    "ALUMINIUM MCX":   "ALI=F",
    "NICKEL MCX":      "NI=F",
}

# ────────────────────────────────────────────────────────
# TOP 30 CRYPTO
# ────────────────────────────────────────────────────────
CRYPTO: dict[str, str] = {
    "BITCOIN":       "BTC-USD",
    "ETHEREUM":      "ETH-USD",
    "BNB":           "BNB-USD",
    "SOLANA":        "SOL-USD",
    "XRP":           "XRP-USD",
    "CARDANO":       "ADA-USD",
    "AVALANCHE":     "AVAX-USD",
    "DOGECOIN":      "DOGE-USD",
    "POLKADOT":      "DOT-USD",
    "CHAINLINK":     "LINK-USD",
    "POLYGON":       "POL-USD",
    "SHIBA INU":     "SHIB-USD",
    "LITECOIN":      "LTC-USD",
    "TRON":          "TRX-USD",
    "UNISWAP":       "UNI-USD",
    "STELLAR":       "XLM-USD",
    "MONERO":        "XMR-USD",
    "ATOM":          "ATOM-USD",
    "NEAR":          "NEAR-USD",
    "FILECOIN":      "FIL-USD",
    "APTOS":         "APT-USD",
    "ARBITRUM":      "ARB-USD",
    "SUI":           "SUI-USD",
    "INJECTIVE":     "INJ-USD",
    "OPTIMISM":      "OP-USD",
    "PEPE":          "PEPE-USD",
    "FLOKI":         "FLOKI-USD",
    "WIF":           "WIF-USD",
    "BONK":          "BONK-USD",
    "NOTCOIN":       "NOT-USD",
}

# Combined
ALL_SYMBOLS: dict[str, str] = {**NSE_INDICES, **NSE_STOCKS, **MCX_COMMODITIES, **CRYPTO}

# Category lookup
SYMBOL_CATEGORY: dict[str, str] = {}
for k in NSE_INDICES:     SYMBOL_CATEGORY[k] = "NSE Index"
for k in NSE_STOCKS:      SYMBOL_CATEGORY[k] = "NSE Stock"
for k in MCX_COMMODITIES: SYMBOL_CATEGORY[k] = "MCX Commodity"
for k in CRYPTO:          SYMBOL_CATEGORY[k] = "Crypto"

def price_unit(name: str) -> str:
    cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
    if cat in ("Crypto", "MCX Commodity"): return "$"
    return "Rs."

# ────────────────────────────────────────────────────────
# STATE
# ────────────────────────────────────────────────────────
last_alert_time: dict[str, float] = {}
daily_signals:   list[dict]       = []
summary_sent_today: bool          = False

# ────────────────────────────────────────────────────────
# MARKET HOURS
# ────────────────────────────────────────────────────────
def is_nse_open() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 5 and NSE_OPEN <= now.time() <= NSE_CLOSE

def is_mcx_open() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 6 and MCX_OPEN <= now.time() <= MCX_CLOSE

def is_crypto_open() -> bool:
    return True

def should_scan(name: str) -> bool:
    cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
    if cat in ("NSE Index", "NSE Stock"): return is_nse_open()
    if cat == "MCX Commodity":            return is_mcx_open()
    if cat == "Crypto":                   return True
    return False

def is_summary_time() -> bool:
    now = datetime.now(IST)
    return SUMMARY_TIME <= now.time() <= dt_time(15, 40) and now.weekday() < 5

# ────────────────────────────────────────────────────────
# INDICATORS
# ────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> Optional[pd.Series]:
    if len(df) < 50:
        return None
    try:
        close = df["Close"].squeeze()
        high  = df["High"].squeeze()
        low   = df["Low"].squeeze()
        df["ema9"]     = EMAIndicator(close, window=9).ema_indicator()
        df["ema21"]    = EMAIndicator(close, window=21).ema_indicator()
        df["sma50"]    = SMAIndicator(close, window=50).sma_indicator()
        df["sma200"]   = SMAIndicator(close, window=200).sma_indicator()
        df["rsi"]      = RSIIndicator(close).rsi()
        macd_obj       = MACD(close)
        df["macd"]     = macd_obj.macd()
        df["macd_sig"] = macd_obj.macd_signal()
        df["macd_dif"] = macd_obj.macd_diff()
        stoch          = StochasticOscillator(high, low, close)
        df["stoch_k"]  = stoch.stoch()
        df["stoch_d"]  = stoch.stoch_signal()
        df["cci"]      = CCIIndicator(high, low, close).cci()
        df["atr"]      = AverageTrueRange(high, low, close).average_true_range()
        bb             = BollingerBands(close)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = bb.bollinger_wband()
        adx            = ADXIndicator(high, low, close)
        df["adx"]      = adx.adx()
        df["adx_pos"]  = adx.adx_pos()
        df["adx_neg"]  = adx.adx_neg()
        df["vol_avg20"]= df["Volume"].rolling(20).mean()
        df["vol_ratio"]= df["Volume"] / df["vol_avg20"]
        row = df.iloc[-1].copy()
        row["prev_close"] = float(df["Close"].iloc[-2])
        return row
    except Exception as e:
        log.error(f"Indicator error: {e}")
        return None

# ────────────────────────────────────────────────────────
# GEMINI AI — Why-This-Trade
# ────────────────────────────────────────────────────────
def ai_analysis(symbol: str, d: pd.Series, category: str) -> Optional[dict]:
    try:
        model  = genai.GenerativeModel("gemini-1.5-flash")
        change = ((float(d["Close"]) - float(d["prev_close"])) / float(d["prev_close"])) * 100
        unit   = price_unit(symbol)
        prompt = f"""
You are the Chief Investment Officer of a world-class quantitative hedge fund.
You have 4 specialised AI agent squads that analysed this instrument.

INSTRUMENT : {symbol}
CATEGORY   : {category}
PRICE      : {unit}{float(d['Close']):.4f}  ({change:+.2f}% vs prev close)
TIMEFRAME  : 15-minute candles

--- TREND SQUAD ---
EMA9={float(d['ema9']):.4f}  EMA21={float(d['ema21']):.4f}
SMA50={float(d['sma50']):.4f}  SMA200={float(d['sma200']):.4f}
ADX={float(d['adx']):.1f} (+DI={float(d['adx_pos']):.1f} / -DI={float(d['adx_neg']):.1f})

--- MOMENTUM SQUAD ---
RSI={float(d['rsi']):.1f}  CCI={float(d['cci']):.1f}
MACD Hist={float(d['macd_dif']):.6f}  Signal={float(d['macd_sig']):.6f}
Stoch %K={float(d['stoch_k']):.1f}  %D={float(d['stoch_d']):.1f}

--- VOLATILITY SQUAD ---
ATR={float(d['atr']):.4f}
BB Upper={float(d['bb_upper']):.4f}  Lower={float(d['bb_lower']):.4f}  Width={float(d['bb_width']):.4f}

--- VOLUME SQUAD ---
Volume Ratio vs 20-day avg = {float(d['vol_ratio']):.2f}x

INSTRUCTIONS:
1. Synthesise ALL squad reports into one trade decision.
2. Entry = current price +/- 0.1%.
3. Stop-Loss = 1.5x ATR from entry.
4. Target = min 2:1 reward-to-risk.
5. Confidence = confluence of agreeing signals.
6. ADX < 20 or conflicting signals = HOLD.
7. "why" = 4-5 bullets, each starting with indicator name in CAPS,
   explaining exactly what that indicator shows and why it supports the trade.

Return ONLY valid JSON, no markdown:
{{"signal":"BUY","confidence":85,"entry":1234.56,"sl":1210.00,"tp":1284.00,
  "rationale":"One concise line.",
  "why":["RSI: ...","MACD: ...","EMA: ...","ADX: ...","VOLUME: ..."]}}
"""
        response = model.generate_content(prompt)
        raw = re.sub(r"```(?:json)?", "", response.text.strip()).replace("```", "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"[{symbol}] JSON parse failed: {e}")
    except Exception as e:
        log.error(f"[{symbol}] Gemini error: {e}")
    return None

# ────────────────────────────────────────────────────────
# TELEGRAM HELPERS
# ────────────────────────────────────────────────────────
def _tg_post(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

def category_emoji(cat: str) -> str:
    return {"NSE Index": "\U0001f4c8", "NSE Stock": "\U0001f3e2",
            "MCX Commodity": "\U0001faa8", "Crypto": "\U0001fa99"}.get(cat, "\U0001f4ca")

def send_signal_alert(symbol: str, sig: dict):
    cat   = SYMBOL_CATEGORY.get(symbol, "NSE Stock")
    unit  = price_unit(symbol)
    emoji = "\U0001f680" if sig["signal"] == "BUY" else "\U0001f53b"
    categ = category_emoji(cat)
    rr    = abs(sig["tp"] - sig["entry"]) / max(abs(sig["sl"] - sig["entry"]), 0.01)
    why_block = ""
    why_lines = sig.get("why", [])
    if why_lines:
        why_block = "\n\n\U0001f9e0 *Why This Trade?*\n"
        for b in why_lines:
            why_block += f"  \u2022 {b}\n"
    _tg_post(
        f"{emoji} *{sig['signal']} SIGNAL* {categ}\n"
        f"*{symbol}* \u2014 _{cat}_\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4cd *Entry     :* `{unit}{sig['entry']:.4f}`\n"
        f"\U0001f6d1 *Stop Loss :* `{unit}{sig['sl']:.4f}`\n"
        f"\U0001f3af *Target    :* `{unit}{sig['tp']:.4f}`\n"
        f"\u2696\ufe0f *R:R       :* `1:{rr:.1f}`\n"
        f"\U0001f4ca *Confidence:* `{sig['confidence']}%`\n"
        f"\U0001f4dd *Summary   :* {sig['rationale']}"
        f"{why_block}\n"
        f"\U0001f550 {datetime.now(IST).strftime('%d %b %Y  %H:%M IST')}\n"
        f"\u26a0\ufe0f _Not financial advice._"
    )
    log.info(f"[{symbol}] {sig['signal']} @ {unit}{sig['entry']:.4f} | Conf {sig['confidence']}%")

def send_daily_summary():
    buys  = [s for s in daily_signals if s["signal"] == "BUY"]
    sells = [s for s in daily_signals if s["signal"] == "SELL"]
    if not daily_signals:
        _tg_post("\U0001f4cb *Daily Summary* \u2014 No signals today."); return
    lines = [
        f"\U0001f4cb *Daily Summary \u2014 {datetime.now(IST).strftime('%d %b %Y')}*",
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"Total: {len(daily_signals)}   \U0001f680 BUY:{len(buys)}   \U0001f53b SELL:{len(sells)}", ""
    ]
    for s in daily_signals:
        e  = "\U0001f680" if s["signal"] == "BUY" else "\U0001f53b"
        ce = category_emoji(SYMBOL_CATEGORY.get(s["symbol"], ""))
        u  = price_unit(s["symbol"])
        lines.append(f"{e}{ce} {s['symbol']} | {u}{s['entry']:.4f} | {s['confidence']}%")
    _tg_post("\n".join(lines))
    log.info("Daily summary sent.")

# ────────────────────────────────────────────────────────
# COOLDOWN & SCAN
# ────────────────────────────────────────────────────────
def is_on_cooldown(symbol: str) -> bool:
    return (time.time() - last_alert_time.get(symbol, 0)) < (COOLDOWN_MIN * 60)

def scan_symbol(name: str, ticker: str):
    try:
        df = yf.download(ticker, period=SCAN_PERIOD, interval=INTERVAL,
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            log.warning(f"[{name}] Insufficient data ({len(df)} rows)"); return
        data = compute_indicators(df)
        if data is None: return
        cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
        sig = ai_analysis(name, data, cat)
        if sig is None: return
        log.info(f"[{name}] {sig['signal']} | Conf={sig['confidence']}%")
        if sig["signal"] == "HOLD": return
        if sig["confidence"] < MIN_CONFIDENCE:
            log.info(f"[{name}] Skipped - low confidence"); return
        if is_on_cooldown(name):
            log.info(f"[{name}] Skipped - cooldown"); return
        send_signal_alert(name, sig)
        last_alert_time[name] = time.time()
        sig["symbol"] = name
        daily_signals.append(sig)
    except Exception:
        log.error(f"[{name}] Error:\n{traceback.format_exc()}")

# ────────────────────────────────────────────────────────
# TELEGRAM COMMAND LISTENER
# ────────────────────────────────────────────────────────
def poll_telegram_commands():
    last_update_id = 0
    log.info("Telegram command listener started.")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 30},
                timeout=35,
            )
            for update in r.json().get("result", []):
                last_update_id = update["update_id"]
                msg     = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text    = msg.get("text", "").strip().lower()
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue
                log.info(f"Command: {text}")

                if text in ["/start", "/help"]:
                    _tg_post(
                        "\U0001f916 *TradingBot v3.1*\n"
                        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        "\U0001f4c8 /indices  \u2014 All Indian indices\n"
                        "\U0001f3e2 /stocks   \u2014 All NSE stocks\n"
                        "\U0001faa8 /mcx      \u2014 MCX Commodities\n"
                        "\U0001fa99 /crypto   \u2014 All 30 cryptos\n"
                        "\U0001f4ca /signals  \u2014 Today's signals\n"
                        "\u2705 /status   \u2014 Uptime & stats\n"
                        "\U0001f555 /market   \u2014 Market hours\n"
                        "\U0001f6d1 /stop     \u2014 Stop the bot"
                    )

                elif text == "/status":
                    uptime = datetime.now(IST) - BOT_START
                    h, rem = divmod(int(uptime.total_seconds()), 3600)
                    m = rem // 60
                    _tg_post(
                        f"\u2705 *TradingBot v3.1 Status*\n"
                        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        f"\U0001f550 Uptime         : {h}h {m}m\n"
                        f"\U0001f4ca Total Symbols  : {len(ALL_SYMBOLS)}\n"
                        f"  \U0001f4c8 Indices      : {len(NSE_INDICES)}\n"
                        f"  \U0001f3e2 NSE Stocks   : {len(NSE_STOCKS)}\n"
                        f"  \U0001faa8 MCX          : {len(MCX_COMMODITIES)}\n"
                        f"  \U0001fa99 Crypto       : {len(CRYPTO)}\n"
                        f"\U0001f4e1 Signals Today  : {len(daily_signals)}\n"
                        f"\U0001f7e2 NSE Open       : {'Yes' if is_nse_open() else 'No'}\n"
                        f"\U0001f7e2 MCX Open       : {'Yes' if is_mcx_open() else 'No'}\n"
                        f"\U0001fa99 Crypto         : Always Open\n"
                        f"\U0001f550 Time           : {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}"
                    )

                elif text == "/signals":
                    if not daily_signals:
                        _tg_post("\U0001f4cb No signals fired yet today.")
                    else:
                        lines = [f"\U0001f4cb *Signals Today ({len(daily_signals)})*",
                                 "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
                        for s in daily_signals:
                            e  = "\U0001f680" if s["signal"] == "BUY" else "\U0001f53b"
                            ce = category_emoji(SYMBOL_CATEGORY.get(s["symbol"], ""))
                            u  = price_unit(s["symbol"])
                            lines.append(f"{e}{ce} *{s['symbol']}* | {u}{s['entry']:.4f} | {s['confidence']}%")
                        _tg_post("\n".join(lines))

                elif text in ["/indices", "/nse"]:
                    lines = ["\U0001f4c8 *All Indian Indices (15)*",
                             "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
                    for n, t in NSE_INDICES.items():
                        lines.append(f"  \u2022 {n} `({t})`")
                    _tg_post("\n".join(lines))

                elif text == "/stocks":
                    lines = [f"\U0001f3e2 *NSE F&O Stocks ({len(NSE_STOCKS)})*",
                             "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
                    cats = {
                        "Banking & Finance": ["HDFC BANK","ICICI BANK","AXIS BANK","SBI","KOTAK BANK","INDUSIND","BAJFINANCE","BAJAJFINSV","HDFCLIFE","SBILIFE"],
                        "IT": ["TCS","INFOSYS","WIPRO","HCLTECH","TECHM","LTIM","MPHASIS"],
                        "Energy": ["RELIANCE","ONGC","BPCL","IOCL","NTPC","POWERGRID","ADANIGREEN","ADANIPORTS","ADANIENT"],
                        "Auto": ["TATAMOTORS","MARUTI","M&M","EICHERMOT","HEROMOTOCO","BAJAJ-AUTO"],
                        "Pharma": ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB"],
                        "Metal": ["TATASTEEL","HINDALCO","JSWSTEEL","COALINDIA","VEDL"],
                        "FMCG": ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA"],
                        "Others": ["LT","ULTRACEMCO","ASIANPAINT","TITAN","ZOMATO","PAYTM"],
                    }
                    for sec, syms in cats.items():
                        lines.append(f"\n*{sec}:*")
                        for s in syms: lines.append(f"  \u2022 {s}")
                    _tg_post("\n".join(lines))

                elif text == "/mcx":
                    lines = ["\U0001faa8 *MCX Commodities*",
                             "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
                    for n, t in MCX_COMMODITIES.items():
                        lines.append(f"  \u2022 {n} `({t})`")
                    _tg_post("\n".join(lines))

                elif text == "/crypto":
                    lines = [f"\U0001fa99 *Crypto 24/7 ({len(CRYPTO)})*",
                             "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
                    for n, t in CRYPTO.items():
                        lines.append(f"  \u2022 {n} `({t})`")
                    _tg_post("\n".join(lines))

                elif text == "/market":
                    _tg_post(
                        f"\U0001f555 *Market Status*\n"
                        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        f"\U0001f4c8 NSE    : {'\U0001f7e2 OPEN' if is_nse_open() else '\U0001f534 CLOSED'} (09:15\u201315:30 Mon-Fri)\n"
                        f"\U0001faa8 MCX    : {'\U0001f7e2 OPEN' if is_mcx_open() else '\U0001f534 CLOSED'} (09:00\u201323:30 Mon-Sat)\n"
                        f"\U0001fa99 Crypto : \U0001f7e2 ALWAYS OPEN (24/7)\n"
                        f"\U0001f550 Now    : {datetime.now(IST).strftime('%d %b  %H:%M IST')}"
                    )

                elif text == "/stop":
                    _tg_post("\U0001f6d1 *Bot stopping...*")
                    log.info("Stop command via Telegram.")
                    os._exit(0)

                else:
                    _tg_post(f"\u2753 Unknown: `{text}`\nType /start for commands.")

        except Exception as e:
            log.error(f"Polling error: {e}")
        time.sleep(1)

# ────────────────────────────────────────────────────────
# MAIN LOOP
# ────────────────────────────────────────────────────────
def main():
    global summary_sent_today, daily_signals
    if not GEMINI_API_KEY:
        log.critical("GEMINI_API_KEY missing."); raise SystemExit(1)
    genai.configure(api_key=GEMINI_API_KEY)

    total = len(ALL_SYMBOLS)
    log.info("=" * 55)
    log.info("  TradingBot v3.1")
    log.info(f"  Indices:{len(NSE_INDICES)} Stocks:{len(NSE_STOCKS)} MCX:{len(MCX_COMMODITIES)} Crypto:{len(CRYPTO)}")
    log.info(f"  Total: {total} symbols | Scan every {LOOP_SLEEP_SEC//60} min")
    log.info("=" * 55)

    _tg_post(
        f"\u2705 *TradingBot v3.1 Online*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4c8 Indices : {len(NSE_INDICES)}  \U0001f3e2 Stocks: {len(NSE_STOCKS)}\n"
        f"\U0001faa8 MCX     : {len(MCX_COMMODITIES)}  \U0001fa99 Crypto: {len(CRYPTO)} (24/7)\n"
        f"\U0001f4ca Total   : *{total} symbols*\n"
        f"\u23f1 Scan every {LOOP_SLEEP_SEC//60} min | Min conf {MIN_CONFIDENCE}%\n"
        f"Type /start for commands"
    )

    threading.Thread(target=poll_telegram_commands, daemon=True).start()

    while True:
        now_ist = datetime.now(IST)
        if now_ist.hour == 0 and now_ist.minute < 15:
            daily_signals = []; summary_sent_today = False
        if is_summary_time() and not summary_sent_today:
            send_daily_summary(); summary_sent_today = True

        log.info(f"-- Scan @ {now_ist.strftime('%H:%M IST')} --")
        scanned = 0
        for name, ticker in ALL_SYMBOLS.items():
            if should_scan(name):
                scan_symbol(name, ticker)
                scanned += 1
                time.sleep(2)
        log.info(f"-- Done ({scanned}/{total} scanned). Sleep {LOOP_SLEEP_SEC//60}m --")
        time.sleep(LOOP_SLEEP_SEC)


if __name__ == "__main__":
    main()
