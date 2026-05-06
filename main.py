"""
TradingBot v3.4 — Production Ready

FIXES in v3.4:
  - FIX 1: yfinance MultiIndex bug — flatten_df() applied in both
            scan_symbol() and handle_signal_command() so /signal BTC works
  - FIX 2: KOTAK_API_KEY default value removed (was hardcoded UUID)
  - FIX 3: safe_json() guard on all Kotak API calls (no crash on empty/HTML response)

FEATURES:
  /signal BTC            → Full AI deep analysis on demand
  /signal NIFTY 50       → Index analysis
  /signal NIFTY 24000 CE → NSE Options AI analysis
  /signal RELIANCE       → Stock analysis
  104 symbols auto-scanned every 15 min
  Gemini 1.5 Flash AI:
    - Risk Rating (LOW/MEDIUM/HIGH)
    - Entry Zone (buy between X and Y)
    - Stop Loss
    - Target 1 (conservative)
    - Target 2 (moderate)
    - Target 3 (aggressive)
    - Why This Trade (5 indicator bullets)
    - Market Sentiment
    - Recommended Hold Time
  @REDBOXINDIA Twitter news context
  KotakNeo READ-ONLY: /portfolio /trades /pnl /positions
  Telegram locked to YOUR chat_id only

Telegram Commands:
  /signal <name>           - e.g. /signal BTC  /signal NIFTY 50  /signal NIFTY 24000 CE
  /portfolio               - KotakNeo holdings
  /trades                  - Recent trade history
  /pnl                     - Today P&L
  /positions               - Open positions
  /news                    - Latest @REDBOXINDIA tweets
  /signals                 - All bot signals today
  /status                  - Uptime & stats
  /indices                 - All Indian indices
  /stocks                  - NSE stocks list
  /mcx                     - MCX commodities
  /crypto                  - All cryptos
  /market                  - Market hours
  /stop                    - Stop bot
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

# ──────────────────────────────────────────────────────────
# BOOTSTRAP
# ──────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
KOTAK_API_KEY      = os.getenv("KOTAK_API_KEY", "")        # FIX 2: no hardcoded default
KOTAK_ACCESS_TOKEN = os.getenv("KOTAK_ACCESS_TOKEN", "")
KOTAK_USER_ID      = os.getenv("KOTAK_USER_ID", "")
TWITTER_BEARER     = os.getenv("TWITTER_BEARER_TOKEN", "")

INTERVAL       = "15m"
SCAN_PERIOD    = "5d"
LOOP_SLEEP_SEC = 900
MIN_CONFIDENCE = 72
COOLDOWN_MIN   = 60
SUMMARY_TIME   = dt_time(15, 35)
NSE_OPEN       = dt_time(9, 15)
NSE_CLOSE      = dt_time(15, 30)
MCX_OPEN       = dt_time(9, 0)
MCX_CLOSE      = dt_time(23, 30)

# ──────────────────────────────────────────────────────────
# ALL INDIAN INDICES
# ──────────────────────────────────────────────────────────
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

NSE_STOCKS: dict[str, str] = {
    "HDFC BANK":  "HDFCBANK.NS",  "ICICI BANK": "ICICIBANK.NS",
    "AXIS BANK":  "AXISBANK.NS",  "SBI":         "SBIN.NS",
    "KOTAK BANK": "KOTAKBANK.NS", "INDUSIND":    "INDUSINDBK.NS",
    "BAJFINANCE": "BAJFINANCE.NS","BAJAJFINSV":  "BAJAJFINSV.NS",
    "HDFCLIFE":   "HDFCLIFE.NS",  "SBILIFE":     "SBILIFE.NS",
    "TCS":        "TCS.NS",       "INFOSYS":     "INFY.NS",
    "WIPRO":      "WIPRO.NS",     "HCLTECH":     "HCLTECH.NS",
    "TECHM":      "TECHM.NS",     "LTIM":        "LTIM.NS",
    "MPHASIS":    "MPHASIS.NS",   "RELIANCE":    "RELIANCE.NS",
    "ONGC":       "ONGC.NS",      "BPCL":        "BPCL.NS",
    "IOCL":       "IOC.NS",       "NTPC":        "NTPC.NS",
    "POWERGRID":  "POWERGRID.NS", "ADANIGREEN":  "ADANIGREEN.NS",
    "ADANIPORTS": "ADANIPORTS.NS","ADANIENT":    "ADANIENT.NS",
    "TATAMOTORS": "TATAMOTORS.NS","MARUTI":      "MARUTI.NS",
    "M&M":        "M&M.NS",       "EICHERMOT":   "EICHERMOT.NS",
    "HEROMOTOCO": "HEROMOTOCO.NS","BAJAJ-AUTO":  "BAJAJ-AUTO.NS",
    "SUNPHARMA":  "SUNPHARMA.NS", "DRREDDY":     "DRREDDY.NS",
    "CIPLA":      "CIPLA.NS",     "DIVISLAB":    "DIVISLAB.NS",
    "TATASTEEL":  "TATASTEEL.NS", "HINDALCO":    "HINDALCO.NS",
    "JSWSTEEL":   "JSWSTEEL.NS",  "COALINDIA":   "COALINDIA.NS",
    "VEDL":       "VEDL.NS",      "HINDUNILVR":  "HINDUNILVR.NS",
    "ITC":        "ITC.NS",       "NESTLEIND":   "NESTLEIND.NS",
    "BRITANNIA":  "BRITANNIA.NS", "LT":          "LT.NS",
    "ULTRACEMCO": "ULTRACEMCO.NS","ASIANPAINT":  "ASIANPAINT.NS",
    "TITAN":      "TITAN.NS",     "ZOMATO":      "ZOMATO.NS",
    "PAYTM":      "PAYTM.NS",
}

MCX_COMMODITIES: dict[str, str] = {
    "GOLD MCX":        "GC=F",  "SILVER MCX":      "SI=F",
    "CRUDE OIL MCX":   "CL=F",  "NATURAL GAS MCX": "NG=F",
    "COPPER MCX":      "HG=F",  "ZINC MCX":        "ZC=F",
    "LEAD MCX":        "PA=F",  "ALUMINIUM MCX":   "ALI=F",
    "NICKEL MCX":      "NI=F",
}

CRYPTO: dict[str, str] = {
    "BITCOIN":   "BTC-USD",  "ETHEREUM":  "ETH-USD",   "BNB":       "BNB-USD",
    "SOLANA":    "SOL-USD",  "XRP":       "XRP-USD",   "CARDANO":   "ADA-USD",
    "AVALANCHE": "AVAX-USD", "DOGECOIN":  "DOGE-USD",  "POLKADOT":  "DOT-USD",
    "CHAINLINK": "LINK-USD", "POLYGON":   "POL-USD",   "SHIBA INU": "SHIB-USD",
    "LITECOIN":  "LTC-USD",  "TRON":      "TRX-USD",   "UNISWAP":   "UNI-USD",
    "STELLAR":   "XLM-USD",  "MONERO":    "XMR-USD",   "ATOM":      "ATOM-USD",
    "NEAR":      "NEAR-USD", "FILECOIN":  "FIL-USD",   "APTOS":     "APT-USD",
    "ARBITRUM":  "ARB-USD",  "SUI":       "SUI-USD",   "INJECTIVE": "INJ-USD",
    "OPTIMISM":  "OP-USD",   "PEPE":      "PEPE-USD",  "FLOKI":     "FLOKI-USD",
    "WIF":       "WIF-USD",  "BONK":      "BONK-USD",  "NOTCOIN":   "NOT-USD",
}

ALL_SYMBOLS: dict[str, str] = {**NSE_INDICES, **NSE_STOCKS, **MCX_COMMODITIES, **CRYPTO}

SYMBOL_CATEGORY: dict[str, str] = {}
for k in NSE_INDICES:     SYMBOL_CATEGORY[k] = "NSE Index"
for k in NSE_STOCKS:      SYMBOL_CATEGORY[k] = "NSE Stock"
for k in MCX_COMMODITIES: SYMBOL_CATEGORY[k] = "MCX Commodity"
for k in CRYPTO:          SYMBOL_CATEGORY[k] = "Crypto"

# Short alias map for /signal command
SHORT_ALIAS: dict[str, str] = {}
for full in ALL_SYMBOLS:
    SHORT_ALIAS[full.upper()] = full
SHORT_ALIAS.update({
    "BTC": "BITCOIN", "ETH": "ETHEREUM", "SOL": "SOLANA",
    "BNB": "BNB", "XRP": "XRP", "ADA": "CARDANO",
    "DOGE": "DOGECOIN", "MATIC": "POLYGON", "DOT": "POLKADOT",
    "AVAX": "AVALANCHE", "LINK": "CHAINLINK", "SHIB": "SHIBA INU",
    "LTC": "LITECOIN", "TRX": "TRON", "UNI": "UNISWAP",
    "XLM": "STELLAR", "XMR": "MONERO", "FIL": "FILECOIN",
    "APT": "APTOS", "ARB": "ARBITRUM", "INJ": "INJECTIVE",
    "OP": "OPTIMISM", "NOTCOIN": "NOTCOIN",
    "NIFTY": "NIFTY 50", "NIFTY50": "NIFTY 50",
    "BANKNIFTY": "BANK NIFTY", "SENSEX": "SENSEX",
    "GOLD": "GOLD MCX", "SILVER": "SILVER MCX",
    "CRUDE": "CRUDE OIL MCX", "CRUDEOIL": "CRUDE OIL MCX",
    "NATURALGAS": "NATURAL GAS MCX", "COPPER": "COPPER MCX",
    "RELIANCE": "RELIANCE", "TCS": "TCS", "INFY": "INFOSYS",
    "SBIN": "SBI", "HDFC": "HDFC BANK", "ICICI": "ICICI BANK",
    "WIPRO": "WIPRO", "ITC": "ITC", "ZOMATO": "ZOMATO",
    "TATAMOTORS": "TATAMOTORS", "MARUTI": "MARUTI",
})

def price_unit(name: str) -> str:
    cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
    return "$" if cat in ("Crypto", "MCX Commodity") else "Rs."

# ──────────────────────────────────────────────────────────
# STATE
# ──────────────────────────────────────────────────────────
last_alert_time: dict[str, float] = {}
daily_signals:   list[dict]       = []
summary_sent_today: bool          = False

# ──────────────────────────────────────────────────────────
# MARKET HOURS
# ──────────────────────────────────────────────────────────
def is_nse_open() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 5 and NSE_OPEN <= now.time() <= NSE_CLOSE

def is_mcx_open() -> bool:
    now = datetime.now(IST)
    return now.weekday() < 6 and MCX_OPEN <= now.time() <= MCX_CLOSE

def should_scan(name: str) -> bool:
    cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
    if cat in ("NSE Index", "NSE Stock"): return is_nse_open()
    if cat == "MCX Commodity":            return is_mcx_open()
    return True  # Crypto always

def is_summary_time() -> bool:
    now = datetime.now(IST)
    return SUMMARY_TIME <= now.time() <= dt_time(15, 40) and now.weekday() < 5

# ──────────────────────────────────────────────────────────
# FIX 1: yfinance v0.2+ MultiIndex flattener
# ──────────────────────────────────────────────────────────
def flatten_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    yfinance >= 0.2 wraps single-ticker downloads in a MultiIndex:
        columns = [('Close','BTC-USD'), ('High','BTC-USD'), ...]
    This collapses them back to simple names: Close, High, Low, Volume.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    return df


def safe_download(ticker: str, period: str = SCAN_PERIOD,
                  interval: str = INTERVAL) -> Optional[pd.DataFrame]:
    """Download + flatten. Retries with daily interval if 15m has < 50 rows."""
    for ivl in [interval, "1d"]:
        try:
            raw = yf.download(
                ticker,
                period=period if ivl == interval else "6mo",
                interval=ivl,
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if raw is None or raw.empty:
                continue
            df = flatten_df(raw.copy())
            df.dropna(subset=["Close", "High", "Low"], inplace=True)
            if len(df) >= 50:
                return df
        except Exception as e:
            log.warning(f"[{ticker}] download error ({ivl}): {e}")
    return None

# ──────────────────────────────────────────────────────────
# INDICATORS  (works on flat DataFrame only)
# ──────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> Optional[pd.Series]:
    if len(df) < 50:
        return None
    try:
        close = df["Close"].astype(float)
        high  = df["High"].astype(float)
        low   = df["Low"].astype(float)
        vol   = df["Volume"].astype(float)

        df = df.copy()
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
        df["vol_avg20"]= vol.rolling(20).mean()
        df["vol_ratio"]= vol / df["vol_avg20"].replace(0, 1)

        row = df.iloc[-1].copy()
        row["prev_close"] = float(df["Close"].iloc[-2])
        return row
    except Exception as e:
        log.error(f"Indicator error: {e}\n{traceback.format_exc()}")
        return None

# ──────────────────────────────────────────────────────────
# FIX 3: Safe JSON helper for Kotak API
# ──────────────────────────────────────────────────────────
def safe_json(resp: requests.Response) -> Optional[dict]:
    """
    KotakNeo returns HTML (login page) or empty body when token is
    missing/expired. Returns None instead of crashing with JSONDecodeError.
    """
    try:
        text = resp.text.strip()
        if not text or text.startswith("<"):
            return None
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return None

def _kotak_token_missing() -> bool:
    return not KOTAK_ACCESS_TOKEN or not KOTAK_ACCESS_TOKEN.strip()

# ──────────────────────────────────────────────────────────
# TWITTER — @REDBOXINDIA latest tweets
# ──────────────────────────────────────────────────────────
def get_redbox_news(max_tweets: int = 5) -> list[str]:
    """Fetch latest tweets from @REDBOXINDIA via Twitter API v2."""
    if not TWITTER_BEARER:
        return []
    try:
        r = requests.get(
            "https://api.twitter.com/2/users/by/username/REDBOXINDIA",
            headers={"Authorization": f"Bearer {TWITTER_BEARER}"},
            timeout=8,
        )
        uid = r.json().get("data", {}).get("id", "")
        if not uid:
            return []
        r2 = requests.get(
            f"https://api.twitter.com/2/users/{uid}/tweets",
            headers={"Authorization": f"Bearer {TWITTER_BEARER}"},
            params={"max_results": max_tweets, "tweet.fields": "created_at,text"},
            timeout=8,
        )
        tweets = r2.json().get("data", [])
        return [f"{t.get('created_at','')[:10]}: {t.get('text','')}" for t in tweets]
    except Exception as e:
        log.warning(f"Twitter fetch error: {e}")
        return []

# ──────────────────────────────────────────────────────────
# KOTAK NEO — READ-ONLY (NO TRADING)
# ──────────────────────────────────────────────────────────
KOTAK_BASE = "https://gw-napi.kotaksecurities.com"

def kotak_headers() -> dict:
    return {
        "Authorization": f"Bearer {KOTAK_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
        "accept":        "application/json",
    }

def kotak_get_holdings() -> str:
    if _kotak_token_missing():
        return (
            "\u274c *KotakNeo not connected*\n"
            "Add `KOTAK_ACCESS_TOKEN` to your `.env` file.\n"
            "Get it from: https://neo.kotaksecurities.com \u2192 API section."
        )
    try:
        r = requests.get(
            f"{KOTAK_BASE}/Holdings/1.0/portfolio/v1/holdings",
            headers=kotak_headers(), timeout=10,
        )
        data = safe_json(r)
        if data is None:
            return "\u274c KotakNeo: Session expired. Update KOTAK_ACCESS_TOKEN in .env"
        holdings = data.get("data", {}).get("holdings", [])
        if not holdings:
            return "\U0001f4bc No holdings found."
        lines = ["\U0001f4bc *Your KotakNeo Holdings*",
                 "\u2501" * 22]
        total_val = 0
        for h in holdings:
            sym   = h.get("tradingSymbol", h.get("symbol", "?"))
            qty   = h.get("quantity", h.get("holdingQty", 0))
            avg   = float(h.get("averagePrice", h.get("avgPrice", 0)))
            ltp   = float(h.get("lastPrice", h.get("ltp", 0)))
            val   = qty * ltp
            pnl   = (ltp - avg) * qty
            pct   = ((ltp - avg) / avg * 100) if avg else 0
            sign  = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
            total_val += val
            lines.append(
                f"{sign} *{sym}* | Qty:{qty} | Avg:Rs.{avg:.2f} | LTP:Rs.{ltp:.2f}\n"
                f"   P&L: Rs.{pnl:+.2f} ({pct:+.1f}%) | Val:Rs.{val:.2f}"
            )
        lines.append(f"\n\U0001f4b0 *Total Value: Rs.{total_val:.2f}*")
        return "\n".join(lines)
    except Exception as e:
        log.error(f"Kotak holdings error: {e}")
        return f"\u274c KotakNeo error: {e}\nCheck KOTAK_ACCESS_TOKEN in .env"

def kotak_get_positions() -> str:
    if _kotak_token_missing():
        return "\u274c KotakNeo not connected. Set KOTAK_ACCESS_TOKEN in .env"
    try:
        r = requests.get(
            f"{KOTAK_BASE}/Orders/2.0/quick/user/positions",
            headers=kotak_headers(), timeout=10,
        )
        data = safe_json(r)
        if data is None:
            return "\u274c KotakNeo: Session expired. Update KOTAK_ACCESS_TOKEN in .env"
        positions = data.get("data", {}).get("net", [])
        if not positions:
            return "\U0001f4ca No open positions."
        lines = ["\U0001f4ca *Open Positions*", "\u2501" * 22]
        for p in positions:
            sym  = p.get("tradingSymbol", "?")
            qty  = p.get("netQty", 0)
            avg  = float(p.get("avgPrice", 0))
            ltp  = float(p.get("ltp", 0))
            pnl  = float(p.get("pnl", (ltp - avg) * qty))
            side = "\U0001f7e2 LONG" if qty > 0 else "\U0001f534 SHORT"
            lines.append(
                f"{side} *{sym}* | Qty:{abs(qty)} | Avg:Rs.{avg:.2f} | LTP:Rs.{ltp:.2f} | P&L:Rs.{pnl:+.2f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"\u274c Positions error: {e}"

def kotak_get_trades() -> str:
    if _kotak_token_missing():
        return (
            "\u274c *KotakNeo not connected*\n"
            "Add `KOTAK_ACCESS_TOKEN` to your `.env` to view trade history."
        )
    try:
        r = requests.get(
            f"{KOTAK_BASE}/Orders/2.0/quick/user/trades",
            headers=kotak_headers(), timeout=10,
        )
        data = safe_json(r)
        if data is None:
            return (
                "\u274c *KotakNeo: Session expired*\n"
                "Update `KOTAK_ACCESS_TOKEN` in your `.env` file and restart."
            )
        trades = data.get("data", {}).get("trade_book", [])
        if not trades:
            return "\U0001f4d2 No trades today."
        lines = [f"\U0001f4d2 *Trade History ({len(trades)} trades)*", "\u2501" * 22]
        for t in trades[:20]:
            sym  = t.get("tradingSymbol", "?")
            qty  = t.get("filledShares", t.get("qty", 0))
            px   = float(t.get("price", 0))
            side = t.get("transactionType", t.get("side", "?")).upper()
            tm   = t.get("orderExecutionTime", t.get("time", ""))[:16]
            em   = "\U0001f7e2" if side in ("BUY", "B") else "\U0001f534"
            lines.append(f"{em} {side} *{sym}* | Qty:{qty} | Rs.{px:.2f} | {tm}")
        return "\n".join(lines)
    except Exception as e:
        return f"\u274c Trade history error: {e}"

def kotak_get_pnl() -> str:
    if _kotak_token_missing():
        return "\u274c KotakNeo not connected. Set KOTAK_ACCESS_TOKEN in .env"
    try:
        r = requests.get(
            f"{KOTAK_BASE}/Orders/2.0/quick/user/positions",
            headers=kotak_headers(), timeout=10,
        )
        data = safe_json(r)
        if data is None:
            return "\u274c KotakNeo: Session expired. Update KOTAK_ACCESS_TOKEN in .env"
        positions  = data.get("data", {}).get("net", [])
        total_pnl  = sum(float(p.get("pnl", 0)) for p in positions)
        realised   = sum(float(p.get("realisedPnl",   0)) for p in positions)
        unrealised = sum(float(p.get("unrealisedPnl", 0)) for p in positions)
        sign = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
        return (
            f"{sign} *Today's P&L*\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f4b0 Total P&L      : Rs.{total_pnl:+.2f}\n"
            f"\u2705 Realised        : Rs.{realised:+.2f}\n"
            f"\u23f3 Unrealised      : Rs.{unrealised:+.2f}\n"
            f"\U0001f550 As of          : {datetime.now(IST).strftime('%d %b %H:%M IST')}"
        )
    except Exception as e:
        return f"\u274c P&L error: {e}"

# ──────────────────────────────────────────────────────────
# GEMINI AI — AUTO SCAN (3 targets)
# ──────────────────────────────────────────────────────────
def ai_analysis(symbol: str, d: pd.Series, category: str,
                news_context: str = "") -> Optional[dict]:
    """Used by auto-scanner — returns BUY/SELL/HOLD with 3 targets."""
    try:
        model  = genai.GenerativeModel("gemini-1.5-flash")
        change = ((float(d["Close"]) - float(d["prev_close"])) / float(d["prev_close"])) * 100
        unit   = price_unit(symbol)
        news_block = f"\n--- MARKET NEWS (@REDBOXINDIA) ---\n{news_context}" if news_context else ""
        sma200_val = "N/A" if pd.isna(d["sma200"]) else f"{float(d['sma200']):.4f}"
        prompt = f"""
You are the Chief Investment Officer of a world-class quant hedge fund.

INSTRUMENT : {symbol}
CATEGORY   : {category}
PRICE      : {unit}{float(d['Close']):.4f}  ({change:+.2f}% vs prev close)
TIMEFRAME  : 15-minute candles

--- TREND ---
EMA9={float(d['ema9']):.4f}  EMA21={float(d['ema21']):.4f}
SMA50={float(d['sma50']):.4f}  SMA200={sma200_val}
ADX={float(d['adx']):.1f} (+DI={float(d['adx_pos']):.1f} / -DI={float(d['adx_neg']):.1f})

--- MOMENTUM ---
RSI={float(d['rsi']):.1f}  CCI={float(d['cci']):.1f}
MACD Hist={float(d['macd_dif']):.6f}  Stoch K={float(d['stoch_k']):.1f}  D={float(d['stoch_d']):.1f}

--- VOLATILITY ---
ATR={float(d['atr']):.4f}
BB Upper={float(d['bb_upper']):.4f}  Lower={float(d['bb_lower']):.4f}

--- VOLUME ---
Vol Ratio = {float(d['vol_ratio']):.2f}x{news_block}

RULES:
1. signal = BUY / SELL / HOLD
2. entry_low and entry_high = entry zone (tight range around current price)
3. sl = 1.5x ATR from entry
4. tp1 = conservative (1.5:1 RR), tp2 = moderate (2.5:1 RR), tp3 = aggressive (4:1 RR)
5. risk = LOW / MEDIUM / HIGH based on ADX, ATR, volatility
6. hold_time = estimated hold time (e.g. "1-3 hours", "1-2 days")
7. sentiment = one word (Bullish/Bearish/Neutral/Cautious)
8. confidence = 0-100
9. ADX < 20 = HOLD
10. why = 5 bullets, each starting with indicator name IN CAPS

Return ONLY valid JSON:
{{"signal":"BUY","confidence":85,
  "entry_low":1230.00,"entry_high":1240.00,
  "sl":1205.00,
  "tp1":1265.00,"tp2":1295.00,"tp3":1330.00,
  "risk":"MEDIUM","hold_time":"2-4 hours",
  "sentiment":"Bullish",
  "rationale":"One concise line.",
  "why":["RSI: ...","MACD: ...","EMA: ...","ADX: ...","VOLUME: ..."]}}
"""
        response = model.generate_content(prompt)
        raw = re.sub(r"```(?:json)?", "", response.text.strip()).replace("```", "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"[{symbol}] JSON parse: {e}")
    except Exception as e:
        log.error(f"[{symbol}] Gemini: {e}")
    return None

# ──────────────────────────────────────────────────────────
# GEMINI AI — ON-DEMAND /signal command (deeper analysis)
# ──────────────────────────────────────────────────────────
def ai_deep_signal(symbol: str, d: pd.Series, category: str,
                   news_context: str = "", is_option: bool = False,
                   option_desc: str = "") -> Optional[dict]:
    """Deeper analysis for /signal command with full context."""
    try:
        model  = genai.GenerativeModel("gemini-1.5-flash")
        change = ((float(d["Close"]) - float(d["prev_close"])) / float(d["prev_close"])) * 100
        unit   = price_unit(symbol)
        news_block = f"\n--- MARKET NEWS (@REDBOXINDIA) ---\n{news_context}" if news_context else ""
        opt_block  = f"\nOPTION REQUESTED: {option_desc}\nAnalyse whether this option is worth buying based on underlying movement." if is_option else ""
        sma200_val = "N/A" if pd.isna(d["sma200"]) else f"{float(d['sma200']):.4f}"

        prompt = f"""
You are a senior Indian market analyst and options trader at a top hedge fund.
A trader is asking for a FULL DETAILED ANALYSIS of this instrument RIGHT NOW.

INSTRUMENT  : {symbol}{f' (Underlying for option: {option_desc})' if is_option else ''}
CATEGORY    : {category}
CURRENT PRICE: {unit}{float(d['Close']):.4f}  ({change:+.2f}% vs prev close)
TIMEFRAME   : 15-minute candles (intraday)

--- TREND INDICATORS ---
EMA9  = {float(d['ema9']):.4f}  |  EMA21 = {float(d['ema21']):.4f}
SMA50 = {float(d['sma50']):.4f}  |  SMA200= {sma200_val}
ADX   = {float(d['adx']):.1f}  (+DI={float(d['adx_pos']):.1f}  -DI={float(d['adx_neg']):.1f})

--- MOMENTUM INDICATORS ---
RSI     = {float(d['rsi']):.1f}
CCI     = {float(d['cci']):.1f}
MACD    = {float(d['macd']):.6f}  Signal={float(d['macd_sig']):.6f}  Hist={float(d['macd_dif']):.6f}
Stoch   = %K:{float(d['stoch_k']):.1f}  %D:{float(d['stoch_d']):.1f}

--- VOLATILITY ---
ATR       = {float(d['atr']):.4f}
BB Upper  = {float(d['bb_upper']):.4f}
BB Lower  = {float(d['bb_lower']):.4f}
BB Width  = {float(d['bb_width']):.4f}

--- VOLUME ---
Volume Ratio vs 20-day avg = {float(d['vol_ratio']):.2f}x{news_block}{opt_block}

DELIVER A COMPLETE TRADE PLAN:
1. signal      = BUY / SELL / HOLD
2. entry_low   = lower bound of entry zone
3. entry_high  = upper bound of entry zone
4. sl          = stop loss (1.5x ATR)
5. tp1         = Target 1 — conservative (1.5:1 RR, book 40% here)
6. tp2         = Target 2 — moderate (2.5:1 RR, book 40% here)
7. tp3         = Target 3 — aggressive (4:1 RR, trail rest)
8. risk        = LOW / MEDIUM / HIGH
9. confidence  = 0-100
10. hold_time  = estimated hold duration (e.g. "2-4 hours", "1-2 days")
11. sentiment  = Bullish / Bearish / Neutral / Cautious
12. market_context = 1 sentence on broader market situation
13. rationale  = 1 concise line trade thesis
14. why        = exactly 5 bullets, each starting with indicator name IN CAPS, explaining what it shows
15. risk_note  = 1 sentence on the main risk to this trade
{f'16. option_view = Should trader BUY the {option_desc}? Why? Premium risk?' if is_option else ''}

Return ONLY valid JSON (no markdown, no extra text):
{{"signal":"BUY","confidence":82,
  "entry_low":24100.0,"entry_high":24150.0,
  "sl":23950.0,
  "tp1":24280.0,"tp2":24450.0,"tp3":24700.0,
  "risk":"MEDIUM","hold_time":"2-4 hours",
  "sentiment":"Bullish",
  "market_context":"Broader market showing strength with FII buying.",
  "rationale":"Strong EMA stack with volume confirmation.",
  "why":["RSI: at 62 in bullish zone with room to run",
         "MACD: histogram positive and expanding = momentum building",
         "EMA: price above EMA9 and EMA21, both sloping up = bull stack",
         "ADX: at 28 confirms strong trend, +DI dominates",
         "VOLUME: 1.8x above avg = institutional participation"],
  "risk_note":"Watch for reversal if price breaks below EMA21.",
  "option_view":"NIFTY 24000 CE looks attractive at current levels given bullish momentum."}}
"""
        response = model.generate_content(prompt)
        raw = re.sub(r"```(?:json)?", "", response.text.strip()).replace("```", "").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"[{symbol}] Deep signal JSON: {e}")
    except Exception as e:
        log.error(f"[{symbol}] Deep signal Gemini: {e}")
    return None

# ──────────────────────────────────────────────────────────
# TELEGRAM HELPERS
# ──────────────────────────────────────────────────────────
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
        log.error(f"Telegram: {e}")
        return False

def category_emoji(cat: str) -> str:
    return {"NSE Index": "\U0001f4c8", "NSE Stock": "\U0001f3e2",
            "MCX Commodity": "\U0001faa8", "Crypto": "\U0001fa99"}.get(cat, "\U0001f4ca")

def risk_emoji(risk: str) -> str:
    return {"LOW": "\U0001f7e2", "MEDIUM": "\U0001f7e1", "HIGH": "\U0001f534"}.get(risk.upper(), "\u26aa")

def format_deep_signal(symbol: str, sig: dict, is_option: bool = False,
                       option_desc: str = "") -> str:
    """Format the full /signal response for Telegram."""
    cat   = SYMBOL_CATEGORY.get(symbol, "NSE Stock")
    unit  = price_unit(symbol)
    arrow = "\U0001f680" if sig["signal"] == "BUY" else ("\U0001f53b" if sig["signal"] == "SELL" else "\u23f8")
    categ = category_emoji(cat)
    risk  = sig.get("risk", "MEDIUM")
    re_   = risk_emoji(risk)
    conf  = sig.get("confidence", 0)
    rr1   = abs(sig.get("tp1", 0) - sig.get("entry_high", 0)) / max(abs(sig.get("entry_high", 1) - sig.get("sl", 0)), 0.01)
    rr2   = abs(sig.get("tp2", 0) - sig.get("entry_high", 0)) / max(abs(sig.get("entry_high", 1) - sig.get("sl", 0)), 0.01)
    rr3   = abs(sig.get("tp3", 0) - sig.get("entry_high", 0)) / max(abs(sig.get("entry_high", 1) - sig.get("sl", 0)), 0.01)

    why_block = ""
    for b in sig.get("why", []):
        why_block += f"  \u2022 {b}\n"

    opt_block = ""
    if is_option and sig.get("option_view"):
        opt_block = f"\n\U0001f4dd *Option View ({option_desc}):*\n  {sig['option_view']}\n"

    msg = (
        f"{arrow} *{sig['signal']} SIGNAL* {categ} \u2014 *{symbol}*\n"
        f"_{cat}_\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"{re_} *Risk Level   :* `{risk}`\n"
        f"\U0001f4ca *Confidence  :* `{conf}%`\n"
        f"\U0001f4ac *Sentiment   :* `{sig.get('sentiment','?')}`\n"
        f"\u23f1 *Hold Time   :* `{sig.get('hold_time','?')}`\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4cd *Entry Zone  :* `{unit}{sig.get('entry_low',0):.4f}` \u2014 `{unit}{sig.get('entry_high',0):.4f}`\n"
        f"\U0001f6d1 *Stop Loss   :* `{unit}{sig.get('sl',0):.4f}`\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f3af *Target 1    :* `{unit}{sig.get('tp1',0):.4f}` _(R:R 1:{rr1:.1f} \u2014 book 40%)_\n"
        f"\U0001f3af *Target 2    :* `{unit}{sig.get('tp2',0):.4f}` _(R:R 1:{rr2:.1f} \u2014 book 40%)_\n"
        f"\U0001f3af *Target 3    :* `{unit}{sig.get('tp3',0):.4f}` _(R:R 1:{rr3:.1f} \u2014 trail rest)_\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f30d *Market      :* {sig.get('market_context','')}\n"
        f"\U0001f4dd *Thesis      :* {sig.get('rationale','')}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f9e0 *Why This Trade?*\n{why_block}"
        f"\u26a0\ufe0f *Risk Note   :* _{sig.get('risk_note','')}_"
        f"{opt_block}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f550 {datetime.now(IST).strftime('%d %b %Y  %H:%M IST')}\n"
        f"_\u26a0\ufe0f Not financial advice. Trade responsibly._"
    )
    return msg

def send_signal_alert(symbol: str, sig: dict):
    """Auto-scanner alert (compact)."""
    cat   = SYMBOL_CATEGORY.get(symbol, "NSE Stock")
    unit  = price_unit(symbol)
    emoji = "\U0001f680" if sig["signal"] == "BUY" else "\U0001f53b"
    categ = category_emoji(cat)
    risk  = sig.get("risk", "MEDIUM")
    re_   = risk_emoji(risk)
    why_block = ""
    for b in sig.get("why", []):
        why_block += f"  \u2022 {b}\n"
    el = sig.get("entry_low",  sig.get("entry", 0))
    eh = sig.get("entry_high", sig.get("entry", 0))
    _tg_post(
        f"{emoji} *AUTO SIGNAL* {categ} *{symbol}*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"{re_} Risk:`{risk}` | \U0001f4ca Conf:`{sig['confidence']}%` | \U0001f4ac `{sig.get('sentiment','')}`\n"
        f"\U0001f4cd Entry:`{unit}{el:.2f}`\u2014`{unit}{eh:.2f}` | \U0001f6d1 SL:`{unit}{sig.get('sl',0):.2f}`\n"
        f"\U0001f3af T1:`{unit}{sig.get('tp1',0):.2f}` | T2:`{unit}{sig.get('tp2',0):.2f}` | T3:`{unit}{sig.get('tp3',0):.2f}`\n"
        f"\U0001f9e0 *Why?*\n{why_block}"
        f"\U0001f550 {datetime.now(IST).strftime('%d %b  %H:%M IST')} | _Not advice_"
    )
    log.info(f"[{symbol}] AUTO {sig['signal']} | Conf={sig['confidence']}% | Risk={risk}")

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
        ce = category_emoji(SYMBOL_CATEGORY.get(s["symbol"], ""))
        u  = price_unit(s["symbol"])
        el = s.get("entry_low", s.get("entry", 0))
        lines.append(f"{e}{ce} {s['symbol']} | {u}{el:.2f} | Conf:{s['confidence']}% | {s.get('risk','?')} risk")
    _tg_post("\n".join(lines))
    log.info("Daily summary sent.")

# ──────────────────────────────────────────────────────────
# /signal COMMAND HANDLER
# ──────────────────────────────────────────────────────────
def handle_signal_command(query: str):
    """
    Parse /signal <query> and deliver full AI analysis.
    Supports:
      /signal BTC
      /signal NIFTY 50
      /signal RELIANCE
      /signal NIFTY 24000 CE   <- options
      /signal BANKNIFTY 52000 PE
    """
    query = query.strip()
    if not query:
        _tg_post(
            "\u2753 *Usage:* `/signal <symbol>`\n\n"
            "*Examples:*\n"
            "  `/signal BTC`\n"
            "  `/signal NIFTY 50`\n"
            "  `/signal RELIANCE`\n"
            "  `/signal GOLD`\n"
            "  `/signal NIFTY 24000 CE`\n"
            "  `/signal BANKNIFTY 52000 PE`\n\n"
            "Type `/indices`, `/stocks`, `/crypto` to see all symbols."
        )
        return

    opt_match = re.match(r"^(.+?)\s+(\d+)\s+(CE|PE)$", query, re.IGNORECASE)
    is_option  = bool(opt_match)
    option_desc = ""
    base_query  = query

    if is_option:
        base_query  = opt_match.group(1).strip()
        strike      = opt_match.group(2)
        opt_type    = opt_match.group(3).upper()
        option_desc = f"{base_query.upper()} {strike} {opt_type}"

    symbol = SHORT_ALIAS.get(base_query.upper()) or SHORT_ALIAS.get(base_query.upper().replace(" ", ""))
    if not symbol:
        for k, v in SHORT_ALIAS.items():
            if base_query.upper() in k:
                symbol = v; break

    if not symbol:
        _tg_post(
            f"\u274c *Symbol not found:* `{query}`\n"
            f"Try: `/signal BTC`, `/signal NIFTY 50`, `/signal RELIANCE`\n"
            f"Use `/crypto`, `/stocks`, `/indices` to see all symbols."
        )
        return

    ticker = ALL_SYMBOLS.get(symbol)
    if not ticker:
        _tg_post(f"\u274c No ticker for `{symbol}`."); return

    _tg_post(f"\u23f3 *Analysing {option_desc if is_option else symbol}...* Fetching data & running AI \u2014 10-20 sec")

    try:
        # FIX 1: use safe_download() which flattens MultiIndex automatically
        df = safe_download(ticker)
        if df is None or len(df) < 50:
            _tg_post(f"\u274c Insufficient data for `{symbol}`. Try again in a few minutes."); return

        data = compute_indicators(df)
        if data is None:
            _tg_post(f"\u274c Could not compute indicators for `{symbol}`."); return

        cat      = SYMBOL_CATEGORY.get(symbol, "NSE Stock")
        news     = get_redbox_news(5)
        news_ctx = "\n".join(news) if news else ""

        sig = ai_deep_signal(symbol, data, cat,
                             news_context=news_ctx,
                             is_option=is_option,
                             option_desc=option_desc)
        if sig is None:
            _tg_post(f"\u274c AI analysis failed for `{symbol}`. Try again."); return

        msg = format_deep_signal(symbol, sig, is_option=is_option, option_desc=option_desc)
        _tg_post(msg)
        log.info(f"[/signal] {symbol} -> {sig['signal']} | Conf={sig['confidence']}%")

    except Exception:
        log.error(f"[/signal] Error:\n{traceback.format_exc()}")
        _tg_post(f"\u274c Error analysing `{symbol}`. Check logs.")

# ──────────────────────────────────────────────────────────
# COOLDOWN & AUTO SCAN
# ──────────────────────────────────────────────────────────
def is_on_cooldown(symbol: str) -> bool:
    return (time.time() - last_alert_time.get(symbol, 0)) < (COOLDOWN_MIN * 60)

def scan_symbol(name: str, ticker: str):
    try:
        # FIX 1: use safe_download() which flattens MultiIndex automatically
        df = safe_download(ticker)
        if df is None or len(df) < 50: return
        data = compute_indicators(df)
        if data is None: return
        cat  = SYMBOL_CATEGORY.get(name, "NSE Stock")
        news = get_redbox_news(3)
        sig  = ai_analysis(name, data, cat, news_context="\n".join(news))
        if sig is None: return
        log.info(f"[AUTO] {name} {sig['signal']} | Conf={sig['confidence']}%")
        if sig["signal"] == "HOLD": return
        if sig["confidence"] < MIN_CONFIDENCE: return
        if is_on_cooldown(name): return
        send_signal_alert(name, sig)
        last_alert_time[name] = time.time()
        sig["symbol"] = name
        daily_signals.append(sig)
    except Exception:
        log.error(f"[{name}]\n{traceback.format_exc()}")

# ──────────────────────────────────────────────────────────
# TELEGRAM COMMAND LISTENER
# ──────────────────────────────────────────────────────────
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
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue
                cmd = text.lower()
                log.info(f"CMD: {text}")

                if cmd.startswith("/signal"):
                    query = text[7:].strip()
                    threading.Thread(target=handle_signal_command, args=(query,), daemon=True).start()

                elif cmd in ["/start", "/help"]:
                    _tg_post(
                        "\U0001f916 *TradingBot v3.4*\n"
                        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        "\U0001f50d *On-Demand Analysis:*\n"
                        "  `/signal BTC`\n"
                        "  `/signal NIFTY 50`\n"
                        "  `/signal RELIANCE`\n"
                        "  `/signal NIFTY 24000 CE`\n"
                        "  `/signal BANKNIFTY 52000 PE`\n\n"
                        "\U0001fa99 *KotakNeo (Read-Only):*\n"
                        "  /portfolio  /positions  /trades  /pnl\n\n"
                        "\U0001f4f0 *News & Info:*\n"
                        "  /news  /signals  /market  /status\n\n"
                        "\U0001f4cb *Symbol Lists:*\n"
                        "  /indices  /stocks  /mcx  /crypto\n\n"
                        "\U0001f6d1 /stop"
                    )

                elif cmd == "/status":
                    uptime = datetime.now(IST) - BOT_START
                    h, rem = divmod(int(uptime.total_seconds()), 3600)
                    m = rem // 60
                    _tg_post(
                        f"\u2705 *TradingBot v3.4*\n"
                        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        f"\U0001f550 Uptime     : {h}h {m}m\n"
                        f"\U0001f4ca Symbols    : {len(ALL_SYMBOLS)} total\n"
                        f"  \U0001f4c8 Indices  : {len(NSE_INDICES)}\n"
                        f"  \U0001f3e2 Stocks   : {len(NSE_STOCKS)}\n"
                        f"  \U0001faa8 MCX      : {len(MCX_COMMODITIES)}\n"
                        f"  \U0001fa99 Crypto   : {len(CRYPTO)}\n"
                        f"\U0001f4e1 Signals Today : {len(daily_signals)}\n"
                        f"\U0001f7e2 NSE    : {'OPEN' if is_nse_open() else 'CLOSED'}\n"
                        f"\U0001f7e2 MCX    : {'OPEN' if is_mcx_open() else 'CLOSED'}\n"
                        f"\U0001fa99 Crypto : 24/7 OPEN\n"
                        f"\U0001f550 {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}"
                    )

                elif cmd == "/signals":
                    if not daily_signals:
                        _tg_post("\U0001f4cb No auto signals today. Use `/signal BTC` for on-demand.")
                    else:
                        lines = [f"\U0001f4cb *Auto Signals Today ({len(daily_signals)})*",
                                 "\u2501" * 22]
                        for s in daily_signals:
                            e  = "\U0001f680" if s["signal"] == "BUY" else "\U0001f53b"
                            ce = category_emoji(SYMBOL_CATEGORY.get(s["symbol"], ""))
                            u  = price_unit(s["symbol"])
                            el = s.get("entry_low", s.get("entry", 0))
                            lines.append(f"{e}{ce} *{s['symbol']}* | {u}{el:.2f} | {s['confidence']}% | {s.get('risk','?')}")
                        _tg_post("\n".join(lines))

                elif cmd == "/news":
                    tweets = get_redbox_news(10)
                    if not tweets:
                        _tg_post("\U0001f4f0 No tweets fetched. Add TWITTER_BEARER_TOKEN to .env\nFollow @REDBOXINDIA manually for now.")
                    else:
                        lines = ["\U0001f4f0 *@REDBOXINDIA Latest News*", "\u2501" * 22]
                        for t in tweets:
                            lines.append(f"\u2022 {t}")
                        _tg_post("\n".join(lines))

                elif cmd == "/portfolio": _tg_post(kotak_get_holdings())
                elif cmd == "/positions": _tg_post(kotak_get_positions())
                elif cmd == "/trades":    _tg_post(kotak_get_trades())
                elif cmd == "/pnl":       _tg_post(kotak_get_pnl())

                elif cmd in ["/indices", "/nse"]:
                    lines = ["\U0001f4c8 *All Indian Indices*", "\u2501" * 22]
                    for n in NSE_INDICES:
                        lines.append(f"  \u2022 {n}  \u2014  use `/signal {n}`")
                    _tg_post("\n".join(lines))

                elif cmd == "/stocks":
                    sects = {
                        "\U0001f3e6 Banking": ["HDFC BANK","ICICI BANK","AXIS BANK","SBI","KOTAK BANK","INDUSIND","BAJFINANCE","BAJAJFINSV","HDFCLIFE","SBILIFE"],
                        "\U0001f4bb IT":      ["TCS","INFOSYS","WIPRO","HCLTECH","TECHM","LTIM","MPHASIS"],
                        "\u26a1 Energy":     ["RELIANCE","ONGC","BPCL","IOCL","NTPC","POWERGRID","ADANIGREEN","ADANIPORTS","ADANIENT"],
                        "\U0001f697 Auto":   ["TATAMOTORS","MARUTI","M&M","EICHERMOT","HEROMOTOCO","BAJAJ-AUTO"],
                        "\U0001f48a Pharma": ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB"],
                        "\U0001faa8 Metal":  ["TATASTEEL","HINDALCO","JSWSTEEL","COALINDIA","VEDL"],
                        "\U0001f6d2 FMCG":   ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA"],
                        "\U0001f4e6 Others": ["LT","ULTRACEMCO","ASIANPAINT","TITAN","ZOMATO","PAYTM"],
                    }
                    lines = [f"\U0001f3e2 *NSE Stocks ({len(NSE_STOCKS)})*  \u2014  use `/signal <name>`",
                             "\u2501" * 22]
                    for sec, syms in sects.items():
                        lines.append(f"\n*{sec}:*  " + "  ".join(syms))
                    _tg_post("\n".join(lines))

                elif cmd == "/mcx":
                    lines = ["\U0001faa8 *MCX Commodities*  \u2014  use `/signal GOLD` etc.", "\u2501" * 22]
                    for n in MCX_COMMODITIES:
                        lines.append(f"  \u2022 {n}  \u2014  `/signal {n.split()[0]}`")
                    _tg_post("\n".join(lines))

                elif cmd == "/crypto":
                    lines = [f"\U0001fa99 *Crypto ({len(CRYPTO)}) 24/7*  \u2014  use `/signal BTC` etc.", "\u2501" * 22]
                    row = []
                    for n in CRYPTO:
                        row.append(n)
                        if len(row) == 3:
                            lines.append("  \u2022 " + "  \u2022 ".join(row)); row = []
                    if row: lines.append("  \u2022 " + "  \u2022 ".join(row))
                    _tg_post("\n".join(lines))

                elif cmd == "/market":
                    _tg_post(
                        f"\U0001f555 *Market Status*\n"
                        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        f"\U0001f4c8 NSE    : {'\U0001f7e2 OPEN' if is_nse_open() else '\U0001f534 CLOSED'} (09:15\u201315:30 Mon-Fri)\n"
                        f"\U0001faa8 MCX    : {'\U0001f7e2 OPEN' if is_mcx_open() else '\U0001f534 CLOSED'} (09:00\u201323:30 Mon-Sat)\n"
                        f"\U0001fa99 Crypto : \U0001f7e2 ALWAYS OPEN (24/7)\n"
                        f"\U0001f550 Now    : {datetime.now(IST).strftime('%d %b  %H:%M IST')}"
                    )

                elif cmd == "/stop":
                    _tg_post("\U0001f6d1 Bot stopping...")
                    os._exit(0)

                else:
                    _tg_post(
                        f"\u2753 Unknown: `{text}`\n"
                        f"Try `/signal BTC` or `/signal NIFTY 24000 CE`\n"
                        f"Type /start for all commands."
                    )

        except Exception as e:
            log.error(f"Poll: {e}")
        time.sleep(1)

# ──────────────────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────────────────
def main():
    global summary_sent_today, daily_signals
    if not GEMINI_API_KEY:
        log.critical("GEMINI_API_KEY missing in .env"); raise SystemExit(1)
    genai.configure(api_key=GEMINI_API_KEY)

    log.info("=" * 58)
    log.info("  TradingBot v3.4  —  All fixes applied")
    log.info(f"  {len(ALL_SYMBOLS)} symbols | /signal on-demand | KotakNeo RO | @REDBOXINDIA")
    log.info("=" * 58)

    _tg_post(
        f"\u2705 *TradingBot v3.4 Online*\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f527 *Fixes applied:*\n"
        f"  \u2705 /signal BTC (yfinance MultiIndex fixed)\n"
        f"  \u2705 /trades (Kotak JSON guard — no crash)\n"
        f"  \u2705 KOTAK_API_KEY hardcode removed\n"
        f"\U0001f4ca {len(ALL_SYMBOLS)} symbols | `/signal BTC` | `/signal NIFTY 24000 CE`\n"
        f"Type /start for all commands."
    )

    threading.Thread(target=poll_telegram_commands, daemon=True).start()

    while True:
        now_ist = datetime.now(IST)
        if now_ist.hour == 0 and now_ist.minute < 15:
            daily_signals = []; summary_sent_today = False
        if is_summary_time() and not summary_sent_today:
            send_daily_summary(); summary_sent_today = True

        log.info(f"-- Auto-scan @ {now_ist.strftime('%H:%M IST')} --")
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
