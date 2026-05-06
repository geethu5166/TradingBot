import os
import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

# LangChain Imports
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

# Data & Analysis Imports
import yfinance as yf
import ccxt
import pandas as pd
import ta # Technical Analysis library
import requests
from bs4 import BeautifulSoup

# Telegram Imports
from telegram import Bot
from telegram.error import TelegramError

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Set these environment variables or hardcode them (not recommended for production)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

# Initialize LLM
llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.3, api_key=OPENAI_API_KEY)

# --- Data Fetching Modules ---

class MarketDataFetcher:
    @staticmethod
    def get_stock_data(symbol: str, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
        """Fetches Indian Stock data using Yahoo Finance (NSE symbols usually end with .NS)"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return None
            return df
        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}")
            return None

    @staticmethod
    def get_crypto_data(symbol: str, timeframe: str = "1d", limit: int = 100) -> pd.DataFrame:
        """Fetches Crypto data using CCXT (Binance public API)"""
        try:
            exchange = ccxt.binance()
            bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error fetching crypto data for {symbol}: {e}")
            return None

    @staticmethod
    def get_news_sentiment(query: str) -> float:
        """Mock sentiment analysis based on news headlines (Simplified for demo)"""
        # In a production system, use NewsAPI or Bloomberg Terminal API
        # Here we simulate a sentiment score between -1 (negative) and 1 (positive)
        try:
            # Placeholder logic: Random fluctuation for demo purposes
            # Real implementation would scrape RSS feeds and use NLP
            import random
            sentiment = random.uniform(-0.5, 0.8) 
            return sentiment
        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}")
            return 0.0

# --- Agent Definitions ---

class TradingAgent:
    def __init__(self, name: str, role: str, expertise: str):
        self.name = name
        self.role = role
        self.expertise = expertise
        self.memory = ConversationBufferMemory(return_messages=True)
        
    def analyze(self, data: Dict[str, Any], market_type: str) -> str:
        """Runs the specific agent's analysis"""
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are an expert {role} in the financial markets. 
            Your expertise is: {expertise}.
            You are part of a committee of 1000 quantitative analysts. 
            Your job is to analyze the provided data and give a concise recommendation (BUY, SELL, or HOLD) 
            with a confidence score (0-100%) and a brief reasoning.
            
            Do not hallucinate data. Use only the provided context.
            """),
            ("human", """Market Type: {market_type}
            Data Context:
            {data_context}
            
            Provide your analysis:"""),
        ])
        
        chain = prompt_template | llm
        
        # Format data context based on agent type
        data_context = ""
        if 'price_data' in data:
            df = data['price_data']
            last_close = df['close'].iloc[-1]
            sma_20 = ta.trend.sma_indicator(df['close'], window=20).iloc[-1]
            rsi_14 = ta.momentum.rsi(df['close'], window=14).iloc[-1]
            data_context += f"Latest Close: {last_close}\nSMA(20): {sma_20}\nRSI(14): {rsi_14}\n"
        
        if 'sentiment' in data:
            data_context += f"Market Sentiment Score: {data['sentiment']}\n"
            
        if 'order_flow' in data:
            data_context += f"Order Flow Imbalance: {data['order_flow']}\n"

        response = chain.invoke({
            "role": self.role,
            "expertise": self.expertise,
            "market_type": market_type,
            "data_context": data_context
        })
        
        return response.content

# --- The Committee (Orchestrator) ---

class QuantCommittee:
    def __init__(self):
        # Define the diverse agents simulating the "1000" minds via specialized roles
        self.agents = [
            TradingAgent("TechAnalyst", "Technical Analyst", "Moving averages, RSI, MACD, and Chart Patterns"),
            TradingAgent("SentimentGuru", "Sentiment Analyst", "News analysis, Social media trends, and Fear/Greed Index"),
            TradingAgent("QuantModeler", "Quantitative Modeler", "Statistical arbitrage, Mean reversion, and Volatility modeling"),
            TradingAgent("RiskManager", "Risk Manager", "Drawdown analysis, Position sizing, and Stop-loss optimization"),
            TradingAgent("MacroStrategist", "Macro Strategist", "Interest rates, Inflation data, and Geopolitical impact")
        ]
        self.telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN" else None

    def run_analysis(self, symbol: str, market_type: str):
        logger.info(f"Starting committee analysis for {symbol} ({market_type})")
        
        # 1. Fetch Data
        fetcher = MarketDataFetcher()
        if market_type == "stock":
            # Example: Reliance Industries on NSE
            if ".NS" not in symbol: symbol += ".NS"
            price_data = fetcher.get_stock_data(symbol)
        else:
            # Example: BTC/USDT
            if "/" not in symbol: symbol += "/USDT"
            price_data = fetcher.get_crypto_data(symbol)
            
        if price_data is None:
            return "Failed to fetch market data."
            
        sentiment = fetcher.get_news_sentiment(symbol)
        
        # Mock order flow data for demonstration
        order_flow = "Neutral to Slightly Bullish" 

        data_context = {
            "price_data": price_data,
            "sentiment": sentiment,
            "order_flow": order_flow
        }

        # 2. Agents Discuss (Parallel Analysis)
        agent_opinions = []
        for agent in self.agents:
            opinion = agent.analyze(data_context, market_type)
            agent_opinions.append(f"**{agent.name}**: {opinion}")
            logger.info(f"{agent.name} completed analysis.")

        # 3. Consensus Aggregation (The "Final Decision")
        aggregation_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the Chief Investment Officer (CIO) of a hedge fund.
            You have received analysis from a committee of expert agents.
            Summarize their findings. Identify conflicts. 
            Make a FINAL DECISION: BUY, SELL, or HOLD.
            Assign a final confidence level based on the agreement among agents.
            Warn about risks.
            """),
            ("human", """Agent Opinions:
            {opinions}
            
            Current Price Data Summary:
            {price_summary}
            
            Provide the final trade recommendation in a structured format suitable for Telegram."""),
        ])
        
        chain = aggregation_prompt | llm
        
        price_summary = f"Symbol: {symbol}\nLast Close: {price_data['close'].iloc[-1]}\nTrend: {'Up' if price_data['close'].iloc[-1] > price_data['close'].iloc[-5] else 'Down'}"
        
        final_decision = chain.invoke({
            "opinions": "\n".join(agent_opinions),
            "price_summary": price_summary
        })
        
        message = f"🚀 **QuantCommittee Trade Alert** 🚀\n\n" \
                  f"📊 **Asset**: {symbol}\n" \
                  f"📅 **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n" \
                  f"🗣️ **Agent Discussions**:\n" \
                  f"{'-'*20}\n" \
                  f"\n".join(agent_opinions)[:1000] + "...\n\n" \ # Truncate for Telegram limits if needed
                  f"🏛️ **Final Consensus**:\n" \
                  f"{'-'*20}\n" \
                  f"{final_decision.content}\n\n" \
                  f"⚠️ *Disclaimer: This is AI-generated analysis, not financial advice. Markets are risky.*"

        # 4. Send to Telegram
        self.send_telegram_message(message)
        
        return final_decision.content

    def send_telegram_message(self, message: str):
        if self.telegram_bot:
            try:
                asyncio.run(self.telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown'))
                logger.info("Message sent to Telegram.")
            except TelegramError as e:
                logger.error(f"Failed to send Telegram message: {e}")
        else:
            logger.warning("Telegram bot not configured. Printing message instead:")
            print(message)

# --- Main Execution ---

if __name__ == "__main__":
    committee = QuantCommittee()
    
    # Example Usage:
    # 1. Indian Stock: Reliance Industries
    # committee.run_analysis("RELIANCE", "stock")
    
    # 2. Crypto: Bitcoin
    committee.run_analysis("BTC/USDT", "crypto")
