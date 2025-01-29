import yfinance as yf
import ccxt
from nsepy import get_history
from datetime import date
import pandas as pd
import requests

class DataFetcher:
    # Stocks (NSE, NYSE)
    @staticmethod
    def get_stock(symbol, exchange="NSE"):
        if exchange == "NSE":
            symbol += ".NS"
        return yf.download(symbol, period="1y", interval="1d")
    
    # NSE F&O
    @staticmethod
    def get_fno(symbol, expiry=date(2024, 12, 26)):
        return get_history(
            symbol=symbol,
            start=date(2023, 1, 1),
            end=date(2024, 12, 31),
            futures=True,
            expiry_date=expiry
        )
    
    # Crypto (All Exchanges)
    @staticmethod
    def get_crypto(symbol, exchange="binance"):
        exchange = getattr(ccxt, exchange)()
        data = exchange.fetch_ohlcv(symbol, '1d')
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    
    # Stock Options (Alpha Vantage)
    @staticmethod
    def get_stock_options(symbol, expiry):
        url = f"https://www.alphavantage.co/query?function=OPTION_CHAIN&symbol={symbol}&apikey={GPB9UJUBSJ9PKWP8}"
        return requests.get(url).json()