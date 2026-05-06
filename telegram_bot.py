#!/usr/bin/env python3
"""
TradingBot v4 - Full Telegram Signal Bot with LIVE NSE Options Prices

Commands:
  /signal              → Auto-scan ALL symbols
  /signal BTC          → Deep signal for any symbol
  /signal NIFTY 24000 CE  → Options signal + LIVE option price in ₹
  /signal NIFTY 24000 PE  → Put option signal + LIVE price
  /option NIFTY 24000 CE  → Live option price, OI, IV, volume only
  /chart SYM           → Mini ASCII chart
  /watchlist           → Quick scan 8 symbols
  /status              → Bot health + market hours
  /help                → All commands
"""

import os, sys, logging, traceback, time
from datetime import datetime, time as dtime
import pytz, requests
import yfinance as yf
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")]
)
log = logging.getLogger(__name__)

# ── NSE Live Options Price Fetcher ─────────────────────────────────────────────────
# NSE India API — completely free, no key needed
NSE_OC_URLS = {
    "NIFTY":     "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
    "BANKNIFTY": "https://www.nseindia.com/api/option-chain-indices?symbol=BANKNIFTY",
    "FINNIFTY":  "https://www.nseindia.com/api/option-chain-indices?symbol=FINNIFTY",
    "MIDCPNIFTY":"https://www.nseindia.com/api/option-chain-indices?symbol=MIDCPNIFTY",
    # Stocks
    "RELIANCE":  "https://www.nseindia.com/api/option-chain-equities?symbol=RELIANCE",
    "TCS":       "https://www.nseindia.com/api/option-chain-equities?symbol=TCS",
    "INFY":      "https://www.nseindia.com/api/option-chain-equities?symbol=INFY",
    "HDFCBANK":  "https://www.nseindia.com/api/option-chain-equities?symbol=HDFCBANK",
    "ICICIBANK": "https://www.nseindia.com/api/option-chain-equities?symbol=ICICIBANK",
    "SBIN":      "https://www.nseindia.com/api/option-chain-equities?symbol=SBIN",
}

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

def get_nse_session() -> requests.Session:
    """Create a session with NSE cookies (required for API access)."""
    sess = requests.Session()
    sess.headers.update(NSE_HEADERS)
    try:
        # First hit the main page to get cookies
        sess.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        sess.get("https://www.nseindia.com/option-chain", timeout=10)
        time.sleep(0.5)
    except Exception:
        pass
    return sess

def fetch_live_option_price(sym: str, strike: float, opt_type: str) -> dict | None:
    """
    Fetch live option price from NSE India API.
    Returns dict with: ltp, oi, volume, iv, change, pct_change, expiry
    Returns None if market closed or data unavailable.
    """
    sym_upper = sym.upper()
    url = NSE_OC_URLS.get(sym_upper)
    if not url:
        return None

    try:
        sess = get_nse_session()
        resp = sess.get(url, timeout=15)
        if resp.status_code != 200:
            log.warning(f"NSE API returned {resp.status_code} for {sym_upper}")
            return None

        data = resp.json()
        records = data.get("records", {}).get("data", [])
        expiry_dates = data.get("records", {}).get("expiryDates", [])
        nearest_expiry = expiry_dates[0] if expiry_dates else None
        underlying = data.get("records", {}).get("underlyingValue", 0)

        # Find matching strike + expiry
        for rec in records:
            if rec.get("strikePrice") == strike:
                # Try nearest expiry first, else take first available
                if nearest_expiry and rec.get("expiryDate") != nearest_expiry:
                    continue
                opt_data = rec.get(opt_type.upper(), {})
                if not opt_data:
                    continue
                return {
                    "ltp":         opt_data.get("lastPrice", 0),
                    "oi":          opt_data.get("openInterest", 0),
                    "oi_change":   opt_data.get("changeinOpenInterest", 0),
                    "volume":      opt_data.get("totalTradedVolume", 0),
                    "iv":          opt_data.get("impliedVolatility", 0),
                    "change":      opt_data.get("change", 0),
                    "pct_change":  opt_data.get("pChange", 0),
                    "bid":         opt_data.get("bidPrice", 0),
                    "ask":         opt_data.get("askPrice", 0),
                    "expiry":      rec.get("expiryDate", "N/A"),
                    "underlying":  underlying,
                    "high":        opt_data.get("highPrice", 0),
                    "low":         opt_data.get("lowPrice", 0),
                }
        # Strike not found exactly — find nearest
        return None
    except Exception as e:
        log.error(f"NSE option fetch error: {e}")
        return None

def find_nearest_strikes(sym: str, count: int = 5) -> list:
    """Find nearest ITM/ATM/OTM strikes around current price."""
    sym_upper = sym.upper()
    url = NSE_OC_URLS.get(sym_upper)
    if not url:
        return []
    try:
        sess = get_nse_session()
        resp = sess.get(url, timeout=15)
        data = resp.json()
        underlying = data.get("records", {}).get("underlyingValue", 0)
        expiry_dates = data.get("records", {}).get("expiryDates", [])
        nearest_expiry = expiry_dates[0] if expiry_dates else None
        records = data.get("records", {}).get("data", [])

        strikes = []
        for rec in records:
            if nearest_expiry and rec.get("expiryDate") != nearest_expiry:
                continue
            sp = rec.get("strikePrice", 0)
            if sp > 0:
                strikes.append(sp)
        strikes = sorted(set(strikes))

        # Find ATM
        atm = min(strikes, key=lambda x: abs(x - underlying)) if strikes else 0
        idx = strikes.index(atm)
        nearby = strikes[max(0, idx-count//2): idx+count//2+1]
        return [(s, underlying) for s in nearby]
    except Exception:
        return []

# ── Symbol Map ────────────────────────────────────────────────────────────────
SYMBOL_MAP = {
    "NIFTY":      "^NSEI",
    "BANKNIFTY":  "^NSEBANK",
    "SENSEX":     "^BSESN",
    "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
    "MIDCAP":     "^NSEMDCP50",
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
    "BTC":   "BTC-USD",  "ETH":   "ETH-USD",
    "BNB":   "BNB-USD",  "SOL":   "SOL-USD",
    "XRP":   "XRP-USD",  "ADA":   "ADA-USD",
    "DOGE":  "DOGE-USD", "AVAX":  "AVAX-USD",
    "AAPL":  "AAPL",     "TSLA":  "TSLA",
    "NVDA":  "NVDA",     "AMZN":  "AMZN",
    "GOOGL": "GOOGL",    "MSFT":  "MSFT",
    "META":  "META",
}

ALL_SYMBOLS = [
    "NIFTY", "BANKNIFTY", "SENSEX",
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN",
    "WIPRO", "BAJFINANCE", "TATAMOTORS", "AXISBANK",
    "BTC", "ETH", "SOL", "BNB",
    "TSLA", "NVDA", "AAPL", "META",
]
WATCHLIST = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "BTC", "ETH", "TSLA", "NVDA"]

def resolve(sym: str) -> str:
    return SYMBOL_MAP.get(sym.upper().strip(), sym.upper().strip())

# ── Data & Indicators ─────────────────────────────────────────────────────────────
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

def indicators(df: pd.DataFrame) -> dict:
    c = df["Close"].squeeze(); h = df["High"].squeeze(); l = df["Low"].squeeze()
    vol = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(dtype=float)
    d = c.diff(); g = d.clip(lower=0).rolling(14).mean()
    ls = (-d.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100/(1 + g/ls.replace(0, np.nan))
    e12 = c.ewm(span=12).mean(); e26 = c.ewm(span=26).mean()
    macd = e12-e26; msig = macd.ewm(span=9).mean(); mhist = macd-msig
    e9=c.ewm(span=9).mean(); e20=c.ewm(span=20).mean()
    e50=c.ewm(span=50).mean(); e200=c.ewm(span=200).mean()
    s20=c.rolling(20).mean(); std20=c.rolling(20).std()
    bb_u=s20+2*std20; bb_l=s20-2*std20
    bb_p=(c-bb_l)/(bb_u-bb_l+1e-9)
    l14=l.rolling(14).min(); h14=h.rolling(14).max()
    sk=100*(c-l14)/(h14-l14+1e-9); sd=sk.rolling(3).mean()
    tr=pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14).mean()
    um=h.diff(); dm=-l.diff()
    pdm=np.where((um>dm)&(um>0),um,0.0); ndm=np.where((dm>um)&(dm>0),dm,0.0)
    a14=tr.rolling(14).mean()
    pdi=100*pd.Series(pdm,index=df.index).rolling(14).mean()/(a14+1e-9)
    ndi=100*pd.Series(ndm,index=df.index).rolling(14).mean()/(a14+1e-9)
    adx=(100*(pdi-ndi).abs()/(pdi+ndi+1e-9)).rolling(14).mean()
    tp=(h+l+c)/3
    cci=(tp-tp.rolling(20).mean())/(0.015*tp.rolling(20).std()+1e-9)
    obv_slope=0.0
    if not vol.empty and len(vol)>5:
        obv=(np.sign(c.diff())*vol).fillna(0).cumsum()
        obv_slope=float(obv.diff(5).iloc[-1])
    h20=h.iloc[-20:].max(); l20=l.iloc[-20:].min(); c0=float(c.iloc[-1])
    piv=(h20+l20+c0)/3; r1=2*piv-l20; r2=piv+(h20-l20)
    s1=2*piv-h20; s2=piv-(h20-l20)
    return dict(
        close=c0,rsi=float(rsi.iloc[-1]),macd=float(macd.iloc[-1]),
        macd_sig=float(msig.iloc[-1]),macd_hist=float(mhist.iloc[-1]),
        e9=float(e9.iloc[-1]),e20=float(e20.iloc[-1]),
        e50=float(e50.iloc[-1]),e200=float(e200.iloc[-1]),
        bb_p=float(bb_p.iloc[-1]),bb_u=float(bb_u.iloc[-1]),bb_l=float(bb_l.iloc[-1]),
        sk=float(sk.iloc[-1]),sd=float(sd.iloc[-1]),
        atr=float(atr.iloc[-1]),adx=float(adx.iloc[-1]),
        pdi=float(pdi.iloc[-1]),ndi=float(ndi.iloc[-1]),
        cci=float(cci.iloc[-1]),obv_slope=obv_slope,
        piv=piv,r1=r1,r2=r2,s1=s1,s2=s2,h20=float(h20),l20=float(l20),
    )

# ── Signal Engine ─────────────────────────────────────────────────────────────
def make_signal(ind: dict, opt_type: str = "") -> dict:
    sb,ss,rb,rs=0,0,[],[]
    c=ind["close"]; rsi=ind["rsi"]; macd=ind["macd"]; ms=ind["macd_sig"]
    adx=ind["adx"]; atr=ind["atr"]; cci=ind["cci"]; sk=ind["sk"]; sd=ind["sd"]; bb=ind["bb_p"]
    if rsi<30: sb+=3;rb.append(f"RSI oversold {rsi:.1f}")
    elif rsi<45: sb+=1;rb.append(f"RSI low {rsi:.1f}")
    elif rsi>70: ss+=3;rs.append(f"RSI overbought {rsi:.1f}")
    elif rsi>55: ss+=1;rs.append(f"RSI high {rsi:.1f}")
    if macd>ms and ind["macd_hist"]>0: sb+=2;rb.append("MACD bullish")
    elif macd<ms and ind["macd_hist"]<0: ss+=2;rs.append("MACD bearish")
    if ind["e9"]>ind["e20"]>ind["e50"]: sb+=2;rb.append("EMA bull stack")
    elif ind["e9"]<ind["e20"]<ind["e50"]: ss+=2;rs.append("EMA bear stack")
    if c>ind["e200"]: sb+=1;rb.append("Above EMA200")
    else: ss+=1;rs.append("Below EMA200")
    if adx>25:
        if ind["pdi"]>ind["ndi"]: sb+=2;rb.append(f"ADX {adx:.1f} bull trend")
        else: ss+=2;rs.append(f"ADX {adx:.1f} bear trend")
    if bb<0.15: sb+=2;rb.append("Near BB lower (oversold)")
    elif bb>0.85: ss+=2;rs.append("Near BB upper (overbought)")
    if sk<20 and sd<20: sb+=2;rb.append(f"Stoch oversold {sk:.1f}")
    elif sk>80 and sd>80: ss+=2;rs.append(f"Stoch overbought {sk:.1f}")
    if cci<-100: sb+=1;rb.append(f"CCI oversold {cci:.0f}")
    elif cci>100: ss+=1;rs.append(f"CCI overbought {cci:.0f}")
    if ind["obv_slope"]>0: sb+=1;rb.append("OBV rising")
    elif ind["obv_slope"]<0: ss+=1;rs.append("OBV falling")
    total=sb+ss
    conf=int(max(sb,ss)/total*100) if total else 50
    raw="BUY" if sb>ss else ("SELL" if ss>sb else "NEUTRAL")
    dir_=raw
    if opt_type=="CE":
        dir_="BUY CE ✅ (Bullish)" if raw=="BUY" else "AVOID CE ❌ (Bearish)"
    elif opt_type=="PE":
        dir_="BUY PE ✅ (Bearish)" if raw=="SELL" else "AVOID PE ❌ (Bullish)"
    if raw=="BUY":
        entry=round(c*1.0015,2); sl=round(max(c-2.0*atr,ind["s1"]),2)
        t1=round(entry+1.5*atr,2); t2=round(entry+2.5*atr,2); t3=round(entry+4.0*atr,2)
    else:
        entry=round(c*0.9985,2); sl=round(min(c+2.0*atr,ind["r1"]),2)
        t1=round(entry-1.5*atr,2); t2=round(entry-2.5*atr,2); t3=round(entry-4.0*atr,2)
    risk=abs(entry-sl)
    rr1=round(abs(t1-entry)/risk,2) if risk else 0
    rr3=round(abs(t3-entry)/risk,2) if risk else 0
    if conf>=75 and adx>25 and rr1>=1.5:
        meter="🟩🟩🟩🟩🟩 LOW RISK"; take=True
        advice="Strong setup ✅ Full position OK"
    elif conf>=65 and rr1>=1.2:
        meter="🟨🟨🟨🟩🟩 MEDIUM RISK"; take=True
        advice="Good setup 🟡 Use 50% position"
    elif conf>=55:
        meter="🟧🟧🟧🟨🟩 HIGH RISK"; take=False
        advice="Weak setup 🟠 Wait for confirmation"
    else:
        meter="🟥🟥🟥🟥🟥 AVOID"; take=False
        advice="No edge ❌ Skip this trade"
    reasons=rb if raw=="BUY" else rs
    return dict(
        dir=dir_,raw=raw,conf=conf,
        entry=entry,sl=sl,t1=t1,t2=t2,t3=t3,
        rr1=rr1,rr3=rr3,meter=meter,take=take,advice=advice,
        reasons=reasons[:5],
        rsi=round(rsi,1),adx=round(adx,1),atr=round(atr,2),
        piv=round(ind["piv"],2),r1=round(ind["r1"],2),r2=round(ind["r2"],2),
        s1=round(ind["s1"],2),s2=round(ind["s2"],2),
    )

# ── Helpers ────────────────────────────────────────────────────────────────────
def f(v,d=2): return f"{v:,.{d}f}" if abs(v)>=1000 else f"{v:.{d}f}"
def risk_bar(conf): filled=round(conf/10); return "["+"█"*filled+"░"*(10-filled)+f"] {conf}%"

def oi_fmt(oi): 
    if oi>=10_000_000: return f"{oi/10_000_000:.2f}Cr"
    if oi>=100_000: return f"{oi/100_000:.2f}L"
    return f"{oi:,}"

def mkt_open() -> bool:
    now=datetime.now(IST); t=now.time(); wd=now.weekday()
    return wd<5 and dtime(9,15)<=t<=dtime(15,30)

def mkt_status():
    now=datetime.now(IST); t=now.time(); wd=now.weekday()
    nse="🟢 Open" if wd<5 and dtime(9,15)<=t<=dtime(15,30) else "🔴 Closed"
    us="🟢 Open" if t>=dtime(19,0) or t<=dtime(1,30) else "🔴 Closed"
    return f"🇮🇳 NSE: {nse} | 🇺🇸 NYSE: {us} | ₿ Crypto: 🟢 24/7"

# ── Message Builders ───────────────────────────────────────────────────────────
def build_options_block(opt_data: dict | None, strike: float, opt_type: str, underlying: float) -> str:
    """Build the LIVE OPTION PRICE block for the message."""
    sep = "━" * 30
    if opt_data is None:
        if not mkt_open():
            return (
                f"\n💹 *LIVE OPTION PRICE*\n`{sep}`\n"
                f"⏰ *NSE is closed right now*\n"
                f"🗓 Market opens Mon–Fri 9:15 AM – 3:30 PM IST\n"
                f"Last traded price unavailable outside market hours.\n"
            )
        return (
            f"\n💹 *LIVE OPTION PRICE*\n`{sep}`\n"
            f"⚠️ Strike {int(strike)} {opt_type} not found in current chain.\n"
            f"Try ATM strike or use `/option {opt_type}` for nearest strikes.\n"
        )

    change_icon = "📈" if opt_data["change"] >= 0 else "📉"
    pct = opt_data["pct_change"]
    moneyness = ""
    if underlying > 0 and strike > 0:
        diff = ((underlying - strike) / strike) * 100
        if opt_type == "CE":
            moneyness = "ITM 🟢" if underlying > strike else ("ATM 🟡" if abs(diff) < 0.5 else "OTM 🔴")
        else:
            moneyness = "ITM 🟢" if underlying < strike else ("ATM 🟡" if abs(diff) < 0.5 else "OTM 🔴")

    return (
        f"\n💹 *LIVE OPTION PRICE — NSE*\n`{sep}`\n"
        f"🗓 Expiry     : `{opt_data['expiry']}`\n"
        f"📍 Moneyness  : `{moneyness}`\n"
        f"💵 *LTP       : ₹{f(opt_data['ltp'])}*\n"
        f"   Bid: `₹{f(opt_data['bid'])}`  Ask: `₹{f(opt_data['ask'])}`\n"
        f"   Day High: `₹{f(opt_data['high'])}`  Low: `₹{f(opt_data['low'])}`\n"
        f"{change_icon} Change     : `₹{f(opt_data['change'])}` ({pct:+.2f}%)\n"
        f"📊 OI         : `{oi_fmt(opt_data['oi'])}`"
        f"  Change: `{oi_fmt(opt_data['oi_change'])}`\n"
        f"📈 Volume     : `{oi_fmt(opt_data['volume'])}`\n"
        f"🌀 Impl.Vol   : `{opt_data['iv']:.1f}%`\n"
        f"🏗 Underlying : `₹{f(underlying)}`\n"
    )

def build_msg(sym, ticker, ind, sig, opt_type="", strike=0.0, opt_data=None):
    now = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    arrow = "🚀" if "BUY" in sig["raw"] else ("📉" if sig["raw"]=="SELL" else "⚖️")
    if opt_type:
        title=f"{sym} {int(strike)} {opt_type}"; tag="📋 NSE OPTIONS"
    elif "-USD" in ticker:
        title=sym; tag="₿ CRYPTO"
    elif any(x in ticker for x in [".NS","^NSE","^BSE"]):
        title=sym; tag="🇮🇳 INDIAN MARKET"
    else:
        title=sym; tag="🇺🇸 US MARKET"
    sep="━"*30
    take_icon="✅ YES — ENTER" if sig["take"] else "❌ NO — SKIP"
    rb="".join(f"  • {r}\n" for r in sig["reasons"])

    opt_block = build_options_block(opt_data, strike, opt_type, ind["close"]) if opt_type else ""

    return (
        f"{arrow} *{title} — {sig['dir']}*\n"
        f"`{sep}`\n"
        f"🕐 {now} | {tag}\n"
        f"{opt_block}\n"
        f"*📊 UNDERLYING SIGNAL*\n"
        f"`{sep}`\n"
        f"💵 Underlying Price : `{f(ind['close'])}`\n"
        f"🎯 Entry Zone        : `{f(sig['entry'])}`\n"
        f"🛑 Stop Loss         : `{f(sig['sl'])}` ← hard stop\n"
        f"🎯 Target 1           : `{f(sig['t1'])}` ← book 40%\n"
        f"🎯 Target 2           : `{f(sig['t2'])}` ← book 35%\n"
        f"🎯 Target 3           : `{f(sig['t3'])}` ← trail rest\n\n"
        f"*⚖️ RISK METER*\n"
        f"`{sep}`\n"
        f"`{risk_bar(sig['conf'])}`\n"
        f"{sig['meter']}\n"
        f"R:R T1:`1:{sig['rr1']}`  T3:`1:{sig['rr3']}`\n"
        f"Trade: *{take_icon}*\n"
        f"💡 {sig['advice']}\n\n"
        f"*📐 TECHNICALS*\n"
        f"`{sep}`\n"
        f"RSI `{sig['rsi']}` ADX `{sig['adx']}` ATR `{f(sig['atr'])}`\n"
        f"Pivot `{f(sig['piv'])}` R1 `{f(sig['r1'])}` S1 `{f(sig['s1'])}`\n\n"
        f"*🧠 REASONS*\n`{sep}`\n{rb}"
        f"\n⚠️ _Not financial advice. Trade at your own risk._"
    )

# ── Handlers ──────────────────────────────────────────────────────────────────
async def cmd_signal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or []

    # ── /signal → auto scan ──
    if not args:
        wait = await update.message.reply_text("🔍 *Scanning all symbols (~30s)...*", parse_mode=ParseMode.MARKDOWN)
        buys, sells, skips = [], [], []
        for sym in ALL_SYMBOLS:
            try:
                df=fetch(resolve(sym))
                if df is None: continue
                ind=indicators(df); sig=make_signal(ind)
                em="🟢" if sig["raw"]=="BUY" else "🔴"
                tk="✅" if sig["take"] else "❌"
                line=f"{em} *{sym}* `{sig['dir']}` Conf:`{sig['conf']}%` E:`{f(sig['entry'])}` SL:`{f(sig['sl'])}` T1:`{f(sig['t1'])}` {tk}"
                if sig["take"] and sig["raw"]=="BUY": buys.append(line)
                elif sig["take"] and sig["raw"]=="SELL": sells.append(line)
                else: skips.append(f"⚪ *{sym}* {sig['dir']} {sig['conf']}% {tk}")
            except Exception: continue
        now=datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
        sep="━"*30
        out=f"📡 *AUTO SCAN — {now}*\n`{sep}`\n{mkt_status()}\n`{sep}`\n\n"
        if buys: out+=f"🚀 *BUY SIGNALS ({len(buys)})*\n`{sep}`\n"+"\n".join(buys)+"\n\n"
        if sells: out+=f"📉 *SELL SIGNALS ({len(sells)})*\n`{sep}`\n"+"\n".join(sells)+"\n\n"
        if not buys and not sells: out+="⚪ *No strong signals now.* Market may be ranging.\n\n"
        if skips: out+=f"⚪ *Low confidence ({len(skips)})*\n"+"\n".join(skips[:5])+"\n"
        out+="\n💡 `/signal NIFTY 24000 CE` for options signal\n⚠️ _Not financial advice._"
        await wait.edit_text(out, parse_mode=ParseMode.MARKDOWN); return

    sym=args[0].upper(); opt_type=""; strike=0.0
    if len(args)==3:
        try:
            strike=float(args[1]); opt_type=args[2].upper()
            if opt_type not in ("CE","PE"):
                await update.message.reply_text("Use CE or PE. Example: `/signal NIFTY 24000 CE`", parse_mode=ParseMode.MARKDOWN); return
        except ValueError:
            await update.message.reply_text("Invalid. Example: `/signal NIFTY 24000 CE`", parse_mode=ParseMode.MARKDOWN); return

    ticker=resolve(sym)
    label=f"{sym} {int(strike)} {opt_type}" if opt_type else sym
    wait=await update.message.reply_text(f"⏳ Fetching *{label}*...", parse_mode=ParseMode.MARKDOWN)

    df=fetch(ticker)
    if df is None:
        await wait.edit_text(f"❌ No data for *{sym}*. Try: NIFTY BTC RELIANCE", parse_mode=ParseMode.MARKDOWN); return

    ind=indicators(df)
    sig=make_signal(ind, opt_type)

    # Fetch live option price from NSE
    opt_data = None
    if opt_type:
        opt_data = fetch_live_option_price(sym, strike, opt_type)

    msg=build_msg(sym, ticker, ind, sig, opt_type, strike, opt_data)
    await wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
    log.info(f"Signal: {label} → {sig['dir']} {sig['conf']}%")

# ── /option — LIVE PRICE ONLY ───────────────────────────────────────────────────
async def cmd_option(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /option NIFTY 24000 CE  → Live price only
    /option NIFTY CE        → Show 5 nearest strikes with prices
    """
    args = ctx.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage:\n`/option NIFTY 24000 CE`\n`/option BANKNIFTY 52000 PE`\n`/option NIFTY CE` (nearest strikes)",
            parse_mode=ParseMode.MARKDOWN
        ); return

    sym = args[0].upper()

    # /option NIFTY CE → show nearest strikes
    if len(args) == 2:
        opt_type = args[1].upper()
        if opt_type not in ("CE", "PE"):
            await update.message.reply_text("Use CE or PE."); return
        wait = await update.message.reply_text(f"⏳ Fetching nearest {opt_type} strikes for *{sym}*...", parse_mode=ParseMode.MARKDOWN)
        strikes = find_nearest_strikes(sym, 7)
        if not strikes:
            await wait.edit_text(f"❌ Cannot fetch strikes for {sym}. NSE may be closed."); return
        sep = "━"*30
        underlying = strikes[0][1]
        msg = f"📋 *{sym} {opt_type} — Nearest Strikes*\n`{sep}`\n🏗 Underlying: `₹{f(underlying)}`\n`{sep}`\n"
        for sp, _ in strikes:
            od = fetch_live_option_price(sym, sp, opt_type)
            if od:
                ltp = od["ltp"]; chg = od["pct_change"]; vol = oi_fmt(od["volume"])
                itm = "ITM🟢" if ((opt_type=="CE" and underlying>sp) or (opt_type=="PE" and underlying<sp)) else "OTM🔴"
                atm = " ⭐ATM" if abs(underlying-sp)<50 else ""
                msg += f"`{int(sp):>7}` {itm}{atm} → `₹{f(ltp)}` ({chg:+.1f}%) Vol:`{vol}`\n"
            else:
                msg += f"`{int(sp):>7}` → No data\n"
        msg += f"\n⚠️ _Not financial advice._"
        await wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN); return

    # /option NIFTY 24000 CE
    if len(args) == 3:
        try:
            strike = float(args[1]); opt_type = args[2].upper()
            if opt_type not in ("CE","PE"):
                await update.message.reply_text("Use CE or PE."); return
        except ValueError:
            await update.message.reply_text("Invalid. Example: `/option NIFTY 24000 CE`", parse_mode=ParseMode.MARKDOWN); return

        wait = await update.message.reply_text(f"⏳ Fetching live price for *{sym} {int(strike)} {opt_type}*...", parse_mode=ParseMode.MARKDOWN)
        od = fetch_live_option_price(sym, strike, opt_type)
        # Get underlying
        df = fetch(resolve(sym))
        underlying = float(df["Close"].squeeze().iloc[-1]) if df is not None else 0

        sep="━"*30
        block = build_options_block(od, strike, opt_type, underlying)
        msg = f"📋 *{sym} {int(strike)} {opt_type} — Live Price*\n`{sep}`\n{block}\n⚠️ _Not financial advice._"
        await wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── /chart ────────────────────────────────────────────────────────────────────
async def cmd_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/chart BTC`", parse_mode=ParseMode.MARKDOWN); return
    sym=ctx.args[0].upper()
    wait=await update.message.reply_text(f"⏳ *{sym}* chart...", parse_mode=ParseMode.MARKDOWN)
    df=fetch(resolve(sym))
    if df is None: await wait.edit_text(f"❌ No data for {sym}"); return
    closes=df["Close"].squeeze().tail(20).values
    mn,mx=closes.min(),closes.max(); chart=[]
    for row in range(6,-1,-1):
        thresh=mn+(row/6)*(mx-mn)
        chart.append("".join("█" if v>=thresh else " " for v in closes))
    trend="📈 UPTREND" if closes[-1]>closes[0] else "📉 DOWNTREND"
    pct=(closes[-1]-closes[0])/closes[0]*100
    txt=f"📊 *{sym} — Last 20 candles*\n```\n"+"\n".join(chart)+f"\n```\nHigh `{f(float(mx))}`  Low `{f(float(mn))}`  Now `{f(float(closes[-1]))}`\n{trend} ({pct:+.2f}%)"
    await wait.edit_text(txt, parse_mode=ParseMode.MARKDOWN)

# ── /watchlist ────────────────────────────────────────────────────────────────
async def cmd_watchlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    wait=await update.message.reply_text("⏳ Scanning watchlist...", parse_mode=ParseMode.MARKDOWN)
    rows=[]
    for sym in WATCHLIST:
        try:
            df=fetch(resolve(sym))
            if df is None: rows.append(f"❌ {sym}"); continue
            ind=indicators(df); sig=make_signal(ind)
            em="🟢" if sig["raw"]=="BUY" else "🔴"
            tk="✅" if sig["take"] else "❌"
            rows.append(f"{em} *{sym}* `{sig['dir']}` Conf:`{sig['conf']}%` E:`{f(sig['entry'])}` {tk}")
        except: rows.append(f"⚠️ {sym}: error")
    now=datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    msg=f"📋 *Watchlist — {now}*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"+"\n".join(rows)+"\n\n⚠️ _Not financial advice._"
    await wait.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── /status ───────────────────────────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now=datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    msg=(f"🤖 *TradingBot v4 — Online*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
         f"🕐 `{now}`\n{mkt_status()}\n\n"
         f"📈 Indicators: RSI MACD EMA9/20/50/200 BB Stoch ATR ADX CCI OBV\n"
         f"🇮🇳 Options: NSE India live prices (CE/PE)\n"
         f"📡 Data: Yahoo Finance + NSE India API\n"
         f"🔢 Symbols: {len(ALL_SYMBOLS)} tracked")
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── /help ────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg=("📖 *TradingBot v4 — Commands*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
         "`/signal` → 🔍 Scan ALL 21 symbols\n"
         "`/signal BTC` → 📊 Deep signal\n"
         "`/signal NIFTY 24000 CE` → Signal + 💹 Live CE price\n"
         "`/signal NIFTY 24000 PE` → Signal + 💹 Live PE price\n"
         "`/option NIFTY 24000 CE` → Live price, OI, IV, volume\n"
         "`/option NIFTY CE` → Nearest 7 strikes with prices\n"
         "`/chart RELIANCE` → ASCII chart\n"
         "`/watchlist` → Quick 8-symbol scan\n"
         "`/status` → Bot health\n\n"
         "*Options available for:*\nNIFTY BANKNIFTY FINNIFTY RELIANCE TCS INFY HDFCBANK ICICIBANK SBIN\n\n"
         "*All symbols:* NIFTY BANKNIFTY SENSEX + 30 stocks/crypto/US\n\n"
         "⚠️ _Not financial advice._")
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *TradingBot v4 LIVE!*\n\n/signal — scan all\n/signal NIFTY 24000 CE — live option price + signal\n/help — all commands", parse_mode=ParseMode.MARKDOWN)

async def unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Try /help")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        log.error("Set TELEGRAM_BOT_TOKEN in .env"); sys.exit(1)
    app=Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("signal",    cmd_signal))
    app.add_handler(CommandHandler("option",    cmd_option))
    app.add_handler(CommandHandler("chart",     cmd_chart))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    log.info("TradingBot v4 started ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
