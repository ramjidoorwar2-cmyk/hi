"""
Technical Strategy and Trade Instruction Engine
Calculates technical indicators (EMA, RSI, MACD, ATR) on candle data and generates
actionable Trade Instructions (Buy/Sell, Entry, Stop-Loss, Targets, Option Strikes).
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from config import TradingConfig


@dataclass
class TradeInstruction:
    id: str
    timestamp: str
    symbol: str
    action: str  # BUY (Long/Call) or SELL (Short/Put)
    trade_type: str  # INTRADAY, SWING
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: str
    confidence: int  # 0 to 100%
    timeframe: str
    rationale: str
    indicators: Dict[str, Any]
    suggested_option: str
    status: str = "ACTIVE"  # ACTIVE, TARGET_1_HIT, TARGET_2_HIT, STOPPED_OUT, EXPIRED

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyEngine:
    """Computes technical indicators and generates trade instructions."""

    def __init__(self, config: TradingConfig):
        self.config = config

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes EMA (9, 21, 50), RSI (14), MACD, and ATR on OHLC candle data."""
        if len(df) < 15:
            return df

        df = df.copy()

        # Exponential Moving Averages
        df["ema_fast"] = df["close"].ewm(span=self.config.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.config.slow_ema, adjust=False).mean()
        df["ema_trend"] = df["close"].ewm(span=self.config.trend_ema, adjust=False).mean()

        # Relative Strength Index (RSI 14)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Exponential or simple moving average for RSI
        avg_gain = gain.rolling(window=self.config.rsi_period, min_periods=1).mean()
        avg_loss = loss.rolling(window=self.config.rsi_period, min_periods=1).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Handle boundary conditions (all gains -> 100, all losses -> 0, zero movement -> 50)
        rsi = rsi.where(avg_loss != 0, 100.0)
        rsi = rsi.where(avg_gain != 0, 0.0)
        rsi = rsi.where((avg_gain != 0) | (avg_loss != 0), 50.0)
        df["rsi"] = rsi.fillna(50.0)

        # MACD (12, 26, 9)
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd_line"] = ema_12 - ema_26
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # Average True Range (ATR 14) for volatility & SL
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.config.atr_period, min_periods=1).mean()
        df["atr"] = df["atr"].fillna(df["close"] * 0.005)

        return df

    def evaluate_signals(self, symbol: str, df: pd.DataFrame) -> Optional[TradeInstruction]:
        """
        Analyzes the latest candle bars and evaluates whether an actionable trade instruction
        should be generated.
        """
        if len(df) < 15:
            return None

        df_ind = self.calculate_indicators(df)
        curr = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]

        close_price = float(curr["close"])
        ema_fast_curr = float(curr["ema_fast"])
        ema_fast_prev = float(prev["ema_fast"])
        ema_slow_curr = float(curr["ema_slow"])
        ema_slow_prev = float(prev["ema_slow"])
        rsi_val = float(curr["rsi"])
        macd_hist_curr = float(curr["macd_hist"])
        atr_val = float(curr["atr"])

        # Determine ATM Strike for Options
        strike_step = 50 if "NIFTY" in symbol and "BANK" not in symbol else (100 if "BANK" in symbol else 20)
        atm_strike = int(round(close_price / strike_step) * strike_step)

        # Bullish conditions
        bullish_cross = (ema_fast_prev <= ema_slow_prev) and (ema_fast_curr > ema_slow_curr)
        bullish_trend = (ema_fast_curr > ema_slow_curr) and (rsi_val >= 50.0) and (macd_hist_curr >= 0)

        # Bearish conditions
        bearish_cross = (ema_fast_prev >= ema_slow_prev) and (ema_fast_curr < ema_slow_curr)
        bearish_trend = (ema_fast_curr < ema_slow_curr) and (rsi_val <= 50.0) and (macd_hist_curr <= 0)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp_id = datetime.now().strftime("%H%M%S")

        # Check BUY signal
        if bullish_cross or (bullish_trend and rsi_val <= 82.0):
            sl_distance = max(round(atr_val * self.config.atr_multiplier_sl, 2), round(close_price * 0.003, 2))
            sl = round(close_price - sl_distance, 2)
            target_1 = round(close_price + (sl_distance * 1.5), 2)
            target_2 = round(close_price + (sl_distance * self.config.risk_reward_ratio), 2)

            confidence = 70
            if bullish_cross:
                confidence += 15
            if 55 <= rsi_val <= 70:
                confidence += 10
            if macd_hist_curr > 0:
                confidence += 5

            confidence = min(confidence, 95)
            rationale = (
                f"Bullish setup: Fast EMA ({ema_fast_curr:.1f}) > Slow EMA ({ema_slow_curr:.1f}), "
                f"RSI={rsi_val:.1f} shows bullish momentum, MACD Histogram={macd_hist_curr:.2f}."
            )
            suggested_opt = f"{atm_strike} CE (Call Option)" if "NIFTY" in symbol else f"{symbol} Long / Delivery"

            return TradeInstruction(
                id=f"TI-{symbol.replace(' ', '')}-BUY-{timestamp_id}",
                timestamp=now_str,
                symbol=symbol,
                action="BUY",
                trade_type="INTRADAY / MOMENTUM",
                entry_price=close_price,
                stop_loss=sl,
                target_1=target_1,
                target_2=target_2,
                risk_reward=f"1:{self.config.risk_reward_ratio:.1f}",
                confidence=confidence,
                timeframe="5m",
                rationale=rationale,
                indicators={
                    "ema_fast": round(ema_fast_curr, 2),
                    "ema_slow": round(ema_slow_curr, 2),
                    "rsi": round(rsi_val, 1),
                    "macd_hist": round(macd_hist_curr, 2),
                    "atr": round(atr_val, 2)
                },
                suggested_option=suggested_opt,
                status="ACTIVE"
            )

        # Check SELL signal
        if bearish_cross or (bearish_trend and rsi_val >= 18.0):
            sl_distance = max(round(atr_val * self.config.atr_multiplier_sl, 2), round(close_price * 0.003, 2))
            sl = round(close_price + sl_distance, 2)
            target_1 = round(close_price - (sl_distance * 1.5), 2)
            target_2 = round(close_price - (sl_distance * self.config.risk_reward_ratio), 2)

            confidence = 70
            if bearish_cross:
                confidence += 15
            if 30 <= rsi_val <= 45:
                confidence += 10
            if macd_hist_curr < 0:
                confidence += 5

            confidence = min(confidence, 95)
            rationale = (
                f"Bearish setup: Fast EMA ({ema_fast_curr:.1f}) < Slow EMA ({ema_slow_curr:.1f}), "
                f"RSI={rsi_val:.1f} shows bearish pressure, MACD Histogram={macd_hist_curr:.2f}."
            )
            suggested_opt = f"{atm_strike} PE (Put Option)" if "NIFTY" in symbol else f"{symbol} Intraday Short"

            return TradeInstruction(
                id=f"TI-{symbol.replace(' ', '')}-SELL-{timestamp_id}",
                timestamp=now_str,
                symbol=symbol,
                action="SELL",
                trade_type="INTRADAY / MOMENTUM",
                entry_price=close_price,
                stop_loss=sl,
                target_1=target_1,
                target_2=target_2,
                risk_reward=f"1:{self.config.risk_reward_ratio:.1f}",
                confidence=confidence,
                timeframe="5m",
                rationale=rationale,
                indicators={
                    "ema_fast": round(ema_fast_curr, 2),
                    "ema_slow": round(ema_slow_curr, 2),
                    "rsi": round(rsi_val, 1),
                    "macd_hist": round(macd_hist_curr, 2),
                    "atr": round(atr_val, 2)
                },
                suggested_option=suggested_opt,
                status="ACTIVE"
            )

        return None
