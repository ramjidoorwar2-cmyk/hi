"""
Unit Tests for Angel One Client & Order Manager
"""

import unittest
from config import TradingConfig
from angel_client import AngelOneClient
from order_manager import OrderManager
from strategy_engine import TradeInstruction


class TestAngelClientAndOrderManager(unittest.TestCase):

    def setUp(self):
        self.config = TradingConfig(paper_trading=True)
        self.client = AngelOneClient(self.config)
        self.order_mgr = OrderManager(self.config, self.client)
        # Clear positions for testing
        self.order_mgr.active_positions = []
        self.order_mgr.completed_trades = []
        self.order_mgr.signals_log = []

    def test_client_simulation_ltp(self):
        ltp_data = self.client.get_ltp("NIFTY 50")
        self.assertIn("ltp", ltp_data)
        self.assertGreater(ltp_data["ltp"], 20000)
        self.assertEqual(ltp_data["symbol"], "NIFTY 50")

    def test_client_candle_generation(self):
        df = self.client.get_candle_data("BANK NIFTY", bars_count=40)
        self.assertEqual(len(df), 40)
        self.assertIn("open", df.columns)
        self.assertIn("close", df.columns)
        self.assertIn("volume", df.columns)

    def test_order_execution_and_exit(self):
        instruction = TradeInstruction(
            id="TI-TEST-01",
            timestamp="2026-11-04 10:00:00",
            symbol="NIFTY 50",
            action="BUY",
            trade_type="INTRADAY",
            entry_price=24000.0,
            stop_loss=23950.0,
            target_1=24100.0,
            target_2=24200.0,
            risk_reward="1:2",
            confidence=85,
            timeframe="5m",
            rationale="Test buy instruction",
            indicators={},
            suggested_option="24000 CE",
            status="ACTIVE"
        )

        # 1. Execute instruction (paper mode)
        res = self.order_mgr.execute_instruction(instruction)
        self.assertTrue(res["success"])
        self.assertEqual(len(self.order_mgr.active_positions), 1)

        pos = self.order_mgr.active_positions[0]
        self.assertEqual(pos["symbol"], "NIFTY 50")
        self.assertEqual(pos["action"], "BUY")

        # 2. Simulate price hitting target 1
        pos["current_price"] = 24150.0
        # Trigger update
        self.client._sim_prices["NIFTY 50"] = 24150.0
        closed = self.order_mgr.update_positions()

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "TARGET_1_HIT")
        self.assertGreater(closed[0]["realized_pnl"], 0)
        self.assertEqual(len(self.order_mgr.active_positions), 0)
        self.assertEqual(len(self.order_mgr.completed_trades), 1)


if __name__ == "__main__":
    unittest.main()
