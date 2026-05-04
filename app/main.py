import os
import time
import random
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

START_TIME = time.time()
MODE = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT = int(os.environ.get("APP_PORT", 3000))

# Chaos state — protected by a lock for thread safety
chaos_lock = threading.Lock()
chaos_state = {
    "mode": None,
    "duration": 0,
    "rate": 0.0,
}

# Routes that must never be affected by chaos
CHAOS_EXEMPT_PATHS = {"/healthz", "/chaos"}


@app.before_request
def apply_chaos():
    """
    Apply active chaos before request processing.
    Only active in canary mode.
    Exempt /healthz and /chaos from chaos effects — health checks must
    always respond so Docker and swiftdeploy promote can verify liveness.
    """
    if MODE != "canary":
        return

    if request.path in CHAOS_EXEMPT_PATHS:
        return

    # Read state once under lock — minimise lock hold time
    with chaos_lock:
        mode = chaos_state["mode"]
        duration = chaos_state["duration"]
        rate = chaos_state["rate"]

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
def inject_headers(response):
    """Inject X-Mode on every response in canary mode."""
    if MODE == "canary":
        response.headers["X-Mode"] = "canary"
    return response


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
    Returns uptime calculated once per request — no caching needed,
    time.time() is a single syscall and extremely fast.
    """
    return jsonify({
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }), 200


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
            # Clamp rate between 0.0 and 1.0
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