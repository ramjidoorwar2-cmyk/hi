"""
Angel One SmartAPI Trading Web API Server
Exposes REST endpoints for the mobile & desktop trading dashboard.
"""

import os
from flask import Flask, jsonify, request, send_from_directory
from config import TradingConfig, DEFAULT_INSTRUMENTS
from angel_client import AngelOneClient
from strategy_engine import StrategyEngine
from order_manager import OrderManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

# Initialize runtime objects
config = TradingConfig.load()
client = AngelOneClient(config)
strategy = StrategyEngine(config)
order_mgr = OrderManager(config, client)

# Try initial login if credentials exist
if config.has_credentials:
    client.login()


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    if os.path.exists(os.path.join(BASE_DIR, path)):
        return send_from_directory(BASE_DIR, path)
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    profile = client.get_profile().get("data", {})
    return jsonify({
        "status": "online",
        "authenticated": client.is_authenticated,
        "is_simulation": client.is_simulation,
        "paper_trading": config.paper_trading,
        "client_code": config.client_code or profile.get("clientcode", "SIMULATED"),
        "broker": "Angel One SmartAPI" if client.is_authenticated else "Simulation / Paper Mode",
        "active_symbols": config.active_symbols,
        "stats": order_mgr.get_summary_stats()
    })


@app.route("/api/market", methods=["GET"])
def get_market():
    results = []
    for sym in config.active_symbols:
        ltp_data = client.get_ltp(sym)
        results.append(ltp_data)
    return jsonify({"market": results})


@app.route("/api/candles", methods=["GET"])
def get_candles():
    symbol = request.args.get("symbol", "NIFTY 50")
    interval = request.args.get("interval", "FIVE_MINUTE")
    bars_count = int(request.args.get("bars", "60"))

    df = client.get_candle_data(symbol, interval=interval, bars_count=bars_count)
    df_ind = strategy.calculate_indicators(df)

    candles = []
    for _, row in df_ind.iterrows():
        t_str = row["timestamp"].strftime("%H:%M") if hasattr(row["timestamp"], "strftime") else str(row["timestamp"])
        candles.append({
            "time": t_str,
            "open": round(row["open"], 2),
            "high": round(row["high"], 2),
            "low": round(row["low"], 2),
            "close": round(row["close"], 2),
            "volume": int(row["volume"]),
            "ema_fast": round(row.get("ema_fast", 0), 2) if "ema_fast" in row else None,
            "ema_slow": round(row.get("ema_slow", 0), 2) if "ema_slow" in row else None,
            "rsi": round(row.get("rsi", 50), 1) if "rsi" in row else None,
        })
    return jsonify({"symbol": symbol, "candles": candles})


@app.route("/api/signals", methods=["GET"])
def get_signals():
    # Update positions before returning signals
    order_mgr.update_positions()
    return jsonify({
        "signals": order_mgr.signals_log,
        "active_positions": order_mgr.active_positions,
        "completed_trades": order_mgr.completed_trades,
        "stats": order_mgr.get_summary_stats()
    })


@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    auto_execute = request.json.get("auto_execute", False) if request.is_json else False
    new_instructions = []

    for sym in config.active_symbols:
        df = client.get_candle_data(sym, interval="FIVE_MINUTE", bars_count=50)
        ti = strategy.evaluate_signals(sym, df)
        if ti:
            new_instructions.append(ti.to_dict())
            if auto_execute:
                order_mgr.execute_instruction(ti)
            else:
                order_mgr.record_signal(ti)

    order_mgr.update_positions()

    return jsonify({
        "success": True,
        "instructions_count": len(new_instructions),
        "instructions": new_instructions,
        "active_positions": order_mgr.active_positions,
        "stats": order_mgr.get_summary_stats()
    })


@app.route("/api/execute", methods=["POST"])
def execute_trade():
    data = request.json or {}
    instruction_id = data.get("instruction_id")
    # Find matching instruction in signals log
    target_ti = None
    for s in order_mgr.signals_log:
        if s.get("id") == instruction_id:
            target_ti = TradeInstruction(**s)
            break

    if not target_ti:
        return jsonify({"success": False, "message": "Signal not found."}), 404

    res = order_mgr.execute_instruction(target_ti)
    return jsonify(res)


@app.route("/api/close-position", methods=["POST"])
def close_position():
    data = request.json or {}
    pos_id = data.get("position_id")
    for pos in list(order_mgr.active_positions):
        if pos.get("id") == pos_id:
            ltp = client.get_ltp(pos["symbol"]).get("ltp", pos["current_price"])
            pos["exit_price"] = ltp
            pos["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pos["exit_reason"] = "MANUAL_EXIT"
            if pos["action"] == "BUY":
                pos["realized_pnl"] = round((ltp - pos["entry_price"]) * pos["quantity"], 2)
            else:
                pos["realized_pnl"] = round((pos["entry_price"] - ltp) * pos["quantity"], 2)
            pos["status"] = "CLOSED"
            order_mgr.completed_trades.insert(0, pos)
            order_mgr.active_positions.remove(pos)
            order_mgr.save_trades()
            return jsonify({"success": True, "message": f"Closed position {pos_id}", "pnl": pos["realized_pnl"]})

    return jsonify({"success": False, "message": "Position not found."}), 404


@app.route("/api/settings", methods=["POST"])
def update_settings():
    global config, client, strategy, order_mgr
    data = request.json or {}

    if "api_key" in data:
        config.api_key = data["api_key"].strip()
    if "client_code" in data:
        config.client_code = data["client_code"].strip()
    if "mpin" in data:
        config.mpin = data["mpin"].strip()
    if "totp_secret" in data:
        config.totp_secret = data["totp_secret"].strip()
    if "paper_trading" in data:
        config.paper_trading = bool(data["paper_trading"])
    if "risk_reward_ratio" in data:
        config.risk_reward_ratio = float(data["risk_reward_ratio"])
    if "fast_ema" in data:
        config.fast_ema = int(data["fast_ema"])
    if "slow_ema" in data:
        config.slow_ema = int(data["slow_ema"])

    config.save()

    # Re-initialize client with updated config
    client = AngelOneClient(config)
    strategy = StrategyEngine(config)
    order_mgr.client = client
    order_mgr.config = config

    login_res = client.login() if config.has_credentials else {"success": False, "mode": "SIMULATION"}

    return jsonify({
        "success": True,
        "message": "Settings updated successfully.",
        "has_credentials": config.has_credentials,
        "login_result": login_res
    })


@app.route("/api/test-connect", methods=["POST"])
def test_connect():
    data = request.json or {}
    test_cfg = TradingConfig.load()
    if data.get("api_key"):
        test_cfg.api_key = data["api_key"]
    if data.get("client_code"):
        test_cfg.client_code = data["client_code"]
    if data.get("mpin"):
        test_cfg.mpin = data["mpin"]
    if data.get("totp_secret"):
        test_cfg.totp_secret = data["totp_secret"]

    test_client = AngelOneClient(test_cfg)
    res = test_client.login()
    return jsonify(res)


def start_server(port: int = 8080):
    banner_text = f"Starting Angel One Trading Server on port {port}..."
    print(banner_text)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    start_server(8080)
