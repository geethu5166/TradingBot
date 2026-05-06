"""
TradingBot v3.2
- /signal BTC           -> Full AI signal for any symbol
- /signal NIFTY 24000 CE -> Options signal with Greeks context
- KotakNeo read-only    -> /portfolio, /positions, /orders, /pnl
- @REDBOXINDIA Twitter  -> News context fed into AI analysis
- 104 symbols scanned   -> 15 Indices + 50 Stocks + 9 MCX + 30 Crypto
- Gemini 1.5 Flash AI   -> Why-This-Trade + 3 Targets + Options details
- Telegram alerts       -> Full signal cards with T1/T2/T3 + SL

Commands:
  /start             Help
  /signal <sym>      Full signal: /signal BTC  or  /signal NIFTY 24000 CE
  /signal <sym> <strike> <CE/PE>  Options signal
  /portfolio         KotakNeo holdings
  /positions         KotakNeo open positions
  /orders            KotakNeo today's orders
  /pnl               KotakNeo P&L summary
  /news              Latest @REDBOXINDIA tweets
  /status            Bot stats
  /signals           Today's auto signals
  /indices /stocks /mcx /crypto /market
  /stop
"""

import os, re, json, time, logging, threading, traceback
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from typing import Optional

import requests
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from dotenv import load_dotenv
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, ADXIndicator, SMAIndicator, EMAIndicator, CCIIndicator
from ta.volatility import AverageTrueRange, BollingerBands

load_dotenv()
IST       = ZoneInfo("Asia/Kolkata")
BOT_START = datetime.now(IST)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")],
)
log = logging.getLogger("TradingBot")

# ─────────────────────────────────────────────
# CONFIG — all from .env
# ─────────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
KOTAK_API_KEY       = os.getenv("KOTAK_API_KEY", "")        # READ-ONLY, NO TRADING
KOTAK_ACCESS_TOKEN  = os.getenv("KOTAK_ACCESS_TOKEN", "")   # generate from Neo dashboard
TWITTER_BEARER      = os.getenv("TWITTER_BEARER_TOKEN", "") # optional for Twitter API v2
REDBOX_USER_ID      = "REDBOXINDIA"                          # @REDBOXINDIA handle

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

# ─────────────────────────────────────────────
# SYMBOL MAPS
# ─────────────────────────────────────────────
NSE_INDICES: dict[str, str] = {
    "NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK", "SENSEX": "^BSESN",
    "NIFTY IT": "^CNXIT", "NIFTY PHARMA": "^CNXPHARMA", "NIFTY AUTO": "^CNXAUTO",
    "NIFTY FMCG": "^CNXFMCG", "NIFTY METAL": "^CNXMETAL", "NIFTY REALTY": "^CNXREALTY",
    "NIFTY ENERGY": "^CNXENERGY", "NIFTY INFRA": "^CNXINFRA",
    "NIFTY MIDCAP 50": "^NSEMDCP50", "NIFTY SMALLCAP": "^CNXSC",
    "NIFTY NEXT 50": "^NSMIDCP", "INDIA VIX": "^INDIAVIX",
}

NSE_STOCKS: dict[str, str] = {
    "HDFC BANK": "HDFCBANK.NS", "ICICI BANK": "ICICIBANK.NS", "AXIS BANK": "AXISBANK.NS",
    "SBI": "SBIN.NS", "KOTAK BANK": "KOTAKBANK.NS", "INDUSIND": "INDUSINDBK.NS",
    "BAJFINANCE": "BAJFINANCE.NS", "BAJAJFINSV": "BAJAJFINSV.NS",
    "HDFCLIFE": "HDFCLIFE.NS", "SBILIFE": "SBILIFE.NS",
    "TCS": "TCS.NS", "INFOSYS": "INFY.NS", "WIPRO": "WIPRO.NS",
    "HCLTECH": "HCLTECH.NS", "TECHM": "TECHM.NS", "LTIM": "LTIM.NS", "MPHASIS": "MPHASIS.NS",
    "RELIANCE": "RELIANCE.NS", "ONGC": "ONGC.NS", "BPCL": "BPCL.NS",
    "IOCL": "IOC.NS", "NTPC": "NTPC.NS", "POWERGRID": "POWERGRID.NS",
    "ADANIGREEN": "ADANIGREEN.NS", "ADANIPORTS": "ADANIPORTS.NS", "ADANIENT": "ADANIENT.NS",
    "TATAMOTORS": "TATAMOTORS.NS", "MARUTI": "MARUTI.NS", "M&M": "M&M.NS",
    "EICHERMOT": "EICHERMOT.NS", "HEROMOTOCO": "HEROMOTOCO.NS", "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "SUNPHARMA": "SUNPHARMA.NS", "DRREDDY": "DRREDDY.NS", "CIPLA": "CIPLA.NS", "DIVISLAB": "DIVISLAB.NS",
    "TATASTEEL": "TATASTEEL.NS", "HINDALCO": "HINDALCO.NS", "JSWSTEEL": "JSWSTEEL.NS",
    "COALINDIA": "COALINDIA.NS", "VEDL": "VEDL.NS",
    "HINDUNILVR": "HINDUNILVR.NS", "ITC": "ITC.NS", "NESTLEIND": "NESTLEIND.NS", "BRITANNIA": "BRITANNIA.NS",
    "LT": "LT.NS", "ULTRACEMCO": "ULTRACEMCO.NS", "ASIANPAINT": "ASIANPAINT.NS",
    "TITAN": "TITAN.NS", "ZOMATO": "ZOMATO.NS", "PAYTM": "PAYTM.NS",
}

MCX_COMMODITIES: dict[str, str] = {
    "GOLD MCX": "GC=F", "SILVER MCX": "SI=F", "CRUDE OIL MCX": "CL=F",
    "NATURAL GAS MCX": "NG=F", "COPPER MCX": "HG=F", "ZINC MCX": "ZC=F",
    "LEAD MCX": "PA=F", "ALUMINIUM MCX": "ALI=F", "NICKEL MCX": "NI=F",
}

CRYPTO: dict[str, str] = {
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "BNB": "BNB-USD",
    "SOLANA": "SOL-USD", "XRP": "XRP-USD", "CARDANO": "ADA-USD",
    "AVALANCHE": "AVAX-USD", "DOGECOIN": "DOGE-USD", "POLKADOT": "DOT-USD",
    "CHAINLINK": "LINK-USD", "POLYGON": "POL-USD", "SHIBA INU": "SHIB-USD",
    "LITECOIN": "LTC-USD", "TRON": "TRX-USD", "UNISWAP": "UNI-USD",
    "STELLAR": "XLM-USD", "MONERO": "XMR-USD", "ATOM": "ATOM-USD",
    "NEAR": "NEAR-USD", "FILECOIN": "FIL-USD", "APTOS": "APT-USD",
    "ARBITRUM": "ARB-USD", "SUI": "SUI-USD", "INJECTIVE": "INJ-USD",
    "OPTIMISM": "OP-USD", "PEPE": "PEPE-USD", "FLOKI": "FLOKI-USD",
    "WIF": "WIF-USD", "BONK": "BONK-USD", "NOTCOIN": "NOT-USD",
}

# Shortcode aliases for /signal command (user types short name)
SYMBOL_ALIAS: dict[str, str] = {
    "BTC": "BITCOIN", "ETH": "ETHEREUM", "BNB": "BNB", "SOL": "SOLANA",
    "XRP": "XRP", "ADA": "CARDANO", "AVAX": "AVALANCHE", "DOGE": "DOGECOIN",
    "DOT": "POLKADOT", "LINK": "CHAINLINK", "MATIC": "POLYGON", "POL": "POLYGON",
    "SHIB": "SHIBA INU", "LTC": "LITECOIN", "TRX": "TRON", "UNI": "UNISWAP",
    "XLM": "STELLAR", "XMR": "MONERO", "NEAR": "NEAR", "FIL": "FILECOIN",
    "APT": "APTOS", "ARB": "ARBITRUM", "SUI": "SUI", "INJ": "INJECTIVE",
    "OP": "OPTIMISM", "PEPE": "PEPE", "FLOKI": "FLOKI", "WIF": "WIF",
    "BONK": "BONK", "NOT": "NOTCOIN",
    "NIFTY": "NIFTY 50", "BANKNIFTY": "BANK NIFTY", "SENSEX": "SENSEX",
    "VIX": "INDIA VIX", "NIFTYIT": "NIFTY IT", "NIFTYPHARMA": "NIFTY PHARMA",
    "NIFTYAUTO": "NIFTY AUTO", "NIFTYFMCG": "NIFTY FMCG", "NIFTYMETAL": "NIFTY METAL",
    "GOLD": "GOLD MCX", "SILVER": "SILVER MCX", "CRUDE": "CRUDE OIL MCX",
    "CRUDEOIL": "CRUDE OIL MCX", "NATGAS": "NATURAL GAS MCX", "COPPER": "COPPER MCX",
    "RELIANCE": "RELIANCE", "TCS": "TCS", "INFY": "INFOSYS", "INFOSYS": "INFOSYS",
    "HDFC": "HDFC BANK", "HDFCBANK": "HDFC BANK", "ICICI": "ICICI BANK",
    "SBIN": "SBI", "SBI": "SBI", "AXISBANK": "AXIS BANK", "AXIS": "AXIS BANK",
    "WIPRO": "WIPRO", "HCLTECH": "HCLTECH", "TATAMOTORS": "TATAMOTORS",
    "MARUTI": "MARUTI", "SUNPHARMA": "SUNPHARMA", "DRREDDY": "DRREDDY",
    "CIPLA": "CIPLA", "TATASTEEL": "TATASTEEL", "HINDALCO": "HINDALCO",
    "ITC": "ITC", "LT": "LT", "ZOMATO": "ZOMATO", "PAYTM": "PAYTM",
}

ALL_SYMBOLS: dict[str, str] = {**NSE_INDICES, **NSE_STOCKS, **MCX_COMMODITIES, **CRYPTO}

SYMBOL_CATEGORY: dict[str, str] = {}
for k in NSE_INDICES:     SYMBOL_CATEGORY[k] = "NSE Index"
for k in NSE_STOCKS:      SYMBOL_CATEGORY[k] = "NSE Stock"
for k in MCX_COMMODITIES: SYMBOL_CATEGORY[k] = "MCX Commodity"
for k in CRYPTO:          SYMBOL_CATEGORY[k] = "Crypto"

def price_unit(name: str) -> str:
    return "$" if SYMBOL_CATEGORY.get(name, "NSE Stock") in ("Crypto", "MCX Commodity") else "Rs."

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
last_alert_time: dict[str, float] = {}
daily_signals:   list[dict]       = []
summary_sent_today: bool          = False

# ─────────────────────────────────────────────
# MARKET HOURS
# ─────────────────────────────────────────────
def is_nse_open() -> bool:
    n = datetime.now(IST)
    return n.weekday() < 5 and NSE_OPEN <= n.time() <= NSE_CLOSE

def is_mcx_open() -> bool:
    n = datetime.now(IST)
    return n.weekday() < 6 and MCX_OPEN <= n.time() <= MCX_CLOSE

def should_scan(name: str) -> bool:
    cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
    if cat in ("NSE Index", "NSE Stock"): return is_nse_open()
    if cat == "MCX Commodity":            return is_mcx_open()
    return True  # Crypto always

def is_summary_time() -> bool:
    n = datetime.now(IST)
    return SUMMARY_TIME <= n.time() <= dt_time(15, 40) and n.weekday() < 5

# ─────────────────────────────────────────────
# TWITTER — @REDBOXINDIA news scraper
# Uses nitter public RSS (no API key needed)
# ─────────────────────────────────────────────
def fetch_redbox_news(limit: int = 5) -> list[str]:
    """Fetch latest tweets from @REDBOXINDIA via Nitter RSS — no API key needed."""
    nitter_urls = [
        "https://nitter.privacydev.net/REDBOXINDIA/rss",
        "https://nitter.net/REDBOXINDIA/rss",
        "https://nitter.1d4.us/REDBOXINDIA/rss",
    ]
    for url in nitter_urls:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            items = re.findall(r"<title>([^<]{10,})</title>", r.text)
            tweets = [t.strip() for t in items if "REDBOX" not in t and "Twitter" not in t][:limit]
            if tweets:
                return tweets
        except Exception:
            continue
    # Fallback: Twitter API v2 bearer token if set
    if TWITTER_BEARER:
        try:
            r = requests.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers={"Authorization": f"Bearer {TWITTER_BEARER}"},
                params={"query": "from:REDBOXINDIA", "max_results": limit,
                        "tweet.fields": "created_at,text"},
                timeout=8,
            )
            data = r.json().get("data", [])
            return [d["text"] for d in data]
        except Exception:
            pass
    return ["Could not fetch @REDBOXINDIA tweets right now."]

# ─────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> Optional[pd.Series]:
    if len(df) < 50: return None
    try:
        close, high, low = df["Close"].squeeze(), df["High"].squeeze(), df["Low"].squeeze()
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
        log.error(f"Indicator error: {e}"); return None

# ─────────────────────────────────────────────
# GEMINI AI — Full signal with 3 Targets
# ─────────────────────────────────────────────
def ai_analysis_full(symbol: str, d: pd.Series, category: str,
                     news: list[str] = None,
                     option_strike: str = None,
                     option_type: str = None) -> Optional[dict]:
    """Returns signal with T1/T2/T3, SL, entry, risk level, why bullets."""
    try:
        model  = genai.GenerativeModel("gemini-1.5-flash")
        change = ((float(d["Close"]) - float(d["prev_close"])) / float(d["prev_close"])) * 100
        unit   = price_unit(symbol)
        news_block = ""
        if news:
            news_block = "\n--- MARKET NEWS (@REDBOXINDIA) ---\n"
            for i, n in enumerate(news[:4], 1):
                news_block += f"{i}. {n}\n"

        options_block = ""
        if option_strike and option_type:
            options_block = f"""
--- OPTIONS CONTEXT ---
Strike: {option_strike}  Type: {option_type.upper()}
Underlying Spot: {unit}{float(d['Close']):.2f}
Note: Analyse this as an OPTIONS trade. Consider:
- Time decay (theta) risk if expiry is near
- Delta approximation based on strike vs spot
- Implied volatility context from BB Width
- Whether CE (bullish) or PE (bearish) aligns with the technical bias
- Suggest approximate option premium entry range
"""

        prompt = f"""
You are an elite quant hedge fund CIO with options expertise.
Analyse this instrument and give a COMPLETE trading plan.

INSTRUMENT  : {symbol}
CATEGORY    : {category}
PRICE       : {unit}{float(d['Close']):.4f}  ({change:+.2f}%)
TIMEFRAME   : 15-min candles

--- TREND ---
EMA9={float(d['ema9']):.2f}  EMA21={float(d['ema21']):.2f}
SMA50={float(d['sma50']):.2f}  SMA200={float(d['sma200']):.2f}
ADX={float(d['adx']):.1f} (+DI={float(d['adx_pos']):.1f} -DI={float(d['adx_neg']):.1f})

--- MOMENTUM ---
RSI={float(d['rsi']):.1f}  CCI={float(d['cci']):.1f}
MACD Hist={float(d['macd_dif']):.4f}  Stoch K={float(d['stoch_k']):.1f} D={float(d['stoch_d']):.1f}

--- VOLATILITY ---
ATR={float(d['atr']):.4f}
BB Upper={float(d['bb_upper']):.2f}  Lower={float(d['bb_lower']):.2f}  Width={float(d['bb_width']):.4f}

--- VOLUME ---
Vol Ratio = {float(d['vol_ratio']):.2f}x (vs 20-day avg)
{news_block}{options_block}
INSTRUCTIONS:
1. Signal: BUY / SELL / HOLD
2. Entry: best price to enter (current ± 0.1%)
3. Stop Loss: 1.5x ATR below entry (BUY) or above entry (SELL)
4. Target1: conservative (1.5:1 R:R)
5. Target2: moderate  (2.5:1 R:R)
6. Target3: aggressive (4:1 R:R)
7. Risk Level: LOW / MEDIUM / HIGH  (based on ADX, BB width, VIX if available)
8. Confidence: 0-100 (confluence of agreeing indicators)
9. Rationale: one crisp sentence
10. Why bullets: 5 bullets, each starts with INDICATOR NAME in caps
11. Risk Note: one sentence on what could invalidate this trade
12. If ADX < 18, signal = HOLD
13. If options context given, add option_advice field with premium range, expiry tip, delta estimate

Return ONLY valid JSON (no markdown):
{{"signal":"BUY","confidence":82,"risk_level":"MEDIUM",
  "entry":1234.00,"sl":1200.00,
  "t1":1270.00,"t2":1310.00,"t3":1370.00,
  "rationale":"...",
  "why":["RSI: ...","MACD: ...","EMA: ...","ADX: ...","VOLUME: ..."],
  "risk_note":"Trade invalidates if price closes below SL on 15m.",
  "option_advice":"Buy 24000 CE at 180-200 premium, prefer weekly expiry, delta ~0.45"}}
"""
        resp = model.generate_content(prompt)
        raw  = re.sub(r"```(?:json)?", "", resp.text.strip()).replace("```", "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"[{symbol}] JSON parse failed: {e}")
    except Exception as e:
        log.error(f"[{symbol}] Gemini error: {e}")
    return None

# ─────────────────────────────────────────────
# KOTAK NEO — READ-ONLY (no trading)
# ─────────────────────────────────────────────
KOTAK_BASE = "https://gw-napi.kotaksecurities.com"

def _kotak_headers() -> dict:
    return {
        "Authorization": f"Bearer {KOTAK_ACCESS_TOKEN}",
        "Api-key": KOTAK_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def kotak_get_holdings() -> dict:
    """GET /Holdings/1.0/holdings  — read only."""
    if not KOTAK_API_KEY or not KOTAK_ACCESS_TOKEN:
        return {"error": "KotakNeo credentials not set in .env"}
    try:
        r = requests.get(f"{KOTAK_BASE}/Holdings/1.0/holdings",
                         headers=_kotak_headers(), timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def kotak_get_positions() -> dict:
    """GET /Orders/2.0/quick/user/positions — read only."""
    if not KOTAK_API_KEY or not KOTAK_ACCESS_TOKEN:
        return {"error": "KotakNeo credentials not set in .env"}
    try:
        r = requests.get(f"{KOTAK_BASE}/Orders/2.0/quick/user/positions",
                         headers=_kotak_headers(), timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def kotak_get_orders() -> dict:
    """GET /Orders/2.0/quick/user/orders — read only."""
    if not KOTAK_API_KEY or not KOTAK_ACCESS_TOKEN:
        return {"error": "KotakNeo credentials not set in .env"}
    try:
        r = requests.get(f"{KOTAK_BASE}/Orders/2.0/quick/user/orders",
                         headers=_kotak_headers(), timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def kotak_get_pnl() -> dict:
    """Derive P&L from positions — read only."""
    pos = kotak_get_positions()
    if "error" in pos:
        return pos
    try:
        items = pos.get("data", {}).get("net", []) or []
        total_pnl = 0.0
        lines = []
        for p in items:
            sym = p.get("trdSym") or p.get("sym", "?")
            qty = float(p.get("flQty") or p.get("qty") or 0)
            buy = float(p.get("buyAmt") or 0)
            sell= float(p.get("sellAmt") or 0)
            pnl = sell - buy
            total_pnl += pnl
            if qty != 0 or pnl != 0:
                lines.append({"symbol": sym, "qty": qty, "pnl": round(pnl, 2)})
        return {"positions": lines, "total_pnl": round(total_pnl, 2)}
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────
def _tg_post(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10)
        r.raise_for_status(); return True
    except Exception as e:
        log.error(f"TG error: {e}"); return False

def cat_emoji(cat: str) -> str:
    return {"NSE Index": "\U0001f4c8", "NSE Stock": "\U0001f3e2",
            "MCX Commodity": "\U0001faa8", "Crypto": "\U0001fa99"}.get(cat, "\U0001f4ca")

def risk_emoji(r: str) -> str:
    return {"LOW": "\U0001f7e2", "MEDIUM": "\U0001f7e1", "HIGH": "\U0001f534"}.get(r.upper(), "\u26aa")

def format_full_signal(symbol: str, sig: dict, is_options: bool = False,
                       strike: str = None, opt_type: str = None) -> str:
    """Format the full /signal response card."""
    cat   = SYMBOL_CATEGORY.get(symbol, "NSE Stock")
    unit  = price_unit(symbol)
    arrow = "\U0001f680" if sig["signal"] == "BUY" else ("\U0001f53b" if sig["signal"] == "SELL" else "\u23f8")
    ce    = cat_emoji(cat)
    rl    = sig.get("risk_level", "MEDIUM")
    rr1   = abs(sig["t1"] - sig["entry"]) / max(abs(sig["sl"] - sig["entry"]), 0.01)
    rr2   = abs(sig["t2"] - sig["entry"]) / max(abs(sig["sl"] - sig["entry"]), 0.01)
    rr3   = abs(sig["t3"] - sig["entry"]) / max(abs(sig["sl"] - sig["entry"]), 0.01)

    title = f"{symbol}"
    if is_options and strike and opt_type:
        title += f" {strike} {opt_type.upper()}"

    why_block = ""
    for b in sig.get("why", []):
        why_block += f"  \u2022 {b}\n"

    opt_block = ""
    if sig.get("option_advice"):
        opt_block = f"\n\U0001f4dc *Options Advice:*\n  {sig['option_advice']}\n"

    msg = (
        f"{arrow} *{sig['signal']} SIGNAL* {ce}\n"
        f"*{title}* \u2014 _{cat}_\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4cd *Entry        :* `{unit}{sig['entry']:.2f}`\n"
        f"\U0001f6d1 *Stop Loss    :* `{unit}{sig['sl']:.2f}`\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f3af *Target 1     :* `{unit}{sig['t1']:.2f}`  \u2696\ufe0f R:R `1:{rr1:.1f}`\n"
        f"\U0001f3af *Target 2     :* `{unit}{sig['t2']:.2f}`  \u2696\ufe0f R:R `1:{rr2:.1f}`\n"
        f"\U0001f3af *Target 3     :* `{unit}{sig['t3']:.2f}`  \u2696\ufe0f R:R `1:{rr3:.1f}`\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4ca *Confidence   :* `{sig['confidence']}%`\n"
        f"{risk_emoji(rl)} *Risk Level   :* `{rl}`\n"
        f"\U0001f4dd *Summary      :* {sig['rationale']}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f9e0 *Why This Trade?*\n{why_block}"
        f"\u26a0\ufe0f *Risk Note    :* _{sig.get('risk_note', 'Use strict SL.')}_\n"
        f"{opt_block}"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f550 {datetime.now(IST).strftime('%d %b %Y  %H:%M IST')}\n"
        f"_Not financial advice. Trade responsibly._"
    )
    return msg

def send_signal_alert(symbol: str, sig: dict):
    _tg_post(format_full_signal(symbol, sig))
    log.info(f"[{symbol}] {sig['signal']} @ {price_unit(symbol)}{sig['entry']:.2f} | {sig['confidence']}%")

def send_daily_summary():
    buys  = [s for s in daily_signals if s["signal"] == "BUY"]
    sells = [s for s in daily_signals if s["signal"] == "SELL"]
    if not daily_signals:
        _tg_post("\U0001f4cb *Daily Summary* \u2014 No signals today."); return
    lines = [
        f"\U0001f4cb *Daily Summary \u2014 {datetime.now(IST).strftime('%d %b %Y')}*",
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"Total:{len(daily_signals)}  \U0001f680 BUY:{len(buys)}  \U0001f53b SELL:{len(sells)}", ""
    ]
    for s in daily_signals:
        e  = "\U0001f680" if s["signal"] == "BUY" else "\U0001f53b"
        ce = cat_emoji(SYMBOL_CATEGORY.get(s["symbol"], ""))
        u  = price_unit(s["symbol"])
        lines.append(f"{e}{ce} {s['symbol']} | {u}{s['entry']:.2f} | {s['confidence']}% | {s.get('risk_level','?')}")
    _tg_post("\n".join(lines))

# ─────────────────────────────────────────────
# COOLDOWN & AUTO-SCAN
# ─────────────────────────────────────────────
def is_on_cooldown(symbol: str) -> bool:
    return (time.time() - last_alert_time.get(symbol, 0)) < (COOLDOWN_MIN * 60)

def resolve_symbol(raw: str) -> Optional[str]:
    """Resolve user input like 'BTC', 'nifty', 'HDFCBANK' to canonical name."""
    u = raw.upper().strip()
    if u in SYMBOL_ALIAS:           return SYMBOL_ALIAS[u]
    if u in ALL_SYMBOLS:            return u
    for k in ALL_SYMBOLS:
        if k.upper() == u:          return k
    return None

def scan_symbol(name: str, ticker: str):
    try:
        df = yf.download(ticker, period=SCAN_PERIOD, interval=INTERVAL,
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            log.warning(f"[{name}] Insufficient data"); return
        data = compute_indicators(df)
        if data is None: return
        news = fetch_redbox_news(3)
        cat  = SYMBOL_CATEGORY.get(name, "NSE Stock")
        sig  = ai_analysis_full(name, data, cat, news=news)
        if sig is None: return
        log.info(f"[{name}] {sig['signal']} | Conf={sig['confidence']}% | Risk={sig.get('risk_level','?')}")
        if sig["signal"] == "HOLD": return
        if sig["confidence"] < MIN_CONFIDENCE: return
        if is_on_cooldown(name): return
        send_signal_alert(name, sig)
        last_alert_time[name] = time.time()
        sig["symbol"] = name
        daily_signals.append(sig)
    except Exception:
        log.error(f"[{name}]\n{traceback.format_exc()}")

# ─────────────────────────────────────────────
# TELEGRAM COMMAND HANDLER
# ─────────────────────────────────────────────
def handle_command(text: str):
    """Process one incoming Telegram command."""
    parts = text.strip().split()
    cmd   = parts[0].lower()

    # ── /signal ──────────────────────────────
    if cmd == "/signal":
        if len(parts) < 2:
            _tg_post(
                "\u2753 *Usage:*\n"
                "`/signal BTC`\n"
                "`/signal NIFTY`\n"
                "`/signal NIFTY 24000 CE`\n"
                "`/signal BANKNIFTY 52000 PE`\n"
                "`/signal RELIANCE`"
            ); return

        # Detect options: /signal NIFTY 24000 CE
        is_option  = len(parts) >= 4 and parts[-1].upper() in ("CE", "PE")
        if is_option:
            raw_sym   = " ".join(parts[1:-2])
            strike    = parts[-2]
            opt_type  = parts[-1].upper()
        else:
            raw_sym   = " ".join(parts[1:])
            strike    = None
            opt_type  = None

        canonical = resolve_symbol(raw_sym)
        if canonical is None:
            _tg_post(f"\u274c Symbol `{raw_sym}` not found.\nTry: BTC, NIFTY, RELIANCE, GOLD, etc."); return

        ticker = ALL_SYMBOLS.get(canonical)
        _tg_post(f"\U0001f50d Analysing *{canonical}*{'  ' + strike + ' ' + opt_type if is_option else ''}... please wait.")

        try:
            df = yf.download(ticker, period=SCAN_PERIOD, interval=INTERVAL,
                             progress=False, auto_adjust=True)
            if df.empty or len(df) < 50:
                _tg_post(f"\u274c Not enough data for `{canonical}`.`"); return
            data = compute_indicators(df)
            if data is None:
                _tg_post("\u274c Indicator calculation failed."); return
            news = fetch_redbox_news(4)
            cat  = SYMBOL_CATEGORY.get(canonical, "NSE Stock")
            sig  = ai_analysis_full(canonical, data, cat, news=news,
                                    option_strike=strike, option_type=opt_type)
            if sig is None:
                _tg_post("\u274c AI analysis failed. Try again."); return
            _tg_post(format_full_signal(canonical, sig,
                                        is_options=is_option, strike=strike, opt_type=opt_type))
        except Exception:
            _tg_post("\u274c Error fetching data. Try again.")
            log.error(traceback.format_exc())

    # ── /news ─────────────────────────────────
    elif cmd == "/news":
        _tg_post("\U0001f4f0 Fetching @REDBOXINDIA tweets...")
        tweets = fetch_redbox_news(8)
        lines  = ["\U0001f426 *@REDBOXINDIA Latest News*",
                  "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for i, t in enumerate(tweets, 1):
            lines.append(f"{i}. {t}")
        lines.append("\n_Source: @REDBOXINDIA on X/Twitter_")
        _tg_post("\n".join(lines))

    # ── /portfolio ───────────────────────────
    elif cmd == "/portfolio":
        _tg_post("\U0001f4bc Fetching KotakNeo holdings...")
        data = kotak_get_holdings()
        if "error" in data:
            _tg_post(f"\u274c KotakNeo Error: {data['error']}\n\nMake sure KOTAK\_ACCESS\_TOKEN is set in .env"); return
        holdings = data.get("data", {}).get("holdings", []) or data.get("data", [])
        if not holdings:
            _tg_post("\U0001f4bc *Portfolio* \u2014 No holdings found."); return
        lines = [f"\U0001f4bc *KotakNeo Portfolio ({len(holdings)} stocks)*",
                 "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        total_val = 0.0
        for h in holdings:
            sym  = h.get("trdSym") or h.get("symbol", "?")
            qty  = h.get("qty") or h.get("holdQty", 0)
            ltp  = float(h.get("ltp") or h.get("mktValue") or 0)
            avg  = float(h.get("avgCost") or h.get("avgPrice") or 0)
            val  = ltp * float(qty)
            pnl  = (ltp - avg) * float(qty)
            pct  = ((ltp - avg) / avg * 100) if avg > 0 else 0
            arrow= "\U0001f7e2" if pnl >= 0 else "\U0001f534"
            total_val += val
            lines.append(f"{arrow} *{sym}* | Qty:{qty} | LTP:{ltp:.2f} | PnL:{pnl:+.0f} ({pct:+.1f}%)")
        lines.append(f"\n\U0001f4b0 *Total Value: Rs.{total_val:,.0f}*")
        _tg_post("\n".join(lines))

    # ── /positions ───────────────────────────
    elif cmd == "/positions":
        _tg_post("\U0001f4c5 Fetching KotakNeo positions...")
        data = kotak_get_positions()
        if "error" in data:
            _tg_post(f"\u274c KotakNeo Error: {data['error']}"); return
        positions = data.get("data", {}).get("net", []) or []
        if not positions:
            _tg_post("\U0001f4c5 *Positions* \u2014 No open positions."); return
        lines = [f"\U0001f4c5 *Open Positions ({len(positions)})*",
                 "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for p in positions:
            sym  = p.get("trdSym") or p.get("sym", "?")
            qty  = p.get("flQty") or p.get("qty", 0)
            ltp  = float(p.get("ltp") or 0)
            avg  = float(p.get("avgCost") or p.get("avgPrice") or 0)
            pnl  = (ltp - avg) * float(qty)
            arrow= "\U0001f7e2" if pnl >= 0 else "\U0001f534"
            lines.append(f"{arrow} *{sym}* | Qty:{qty} | LTP:{ltp:.2f} | Avg:{avg:.2f} | PnL:{pnl:+.0f}")
        _tg_post("\n".join(lines))

    # ── /orders ──────────────────────────────
    elif cmd == "/orders":
        _tg_post("\U0001f4cb Fetching KotakNeo orders...")
        data = kotak_get_orders()
        if "error" in data:
            _tg_post(f"\u274c KotakNeo Error: {data['error']}"); return
        orders = data.get("data", []) or []
        if not orders:
            _tg_post("\U0001f4cb *Orders* \u2014 No orders today."); return
        lines = [f"\U0001f4cb *Today's Orders ({len(orders)})*",
                 "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for o in orders:
            sym   = o.get("trdSym") or o.get("sym", "?")
            side  = o.get("trnsTp") or o.get("side", "?")
            qty   = o.get("qty", "?")
            price = o.get("prc") or o.get("price", "?")
            stat  = o.get("ordSt") or o.get("status", "?")
            icon  = "\U0001f7e2" if "BUY" in str(side).upper() else "\U0001f534"
            lines.append(f"{icon} *{sym}* | {side} {qty} @ {price} | *{stat}*")
        _tg_post("\n".join(lines))

    # ── /pnl ─────────────────────────────────
    elif cmd == "/pnl":
        _tg_post("\U0001f4b9 Calculating P&L...")
        data = kotak_get_pnl()
        if "error" in data:
            _tg_post(f"\u274c KotakNeo Error: {data['error']}"); return
        positions = data.get("positions", [])
        total     = data.get("total_pnl", 0)
        icon      = "\U0001f7e2" if total >= 0 else "\U0001f534"
        lines = ["\U0001f4b9 *Today's P&L Summary*",
                 "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for p in positions:
            a = "\U0001f7e2" if p["pnl"] >= 0 else "\U0001f534"
            lines.append(f"{a} {p['symbol']} | Qty:{p['qty']} | PnL: Rs.{p['pnl']:+.2f}")
        lines.append(f"\n{icon} *Total P&L: Rs.{total:+.2f}*")
        _tg_post("\n".join(lines))

    # ── /status ──────────────────────────────
    elif cmd == "/status":
        uptime = datetime.now(IST) - BOT_START
        h, rem = divmod(int(uptime.total_seconds()), 3600)
        m = rem // 60
        _tg_post(
            f"\u2705 *TradingBot v3.2 Status*\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f550 Uptime      : {h}h {m}m\n"
            f"\U0001f4c8 Indices     : {len(NSE_INDICES)}\n"
            f"\U0001f3e2 Stocks      : {len(NSE_STOCKS)}\n"
            f"\U0001faa8 MCX         : {len(MCX_COMMODITIES)}\n"
            f"\U0001fa99 Crypto      : {len(CRYPTO)}\n"
            f"\U0001f4ca Total       : {len(ALL_SYMBOLS)} symbols\n"
            f"\U0001f4e1 Signals     : {len(daily_signals)} today\n"
            f"\U0001f7e2 NSE         : {'OPEN' if is_nse_open() else 'CLOSED'}\n"
            f"\U0001f7e2 MCX         : {'OPEN' if is_mcx_open() else 'CLOSED'}\n"
            f"\U0001fa99 Crypto      : ALWAYS OPEN\n"
            f"\U0001f426 News Source : @REDBOXINDIA\n"
            f"\U0001f4bc KotakNeo    : {'\u2705 Connected' if KOTAK_API_KEY else '\u274c Not set'}\n"
            f"\U0001f550 {datetime.now(IST).strftime('%d %b %Y  %H:%M IST')}"
        )

    elif cmd in ["/start", "/help"]:
        _tg_post(
            "\U0001f916 *TradingBot v3.2*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            "\U0001f50d *Signal Commands:*\n"
            "`/signal BTC` \u2014 full BTC signal\n"
            "`/signal NIFTY` \u2014 Nifty signal\n"
            "`/signal NIFTY 24000 CE` \u2014 options signal\n"
            "`/signal BANKNIFTY 52000 PE`\n\n"
            "\U0001f4f0 *News:*\n"
            "`/news` \u2014 @REDBOXINDIA latest\n\n"
            "\U0001f4bc *KotakNeo (Read-Only):*\n"
            "`/portfolio` \u2014 your holdings\n"
            "`/positions` \u2014 open positions\n"
            "`/orders`    \u2014 today's orders\n"
            "`/pnl`       \u2014 P&L summary\n\n"
            "\U0001f4ca *Market:*\n"
            "`/signals /indices /stocks /mcx /crypto /market /status /stop`"
        )

    elif cmd == "/signals":
        if not daily_signals:
            _tg_post("\U0001f4cb No auto-signals fired yet today.")
        else:
            lines = [f"\U0001f4cb *Auto Signals Today ({len(daily_signals)})*",
                     "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
            for s in daily_signals:
                e  = "\U0001f680" if s["signal"] == "BUY" else "\U0001f53b"
                ce = cat_emoji(SYMBOL_CATEGORY.get(s["symbol"], ""))
                u  = price_unit(s["symbol"])
                rl = s.get("risk_level", "?")
                lines.append(f"{e}{ce} *{s['symbol']}* | {u}{s['entry']:.2f} | {s['confidence']}% | {rl}")
            _tg_post("\n".join(lines))

    elif cmd in ["/indices", "/nse"]:
        lines = ["\U0001f4c8 *All Indian Indices*", "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for n, t in NSE_INDICES.items(): lines.append(f"  \u2022 {n} `{t}`")
        _tg_post("\n".join(lines))

    elif cmd == "/stocks":
        lines = [f"\U0001f3e2 *NSE Stocks ({len(NSE_STOCKS)})*", "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        secs = {
            "Banking": ["HDFC BANK","ICICI BANK","AXIS BANK","SBI","KOTAK BANK","INDUSIND","BAJFINANCE","BAJAJFINSV","HDFCLIFE","SBILIFE"],
            "IT": ["TCS","INFOSYS","WIPRO","HCLTECH","TECHM","LTIM","MPHASIS"],
            "Energy": ["RELIANCE","ONGC","BPCL","IOCL","NTPC","POWERGRID","ADANIGREEN","ADANIPORTS","ADANIENT"],
            "Auto": ["TATAMOTORS","MARUTI","M&M","EICHERMOT","HEROMOTOCO","BAJAJ-AUTO"],
            "Pharma": ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB"],
            "Metal": ["TATASTEEL","HINDALCO","JSWSTEEL","COALINDIA","VEDL"],
            "FMCG": ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA"],
            "Others": ["LT","ULTRACEMCO","ASIANPAINT","TITAN","ZOMATO","PAYTM"],
        }
        for sec, syms in secs.items():
            lines.append(f"\n*{sec}:*"); [lines.append(f"  \u2022 {s}") for s in syms]
        _tg_post("\n".join(lines))

    elif cmd == "/mcx":
        lines = ["\U0001faa8 *MCX Commodities*", "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for n, t in MCX_COMMODITIES.items(): lines.append(f"  \u2022 {n} `{t}`")
        _tg_post("\n".join(lines))

    elif cmd == "/crypto":
        lines = [f"\U0001fa99 *Crypto 24/7 ({len(CRYPTO)})*", "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
        for n, t in CRYPTO.items(): lines.append(f"  \u2022 {n} `{t}`")
        _tg_post("\n".join(lines))

    elif cmd == "/market":
        _tg_post(
            f"\U0001f555 *Market Status*\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f4c8 NSE    : {'\U0001f7e2 OPEN' if is_nse_open() else '\U0001f534 CLOSED'} (09:15\u201315:30 Mon-Fri)\n"
            f"\U0001faa8 MCX    : {'\U0001f7e2 OPEN' if is_mcx_open() else '\U0001f534 CLOSED'} (09:00\u201323:30 Mon-Sat)\n"
            f"\U0001fa99 Crypto : \U0001f7e2 ALWAYS OPEN\n"
            f"\U0001f550 Now    : {datetime.now(IST).strftime('%d %b  %H:%M IST')}"
        )

    elif cmd == "/stop":
        _tg_post("\U0001f6d1 *Bot stopping...*")
        os._exit(0)

    else:
        _tg_post(f"\u2753 Unknown command: `{cmd}`\nType /start for help.")

# ─────────────────────────────────────────────
# TELEGRAM POLL LOOP
# ─────────────────────────────────────────────
def poll_telegram_commands():
    last_update_id = 0
    log.info("Telegram listener started.")
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
                text    = msg.get("text", "").strip()
                if chat_id != str(TELEGRAM_CHAT_ID) or not text: continue
                log.info(f"CMD: {text}")
                threading.Thread(target=handle_command, args=(text,), daemon=True).start()
        except Exception as e:
            log.error(f"Poll error: {e}")
        time.sleep(1)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    global summary_sent_today, daily_signals
    if not GEMINI_API_KEY:
        log.critical("GEMINI_API_KEY missing."); raise SystemExit(1)
    genai.configure(api_key=GEMINI_API_KEY)

    log.info("=" * 55)
    log.info("  TradingBot v3.2")
    log.info(f"  {len(ALL_SYMBOLS)} symbols | News: @REDBOXINDIA | KotakNeo: {'yes' if KOTAK_API_KEY else 'no'}")
    log.info("=" * 55)

    _tg_post(
        f"\u2705 *TradingBot v3.2 Online*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4c8 {len(NSE_INDICES)} Indices  \U0001f3e2 {len(NSE_STOCKS)} Stocks\n"
        f"\U0001faa8 {len(MCX_COMMODITIES)} MCX  \U0001fa99 {len(CRYPTO)} Crypto (24/7)\n"
        f"\U0001f4ca *{len(ALL_SYMBOLS)} total symbols*\n"
        f"\U0001f426 News: @REDBOXINDIA\n"
        f"\U0001f4bc KotakNeo: {'Read-Only Connected' if KOTAK_API_KEY else 'Not configured'}\n"
        f"\n*Try:* `/signal BTC` or `/signal NIFTY 24000 CE`"
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
        log.info(f"-- Done ({scanned}/{len(ALL_SYMBOLS)} scanned) --")
        time.sleep(LOOP_SLEEP_SEC)


if __name__ == "__main__":
    main()
