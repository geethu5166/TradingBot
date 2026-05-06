"""
TradingBot v3.2 — Full Professional Grade

 FEATURES:
 - /signal BTC          → Full AI analysis on demand for any symbol
 - /signal NIFTY 24000 CE → Options analysis with AI
 - Twitter @REDBOXINDIA  → News context fed into AI analysis
 - KotakNeo READ-ONLY    → View portfolio, holdings, trades (NO trading)
 - 104 symbols auto-scanned every 15 min
 - Gemini 1.5 Flash AI with Why-This-Trade, 3 targets, risk rating
 - Telegram commands locked to your chat_id only

Telegram Commands:
  /signal <symbol>         - On-demand full analysis (e.g. /signal BTC)
  /signal NIFTY 24000 CE   - Options analysis
  /portfolio               - Your KotakNeo holdings
  /trades                  - Your recent trade history
  /pnl                     - Today's P&L from KotakNeo
  /positions               - Open positions
  /news                    - Latest @REDBOXINDIA tweets
  /signals                 - All bot signals today
  /status                  - Uptime & stats
  /indices                 - All Indian indices
  /stocks                  - All NSE stocks
  /mcx                     - MCX Commodities
  /crypto                  - All 30 cryptos
  /market                  - Market hours
  /stop                    - Stop the bot
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

# ─────────────────────────────────────────────
# BOOTSTRAP
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# CONFIG — all from .env
# ─────────────────────────────────────────────
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
KOTAK_API_KEY      = os.getenv("KOTAK_API_KEY", "")
KOTAK_ACCESS_TOKEN = os.getenv("KOTAK_ACCESS_TOKEN", "")   # Generate from KotakNeo app
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

REDBOX_USER_ID = "1234567890"   # @REDBOXINDIA Twitter user_id (resolved at startup)

# ─────────────────────────────────────────────
# ALL INDIAN INDICES
# ─────────────────────────────────────────────
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

# Quick-lookup: short names → full name (for /signal command)
SHORT_ALIAS: dict[str, str] = {}
for full, ticker in ALL_SYMBOLS.items():
    # Add full name
    SHORT_ALIAS[full.upper()] = full
    # Add ticker variants
    SHORT_ALIAS[ticker.upper().replace(".NS","").replace("-USD","").replace("^CNX","").replace("^NSE","").replace("=F","")] = full
    # Common short aliases
SHORT_ALIAS.update({
    "BTC": "BITCOIN", "ETH": "ETHEREUM", "SOL": "SOLANA",
    "BNB": "BNB", "XRP": "XRP", "ADA": "CARDANO",
    "DOGE": "DOGECOIN", "MATIC": "POLYGON", "DOT": "POLKADOT",
    "AVAX": "AVALANCHE", "LINK": "CHAINLINK", "SHIB": "SHIBA INU",
    "LTC": "LITECOIN", "TRX": "TRON", "UNI": "UNISWAP",
    "XLM": "STELLAR", "XMR": "MONERO", "FIL": "FILECOIN",
    "APT": "APTOS", "ARB": "ARBITRUM", "INJ": "INJECTIVE",
    "OP": "OPTIMISM", "PEPE": "PEPE", "BONK": "BONK",
    "NIFTY": "NIFTY 50", "BANKNIFTY": "BANK NIFTY", "FINNIFTY": "NIFTY IT",
    "GOLD": "GOLD MCX", "SILVER": "SILVER MCX", "CRUDE": "CRUDE OIL MCX",
    "CRUDEOIL": "CRUDE OIL MCX", "NATURALGAS": "NATURAL GAS MCX",
    "RELIANCE": "RELIANCE", "TCS": "TCS", "INFY": "INFOSYS",
    "SBIN": "SBI", "HDFC": "HDFC BANK", "ICICI": "ICICI BANK",
})

def price_unit(name: str) -> str:
    cat = SYMBOL_CATEGORY.get(name, "NSE Stock")
    return "$" if cat in ("Crypto", "MCX Commodity") else "Rs."

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
last_alert_time: dict[str, float] = {}
daily_signals:   list[dict]       = []
summary_sent_today: bool          = False

# ─────────────────────────────────────────────
# MARKET HOURS
# ─────────────────────────────────────