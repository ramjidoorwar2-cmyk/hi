"""
Angel One SmartAPI Client Module
Handles authentication, session management, live market data (LTP),
historical candles, and order routing with robust error handling and mock simulation fallback.
"""

import math
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import pyotp

try:
    from SmartApi import SmartConnect
    SMART_API_AVAILABLE = True
except ImportError:
    SMART_API_AVAILABLE = False

from config import TradingConfig, InstrumentConfig, DEFAULT_INSTRUMENTS


class AngelOneClient:
    """Angel One SmartAPI wrapper for real-time market data & trading."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.smart_api: Optional[Any] = None
        self.session_data: Optional[Dict[str, Any]] = None
        self.jwt_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        self.is_authenticated: bool = False
        self.is_simulation: bool = not config.has_credentials

        # Simulation base prices for realistic Indian market behavior
        self._sim_prices: Dict[str, float] = {
            "NIFTY 50": 24350.25,
            "BANK NIFTY": 52180.50,
            "FINNIFTY": 23450.00,
            "RELIANCE": 2980.40,
            "HDFCBANK": 1640.80,
            "TCS": 3950.00,
        }
        self._sim_prev_close: Dict[str, float] = {
            "NIFTY 50": 24260.00,
            "BANK NIFTY": 51950.00,
            "FINNIFTY": 23380.00,
            "RELIANCE": 2965.00,
            "HDFCBANK": 1632.00,
            "TCS": 3935.00,
        }

    def login(self) -> Dict[str, Any]:
        """
        Authenticates with Angel One SmartAPI using TOTP.
        Returns a dict with success status and details.
        """
        if not self.config.has_credentials:
            self.is_simulation = True
            self.is_authenticated = False
            return {
                "success": False,
                "mode": "SIMULATION",
                "message": "No Angel One credentials supplied. Operating in realistic Simulation / Paper Trading mode."
            }

        if not SMART_API_AVAILABLE:
            self.is_simulation = True
            return {
                "success": False,
                "mode": "SIMULATION",
                "message": "smartapi-python library not available."
            }

        try:
            # Generate automated TOTP 2FA code
            totp = pyotp.TOTP(self.config.totp_secret).now()
            self.smart_api = SmartConnect(api_key=self.config.api_key)

            # Generate Session
            session = self.smart_api.generateSession(
                clientCode=self.config.client_code,
                password=self.config.mpin,
                totp=totp
            )

            if session.get("status") is True and "data" in session:
                self.session_data = session["data"]
                self.jwt_token = session["data"].get("jwtToken")
                self.refresh_token = session["data"].get("refreshToken")
                self.feed_token = session["data"].get("feedToken")
                self.is_authenticated = True
                self.is_simulation = False
                return {
                    "success": True,
                    "mode": "LIVE",
                    "message": "Successfully authenticated with Angel One SmartAPI!",
                    "client_code": self.config.client_code,
                    "feed_token_present": bool(self.feed_token)
                }
            else:
                err_msg = session.get("message", "Authentication rejected by Angel One.")
                err_code = session.get("errorcode", "UNKNOWN")
                print(f"[AngelClient] Login failed ({err_code}): {err_msg}")
                self.is_simulation = self.config.simulation_fallback
                return {
                    "success": False,
                    "mode": "SIMULATION" if self.is_simulation else "ERROR",
                    "error_code": err_code,
                    "message": f"Angel One Login Error: {err_msg}"
                }

        except Exception as e:
            print(f"[AngelClient] Exception during login: {e}")
            self.is_simulation = self.config.simulation_fallback
            return {
                "success": False,
                "mode": "SIMULATION" if self.is_simulation else "ERROR",
                "message": f"Connection exception: {str(e)}"
            }

    def get_profile(self) -> Dict[str, Any]:
        """Fetches Angel One user profile and balance or simulated equivalent."""
        if self.is_authenticated and self.smart_api and self.refresh_token:
            try:
                res = self.smart_api.getProfile(self.refresh_token)
                if res.get("status"):
                    return {"success": True, "data": res.get("data", {})}
            except Exception as e:
                print(f"[AngelClient] Profile error: {e}")

        # Simulated profile
        return {
            "success": True,
            "data": {
                "clientcode": self.config.client_code or "SIM_TRADER_01",
                "name": "Simulated Angel One Trader",
                "email": "trader@simulated.market",
                "broker": "Angel One SmartAPI (Simulation Mode)",
                "available_cash": self.config.default_capital_inr,
                "mode": "PAPER_TRADING" if self.config.paper_trading else "LIVE"
            }
        }

    def get_ltp(self, instrument_name: str) -> Dict[str, Any]:
        """
        Gets the Last Traded Price (LTP) and day's range for an instrument.
        """
        inst = DEFAULT_INSTRUMENTS.get(instrument_name)
        if not inst:
            # Create a dynamic fallback
            inst = InstrumentConfig(
                symbol=instrument_name,
                token="0000",
                exchange="NSE",
                instrument_type="EQUITY"
            )

        if self.is_authenticated and self.smart_api:
            try:
                res = self.smart_api.ltpData(
                    exchange=inst.exchange,
                    tradingsymbol=inst.symbol,
                    symboltoken=inst.token
                )
                if res.get("status") and "data" in res:
                    data = res["data"]
                    return {
                        "symbol": instrument_name,
                        "ltp": float(data.get("ltp", 0.0)),
                        "open": float(data.get("open", 0.0)),
                        "high": float(data.get("high", 0.0)),
                        "low": float(data.get("low", 0.0)),
                        "close": float(data.get("close", 0.0)),
                        "source": "ANGEL_ONE_LIVE"
                    }
            except Exception as e:
                print(f"[AngelClient] LTP fetch failed for {instrument_name}: {e}")

        # Simulation price with realistic micro-volatility
        base = self._sim_prices.get(instrument_name, 1000.0)
        prev_close = self._sim_prev_close.get(instrument_name, base * 0.995)
        # Random jitter between -0.15% and +0.15%
        jitter_pct = random.uniform(-0.0015, 0.0018)
        new_ltp = round(base * (1.0 + jitter_pct), 2)
        self._sim_prices[instrument_name] = new_ltp

        change_inr = round(new_ltp - prev_close, 2)
        change_pct = round((change_inr / prev_close) * 100, 2)

        return {
            "symbol": instrument_name,
            "tradingsymbol": inst.symbol,
            "ltp": new_ltp,
            "open": round(prev_close * 1.001, 2),
            "high": round(max(new_ltp, prev_close) * 1.004, 2),
            "low": round(min(new_ltp, prev_close) * 0.994, 2),
            "close": prev_close,
            "change": change_inr,
            "change_pct": change_pct,
            "source": "SIMULATION"
        }

    def get_candle_data(
        self,
        instrument_name: str,
        interval: str = "FIVE_MINUTE",
        bars_count: int = 60
    ) -> pd.DataFrame:
        """
        Fetches historical OHLC candle data as a pandas DataFrame.
        Columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        inst = DEFAULT_INSTRUMENTS.get(instrument_name)
        now = datetime.now()

        if self.is_authenticated and self.smart_api and inst:
            try:
                from_date = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
                to_date = now.strftime("%Y-%m-%d %H:%M")
                params = {
                    "exchange": inst.exchange,
                    "symboltoken": inst.token,
                    "interval": interval,
                    "fromdate": from_date,
                    "todate": to_date
                }
                res = self.smart_api.getCandleData(params)
                if res.get("status") and "data" in res and res["data"]:
                    df = pd.DataFrame(res["data"], columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
                    return df.tail(bars_count).reset_index(drop=True)
            except Exception as e:
                print(f"[AngelClient] Candle data fetch failed for {instrument_name}: {e}")

        # Realistic synthetic OHLC series for technical indicators
        return self._generate_simulated_candles(instrument_name, bars_count=bars_count)

    def _generate_simulated_candles(self, instrument_name: str, bars_count: int = 60) -> pd.DataFrame:
        """Generates realistic trending/oscillating OHLC candles for Indian markets."""
        base_price = self._sim_prices.get(instrument_name, 1000.0)
        volatility = 0.0018 if "NIFTY" in instrument_name else 0.0035

        end_time = datetime.now().replace(second=0, microsecond=0)
        records = []
        curr_price = base_price * (1 - (bars_count * 0.0004))  # slight prior trend

        for i in range(bars_count):
            bar_time = end_time - timedelta(minutes=5 * (bars_count - i))
            # Random walk with slight mean reversion
            drift = random.uniform(-volatility, volatility * 1.08)
            open_p = curr_price
            close_p = round(open_p * (1.0 + drift), 2)
            high_p = round(max(open_p, close_p) + (abs(drift) * open_p * random.uniform(0.1, 0.8)), 2)
            low_p = round(min(open_p, close_p) - (abs(drift) * open_p * random.uniform(0.1, 0.8)), 2)
            volume = int(random.uniform(10000, 85000))

            records.append({
                "timestamp": bar_time,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": volume
            })
            curr_price = close_p

        df = pd.DataFrame(records)
        return df

    def place_order(self, order_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Routes order to Angel One or logs paper trade.
        """
        if self.config.paper_trading or self.is_simulation:
            # Paper execution
            order_id = f"PAPER_{int(time.time() * 1000)}"
            return {
                "success": True,
                "order_id": order_id,
                "mode": "PAPER_TRADING",
                "status": "EXECUTED",
                "details": order_dict,
                "message": f"Paper Trade Order {order_id} recorded successfully."
            }

        if not self.is_authenticated or not self.smart_api:
            return {
                "success": False,
                "mode": "LIVE_FAILED",
                "message": "Cannot place live order: Angel One SmartAPI is not authenticated."
            }

        try:
            # Live Order via SmartAPI
            response = self.smart_api.placeOrder(order_dict)
            if response.get("status"):
                return {
                    "success": True,
                    "order_id": response.get("data", {}).get("orderid"),
                    "mode": "LIVE",
                    "status": "SUBMITTED",
                    "details": response.get("data", {}),
                    "message": "Live order routed to Angel One exchange successfully."
                }
            else:
                return {
                    "success": False,
                    "mode": "LIVE_FAILED",
                    "message": response.get("message", "Order rejected by Angel One broker.")
                }
        except Exception as e:
            return {
                "success": False,
                "mode": "EXCEPTION",
                "message": f"Failed to place order: {str(e)}"
            }
