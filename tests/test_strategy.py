"""
Unit Tests for Strategy Engine
Verifies indicator calculations (EMA, RSI, MACD, ATR) and signal triggers.
"""

import unittest
import pandas as pd
import numpy as np

from config import TradingConfig
from strategy_engine import StrategyEngine, TradeInstruction


class TestStrategyEngine(unittest.TestCase):

    def setUp(self):
        self.config = TradingConfig()
        self.engine = StrategyEngine(self.config)

    def test_indicator_calculation(self):
        # Generate 40 synthetic candle bars
        dates = pd.date_range("2026-11-04 09:15", periods=40, freq="5min")
        close_prices = [24000 + i * 5 for i in range(40)]  # Uptrend
        df = pd.DataFrame({
            "timestamp": dates,
            "open": close_prices,
            "high": [c + 10 for c in close_prices],
            "low": [c - 5 for c in close_prices],
            "close": close_prices,
            "volume": [15000] * 40
        })

        df_ind = self.engine.calculate_indicators(df)
        self.assertIn("ema_fast", df_ind.columns)
        self.assertIn("ema_slow", df_ind.columns)
        self.assertIn("rsi", df_ind.columns)
        self.assertIn("macd_hist", df_ind.columns)
        self.assertIn("atr", df_ind.columns)

        # In a sustained uptrend, fast EMA should be above slow EMA
        last_row = df_ind.iloc[-1]
        self.assertGreater(last_row["ema_fast"], last_row["ema_slow"])
        self.assertGreater(last_row["rsi"], 50)

    def test_bullish_signal_generation(self):
        dates = pd.date_range("2026-11-04 09:15", periods=30, freq="5min")
        # Steady uptrend after flat
        prices = [24000] * 10 + [24000 + (i * 12) for i in range(20)]
        df = pd.DataFrame({
            "timestamp": dates,
            "open": prices,
            "high": [p + 8 for p in prices],
            "low": [p - 5 for p in prices],
            "close": prices,
            "volume": [20000] * 30
        })

        ti = self.engine.evaluate_signals("NIFTY 50", df)
        self.assertIsNotNone(ti)
        self.assertEqual(ti.action, "BUY")
        self.assertEqual(ti.symbol, "NIFTY 50")
        self.assertGreater(ti.target_1, ti.entry_price)
        self.assertLess(ti.stop_loss, ti.entry_price)
        self.assertIn("CE", ti.suggested_option)

    def test_bearish_signal_generation(self):
        dates = pd.date_range("2026-11-04 09:15", periods=30, freq="5min")
        # Steady downtrend after flat
        prices = [24000] * 10 + [24000 - (i * 12) for i in range(20)]
        df = pd.DataFrame({
            "timestamp": dates,
            "open": prices,
            "high": [p + 5 for p in prices],
            "low": [p - 8 for p in prices],
            "close": prices,
            "volume": [20000] * 30
        })

        ti = self.engine.evaluate_signals("NIFTY 50", df)
        self.assertIsNotNone(ti)
        self.assertEqual(ti.action, "SELL")
        self.assertLess(ti.target_1, ti.entry_price)
        self.assertGreater(ti.stop_loss, ti.entry_price)
        self.assertIn("PE", ti.suggested_option)


if __name__ == "__main__":
    unittest.main()
