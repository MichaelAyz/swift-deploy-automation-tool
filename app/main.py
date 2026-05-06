import os
import time
import random
import threading
from flask import Flask, request, jsonify, Response
from prometheus_client import (
    Counter, Histogram, Gauge,
    generate_latest, CONTENT_TYPE_LATEST,
    REGISTRY
)

app = Flask(__name__)

START_TIME = time.time()
MODE = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT = int(os.environ.get("APP_PORT", 3000))

# ── Prometheus metrics ────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

UPTIME_GAUGE = Gauge(
    "app_uptime_seconds",
    "Seconds since app started"
)

MODE_GAUGE = Gauge(
    "app_mode",
    "Current deployment mode: 0=stable, 1=canary"
)

CHAOS_GAUGE = Gauge(
    "chaos_active",
    "Active chaos state: 0=none, 1=slow, 2=error"
)

# Initialise static gauges to reflect startup state
MODE_GAUGE.set(1 if MODE == "canary" else 0)
CHAOS_GAUGE.set(0)

# ── Chaos state ───────────────────────────────────────────────────────────────

chaos_lock = threading.Lock()
chaos_state = {
    "mode": None,
    "duration": 0,
    "rate": 0.0,
}

# Routes that must never be affected by chaos
# /metrics added: pre-promote scrape must always succeed
CHAOS_EXEMPT_PATHS = {"/healthz", "/chaos", "/metrics"}

# Per-request start time storage (thread-local)
_request_start = threading.local()


# ── Request hooks ─────────────────────────────────────────────────────────────

@app.before_request
def before_request_handler():
    """Record request start time and apply chaos effects."""
    _request_start.time = time.time()

    # Chaos only in canary mode, never on exempt paths
    if MODE != "canary" or request.path in CHAOS_EXEMPT_PATHS:
        return

    with chaos_lock:
        mode     = chaos_state["mode"]
        duration = chaos_state["duration"]
        rate     = chaos_state["rate"]

    if mode == "slow":
        time.sleep(duration)

    elif mode == "error":
        if random.random() < rate:
            response = jsonify({
                "error": "chaos error injection",
                "code": 500
            })
            response.status_code = 500
            response.headers["X-Mode"] = "canary"
            return response


@app.after_request
def after_request_handler(response):
    """
    Record metrics for every completed request.
    Update uptime, mode, and chaos gauges on each request
    so /metrics always reflects current state without a background thread.
    """
    # Update live gauges
    UPTIME_GAUGE.set(round(time.time() - START_TIME, 2))
    MODE_GAUGE.set(1 if MODE == "canary" else 0)

    with chaos_lock:
        cm = chaos_state["mode"]
    if cm == "slow":
        CHAOS_GAUGE.set(1)
    elif cm == "error":
        CHAOS_GAUGE.set(2)
    else:
        CHAOS_GAUGE.set(0)

    # Record counter and histogram
    path = request.path
    method = request.method
    status = str(response.status_code)

    REQUEST_COUNT.labels(method=method, path=path, status_code=status).inc()

    start = getattr(_request_start, "time", None)
    if start is not None:
        REQUEST_LATENCY.labels(method=method, path=path).observe(
            time.time() - start
        )

    # Inject canary header
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"

    return response


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": f"SwiftDeploy service is running in {MODE} mode",
        "mode": MODE,
        "version": APP_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }), 200


@app.route("/healthz", methods=["GET"])
def healthz():
    """
    Liveness check. Never affected by chaos.
    Returns uptime calculated once per request.
    """
    return jsonify({
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    """
    Prometheus metrics endpoint.
    Exempt from chaos so the CLI pre-promote scrape always succeeds.
    Returns text/plain in Prometheus exposition format.
    """
    return Response(
        generate_latest(REGISTRY),
        mimetype=CONTENT_TYPE_LATEST
    )


@app.route("/chaos", methods=["POST"])
def chaos():
    if MODE != "canary":
        return jsonify({
            "error": "chaos endpoint only available in canary mode"
        }), 403

    body = request.get_json(silent=True)
    if not body or "mode" not in body:
        return jsonify({
            "error": "invalid request body, expected JSON with 'mode' field"
        }), 400

    chaos_mode = body["mode"]

    with chaos_lock:
        if chaos_mode == "slow":
            duration = max(0, int(body.get("duration", 1)))
            chaos_state.update({"mode": "slow", "duration": duration, "rate": 0.0})
            return jsonify({
                "message": f"chaos slow mode active, duration {duration}s"
            }), 200

        elif chaos_mode == "error":
            rate = max(0.0, min(1.0, float(body.get("rate", 0.5))))
            chaos_state.update({"mode": "error", "duration": 0, "rate": rate})
            return jsonify({
                "message": f"chaos error mode active, rate {rate}"
            }), 200

        elif chaos_mode == "recover":
            chaos_state.update({"mode": None, "duration": 0, "rate": 0.0})
            return jsonify({"message": "chaos cleared, service recovering"}), 200

        else:
            return jsonify({
                "error": f"unknown chaos mode: {chaos_mode}"
            }), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)