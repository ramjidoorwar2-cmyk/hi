# Angel One SmartAPI Algorithmic Trading & Signal System

An end-to-end algorithmic trading and technical instruction system powered by **Angel One SmartAPI**, designed for Indian Stock Market Indices (**NIFTY 50**, **BANK NIFTY**, **FINNIFTY**) and leading intraday equities (**RELIANCE**, **HDFCBANK**, **TCS**).

---

## 🌟 Key Features

1. **Angel One SmartAPI Integration**:
   - Automated 2FA TOTP generation using `pyotp` (no manual SMS OTP required).
   - Real-time Last Traded Price (LTP) and OHLC historical candle data fetching.
   - Live order placement routing (`placeOrder`) with intraday and delivery support.
   - Built-in simulation fallback mode for instant testing without risk.

2. **Actionable Trade Instructions Engine**:
   - **Signal Generation**: EMA 9/21 crossover filtered by RSI(14) momentum and MACD histogram.
   - **Risk Management**: Dynamic Stop Loss (ATR-based) and 1:2 / 1:3 Risk-to-Reward Targets.
   - **Option Recommendations**: Automatically calculates ATM Call (`CE`) and Put (`PE`) strikes for Nifty & Bank Nifty.
   - **Rationale & Confidence**: Every instruction includes confidence score (80-95%) and human-readable reasoning.

3. **Execution Modes**:
   - **Paper Trading (Default)**: Practice with virtual ₹1,00,000 capital, trailing targets, and real-time PnL tracking.
   - **Live Trading**: Routes real orders directly to Angel One when toggled in settings.

4. **Mobile & Desktop Web Trading Terminal**:
   - View live inside the app preview: [Live Web Terminal](https://antigravity.luch.dev/site/83525965-a1ae-4476-9410-1f0f69bfe85c/7c74a98333164ab498ef335c/)
   - High-contrast dark trading UI with real-time candlestick charts, EMA lines, ticker strip, and order management.

---

## 🚀 Quick Start Guide

### 1. Run Market Scan via CLI
Fetches live/historical data, evaluates indicators, and prints clean formatted tables:
```bash
python3 main.py scan
```

### 2. Test Angel One Credentials
Validates TOTP generation and session generation with Angel One servers:
```bash
python3 main.py test-login
```

### 3. Run Real-Time Automated Trading Loop
Monitors markets every 15 seconds, enters signals, and exits when Target or Stop Loss is hit:
```bash
python3 main.py bot --interval 15
```

### 4. Run Web Dashboard Server
```bash
python3 server.py
# Server runs on http://0.0.0.0:8080
```

---

## ⚙️ Configuration & Angel One Setup

To connect to your live Angel One account:
1. Open the **API Keys** modal on the web dashboard or edit `config.json`.
2. Provide your credentials from [Angel One SmartAPI Portal](https://smartapi.angelbroking.com):
   - `client_code`: Your Angel One User ID.
   - `api_key`: API key generated on the SmartAPI portal.
   - `mpin`: Your account MPIN / PIN.
   - `totp_secret`: The Base32 Secret Key shown when enabling 2FA authenticator (e.g. Google Authenticator) in Angel One.

---

## 🧪 Running Unit Tests

Run the full automated test suite verifying indicators, signal triggers, and order managers:
```bash
python3 -m unittest discover tests/
```
