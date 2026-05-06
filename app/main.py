"""
SwiftDeploy API Service
Runs in stable or canary mode via MODE env var.
Exposes Prometheus metrics at /metrics.
"""
import os
import time
import random
import threading
import math
from flask import Flask, jsonify, request, g, Response

app = Flask(__name__)

MODE        = os.getenv("MODE", "stable")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_PORT    = int(os.getenv("APP_PORT", "3000"))
START_TIME  = time.time()

# ── Chaos state ───────────────────────────────────────────────────────────────
_chaos = {"mode": None, "duration": 0, "rate": 0.0, "lock": threading.Lock()}

# ── Metrics state ─────────────────────────────────────────────────────────────
# http_requests_total{method, path, status_code}
_req_counts = {}          # key: (method, path, status_code) → int
_req_counts_lock = threading.Lock()

# http_request_duration_seconds histogram
# Standard Prometheus buckets (seconds)
BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
_duration_buckets = {b: 0 for b in BUCKETS}   # cumulative counts per bucket
_duration_inf     = 0                           # +Inf bucket
_duration_sum     = 0.0                         # sum of all durations
_duration_count   = 0                           # total observations
_duration_lock    = threading.Lock()


def _record_request(method, path, status_code, duration_s):
    """Thread-safe update of all metrics after a request completes."""
    key = (method.upper(), path, str(status_code))
    with _req_counts_lock:
        _req_counts[key] = _req_counts.get(key, 0) + 1

    global _duration_inf, _duration_sum, _duration_count
    with _duration_lock:
        for b in BUCKETS:
            if duration_s <= b:
                _duration_buckets[b] += 1
        _duration_inf   += 1
        _duration_sum   += duration_s
        _duration_count += 1


def _chaos_active_value():
    """Return numeric chaos state: 0=none, 1=slow, 2=error."""
    with _chaos["lock"]:
        m = _chaos.get("mode")
    if m == "slow":
        return 1
    if m == "error":
        return 2
    return 0


# ── Flask hooks ───────────────────────────────────────────────────────────────

@app.before_request
def before():
    g.start = time.time()


@app.after_request
def after(response):
    # Record metrics for every request except /metrics itself
    if request.path != "/metrics":
        duration = time.time() - g.start
        _record_request(request.method, request.path, response.status_code, duration)

    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    response.headers["X-Deployed-By"] = "swiftdeploy"
    return response


# ── Chaos helper ──────────────────────────────────────────────────────────────

def apply_chaos():
    """Apply active chaos. Returns error response tuple or None."""
    with _chaos["lock"]:
        mode = _chaos.get("mode")
        if mode == "slow":
            time.sleep(_chaos.get("duration", 0))
        elif mode == "error":
            if random.random() < _chaos.get("rate", 0.0):
                return jsonify({"error": "chaos error injection", "code": 500}), 500
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    chaos_resp = apply_chaos() if MODE == "canary" else None
    if chaos_resp:
        return chaos_resp
    return jsonify({
        "message": "Welcome to SwiftDeploy API",
        "mode":    MODE,
        "version": APP_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@app.route("/healthz")
def healthz():
    uptime = round(time.time() - START_TIME, 2)
    return jsonify({
        "status":         "ok",
        "mode":           MODE,
        "version":        APP_VERSION,
        "uptime_seconds": uptime,
    })


@app.route("/chaos", methods=["POST"])
def chaos():
    if MODE != "canary":
        return jsonify({"error": "chaos endpoint only available in canary mode"}), 403

    body      = request.get_json(force=True) or {}
    chaos_mode = body.get("mode")

    with _chaos["lock"]:
        if chaos_mode == "slow":
            _chaos["mode"]     = "slow"
            _chaos["duration"] = int(body.get("duration", 2))
            return jsonify({"status": "chaos active", "mode": "slow",
                            "duration": _chaos["duration"]})
        elif chaos_mode == "error":
            _chaos["mode"] = "error"
            _chaos["rate"] = float(body.get("rate", 0.5))
            return jsonify({"status": "chaos active", "mode": "error",
                            "rate": _chaos["rate"]})
        elif chaos_mode == "recover":
            _chaos["mode"]     = None
            _chaos["duration"] = 0
            _chaos["rate"]     = 0.0
            return jsonify({"status": "chaos cleared"})
        else:
            return jsonify({"error": "unknown chaos mode",
                            "valid": ["slow", "error", "recover"]}), 400


@app.route("/metrics")
def metrics():
    """Prometheus text format metrics endpoint."""
    lines = []

    # ── http_requests_total ───────────────────────────────────────────────────
    lines.append("# HELP http_requests_total Total HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    with _req_counts_lock:
        snapshot = dict(_req_counts)
    for (method, path, status_code), count in sorted(snapshot.items()):
        lines.append(
            f'http_requests_total{{method="{method}",path="{path}",'
            f'status_code="{status_code}"}} {count}'
        )

    # ── http_request_duration_seconds ─────────────────────────────────────────
    lines.append("# HELP http_request_duration_seconds Request latency histogram")
    lines.append("# TYPE http_request_duration_seconds histogram")
    with _duration_lock:
        for b in BUCKETS:
            lines.append(
                f'http_request_duration_seconds_bucket{{le="{b}"}} {_duration_buckets[b]}'
            )
        lines.append(f'http_request_duration_seconds_bucket{{le="+Inf"}} {_duration_inf}')
        lines.append(f"http_request_duration_seconds_sum {_duration_sum:.6f}")
        lines.append(f"http_request_duration_seconds_count {_duration_count}")

    # ── app_uptime_seconds ────────────────────────────────────────────────────
    lines.append("# HELP app_uptime_seconds Seconds since app started")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {round(time.time() - START_TIME, 2)}")

    # ── app_mode ──────────────────────────────────────────────────────────────
    lines.append("# HELP app_mode Current deployment mode (0=stable, 1=canary)")
    lines.append("# TYPE app_mode gauge")
    lines.append(f"app_mode {1 if MODE == 'canary' else 0}")

    # ── chaos_active ──────────────────────────────────────────────────────────
    lines.append("# HELP chaos_active Active chaos state (0=none, 1=slow, 2=error)")
    lines.append("# TYPE chaos_active gauge")
    lines.append(f"chaos_active {_chaos_active_value()}")

    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)
