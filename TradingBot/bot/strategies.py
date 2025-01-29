import pandas as pd
from ta import add_all_ta_features
from sklearn.ensemble import RandomForestClassifier
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from sklearn.preprocessing import MinMaxScaler

class TradingStrategies:
    # Random Forest Model (Stocks/F&O)
    @staticmethod
    def predict_rf(df):
        df = add_all_ta_features(df, open="Open", high="High", low="Low", close="Close", volume="Volume")
        df['target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
        df.dropna(inplace=True)
        
        X = df.drop(['target'], axis=1)
        y = df['target']
        
        model = RandomForestClassifier(n_estimators=200)
        model.fit(X, y)
        return "BUY" if model.predict(df.tail(1))[0] == 1 else "SELL"
    
    # LSTM Model (Crypto)
    @staticmethod
    def predict_lstm(df):
        scaler = MinMaxScaler()
        scaled_data = scaler.fit_transform(df[['close']])
        
        X, y = [], []
        for i in range(60, len(scaled_data)):
            X.append(scaled_data[i-60:i, 0])
            y.append(scaled_data[i, 0])
        X, y = np.array(X), np.array(y)
        X = np.reshape(X, (X.shape[0], X.shape[1], 1))
        
        model = Sequential()
        model.add(LSTM(100, return_sequences=True, input_shape=(X.shape[1], 1)))
        model.add(LSTM(100))
        model.add(Dense(1))
        model.compile(optimizer='adam', loss='mse')
        model.fit(X, y, epochs=50, batch_size=64, verbose=0)
        
        last_sequence = scaled_data[-60:]
        prediction = model.predict(last_sequence.reshape(1, 60, 1))
        return "BUY" if prediction[0][0] > scaled_data[-1][0] else "SELL"