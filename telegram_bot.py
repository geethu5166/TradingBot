#!/usr/bin/env python3
"""
Full-featured Telegram Trading Signal Bot
Commands:
  /signal <SYMBOL>           - Full signal for stocks/crypto/options
  /signal <SYMBOL> <STRIKE> <CE/PE>  - Options signal
  /chart <SYMBOL>            - Mini text chart + trend
  /watchlist                 - Signal scan on all watchlist symbols
  /status                    - Bot health + market status
  /help                      - All commands
"""

import os
import sys
import logging
import asyncio
import traceback
from datetime import datetime, time as dtime
import pytz

import yfinance as yf
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHATID = os.getenv("TELEGRAM_CHAT_ID", "")
IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")]
)
log = logging.getLogger(__name__)

# ─── Symbol resolver ──────────────────────────────────────────────────────────
SYMBOL_MAP = {
    # Indian indices
    "NIFTY":    "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX":   "^BSESN",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "MIDCAP":   "^NSEMDCP50",
    # Indian stocks
    "RELIANCE": "RELIANCE.NS",
    "TCS":      "TCS.NS",
    "INFY":     "INFY.NS",
    "HDFC":     "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "SBIN":     "SBIN.NS",
    "WIPRO":    "WIPRO.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "ADANIENT": "ADANIENT.NS",
    "MARUTI":   "MARUTI.NS",
    "SUNPHARMA": "SUNPHARMA.NS",
    "AXISBANK": "AXISBANK.NS",
    "LT":       "LT.NS",
    "TITAN":    "TITAN.NS",
    "ULTRACEMCO": "ULTRACEMCO.NS",
    # Crypto
    "BTC":      "BTC-USD",
    "ETH":      "ETH-USD",
    "BNB":      "BNB-USD",
    "SOL":      "SOL-USD",
    "XRP":      "XRP-USD",
    "ADA":      "ADA-USD",
    "DOGE":     "DOGE-USD",
    "AVAX":     "AVAX-USD",
    "MATIC":    "MATIC-USD",
    "DOT":      "DOT-USD",
    # US stocks
    "AAPL":     "AAPL",
    "TSLA":     "TSLA",
    "NVDA":     "NVDA",
    "AMZN":     "AMZN",
    "GOOGL":    "GOOGL",
    "MSFT":     "MSFT",
    "META":     "META",
}

WATCHLIST = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "BTC", "ETH", "TSLA", "NVDA"]

def resolve_symbol(sym: str) -> str:
    s = sym.upper().strip()
    return SYMBOL_MAP.get(s, s if "-" in s or "." in s else s)

# ─── Indicator Engine ─────────────────────────────────────────────────────────
def fetch_data(ticker: str, period="3mo", interval="1h") -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df is None or len(df) < 30:
            # fallback to daily
            df = yf.download(ticker, period="6mo", interval="1d",
                             auto_adjust=True, progress=False)
        if df is None or len(df) < 20:
            return None
        df.dropna(inplace=True)
        return df
    except Exception:
        log.error(traceback.format_exc())
        return None

def calc_indicators(df: pd.DataFrame) -> dict:
    close = df["Close"].squeeze()
    high  = df["High"].squeeze()
    low   = df["Low"].squeeze()
    vol   = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(dtype=float)

    # ── RSI ──
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))

    # ── MACD ──
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd  = ema12 - ema26
    signal= macd.ewm(span=9).mean()
    hist  = macd - signal

    # ── EMA stack ──
    ema9  = close.ewm(span=9).mean()
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()
    ema200= close.ewm(span=200).mean()

    # ── Bollinger Bands ──
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_up = sma20 + 2 * std20
    bb_lo = sma20 - 2 * std20
    bb_pct= (close - bb_lo) / (bb_up - bb_lo + 1e-9)

    # ── Stochastic ──
    lo14 = low.rolling(14).min()
    hi14 = high.rolling(14).max()
    stoch_k = 100 * (close - lo14) / (hi14 - lo14 + 1e-9)
    stoch_d = stoch_k.rolling(3).mean()

    # ── ATR ──
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # ── ADX ──
    up_move  = high.diff()
    dn_move  = -low.diff()
    plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
    atr14    = tr.rolling(14).mean()
    plus_di  = 100 * pd.Series(plus_dm,  index=df.index).rolling(14).mean() / (atr14 + 1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(14).mean() / (atr14 + 1e-9)
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx      = dx.rolling(14).mean()

    # ── CCI ──
    tp   = (high + low + close) / 3
    cci  = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std() + 1e-9)

    # ── OBV ──
    if not vol.empty:
        obv = (np.sign(close.diff()) * vol).fillna(0).cumsum()
        obv_slope = obv.diff(5).iloc[-1]
    else:
        obv_slope = 0

    # ── Support / Resistance ──
    pivot  = (high.iloc[-20:].max() + low.iloc[-20:].min() + close.iloc[-1]) / 3
    r1 = 2 * pivot - low.iloc[-20:].min()
    r2 = pivot + (high.iloc[-20:].max() - low.iloc[-20:].min())
    s1 = 2 * pivot - high.iloc[-20:].max()
    s2 = pivot - (high.iloc[-20:].max() - low.iloc[-20:].min())

    return {
        "close":    float(close.iloc[-1]),
        "rsi":      float(rsi.iloc[-1]),
        "macd":     float(macd.iloc[-1]),
        "macd_sig": float(signal.iloc[-1]),
        "macd_hist":float(hist.iloc[-1]),
        "ema9":     float(ema9.iloc[-1]),
        "ema20":    float(ema20.iloc[-1]),
        "ema50":    float(ema50.iloc[-1]),
        "ema200":   float(ema200.iloc[-1]),
        "bb_pct":   float(bb_pct.iloc[-1]),
        "bb_up":    float(bb_up.iloc[-1]),
        "bb_lo":    float(bb_lo.iloc[-1]),
        "stoch_k":  float(stoch_k.iloc[-1]),
        "stoch_d":  float(stoch_d.iloc[-1]),
        "atr":      float(atr.iloc[-1]),
        "adx":      float(adx.iloc[-1]),
        "plus_di":  float(plus_di.iloc[-1]),
        "minus_di": float(minus_di.iloc[-1]),
        "cci":      float(cci.iloc[-1]),
        "obv_slope":float(obv_slope),
        "pivot":    float(pivot),
        "r1":       float(r1),
        "r2":       float(r2),
        "s1":       float(s1),
        "s2":       float(s2),
        "high20":   float(high.iloc[-20:].max()),
        "low20":    float(low.iloc[-20:].min()),
    }

# ─── Signal Generator ─────────────────────────────────────────────────────────
def generate_signal(ind: dict, is_options: bool = False,
                    opt_type: str = "", strike: float = 0) -> dict:
    score_bull = 0
    score_bear = 0
    reasons_bull = []
    reasons_bear = []

    c     = ind["close"]
    rsi   = ind["rsi"]
    macd  = ind["macd"]
    msig  = ind["macd_sig"]
    mhist = ind["macd_hist"]
    adx   = ind["adx"]
    atr   = ind["atr"]
    cci   = ind["cci"]
    stk   = ind["stoch_k"]
    std   = ind["stoch_d"]
    bb    = ind["bb_pct"]

    # RSI
    if rsi < 30:
        score_bull += 3; reasons_bull.append(f"RSI oversold ({rsi:.1f})")
    elif rsi < 45:
        score_bull += 1; reasons_bull.append(f"RSI low ({rsi:.1f})")
    elif rsi > 70:
        score_bear += 3; reasons_bear.append(f"RSI overbought ({rsi:.1f})")
    elif rsi > 55:
        score_bear += 1; reasons_bear.append(f"RSI high ({rsi:.1f})")

    # MACD
    if macd > msig and mhist > 0:
        score_bull += 2; reasons_bull.append("MACD bullish crossover")
    elif macd < msig and mhist < 0:
        score_bear += 2; reasons_bear.append("MACD bearish crossover")

    # EMA stack
    if ind["ema9"] > ind["ema20"] > ind["ema50"]:
        score_bull += 2; reasons_bull.append("EMA9>EMA20>EMA50 bull stack")
    elif ind["ema9"] < ind["ema20"] < ind["ema50"]:
        score_bear += 2; reasons_bear.append("EMA9<EMA20<EMA50 bear stack")

    # Price vs EMA200
    if c > ind["ema200"]:
        score_bull += 1; reasons_bull.append("Price above EMA200")
    else:
        score_bear += 1; reasons_bear.append("Price below EMA200")

    # ADX / DI
    if adx > 25:
        if ind["plus_di"] > ind["minus_di"]:
            score_bull += 2; reasons_bull.append(f"ADX strong trend bullish ({adx:.1f})")
        else:
            score_bear += 2; reasons_bear.append(f"ADX strong trend bearish ({adx:.1f})")

    # Bollinger Bands
    if bb < 0.15:
        score_bull += 2; reasons_bull.append(f"Near BB lower band")
    elif bb > 0.85:
        score_bear += 2; reasons_bear.append(f"Near BB upper band")

    # Stochastic
    if stk < 20 and std < 20:
        score_bull += 2; reasons_bull.append(f"Stoch oversold ({stk:.1f})")
    elif stk > 80 and std > 80:
        score_bear += 2; reasons_bear.append(f"Stoch overbought ({stk:.1f})")

    # CCI
    if cci < -100:
        score_bull += 1; reasons_bull.append(f"CCI oversold ({cci:.0f})")
    elif cci > 100:
        score_bear += 1; reasons_bear.append(f"CCI overbought ({cci:.0f})")

    # OBV
    if ind["obv_slope"] > 0:
        score_bull += 1; reasons_bull.append("OBV rising (buy pressure)")
    elif ind["obv_slope"] < 0:
        score_bear += 1; reasons_bear.append("OBV falling (sell pressure)")

    total = score_bull + score_bear
    if total == 0:
        confidence = 50
        direction  = "NEUTRAL"
    else:
        confidence = int(max(score_bull, score_bear) / total * 100)
        direction  = "BUY" if score_bull > score_bear else "SELL"

    # For options: flip if PE
    if is_options:
        if opt_type == "PE" and direction == "BUY":
            direction = "BUY PE (Bearish Underlying)"
        elif opt_type == "CE" and direction == "SELL":
            direction = "SELL CE (Bearish)" 
        elif opt_type == "CE" and direction == "BUY":
            direction = "BUY CE (Bullish Underlying)"
        elif opt_type == "PE" and direction == "SELL":
            direction = "SELL PE (Bullish)"

    # ─── Targets & SL ─────────────────────────────────────────────────────────
    multiplier = 1 if "BUY" in direction.upper() else -1

    if "BUY" in direction.upper():
        entry   = c * 1.001                     # slight slippage
        sl      = max(c - 2.0 * atr, ind["s1"])
        t1      = entry + 1.5 * atr
        t2      = entry + 2.5 * atr
        t3      = entry + 4.0 * atr
    else:
        entry   = c * 0.999
        sl      = min(c + 2.0 * atr, ind["r1"])
        t1      = entry - 1.5 * atr
        t2      = entry - 2.5 * atr
        t3      = entry - 4.0 * atr

    risk    = abs(entry - sl)
    reward1 = abs(t1 - entry)
    reward3 = abs(t3 - entry)
    rr1     = reward1 / risk if risk > 0 else 0
    rr3     = reward3 / risk if risk > 0 else 0

    # Risk assessment
    if confidence >= 75 and adx > 25 and rr1 >= 1.5:
        risk_level = "🟢 LOW RISK"
        take_trade = True
        advice = "Strong setup. Consider full position."
    elif confidence >= 65 and rr1 >= 1.2:
        risk_level = "🟡 MEDIUM RISK"
        take_trade = True
        advice = "Decent setup. Use 50% position size."
    elif confidence >= 55:
        risk_level = "🟠 HIGH RISK"
        take_trade = False
        advice = "Weak setup. Avoid or wait for confirmation."
    else:
        risk_level = "🔴 AVOID"
        take_trade = False
        advice = "No clear edge. Skip this trade."

    reasons = reasons_bull if "BUY" in direction.upper() else reasons_bear

    return {
        "direction":  direction,
        "confidence": confidence,
        "entry":      round(entry, 2),
        "sl":         round(sl, 2),
        "t1":         round(t1, 2),
        "t2":         round(t2, 2),
        "t3":         round(t3, 2),
        "rr1":        round(rr1, 2),
        "rr3":        round(rr3, 2),
        "risk_level": risk_level,
        "take_trade": take_trade,
        "advice":     advice,
        "reasons":    reasons[:5],
        "atr":        round(atr, 2),
        "adx":        round(adx, 2),
        "rsi":        round(rsi, 2),
        "pivot":      round(ind["pivot"], 2),
        "r1":         round(ind["r1"], 2),
        "r2":         round(ind["r2"], 2),
        "s1":         round(ind["s1"], 2),
        "s2":         round(ind["s2"], 2),
    }

# ─── Formatting ───────────────────────────────────────────────────────────────
def fmt(val: float, decimals: int = 2) -> str:
    """Format number with commas for Indian readability."""
    if val >= 1000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"

def build_signal_message(sym: str, ticker: str, ind: dict, sig: dict,
                         is_options: bool = False, opt_type: str = "",
                         strike: float = 0) -> str:
    now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")

    direction = sig["direction"]
    arrow = "🚀" if "BUY" in direction.upper() else ("📉" if "SELL" in direction.upper() else "⚖️")

    if is_options:
        title = f"{sym} {int(strike)} {opt_type}"
        asset_type = "📋 Options"
    elif "-USD" in ticker:
        title = sym
        asset_type = "₿ Crypto"
    elif ".NS" in ticker or "^NSE" in ticker or "^BSE" in ticker:
        title = sym
        asset_type = "🇮🇳 Indian Market"
    else:
        title = sym
        asset_type = "🇺🇸 US Market"

    bar = "━" * 28

    reasons_txt = ""
    for r in sig["reasons"]:
        reasons_txt += f"  • {r}\n"

    trade_emoji = "✅" if sig["take_trade"] else "❌"

    msg = (
        f"{arrow} *{title} — {direction}*\n"
        f"`{bar}`\n"
        f"🕐 {now}\n"
        f"{asset_type}\n\n"
        f"*📊 SIGNAL DETAILS*\n"
        f"`{bar}`\n"
        f"💰 Current Price:  `{fmt(ind['close'])}`\n"
        f"🎯 Entry Zone:     `{fmt(sig['entry'])}`\n"
        f"🛑 Stop Loss:      `{fmt(sig['sl'])}`\n"
        f"🎯 Target 1:       `{fmt(sig['t1'])}`\n"
        f"🎯 Target 2:       `{fmt(sig['t2'])}`\n"
        f"🎯 Target 3:       `{fmt(sig['t3'])}`\n\n"
        f"*⚖️ RISK ANALYSIS*\n"
        f"`{bar}`\n"
        f"{sig['risk_level']}\n"
        f"📈 Confidence:     `{sig['confidence']}%`\n"
        f"⚖️ R:R (T1):       `1 : {sig['rr1']}`\n"
        f"⚖️ R:R (T3):       `1 : {sig['rr3']}`\n"
        f"{trade_emoji} Take Trade:    `{'YES' if sig['take_trade'] else 'NO'}`\n"
        f"💡 Advice:         _{sig['advice']}_\n\n"
        f"*📐 TECHNICALS*\n"
        f"`{bar}`\n"
        f"RSI:  `{sig['rsi']}`   ADX: `{sig['adx']}`   ATR: `{fmt(sig['atr'])}`\n"
        f"Pivot: `{fmt(sig['pivot'])}`\n"
        f"R1: `{fmt(sig['r1'])}`   R2: `{fmt(sig['r2'])}`\n"
        f"S1: `{fmt(sig['s1'])}`   S2: `{fmt(sig['s2'])}`\n\n"
        f"*🧠 WHY THIS SIGNAL*\n"
        f"`{bar}`\n"
        f"{reasons_txt}"
        f"\n⚠️ _Not financial advice. Trade responsibly._"
    )
    return msg

# ─── Mini text chart ──────────────────────────────────────────────────────────
def mini_chart(df: pd.DataFrame, sym: str) -> str:
    closes = df["Close"].squeeze().tail(20).values
    mn, mx = closes.min(), closes.max()
    rows   = 6
    chart  = []
    for row in range(rows, -1, -1):
        line = ""
        threshold = mn + (row / rows) * (mx - mn)
        for val in closes:
            line += "█" if val >= threshold else " "
        chart.append(line)
    trend = "📈 UPTREND" if closes[-1] > closes[0] else "📉 DOWNTREND"
    pct   = ((closes[-1] - closes[0]) / closes[0]) * 100
    txt   = (
        f"📊 *{sym} — Last 20 Candles*\n"
        f"```\n"
    )
    for row in chart:
        txt += row + "\n"
    txt += (
        f"```\n"
        f"High: `{fmt(mx)}`  Low: `{fmt(mn)}`\n"
        f"Now:  `{fmt(float(closes[-1]))}`\n"
        f"{trend}  ({pct:+.2f}% over 20 bars)\n"
    )
    return txt

# ─── Market status helper ─────────────────────────────────────────────────────
def market_status() -> str:
    now = datetime.now(IST)
    weekday = now.weekday()  # 0=Mon 6=Sun
    t = now.time()
    nse_open  = dtime(9, 15)
    nse_close = dtime(15, 30)
    if weekday >= 5:
        nse = "🔴 Closed (Weekend)"
    elif nse_open <= t <= nse_close:
        nse = "🟢 Open"
    else:
        nse = "🔴 Closed"
    # Crypto is always open
    crypto = "🟢 Always Open"
    # US market rough (UTC+5:30 → NYSE 9:30–16:00 ET = 19:00–01:30 IST)
    us_open  = dtime(19, 0)
    us_close = dtime(1, 30)
    if us_open <= t or t <= us_close:
        us = "🟢 Open"
    else:
        us = "🔴 Closed"
    return (
        f"🇮🇳 *NSE/BSE:*  {nse}\n"
        f"₿  *Crypto:*   {crypto}\n"
        f"🇺🇸 *NYSE/NASDAQ:* {us}\n"
    )

# ─── Handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *TradingBot v2 is LIVE!*\n\n"
        "Type /help to see all commands.",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *TradingBot Commands*\n\n"
        "`/signal BTC`\n"
        "  → Full signal for crypto/stocks/indices\n\n"
        "`/signal NIFTY`\n"
        "  → NSE index signal\n\n"
        "`/signal NIFTY 24000 CE`\n"
        "  → Options signal (CE or PE)\n\n"
        "`/chart RELIANCE`\n"
        "  → Mini price chart + trend\n\n"
        "`/watchlist`\n"
        "  → Quick scan of all tracked symbols\n\n"
        "`/status`\n"
        "  → Bot health + market hours\n\n"
        "*Supported: BTC ETH NIFTY BANKNIFTY SENSEX*\n"
        "*RELIANCE TCS INFY HDFC ICICIBANK SBIN*\n"
        "*TSLA NVDA AAPL MSFT META GOOGL AMZN*\n\n"
        "⚠️ _Not financial advice._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage:\n`/signal BTC`\n`/signal NIFTY`\n`/signal NIFTY 24000 CE`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    sym       = args[0].upper()
    is_options= len(args) == 3
    strike    = 0.0
    opt_type  = ""

    if is_options:
        try:
            strike   = float(args[1])
            opt_type = args[2].upper()
            if opt_type not in ("CE", "PE"):
                await update.message.reply_text("Option type must be CE or PE.")
                return
        except ValueError:
            await update.message.reply_text("Invalid strike. Example: `/signal NIFTY 24000 CE`",
                                             parse_mode=ParseMode.MARKDOWN)
            return

    ticker = resolve_symbol(sym)
    wait_msg = await update.message.reply_text(f"⏳ Analysing *{sym}*...",
                                                parse_mode=ParseMode.MARKDOWN)

    df = fetch_data(ticker)
    if df is None:
        await wait_msg.edit_text(
            f"❌ Could not fetch data for *{sym}* (`{ticker}`)\n"
            f"Check symbol or try: BTC, NIFTY, RELIANCE, TSLA",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    ind = calc_indicators(df)
    sig = generate_signal(ind, is_options, opt_type, strike)
    msg = build_signal_message(sym, ticker, ind, sig, is_options, opt_type, strike)

    await wait_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
    log.info(f"Signal sent: {sym} → {sig['direction']} @ {sig['entry']} | Conf: {sig['confidence']}%")

async def cmd_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/chart BTC`", parse_mode=ParseMode.MARKDOWN)
        return
    sym    = ctx.args[0].upper()
    ticker = resolve_symbol(sym)
    wait   = await update.message.reply_text(f"⏳ Loading chart for *{sym}*...",
                                              parse_mode=ParseMode.MARKDOWN)
    df = fetch_data(ticker)
    if df is None:
        await wait.edit_text(f"❌ No data for {sym}")
        return
    txt = mini_chart(df, sym)
    await wait.edit_text(txt, parse_mode=ParseMode.MARKDOWN)

async def cmd_watchlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    wait = await update.message.reply_text("⏳ Scanning watchlist...",
                                            parse_mode=ParseMode.MARKDOWN)
    results = []
    for sym in WATCHLIST:
        try:
            ticker = resolve_symbol(sym)
            df     = fetch_data(ticker)
            if df is None:
                results.append(f"❌ {sym}: No data")
                continue
            ind = calc_indicators(df)
            sig = generate_signal(ind)
            emoji = "🟢" if "BUY" in sig["direction"] else ("🔴" if "SELL" in sig["direction"] else "⚖️")
            take  = "✅" if sig["take_trade"] else "❌"
            results.append(
                f"{emoji} *{sym}*: {sig['direction']} | "
                f"Conf: `{sig['confidence']}%` | "
                f"Entry: `{fmt(sig['entry'])}` | {take}"
            )
        except Exception:
            results.append(f"⚠️ {sym}: Error")

    now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    msg = f"📋 *Watchlist Scan — {now}*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "\n".join(results)
    msg += "\n\n⚠️ _Not financial advice._"
    await wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    ms  = market_status()
    msg = (
        f"🤖 *TradingBot v2 — Status*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Bot: *Online*\n"
        f"🕐 Time: `{now}`\n\n"
        f"*Market Hours:*\n{ms}\n"
        f"Data Source: Yahoo Finance\n"
        f"Indicators: RSI, MACD, EMA9/20/50/200,\n"
        f"  BB, Stoch, ATR, ADX, CCI, OBV\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def unknown_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Unknown command. Type /help for all commands."
    )

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("signal",    cmd_signal))
    app.add_handler(CommandHandler("chart",     cmd_chart))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))

    log.info("TradingBot Telegram interface started ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
