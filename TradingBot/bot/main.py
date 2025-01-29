from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import config
from data_fetcher import DataFetcher
from strategies import TradingStrategies

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 **Ultimate Trading Bot**\n\n"
        "Commands:\n"
        "/stock <SYMBOL> (e.g., /stock TCS)\n"
        "/fno <SYMBOL> (e.g., /fno NIFTY)\n"
        "/crypto <SYMBOL> <EXCHANGE> (e.g., /crypto BTC/USDT binance)\n"
        "/options <SYMBOL> (e.g., /options AAPL)"
    )

async def stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0] if context.args else "RELIANCE"
    df = DataFetcher.get_stock(symbol)
    signal = TradingStrategies.predict_rf(df)
    await update.message.reply_text(f"📊 {symbol}: {signal}")

async def fno(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0] if context.args else "NIFTY"
    df = DataFetcher.get_fno(symbol)
    signal = TradingStrategies.predict_rf(df)
    await update.message.reply_text(f"📜 {symbol} F&O: {signal}")

async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0] if context.args else "BTC/USDT"
    exchange = context.args[1] if len(context.args) > 1 else "binance"
    df = DataFetcher.get_crypto(symbol, exchange)
    signal = TradingStrategies.predict_lstm(df)
    await update.message.reply_text(f"🪙 {symbol} ({exchange}): {signal}")

async def options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0] if context.args else "AAPL"
    data = DataFetcher.get_stock_options(symbol, "2024-12-31")
    await update.message.reply_text(f"📊 {symbol} Options: Use IV or Greeks for signals.")

def main():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stock", stock))
    app.add_handler(CommandHandler("fno", fno))
    app.add_handler(CommandHandler("crypto", crypto))
    app.add_handler(CommandHandler("options", options))
    app.run_polling()

if name == "__main__":
    main()