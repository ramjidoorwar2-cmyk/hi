"""
Angel One SmartAPI Trading Configuration Module
Manages API keys, trading parameters, instruments, and risk rules.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


@dataclass
class InstrumentConfig:
    symbol: str
    token: str
    exchange: str
    instrument_type: str  # INDEX, EQUITY, OPTION, FUTURE
    lot_size: int = 1
    tick_size: float = 0.05
    description: str = ""


DEFAULT_INSTRUMENTS = {
    "NIFTY 50": InstrumentConfig(
        symbol="NIFTY",
        token="99926000",
        exchange="NSE",
        instrument_type="INDEX",
        lot_size=25,
        tick_size=0.05,
        description="Nifty 50 Index"
    ),
    "BANK NIFTY": InstrumentConfig(
        symbol="BANKNIFTY",
        token="99926009",
        exchange="NSE",
        instrument_type="INDEX",
        lot_size=15,
        tick_size=0.05,
        description="Bank Nifty Index"
    ),
    "FINNIFTY": InstrumentConfig(
        symbol="FINNIFTY",
        token="99926037",
        exchange="NSE",
        instrument_type="INDEX",
        lot_size=25,
        tick_size=0.05,
        description="Nifty Financial Services"
    ),
    "RELIANCE": InstrumentConfig(
        symbol="RELIANCE-EQ",
        token="2885",
        exchange="NSE",
        instrument_type="EQUITY",
        lot_size=1,
        tick_size=0.05,
        description="Reliance Industries Ltd."
    ),
    "HDFCBANK": InstrumentConfig(
        symbol="HDFCBANK-EQ",
        token="1333",
        exchange="NSE",
        instrument_type="EQUITY",
        lot_size=1,
        tick_size=0.05,
        description="HDFC Bank Ltd."
    ),
    "TCS": InstrumentConfig(
        symbol="TCS-EQ",
        token="11536",
        exchange="NSE",
        instrument_type="EQUITY",
        lot_size=1,
        tick_size=0.05,
        description="Tata Consultancy Services Ltd."
    ),
}


@dataclass
class TradingConfig:
    # Angel One SmartAPI Credentials
    api_key: str = ""
    client_code: str = ""
    mpin: str = ""
    totp_secret: str = ""

    # Execution Modes
    paper_trading: bool = True  # True = Paper / Simulation, False = Live Orders
    simulation_fallback: bool = True  # Generate synthetic ticks when offline/unauthenticated

    # Strategy Parameters
    fast_ema: int = 9
    slow_ema: int = 21
    trend_ema: int = 50
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14
    atr_multiplier_sl: float = 1.5
    risk_reward_ratio: float = 2.0  # 1:2 R:R

    # Risk Management
    max_risk_per_trade_pct: float = 1.0  # 1% capital per trade
    max_open_positions: int = 3
    daily_max_loss_inr: float = 5000.0
    default_capital_inr: float = 100000.0

    # Instruments to scan
    active_symbols: List[str] = field(default_factory=lambda: ["NIFTY 50", "BANK NIFTY", "RELIANCE"])

    @classmethod
    def load(cls, file_path: str = CONFIG_FILE) -> "TradingConfig":
        """Loads configuration from environment variables first, then config.json, or defaults."""
        config_data = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"[Config] Warning: Failed to read {file_path}: {e}")

        # Environment variable overrides
        api_key = os.environ.get("ANGEL_API_KEY", config_data.get("api_key", ""))
        client_code = os.environ.get("ANGEL_CLIENT_CODE", config_data.get("client_code", ""))
        mpin = os.environ.get("ANGEL_MPIN", config_data.get("mpin", ""))
        totp_secret = os.environ.get("ANGEL_TOTP_SECRET", config_data.get("totp_secret", ""))

        # Merge with file data
        return cls(
            api_key=api_key,
            client_code=client_code,
            mpin=mpin,
            totp_secret=totp_secret,
            paper_trading=config_data.get("paper_trading", True),
            simulation_fallback=config_data.get("simulation_fallback", True),
            fast_ema=config_data.get("fast_ema", 9),
            slow_ema=config_data.get("slow_ema", 21),
            trend_ema=config_data.get("trend_ema", 50),
            rsi_period=config_data.get("rsi_period", 14),
            rsi_overbought=config_data.get("rsi_overbought", 70.0),
            rsi_oversold=config_data.get("rsi_oversold", 30.0),
            atr_period=config_data.get("atr_period", 14),
            atr_multiplier_sl=config_data.get("atr_multiplier_sl", 1.5),
            risk_reward_ratio=config_data.get("risk_reward_ratio", 2.0),
            max_risk_per_trade_pct=config_data.get("max_risk_per_trade_pct", 1.0),
            max_open_positions=config_data.get("max_open_positions", 3),
            daily_max_loss_inr=config_data.get("daily_max_loss_inr", 5000.0),
            default_capital_inr=config_data.get("default_capital_inr", 100000.0),
            active_symbols=config_data.get("active_symbols", ["NIFTY 50", "BANK NIFTY", "RELIANCE"])
        )

    def save(self, file_path: str = CONFIG_FILE) -> None:
        """Saves current configuration to file."""
        data = asdict(self)
        # Avoid storing raw secrets if blank
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @property
    def has_credentials(self) -> bool:
        """Returns True if minimum required credentials for Angel One are supplied."""
        return bool(self.api_key and self.client_code and self.mpin and self.totp_secret)
