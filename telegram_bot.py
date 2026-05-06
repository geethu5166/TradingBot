#!/usr/bin/env python3
"""
TradingBot v3 - Full Telegram Signal Bot

Commands:
  /signal              → Auto-scan ALL symbols, show only actionable ones
  /signal BTC          → Full detailed signal for one symbol
  /signal NIFTY 24000 CE  → Options signal with entry price, risk meter, T1/T2/T3, SL
  /signal NIFTY 24000 PE  → Put options signal
  /chart SYM           → Mini ASCII chart + trend
  /watchlist           → Quick table scan of all symbols
  /status              → Bot health + market hours
  /help                → All commands
"""

import os, sys, logging, traceback
from datetime import datetime, time as dtime
import pytz
import yfinance as yf
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")]
)
log = logging.getLogger(__name__)

# ── Symbol Map ────────────────────────────────────────────────────────────────
SYMBOL_MAP = {
    # Indian indices
    "NIFTY":      "^NSEI",
    "BANKNIFTY":  "^NSEBANK",
    "SENSEX":     "^BSESN",
    "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
    "MIDCAP":     "^NSEMDCP50",
    # Indian stocks
    "RELIANCE":   "RELIANCE.NS",
    "TCS":        "TCS.NS",
    "INFY":       "INFY.NS",
    "HDFC":       "HDFCBANK.NS",
    "HDFCBANK":   "HDFCBANK.NS",
    "ICICIBANK":  "ICICIBANK.NS",
    "SBIN":       "SBIN.NS",
    "WIPRO":      "WIPRO.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "ADANIENT":   "ADANIENT.NS",
    "MARUTI":     "MARUTI.NS",
    "SUNPHARMA":  "SUNPHARMA.NS",
    "AXISBANK":   "AXISBANK.NS",
    "LT":         "LT.NS",
    "TITAN":      "TITAN.NS",
    # Crypto
    "BTC":   "BTC-USD",
    "ETH":   "ETH-USD",
    "BNB":   "BNB-USD",
    "SOL":   "SOL-USD",
    "XRP":   "XRP-USD",
    "ADA":   "ADA-USD",
    "DOGE":  "DOGE-USD",
    "AVAX":  "AVAX-USD",
    "MATIC": "MATIC-USD",
    # US stocks
    "AAPL":  "AAPL",
    "TSLA":  "TSLA",
    "NVDA":  "NVDA",
    "AMZN":  "AMZN",
    "GOOGL": "GOOGL",
    "MSFT":  "MSFT",
    "META":  "META",
}

# Full auto-scan list (used when /signal is typed alone)
ALL_SYMBOLS = [
    "NIFTY", "BANKNIFTY", "SENSEX",
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN",
    "WIPRO", "BAJFINANCE", "TATAMOTORS", "AXISBANK",
    "BTC", "ETH", "SOL", "BNB",
    "TSLA", "NVDA", "AAPL", "META",
]

def resolve(sym: str) -> str:
    s = sym.upper().strip()
    return SYMBOL_MAP.get(s, s)

# ── Data Fetch ────────────────────────────────────────────────────────────────
def fetch(ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, period="3mo", interval="1h",
                         auto_adjust=True, progress=False, threads=False)
        if df is None or len(df) < 30:
            df = yf.download(ticker, period="6mo", interval="1d",
                             auto_adjust=True, progress=False, threads=False)
        if df is None or len(df) < 20:
            return None
        df.dropna(inplace=True)
        return df
    except Exception:
        return None

# ── Indicators ────────────────────────────────────────────────────────────────
def indicators(df: pd.DataFrame) -> dict:
    c   = df["Close"].squeeze()
    h   = df["High"].squeeze()
    l   = df["Low"].squeeze()
    vol = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(dtype=float)

    # RSI
    d  = c.diff()
    g  = d.clip(lower=0).rolling(14).mean()
    ls = (-d.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + g / ls.replace(0, np.nan))

    # MACD
    e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean()
    macd = e12 - e26; msig = macd.ewm(span=9).mean(); mhist = macd - msig

    # EMAs
    e9  = c.ewm(span=9).mean()
    e20 = c.ewm(span=20).mean()
    e50 = c.ewm(span=50).mean()
    e200= c.ewm(span=200).mean()

    # Bollinger
    s20  = c.rolling(20).mean(); std20 = c.rolling(20).std()
    bb_u = s20 + 2*std20; bb_l = s20 - 2*std20
    bb_p = (c - bb_l) / (bb_u - bb_l + 1e-9)

    # Stochastic
    l14 = l.rolling(14).min(); h14 = h.rolling(14).max()
    sk = 100*(c-l14)/(h14-l14+1e-9); sd = sk.rolling(3).mean()

    # ATR
    tr = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # ADX
    um = h.diff(); dm = -l.diff()
    pdm = np.where((um>dm)&(um>0), um, 0.0)
    ndm = np.where((dm>um)&(dm>0), dm, 0.0)
    a14 = tr.rolling(14).mean()
    pdi = 100*pd.Series(pdm,index=df.index).rolling(14).mean()/(a14+1e-9)
    ndi = 100*pd.Series(ndm,index=df.index).rolling(14).mean()/(a14+1e-9)
    adx = (100*(pdi-ndi).abs()/(pdi+ndi+1e-9)).rolling(14).mean()

    # CCI
    tp  = (h+l+c)/3
    cci = (tp - tp.rolling(20).mean())/(0.015*tp.rolling(20).std()+1e-9)

    # OBV
    obv_slope = 0.0
    if not vol.empty and len(vol) > 5:
        obv = (np.sign(c.diff())*vol).fillna(0).cumsum()
        obv_slope = float(obv.diff(5).iloc[-1])

    # Pivot / S/R
    h20  = h.iloc[-20:].max(); l20 = l.iloc[-20:].min(); c0 = float(c.iloc[-1])
    piv  = (h20+l20+c0)/3
    r1   = 2*piv - l20;  r2 = piv+(h20-l20)
    s1   = 2*piv - h20;  s2 = piv-(h20-l20)

    return dict(
        close=c0, rsi=float(rsi.iloc[-1]), macd=float(macd.iloc[-1]),
        macd_sig=float(msig.iloc[-1]), macd_hist=float(mhist.iloc[-1]),
        e9=float(e9.iloc[-1]), e20=float(e20.iloc[-1]),
        e50=float(e50.iloc[-1]), e200=float(e200.iloc[-1]),
        bb_p=float(bb_p.iloc[-1]), bb_u=float(bb_u.iloc[-1]), bb_l=float(bb_l.iloc[-1]),
        sk=float(sk.iloc[-1]), sd=float(sd.iloc[-1]),
        atr=float(atr.iloc[-1]), adx=float(adx.iloc[-1]),
        pdi=float(pdi.iloc[-1]), ndi=float(ndi.iloc[-1]),
        cci=float(cci.iloc[-1]), obv_slope=obv_slope,
        piv=piv, r1=r1, r2=r2, s1=s1, s2=s2,
        h20=float(h20), l20=float(l20),
    )

# ── Signal Engine ─────────────────────────────────────────────────────────────
def signal(ind: dict, opt_type: str = "") -> dict:
    sb, ss, rb, rs = 0, 0, [], []
    c   = ind["close"]
    rsi = ind["rsi"]; macd = ind["macd"]; ms = ind["macd_sig"]
    adx = ind["adx"]; atr  = ind["atr"];  cci = ind["cci"]
    sk  = ind["sk"];  sd   = ind["sd"];    bb  = ind["bb_p"]

    # ── scoring ──
    if rsi < 30:   sb+=3; rb.append(f"RSI oversold {rsi:.1f}")
    elif rsi < 45: sb+=1; rb.append(f"RSI low {rsi:.1f}")
    elif rsi > 70: ss+=3; rs.append(f"RSI overbought {rsi:.1f}")
    elif rsi > 55: ss+=1; rs.append(f"RSI high {rsi:.1f}")

    if macd > ms and ind["macd_hist"] > 0: sb+=2; rb.append("MACD bullish crossover")
    elif macd < ms and ind["macd_hist"] < 0: ss+=2; rs.append("MACD bearish crossover")

    if ind["e9"]>ind["e20"]>ind["e50"]: sb+=2; rb.append("EMA bull stack 9>20>50")
    elif ind["e9"]<ind["e20"]<ind["e50"]: ss+=2; rs.append("EMA bear stack 9<20<50")

    if c > ind["e200"]: sb+=1; rb.append("Above EMA200")
    else: ss+=1; rs.append("Below EMA200")

    if adx > 25:
        if ind["pdi"] > ind["ndi"]: sb+=2; rb.append(f"ADX {adx:.1f} trending bull")
        else: ss+=2; rs.append(f"ADX {adx:.1f} trending bear")

    if bb < 0.15: sb+=2; rb.append("Near BB lower band (oversold)")
    elif bb > 0.85: ss+=2; rs.append("Near BB upper band (overbought)")

    if sk < 20 and sd < 20: sb+=2; rb.append(f"Stoch oversold {sk:.1f}")
    elif sk > 80 and sd > 80: ss+=2; rs.append(f"Stoch overbought {sk:.1f}")

    if cci < -100: sb+=1; rb.append(f"CCI oversold {cci:.0f}")
    elif cci > 100: ss+=1; rs.append(f"CCI overbought {cci:.0f}")

    if ind["obv_slope"] > 0: sb+=1; rb.append("OBV rising — buy pressure")
    elif ind["obv_slope"] < 0: ss+=1; rs.append("OBV falling — sell pressure")

    total = sb + ss
    conf  = int(max(sb,ss)/total*100) if total else 50
    raw   = "BUY" if sb > ss else ("SELL" if ss > sb else "NEUTRAL")
    dir_  = raw

    # Options direction label
    if opt_type == "CE":
        dir_ = "BUY CE ✅ (Underlying Bullish)" if raw=="BUY" else "AVOID CE ❌ (Underlying Bearish)"
    elif opt_type == "PE":
        dir_ = "BUY PE ✅ (Underlying Bearish)" if raw=="SELL" else "AVOID PE ❌ (Underlying Bullish)"

    # ── Levels ──
    if raw == "BUY":
        entry = round(c * 1.0015, 2)
        sl    = round(max(c - 2.0*atr, ind["s1"]), 2)
        t1    = round(entry + 1.5*atr, 2)
        t2    = round(entry + 2.5*atr, 2)
        t3    = round(entry + 4.0*atr, 2)
    else:
        entry = round(c * 0.9985, 2)
        sl    = round(min(c + 2.0*atr, ind["r1"]), 2)
        t1    = round(entry - 1.5*atr, 2)
        t2    = round(entry - 2.5*atr, 2)
        t3    = round(entry - 4.0*atr, 2)

    risk = abs(entry - sl)
    rr1  = round(abs(t1-entry)/risk, 2) if risk else 0
    rr3  = round(abs(t3-entry)/risk, 2) if risk else 0

    # ── Risk meter (visual bar) ──
    if conf >= 75 and adx > 25 and rr1 >= 1.5:
        meter = "🟩🟩🟩🟩🟩  LOW RISK";      grade="LOW";    take=True
        advice = "Strong setup ✅ — Full position size OK"
    elif conf >= 65 and rr1 >= 1.2:
        meter = "🟨🟨🟨🟩🟩  MEDIUM RISK";   grade="MEDIUM"; take=True
        advice = "Good setup 🟡 — Use 50% position size"
    elif conf >= 55:
        meter = "🟧🟧🟧🟨🟩  HIGH RISK";     grade="HIGH";   take=False
        advice = "Weak setup 🟠 — Wait for confirmation"
    else:
        meter = "🟥🟥🟥🟥🟥  AVOID";         grade="AVOID";  take=False
        advice = "No edge ❌ — Skip this trade"

    reasons = rb if raw=="BUY" else rs

    return dict(
        dir=dir_, raw=raw, conf=conf,
        entry=entry, sl=sl, t1=t1, t2=t2, t3=t3,
        rr1=rr1, rr3=rr3,
        meter=meter, grade=grade, take=take, advice=advice,
        reasons=reasons[:5],
        rsi=round(rsi,1), adx=round(adx,1), atr=round(atr,2),
        piv=round(ind["piv"],2),
        r1=round(ind["r1"],2), r2=round(ind["r2"],2),
        s1=round(ind["s1"],2), s2=round(ind["s2"],2),
    )

# ── Formatting helpers ────────────────────────────────────────────────────────
def f(v: float, d=2) -> str:
    return f"{v:,.{d}f}" if abs(v) >= 1000 else f"{v:.{d}f}"

def risk_bar(conf: int) -> str:
    filled = round(conf / 10)
    return "[" + "█"*filled + "░"*(10-filled) + f"] {conf}%"

def build_msg(sym: str, ticker: str, ind: dict, sig: dict,
              opt_type: str = "", strike: float = 0) -> str:
    now   = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    arrow = "🚀" if "BUY" in sig["raw"] else ("📉" if sig["raw"]=="SELL" else "⚖️")

    if opt_type:
        title     = f"{sym} {int(strike)} {opt_type}"
        asset_tag = "📋 NSE OPTIONS"
    elif "-USD" in ticker:
        title     = sym;  asset_tag = "₿ CRYPTO"
    elif any(x in ticker for x in [".NS","^NSE","^BSE"]):
        title     = sym;  asset_tag = "🇮🇳 INDIAN MARKET"
    else:
        title     = sym;  asset_tag = "🇺🇸 US MARKET"

    sep = "━" * 30
    take_icon = "✅ YES — ENTER TRADE" if sig["take"] else "❌ NO — SKIP"
    reasons_block = "".join(f"  • {r}\n" for r in sig["reasons"])

    # Options note
    opt_note = ""
    if opt_type:
        opt_note = (
            f"\n📌 *OPTIONS NOTE*\n"
            f"`{sep}`\n"
            f"Strike: `{int(strike)} {opt_type}`\n"
            f"Underlying trend: `{'BULLISH' if sig['raw']=='BUY' else 'BEARISH' if sig['raw']=='SELL' else 'NEUTRAL'}`\n"
            f"→ {'BUY CE if underlying rises ✅' if opt_type=='CE' and sig['raw']=='BUY' else 'AVOID CE — underlying is bearish ❌' if opt_type=='CE' else 'BUY PE if underlying falls ✅' if opt_type=='PE' and sig['raw']=='SELL' else 'AVOID PE — underlying is bullish ❌'}\n"
        )

    msg = (
        f"{arrow} *{title} — {sig['dir']}*\n"
        f"`{sep}`\n"
        f"🕐 {now} | {asset_tag}\n\n"

        f"*📊 ENTRY DETAILS*\n"
        f"`{sep}`\n"
        f"💵 Current Price : `{f(ind['close'])}`\n"
        f"🎯 Entry Zone    : `{f(sig['entry'])}`\n"
        f"🛑 Stop Loss     : `{f(sig['sl'])}`  ← hard stop\n"
        f"🎯 Target 1      : `{f(sig['t1'])}` ← book 40%\n"
        f"🎯 Target 2      : `{f(sig['t2'])}` ← book 35%\n"
        f"🎯 Target 3      : `{f(sig['t3'])}` ← trail rest\n\n"

        f"*⚖️ RISK METER*\n"
        f"`{sep}`\n"
        f"`{risk_bar(sig['conf'])}`\n"
        f"{sig['meter']}\n"
        f"R:R (T1) : `1 : {sig['rr1']}`   R:R (T3) : `1 : {sig['rr3']}`\n"
        f"Take Trade : *{take_icon}*\n"
        f"💡 {sig['advice']}\n\n"

        f"*📐 TECHNICALS*\n"
        f"`{sep}`\n"
        f"RSI `{sig['rsi']}` | ADX `{sig['adx']}` | ATR `{f(sig['atr'])}`\n"
        f"Pivot `{f(sig['piv'])}` | R1 `{f(sig['r1'])}` | R2 `{f(sig['r2'])}`\n"
        f"S1 `{f(sig['s1'])}` | S2 `{f(sig['s2'])}`\n\n"

        f"*🧠 SIGNAL REASONS*\n"
        f"`{sep}`\n"
        f"{reasons_block}"
        f"{opt_note}"
        f"\n⚠️ _Not financial advice. Trade at your own risk._"
    )
    return msg

# ── Market hours ──────────────────────────────────────────────────────────────
def mkt_status() -> str:
    now = datetime.now(IST)
    t   = now.time()
    wd  = now.weekday()
    nse = "🟢 Open" if wd<5 and dtime(9,15)<=t<=dtime(15,30) else "🔴 Closed"
    us  = "🟢 Open" if t>=dtime(19,0) or t<=dtime(1,30) else "🔴 Closed"
    return f"🇮🇳 NSE: {nse} | 🇺🇸 NYSE: {us} | ₿ Crypto: 🟢 24/7"

# ── /signal (no args) → auto scan ALL symbols ─────────────────────────────────
async def cmd_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []

    # ── CASE 1: /signal → scan everything ──
    if not args:
        wait = await update.message.reply_text(
            "🔍 *Scanning all symbols... please wait (~30s)*",
            parse_mode=ParseMode.MARKDOWN
        )
        buys, sells, skips = [], [], []
        for sym in ALL_SYMBOLS:
            try:
                df = fetch(resolve(sym))
                if df is None: continue
                ind = indicators(df)
                sig = signal(ind)
                emoji = "🟢" if sig["raw"]=="BUY" else "🔴"
                take  = "✅" if sig["take"] else "❌"
                line  = f"{emoji} *{sym}* `{sig['dir']}` | Conf:`{sig['conf']}%` | Entry:`{f(sig['entry'])}` | SL:`{f(sig['sl'])}` | T1:`{f(sig['t1'])}` {take}"
                if sig["take"] and sig["raw"]=="BUY":   buys.append(line)
                elif sig["take"] and sig["raw"]=="SELL": sells.append(line)
                else: skips.append(f"⚪ *{sym}*: {sig['dir']} | Conf:`{sig['conf']}%` {take}")
            except Exception:
                continue

        now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
        sep = "━"*30
        out = f"📡 *AUTO SCAN — {now}*\n`{sep}`\n{mkt_status()}\n`{sep}`\n\n"

        if buys:
            out += f"🚀 *BUY SIGNALS ({len(buys)})*\n`{sep}`\n" + "\n".join(buys) + "\n\n"
        if sells:
            out += f"📉 *SELL SIGNALS ({len(sells)})*\n`{sep}`\n" + "\n".join(sells) + "\n\n"
        if not buys and not sells:
            out += "⚪ *No actionable signals right now.*\nMarket is ranging or low confidence.\n\n"
        if skips:
            out += f"⚪ *Skipped/Low confidence ({len(skips)})*\n" + "\n".join(skips[:5]) + "\n"
        out += f"\n💡 _Type `/signal BTC` for a deep dive on any symbol._\n⚠️ _Not financial advice._"

        await wait.edit_text(out, parse_mode=ParseMode.MARKDOWN)
        return

    # ── CASE 2: /signal SYM or /signal SYM STRIKE CE/PE ──
    sym      = args[0].upper()
    opt_type = ""
    strike   = 0.0

    if len(args) == 3:
        try:
            strike   = float(args[1])
            opt_type = args[2].upper()
            if opt_type not in ("CE", "PE"):
                await update.message.reply_text("Option type must be CE or PE.\nExample: `/signal NIFTY 24000 CE`",
                                                 parse_mode=ParseMode.MARKDOWN)
                return
        except ValueError:
            await update.message.reply_text("Invalid format.\nExample: `/signal NIFTY 24000 CE`",
                                             parse_mode=ParseMode.MARKDOWN)
            return

    ticker   = resolve(sym)
    wait_msg = await update.message.reply_text(
        f"⏳ Analysing *{sym}{'  '+str(int(strike))+' '+opt_type if opt_type else ''}*...",
        parse_mode=ParseMode.MARKDOWN
    )

    df = fetch(ticker)
    if df is None:
        await wait_msg.edit_text(
            f"❌ No data for *{sym}* (`{ticker}`)\nTry: BTC NIFTY RELIANCE TSLA",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    ind = indicators(df)
    sig = signal(ind, opt_type)
    msg = build_msg(sym, ticker, ind, sig, opt_type, strike)
    await wait_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
    log.info(f"Signal: {sym} {opt_type} → {sig['dir']} | {sig['conf']}% | Entry {sig['entry']}")

# ── /chart ────────────────────────────────────────────────────────────────────
async def cmd_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/chart BTC`", parse_mode=ParseMode.MARKDOWN)
        return
    sym  = ctx.args[0].upper()
    wait = await update.message.reply_text(f"⏳ *{sym}* chart...", parse_mode=ParseMode.MARKDOWN)
    df   = fetch(resolve(sym))
    if df is None:
        await wait.edit_text(f"❌ No data for {sym}"); return
    closes = df["Close"].squeeze().tail(20).values
    mn, mx = closes.min(), closes.max()
    rows   = 6; chart = []
    for row in range(rows, -1, -1):
        thresh = mn + (row/rows)*(mx-mn)
        chart.append("".join("█" if v>=thresh else " " for v in closes))
    trend = "📈 UPTREND" if closes[-1]>closes[0] else "📉 DOWNTREND"
    pct   = (closes[-1]-closes[0])/closes[0]*100
    txt   = f"📊 *{sym} — Last 20 candles*\n```\n" + "\n".join(chart) + f"\n```\n"
    txt  += f"High `{f(float(mx))}`  Low `{f(float(mn))}`  Now `{f(float(closes[-1]))}`\n"
    txt  += f"{trend}  ({pct:+.2f}% / 20 bars)"
    await wait.edit_text(txt, parse_mode=ParseMode.MARKDOWN)

# ── /watchlist ────────────────────────────────────────────────────────────────
WATCHLIST = ["NIFTY","BANKNIFTY","RELIANCE","TCS","BTC","ETH","TSLA","NVDA"]

async def cmd_watchlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    wait = await update.message.reply_text("⏳ Scanning watchlist...", parse_mode=ParseMode.MARKDOWN)
    rows = []
    for sym in WATCHLIST:
        try:
            df  = fetch(resolve(sym))
            if df is None: rows.append(f"❌ {sym}"); continue
            ind = indicators(df)
            sig = signal(ind)
            em  = "🟢" if sig["raw"]=="BUY" else "🔴"
            tk  = "✅" if sig["take"] else "❌"
            rows.append(f"{em} *{sym}*: `{sig['dir']}` Conf:`{sig['conf']}%` E:`{f(sig['entry'])}` {tk}")
        except Exception:
            rows.append(f"⚠️ {sym}: error")
    now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    msg = f"📋 *Watchlist — {now}*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "\n".join(rows) + "\n\n⚠️ _Not financial advice._"
    await wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── /status ───────────────────────────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    msg = (
        f"🤖 *TradingBot v3 — Online*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 `{now}`\n{mkt_status()}\n\n"
        f"📈 Indicators: RSI · MACD · EMA9/20/50/200\n"
        f"  Bollinger · Stoch · ATR · ADX · CCI · OBV\n"
        f"📡 Data: Yahoo Finance (1h + 1d fallback)\n"
        f"🔢 Symbols tracked: {len(ALL_SYMBOLS)}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── /help ─────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *TradingBot v3 — Commands*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "`/signal`\n"
        "  → 🔍 Auto-scan ALL symbols\n\n"
        "`/signal BTC`\n"
        "  → 📊 Deep signal: entry, SL, T1/T2/T3, risk meter\n\n"
        "`/signal NIFTY 24000 CE`\n"
        "  → 📋 Options signal for CE\n\n"
        "`/signal NIFTY 24000 PE`\n"
        "  → 📋 Options signal for PE\n\n"
        "`/chart RELIANCE`\n"
        "  → 📈 ASCII price chart\n\n"
        "`/watchlist`\n"
        "  → 📋 Quick scan of 8 key symbols\n\n"
        "`/status`\n"
        "  → 🤖 Bot health + market hours\n\n"
        "*Symbols:* NIFTY BANKNIFTY SENSEX RELIANCE TCS INFY\n"
        "HDFCBANK ICICIBANK SBIN BTC ETH SOL TSLA NVDA AAPL...\n\n"
        "⚠️ _Not financial advice._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *TradingBot v3 is LIVE!*\n\nType /help or just `/signal` to scan all symbols.",
        parse_mode=ParseMode.MARKDOWN
    )

async def unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Try /help")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        log.error("Set TELEGRAM_BOT_TOKEN in .env"); sys.exit(1)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("signal",    cmd_signal))
    app.add_handler(CommandHandler("chart",     cmd_chart))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    log.info("TradingBot v3 started ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
