"""
SwiftDeploy API Service
Runs in stable or canary mode via MODE env var.
"""
import os
import time
import random
import threading
from flask import Flask, jsonify, request, g

app = Flask(__name__)

MODE = os.getenv("MODE", "stable")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_PORT = int(os.getenv("APP_PORT", "3000"))
START_TIME = time.time()

# Chaos state
_chaos = {"mode": None, "duration": 0, "rate": 0.0, "lock": threading.Lock()}


def apply_chaos():
    """Apply active chaos before handling request. Returns error response or None."""
    with _chaos["lock"]:
        mode = _chaos.get("mode")
        if mode == "slow":
            duration = _chaos.get("duration", 0)
            time.sleep(duration)
        elif mode == "error":
            rate = _chaos.get("rate", 0.0)
            if random.random() < rate:
                return jsonify({"error": "chaos error injection", "code": 500}), 500
    return None


@app.before_request
def before():
    g.start = time.time()


@app.after_request
def after(response):
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    response.headers["X-Deployed-By"] = "swiftdeploy"
    return response


@app.route("/")
def index():
    chaos_resp = apply_chaos() if MODE == "canary" else None
    if chaos_resp:
        return chaos_resp
    return jsonify({
        "message": f"Welcome to SwiftDeploy API",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@app.route("/healthz")
def healthz():
    uptime = round(time.time() - START_TIME, 2)
    return jsonify({
        "status": "ok",
        "mode": MODE,
        "version": APP_VERSION,
        "uptime_seconds": uptime,
    })


@app.route("/chaos", methods=["POST"])
def chaos():
    if MODE != "canary":
        return jsonify({"error": "chaos endpoint only available in canary mode"}), 403

    body = request.get_json(force=True) or {}
    chaos_mode = body.get("mode")

    with _chaos["lock"]:
        if chaos_mode == "slow":
            _chaos["mode"] = "slow"
            _chaos["duration"] = int(body.get("duration", 2))
            return jsonify({"status": "chaos active", "mode": "slow", "duration": _chaos["duration"]})
        elif chaos_mode == "error":
            _chaos["mode"] = "error"
            _chaos["rate"] = float(body.get("rate", 0.5))
            return jsonify({"status": "chaos active", "mode": "error", "rate": _chaos["rate"]})
        elif chaos_mode == "recover":
            _chaos["mode"] = None
            _chaos["duration"] = 0
            _chaos["rate"] = 0.0
            return jsonify({"status": "chaos cleared"})
        else:
            return jsonify({"error": "unknown chaos mode", "valid": ["slow", "error", "recover"]}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)
