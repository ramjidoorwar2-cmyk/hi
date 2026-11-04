"""
Angel One SmartAPI Trading System - Main CLI & Engine Runner
Provides commands for scanning markets, testing Angel One connection,
viewing trade instructions, and launching the trading loop.
"""

import argparse
import sys
import time
from datetime import datetime
from tabulate import tabulate

from config import TradingConfig, DEFAULT_INSTRUMENTS
from angel_client import AngelOneClient
from strategy_engine import StrategyEngine
from order_manager import OrderManager


def banner():
    print("=" * 72)
    print("       ANGEL ONE SMARTAPI ALGO TRADING & SIGNAL SYSTEM       ")
    print("        Indices (Nifty/BankNifty) & Intraday Technical Engine")
    print("=" * 72)


def cmd_test_login(config: TradingConfig):
    """Tests Angel One authentication with TOTP or shows simulation state."""
    banner()
    print("\n[+] Initializing Angel One SmartAPI Client...")
    print(f"    Client Code : {config.client_code or 'Not Set (Simulation Mode)'}")
    print(f"    API Key     : {'***' + config.api_key[-4:] if config.api_key else 'Not Set'}")
    print(f"    Paper Trade : {config.paper_trading}")

    client = AngelOneClient(config)
    res = client.login()

    print("\n[+] Authentication Result:")
    print(f"    Status  : {'SUCCESS' if res.get('success') else 'SIMULATION / OFFLINE'}")
    print(f"    Mode    : {res.get('mode')}")
    print(f"    Message : {res.get('message')}")

    profile = client.get_profile()
    if profile.get("success"):
        pdata = profile.get("data", {})
        print("\n[+] Account Profile Details:")
        for k, v in pdata.items():
            print(f"    - {k:18}: {v}")


def cmd_scan(config: TradingConfig, execute: bool = False):
    """Fetches market data for all instruments and displays Trade Instructions."""
    banner()
    print(f"\n[+] Scanning Instruments at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...\n")

    client = AngelOneClient(config)
    client.login()
    strategy = StrategyEngine(config)
    order_mgr = OrderManager(config, client)

    # 1. Market Rates Table
    market_rows = []
    instructions = []

    for name in config.active_symbols:
        ltp_data = client.get_ltp(name)
        symbol = ltp_data.get("symbol", name)
        ltp = ltp_data.get("ltp", 0.0)
        chg = ltp_data.get("change", 0.0)
        pct = ltp_data.get("change_pct", 0.0)
        src = ltp_data.get("source", "SIM")
        sign = "+" if chg >= 0 else ""
        market_rows.append([symbol, f"₹{ltp:,.2f}", f"{sign}{chg:,.2f} ({sign}{pct:.2f}%)", src])

        # Fetch candles and evaluate strategy
        df = client.get_candle_data(name, interval="FIVE_MINUTE", bars_count=50)
        instruction = strategy.evaluate_signals(name, df)
        if instruction:
            instructions.append(instruction)
            if execute:
                order_mgr.execute_instruction(instruction)

    print("📊 CURRENT WATCHLIST & MARKET PRICES:")
    print(tabulate(market_rows, headers=["Symbol", "LTP", "Day Change", "Source"], tablefmt="fancy_grid"))

    # 2. Trade Instructions Table
    print("\n🎯 ACTIONABLE TRADE INSTRUCTIONS:")
    if not instructions:
        print("    No active crossover signals right now. Market is in consolidation / neutral zone.")
    else:
        inst_rows = []
        for ti in instructions:
            action_badge = f"🟢 {ti.action}" if ti.action == "BUY" else f"🔴 {ti.action}"
            inst_rows.append([
                action_badge,
                ti.symbol,
                f"₹{ti.entry_price:,.2f}",
                f"₹{ti.stop_loss:,.2f}",
                f"₹{ti.target_1:,.2f}",
                f"₹{ti.target_2:,.2f}",
                ti.risk_reward,
                f"{ti.confidence}%",
                ti.suggested_option
            ])

        print(tabulate(
            inst_rows,
            headers=["Signal", "Instrument", "Entry", "Stop Loss", "Target 1", "Target 2", "R:R", "Confidence", "Option Suggestion"],
            tablefmt="fancy_grid"
        ))

        print("\n📋 STRATEGY RATIONALE & INDICATOR BREAKDOWN:")
        for idx, ti in enumerate(instructions, 1):
            print(f"    [{idx}] {ti.symbol} ({ti.action}):")
            print(f"        • Rationale: {ti.rationale}")
            print(f"        • Indicators: EMA9={ti.indicators.get('ema_fast')}, EMA21={ti.indicators.get('ema_slow')}, "
                  f"RSI={ti.indicators.get('rsi')}, MACD_Hist={ti.indicators.get('macd_hist')}")

    # 3. Active Positions
    closed = order_mgr.update_positions()
    stats = order_mgr.get_summary_stats()
    print(f"\n💼 PORTFOLIO STATUS (Mode: {'Paper Trading' if config.paper_trading else 'Live Trading'}):")
    print(f"    Open Positions: {stats['open_positions_count']} | Realized PnL: ₹{stats['total_realized_pnl']:,.2f} | Unrealized PnL: ₹{stats['total_unrealized_pnl']:,.2f}")


def cmd_run_bot(config: TradingConfig, interval_sec: int = 15):
    """Runs periodic scanning and order tracking loop."""
    banner()
    print(f"\n[+] Starting Automated Trading Loop (Every {interval_sec}s)...")
    print("    Press Ctrl+C to terminate cleanly.\n")

    client = AngelOneClient(config)
    client.login()
    strategy = StrategyEngine(config)
    order_mgr = OrderManager(config, client)

    try:
        iteration = 1
        while True:
            print(f"\n--- Scan Iteration #{iteration} [{datetime.now().strftime('%H:%M:%S')}] ---")
            # Update open positions and evaluate exit conditions
            closed = order_mgr.update_positions()
            for c in closed:
                pnl = c.get('realized_pnl', 0)
                emoji = "🎉 PROFIT" if pnl >= 0 else "🛑 STOPPED"
                print(f"    [{emoji}] Exited {c['action']} {c['symbol']} @ ₹{c['exit_price']:,.2f} | Reason: {c['exit_reason']} | PnL: ₹{pnl:,.2f}")

            # Scan for new signals
            for name in config.active_symbols:
                df = client.get_candle_data(name, interval="FIVE_MINUTE", bars_count=50)
                instruction = strategy.evaluate_signals(name, df)
                if instruction:
                    print(f"    [SIGNAL] {instruction.action} {instruction.symbol} @ ₹{instruction.entry_price:,.2f} (Target: ₹{instruction.target_1:,.2f}, SL: ₹{instruction.stop_loss:,.2f})")
                    res = order_mgr.execute_instruction(instruction)
                    if res.get("success"):
                        print(f"    [ORDER] {res.get('message')}")

            stats = order_mgr.get_summary_stats()
            print(f"    Open: {stats['open_positions_count']} | Net PnL: ₹{stats['net_pnl']:,.2f}")

            iteration += 1
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n[+] Trading bot stopped by user.")


def main():
    parser = argparse.ArgumentParser(description="Angel One SmartAPI Trading & Signal System")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("scan", help="Scan markets and generate trade instructions")
    subparsers.add_parser("test-login", help="Test Angel One credentials and session handshake")

    bot_parser = subparsers.add_parser("bot", help="Run automated trading/monitoring loop")
    bot_parser.add_argument("--interval", type=int, default=15, help="Loop interval in seconds")

    serve_parser = subparsers.add_parser("serve", help="Run web dashboard server")
    serve_parser.add_argument("--port", type=int, default=8080, help="Web server port")

    args = parser.parse_args()
    config = TradingConfig.load()

    if args.command == "test-login":
        cmd_test_login(config)
    elif args.command == "bot":
        cmd_run_bot(config, interval_sec=args.interval)
    elif args.command == "serve":
        from server import start_server
        start_server(port=args.port)
    else:
        # Default action: run scan
        cmd_scan(config, execute=False)


if __name__ == "__main__":
    main()
