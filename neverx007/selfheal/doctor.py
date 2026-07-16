#!/usr/bin/env python3
import os, sys, time, sqlite3, subprocess, requests
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict, deque

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
DB = DATA / "watcher.db"
LOG_DIR = DATA / "logs"
DATA.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL = 60
API_CHECK_INTERVAL = 300
FAILURE_WINDOW = 6
API_FAILURE_THRESHOLD = 3

SERVICES = {
    "northfraim": ("northfraim", "http://localhost:8001/health", True),
    "api_health_check": ("api_health_check", None, True),
    "governor": ("governor", None, True),
    "doctor": ("doctor", None, False),
}

EXTERNAL_APIS = {
    "elevenlabs": {"url": "https://api.elevenlabs.io/v1/voices", "header": "xi-api-key", "env_key": "ELEVENLABS_API_KEY"},
    "json2video": {"url": "https://api.json2video.com/v2/movies", "header": "x-api-key", "env_key": "JSON2VIDEO_API_KEY"},
    "pixverse": {"url": "https://app-api.pixverse.ai/openapi/v2/account/balance", "header": "API-KEY", "env_key": "PIXVERSE_API_KEY"},
}

failure_history = defaultdict(lambda: deque(maxlen=FAILURE_WINDOW))
api_failure_history = defaultdict(lambda: deque(maxlen=API_FAILURE_THRESHOLD))
last_api_check = 0

def _log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with open(LOG_DIR / "doctor.out.log", "a") as f:
        f.write(line + "\n")

def _load_env():
    env_path = BASE / ".env"
    if not env_path.exists(): return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

def _db_conn(): return sqlite3.connect(DB)

def _init_db():
    with _db_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, error TEXT NOT NULL, context TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS doctor_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, level TEXT, message TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS doctor_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
        conn.commit()

def _log_to_db(level, message):
    try:
        with _db_conn() as conn:
            conn.execute("INSERT INTO doctor_log (timestamp, level, message) VALUES (?, ?, ?)", (datetime.now(timezone.utc).isoformat(), level, message))
            conn.commit()
    except: pass

def _read_recent_errors(limit=20):
    try:
        with _db_conn() as conn:
            return conn.execute("SELECT timestamp, error, context FROM errors ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    except: return []

def check_local_service(name, health_url):
    if health_url is None:
        try:
            result = subprocess.run(["supervisorctl", "status", name], capture_output=True, text=True, timeout=10)
            if "RUNNING" in result.stdout: return {"status": "healthy", "detail": "Process running"}
            elif "FATAL" in result.stdout or "EXITED" in result.stdout: return {"status": "dead", "detail": result.stdout.strip()}
            else: return {"status": "unknown", "detail": result.stdout.strip()}
        except Exception as e: return {"status": "error", "detail": str(e)}
    try:
        r = requests.get(health_url, timeout=5)
        if r.status_code == 200: return {"status": "healthy", "detail": str(r.json())[:100]}
        else: return {"status": "unhealthy", "detail": f"HTTP {r.status_code}"}
    except requests.exceptions.ConnectionError: return {"status": "dead", "detail": "Connection refused"}
    except requests.exceptions.Timeout: return {"status": "unhealthy", "detail": "Timeout"}
    except Exception as e: return {"status": "error", "detail": str(e)}

def classify_local_failure(name, result):
    detail = result.get("detail", "")
    if result["status"] == "dead":
        if "Connection refused" in detail or "FATAL" in detail or "EXITED" in detail: return "process_crashed"
        return "unknown_dead"
    if result["status"] == "unhealthy": return "overloaded" if "Timeout" in detail else "unhealthy_response"
    if result["status"] == "error": return "check_error"
    return "unknown"

def act_on_local_failure(name, classification, supervisor_name, restartable):
    if classification == "process_crashed" and restartable:
        _log(f"{name}: Process crashed -- restarting via supervisorctl", "ACTION")
        try:
            result = subprocess.run(["supervisorctl", "restart", supervisor_name], capture_output=True, text=True, timeout=15)
            if result.returncode == 0: _log(f"{name}: Restart succeeded", "OK"); return "restarted"
            else: _log(f"{name}: Restart failed -- {result.stderr.strip()}", "FAIL"); return "restart_failed"
        except Exception as e: _log(f"{name}: Restart exception -- {e}", "FAIL"); return "restart_failed"
    if classification == "overloaded": _log(f"{name}: Overloaded -- monitoring", "WARN"); return "monitoring"
    if classification == "unhealthy_response": _log(f"{name}: Unhealthy HTTP -- needs investigation", "WARN"); return "needs_investigation"
    if not restartable: _log(f"{name}: Cannot restart self -- escalate to human", "ESCALATE"); return "escalate"
    _log(f"{name}: Unknown failure -- monitoring", "WARN"); return "monitoring"

def check_external_api(name, config):
    key = os.getenv(config["env_key"], "")
    if not key or key.startswith("your_"): return {"status": "no_key", "detail": f"{config['env_key']} missing"}
    try:
        headers = {config["header"]: key}
        r = requests.get(config["url"], headers=headers, timeout=15)
        if r.status_code == 200: return {"status": "healthy", "detail": f"HTTP {r.status_code}"}
        elif r.status_code == 401: return {"status": "auth_error", "detail": "HTTP 401 -- key invalid"}
        elif r.status_code == 429: return {"status": "rate_limited", "detail": "HTTP 429"}
        elif r.status_code >= 500: return {"status": "provider_error", "detail": f"HTTP {r.status_code}"}
        else: return {"status": "error", "detail": f"HTTP {r.status_code}"}
    except requests.exceptions.Timeout: return {"status": "timeout", "detail": "Timeout"}
    except requests.exceptions.ConnectionError: return {"status": "unreachable", "detail": "Cannot connect"}
    except Exception as e: return {"status": "error", "detail": str(e)}

def classify_api_failure(name, result):
    s = result["status"]
    if s == "auth_error": return "dead_key"
    if s == "rate_limited": return "rate_limited"
    if s == "provider_error": return "their_outage"
    if s in ("timeout", "unreachable"): return "network_issue"
    if s == "no_key": return "missing_key"
    return "unknown"

def act_on_api_failure(name, classification, result):
    if classification == "dead_key":
        msg = f"{name}: AUTH FAILURE -- key invalid. NO RESTART FIXES THIS. Rotate key at provider dashboard."
        _log(msg, "ESCALATE"); _log_to_db("ESCALATE", msg); return "escalate_key_rotation"
    if classification == "rate_limited": _log(f"{name}: Rate limited -- backing off", "WARN"); return "backoff"
    if classification == "their_outage": _log(f"{name}: Provider error -- monitoring", "WARN"); return "monitoring"
    if classification == "network_issue": _log(f"{name}: Network issue -- transient", "WARN"); return "monitoring"
    if classification == "missing_key": _log(f"{name}: Key missing -- add to .env", "ESCALATE"); return "escalate_config"
    _log(f"{name}: Unclassified error -- {result.get('detail', '')}", "WARN"); return "monitoring"

def analyze_error_patterns():
    errors = _read_recent_errors(50)
    if not errors: return
    now = datetime.now(timezone.utc)
    hour_ago = now.timestamp() - 3600
    counts = defaultdict(int)
    for ts_str, error, ctx in errors:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.timestamp() > hour_ago:
                for svc in list(EXTERNAL_APIS.keys()) + ["northfraim", "governor"]:
                    if svc in error.lower(): counts[svc] += 1
        except: pass
    for svc, count in counts.items():
        if count >= 10:
            msg = f"PATTERN ALERT: {svc} has {count} errors/hour -- needs human attention"
            _log(msg, "ESCALATE"); _log_to_db("ESCALATE", msg)

def run_cycle():
    global last_api_check
    _log("=" * 60); _log("Starting diagnostic cycle"); _log("=" * 60)
    for name, (supervisor_name, health_url, restartable) in SERVICES.items():
        result = check_local_service(name, health_url)
        if result["status"] == "healthy":
            if name in failure_history: failure_history[name].clear()
            _log(f"{name}: HEALTHY -- {result['detail']}", "OK")
        else:
            failure_history[name].append((time.time(), result))
            count = len(failure_history[name])
            classification = classify_local_failure(name, result)
            _log(f"{name}: UNHEALTHY ({classification}) -- {count}/{FAILURE_WINDOW} -- {result['detail']}", "WARN")
            if count >= FAILURE_WINDOW:
                action = act_on_local_failure(name, classification, supervisor_name, restartable)
                if action in ("restarted", "restart_failed"): failure_history[name].clear()
    if time.time() - last_api_check >= API_CHECK_INTERVAL:
        last_api_check = time.time()
        for name, config in EXTERNAL_APIS.items():
            result = check_external_api(name, config)
            if result["status"] == "healthy":
                if name in api_failure_history: api_failure_history[name].clear()
                _log(f"{name}: API HEALTHY -- {result['detail']}", "OK")
            else:
                api_failure_history[name].append((time.time(), result))
                count = len(api_failure_history[name])
                classification = classify_api_failure(name, result)
                _log(f"{name}: API UNHEALTHY ({classification}) -- {count}/{API_FAILURE_THRESHOLD} -- {result['detail']}", "WARN")
                if count >= API_FAILURE_THRESHOLD:
                    action = act_on_api_failure(name, classification, result)
                    if action.startswith("escalate"): api_failure_history[name].clear()
    analyze_error_patterns()
    _log("Cycle complete. Sleeping...\n")

def main():
    _load_env(); _init_db()
    _log("NeverX007 Doctor v2.1 started -- THE GENERAL IS ONLINE")
    _log(f"Services: {list(SERVICES.keys())}")
    _log(f"External APIs: {list(EXTERNAL_APIS.keys())}")
    while True:
        try: run_cycle()
        except Exception as e: _log(f"CRITICAL: Cycle crashed -- {e}", "CRITICAL"); _log_to_db("CRITICAL", str(e))
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__": main()
