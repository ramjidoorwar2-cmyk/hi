"""
Order and Position Manager
Handles trade execution (Paper vs Live), active position tracking,
trailing stop-loss / target evaluation, and persistence to trades.json.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from angel_client import AngelOneClient
from config import TradingConfig, DEFAULT_INSTRUMENTS
from strategy_engine import TradeInstruction

TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.json")


class OrderManager:
    """Manages active trades, paper trading simulation, and order logging."""

    def __init__(self, config: TradingConfig, client: AngelOneClient):
        self.config = config
        self.client = client
        self.active_positions: List[Dict[str, Any]] = []
        self.completed_trades: List[Dict[str, Any]] = []
        self.signals_log: List[Dict[str, Any]] = []
        self.load_trades()

    def load_trades(self) -> None:
        """Loads previous trade records from disk."""
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_positions = data.get("active_positions", [])
                    self.completed_trades = data.get("completed_trades", [])
                    self.signals_log = data.get("signals_log", [])
            except Exception as e:
                print(f"[OrderManager] Error loading {TRADES_FILE}: {e}")

    def save_trades(self) -> None:
        """Saves current trade history and active positions."""
        data = {
            "updated_at": datetime.now().isoformat(),
            "active_positions": self.active_positions,
            "completed_trades": self.completed_trades,
            "signals_log": self.signals_log[-50:]  # Keep last 50 signals
        }
        try:
            with open(TRADES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[OrderManager] Error saving {TRADES_FILE}: {e}")

    def record_signal(self, instruction: TradeInstruction) -> None:
        """Adds a generated instruction to signal log."""
        inst_dict = instruction.to_dict()
        # Prevent exact duplicate signal within short timeframe
        for s in self.signals_log[-5:]:
            if s.get("symbol") == instruction.symbol and s.get("action") == instruction.action:
                return
        self.signals_log.insert(0, inst_dict)
        self.save_trades()

    def execute_instruction(self, instruction: TradeInstruction, auto_execute: bool = False) -> Dict[str, Any]:
        """
        Executes a trade instruction either in Paper Trading mode or Live Order mode.
        """
        self.record_signal(instruction)

        # Check max positions limit
        if len(self.active_positions) >= self.config.max_open_positions:
            return {
                "success": False,
                "message": f"Maximum open positions limit ({self.config.max_open_positions}) reached."
            }

        # Check if already in active trade for this symbol
        for pos in self.active_positions:
            if pos["symbol"] == instruction.symbol:
                return {
                    "success": False,
                    "message": f"Position already active for {instruction.symbol}."
                }

        inst = DEFAULT_INSTRUMENTS.get(instruction.symbol)
        qty = inst.lot_size if inst else 1

        position_record = {
            "id": f"POS-{int(time.time() * 1000)}",
            "instruction_id": instruction.id,
            "symbol": instruction.symbol,
            "action": instruction.action,
            "quantity": qty,
            "entry_price": instruction.entry_price,
            "current_price": instruction.entry_price,
            "stop_loss": instruction.stop_loss,
            "target_1": instruction.target_1,
            "target_2": instruction.target_2,
            "risk_reward": instruction.risk_reward,
            "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "PAPER_TRADING" if self.config.paper_trading else "LIVE",
            "suggested_option": instruction.suggested_option,
            "unrealized_pnl": 0.0,
            "status": "OPEN"
        }

        if self.config.paper_trading or self.client.is_simulation:
            # Paper execution
            self.active_positions.append(position_record)
            self.save_trades()
            return {
                "success": True,
                "position": position_record,
                "message": f"Paper Trade entered: {instruction.action} {qty}x {instruction.symbol} @ ₹{instruction.entry_price:,.2f}"
            }
        else:
            # Live execution via Angel One API
            order_dict = {
                "variety": "NORMAL",
                "tradingsymbol": inst.symbol if inst else instruction.symbol,
                "symboltoken": inst.token if inst else "0",
                "transactiontype": instruction.action,
                "exchange": inst.exchange if inst else "NSE",
                "ordertype": "MARKET",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": "0",
                "squareoff": "0",
                "stoploss": "0",
                "quantity": str(qty)
            }
            order_res = self.client.place_order(order_dict)
            if order_res.get("success"):
                position_record["order_id"] = order_res.get("order_id")
                self.active_positions.append(position_record)
                self.save_trades()
                return {
                    "success": True,
                    "position": position_record,
                    "message": f"Live Order routed to Angel One: {order_res.get('order_id')}"
                }
            else:
                return {
                    "success": False,
                    "message": f"Live Order failed: {order_res.get('message')}"
                }

    def update_positions(self) -> List[Dict[str, Any]]:
        """
        Polls current LTP for all active positions and evaluates Target/Stop-loss triggers.
        """
        closed_now = []
        for pos in list(self.active_positions):
            symbol = pos["symbol"]
            ltp_data = self.client.get_ltp(symbol)
            curr_ltp = ltp_data.get("ltp", pos["current_price"])
            pos["current_price"] = curr_ltp

            # Calculate Unrealized PnL
            if pos["action"] == "BUY":
                pnl = (curr_ltp - pos["entry_price"]) * pos["quantity"]
            else:
                pnl = (pos["entry_price"] - curr_ltp) * pos["quantity"]

            pos["unrealized_pnl"] = round(pnl, 2)

            # Check Stop Loss & Target triggers
            exit_reason = None
            if pos["action"] == "BUY":
                if curr_ltp <= pos["stop_loss"]:
                    exit_reason = "STOP_LOSS_HIT"
                elif curr_ltp >= pos["target_2"]:
                    exit_reason = "TARGET_2_HIT"
                elif curr_ltp >= pos["target_1"]:
                    exit_reason = "TARGET_1_HIT"
            elif pos["action"] == "SELL":
                if curr_ltp >= pos["stop_loss"]:
                    exit_reason = "STOP_LOSS_HIT"
                elif curr_ltp <= pos["target_2"]:
                    exit_reason = "TARGET_2_HIT"
                elif curr_ltp <= pos["target_1"]:
                    exit_reason = "TARGET_1_HIT"

            if exit_reason:
                pos["exit_price"] = curr_ltp
                pos["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                pos["exit_reason"] = exit_reason
                pos["realized_pnl"] = pos["unrealized_pnl"]
                pos["status"] = "CLOSED"

                self.completed_trades.insert(0, pos)
                self.active_positions.remove(pos)
                closed_now.append(pos)

        if closed_now or self.active_positions:
            self.save_trades()

        return closed_now

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates performance statistics from trade history."""
        total_trades = len(self.completed_trades)
        winning_trades = sum(1 for t in self.completed_trades if t.get("realized_pnl", 0) > 0)
        losing_trades = sum(1 for t in self.completed_trades if t.get("realized_pnl", 0) < 0)
        total_realized_pnl = sum(t.get("realized_pnl", 0) for t in self.completed_trades)
        total_unrealized_pnl = sum(p.get("unrealized_pnl", 0) for p in self.active_positions)
        win_rate = round((winning_trades / total_trades * 100), 1) if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "net_pnl": round(total_realized_pnl + total_unrealized_pnl, 2),
            "open_positions_count": len(self.active_positions)
        }
