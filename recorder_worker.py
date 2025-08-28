# recorder_worker.py
"""
Background worker for Render.

Behavior:
 - On startup, fetch token.pkl from the web service (protected by TOKEN_FETCH_SECRET).
 - Monitor usernames.txt every CHECK_INTERVAL seconds.
 - When a username is live, start a recorder subprocess (RECORDER_CMD template).
 - Track running recorder processes and let them run until they exit (when the stream ends).
 - If token.pkl is missing or expired, re-fetch from the web service.
"""

import os
import time
import logging
import requests
import shlex
import subprocess
from threading import Thread, Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recorder-worker")

# ---------- Config (via env vars) ----------
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "https://tiktok-livestream-recorder.onrender.com")
TOKEN_FETCH_URL = os.environ.get("TOKEN_FETCH_URL", WEB_BASE_URL.rstrip("/") + "/_internal/token")
TOKEN_FETCH_SECRET = os.environ.get("TOKEN_FETCH_SECRET", None)
TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "token.pkl")
USERNAMES_FILE = os.environ.get("USERNAMES_FILE", "usernames.txt")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))  # seconds
# RECORDER_CMD should include {username} placeholder. If not set, worker falls back to local scripts auto-detected below.
RECORDER_CMD = os.environ.get("RECORDER_CMD", "")  # example: "python -u -m src.core.tiktok_recorder {username}"
# Directory where to store recordings locally if recorder writes them to disk
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "recordings")

# Runtime state
active_procs = {}  # username -> subprocess.Popen
state_lock = Lock()


# ---------- Utilities ----------
def fetch_token_from_web(force=False):
    """
    Fetch token.pkl from web service and save to TOKEN_FILE.
    Requires TOKEN_FETCH_SECRET env var to match the web service.
    """
    if not TOKEN_FETCH_SECRET:
        logger.error("TOKEN_FETCH_SECRET not configured in worker. Cannot fetch token.")
        return False

    if os.path.exists(TOKEN_FILE) and not force:
        logger.debug("token.pkl already present locally at %s", TOKEN_FILE)
        return True

    headers = {"Authorization": f"Bearer {TOKEN_FETCH_SECRET}"}
    try:
        logger.info("Requesting token from %s", TOKEN_FETCH_URL)
        r = requests.get(TOKEN_FETCH_URL, headers=headers, timeout=20)
        if r.status_code == 200:
            with open(TOKEN_FILE, "wb") as f:
                f.write(r.content)
            logger.info("Fetched and saved token.pkl to %s", TOKEN_FILE)
            return True
        else:
            logger.warning("Failed to fetch token.pkl (%s): %s", r.status_code, r.text)
            return False
    except Exception as e:
        logger.exception("Exception while fetching token.pkl: %s", e)
        return False


def read_usernames():
    if not os.path.exists(USERNAMES_FILE):
        logger.warning("usernames.txt not found at path: %s", USERNAMES_FILE)
        return []
    with open(USERNAMES_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines()]
    # remove blank lines and comments
    return [l for l in lines if l and not l.startswith("#")]


def detect_live_status_importable():
    """
    Try to import a function to detect livestream status from your project.
    Tries common names in your repo. Returns a callable(username)->bool or None.
    """
    candidates = [
        ("src.core.tiktok_api", "is_user_live"),
        ("src.core.tiktok_api", "user_is_live"),
        ("src.core.tiktok_recorder", "is_user_live"),
        ("src.core.recorder", "is_user_live"),
    ]
    for module_name, func_name in candidates:
        try:
            module = __import__(module_name, fromlist=[func_name])
            fn = getattr(module, func_name, None)
            if callable(fn):
                logger.info("Using live-check function: %s.%s", module_name, func_name)
                return fn
        except Exception:
            continue
    logger.warning("No live-check function found in src.core. Worker will not auto-detect live status.")
    return None


def choose_recorder_command(username):
    """
    Build a concrete command (list) to start the recorder for `username`.
    1) If RECORDER_CMD env var is set, use it (format with username).
    2) Otherwise, prefer src/core/tiktok_recorder.py if present, else src/core/recorder.py.
    """
    if RECORDER_CMD:
        cmd = RECORDER_CMD.format(username=username)
        return shlex.split(cmd)

    # Fallback detection
    candidates = [
        f"python -u -m src.core.tiktok_recorder {username}",
        f"python -u src/core/tiktok_recorder.py {username}",
        f"python -u src/core/recorder.py --username {username}",
        f"python -u src/core/recorder.py {username}",
    ]
    for c in candidates:
        parts = shlex.split(c)
        # quick existence test: if refers to a file, check file exists
        if any(part.endswith(".py") and os.path.exists(part) for part in parts):
            logger.info("Autodetected recorder command: %s", c)
            return parts
        # if using -m style module, we cannot easily test; still try it
        if "-m" in parts:
            logger.info("Autodetected -m recorder command: %s", c)
            return parts

    # if nothing found, return last candidate (likely to fail until you set RECORDER_CMD)
    logger.warning("No recorder script autodetected. Set RECORDER_CMD env var to a valid command.")
    return shlex.split(candidates[-1])


def start_recorder_process(username):
    """Launch recorder subprocess for the username and track it in active_procs."""
    with state_lock:
        if username in active_procs:
            proc = active_procs[username]
            if proc.poll() is None:
                logger.info("Recorder already running for %s (pid=%s)", username, proc.pid)
                return False

    cmd = choose_recorder_command(username)
    logger.info("Starting recorder for %s with command: %s", username, " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with state_lock:
            active_procs[username] = proc

        # Launch threads to stream logs
        Thread(target=_stream_proc_logs, args=(username, proc.stdout, False), daemon=True).start()
        Thread(target=_stream_proc_logs, args=(username, proc.stderr, True), daemon=True).start()
        return True
    except Exception as e:
        logger.exception("Failed to start recorder for %s: %s", username, e)
        return False


def _stream_proc_logs(username, stream, is_err):
    """Read process stream lines and log them (prevents pipes from filling)."""
    try:
        for line in iter(stream.readline, b""):
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if is_err:
                logger.warning("[%s][recorder-stderr] %s", username, text)
            else:
                logger.info("[%s][recorder-stdout] %s", username, text)
    except Exception:
        pass


def cleanup_finished_processes():
    """Remove entries for processes that have exited."""
    with state_lock:
        to_remove = []
        for username, proc in list(active_procs.items()):
            if proc.poll() is not None:
                logger.info("Recorder for %s exited (rc=%s). Cleaning up.", username, proc.returncode)
                to_remove.append(username)
        for username in to_remove:
            active_procs.pop(username, None)


# ---------- Main loop ----------
def main_loop():
    # ensure recordings dir exists
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    # fetch token initially (web service must have token.pkl available)
    token_ok = fetch_token_from_web()
    if not token_ok:
        logger.warning("Initial token fetch failed. Worker will keep trying while running.")

    # attempt to discover live-check function
    live_check_fn = detect_live_status_importable()

    while True:
        try:
            usernames = read_usernames()
            if not usernames:
                logger.debug("No usernames found; sleeping.")
                time.sleep(CHECK_INTERVAL)
                continue

            # refresh token if missing
            if not os.path.exists(TOKEN_FILE):
                logger.info("token.pkl missing; attempting to fetch from web service.")
                fetch_token_from_web(force=True)

            # For each username, decide whether to start/stop recorder
            for username in usernames:
                username = username.strip()
                if not username:
                    continue

                # If we have a live-check function, use it
                is_live = False
                if live_check_fn:
                    try:
                        is_live = bool(live_check_fn(username))
                    except Exception:
                        logger.exception("live_check_fn raised for %s; assuming not live", username)
                        is_live = False
                else:
                    # If no live-check available: optionally try to always run recorder (commented)
                    logger.debug("No live-check available; worker will not auto-start recorders. Set RECORDER_CMD and/or implement is_user_live.")
                    is_live = False

                with state_lock:
                    running = username in active_procs and active_procs[username].poll() is None

                if is_live and not running:
                    logger.info("%s is live — starting recorder.", username)
                    started = start_recorder_process(username)
                    if not started:
                        logger.warning("Failed to start recorder for %s", username)

                # cleanup if no longer live and process finished
                if not is_live and running:
                    logger.info("%s is not live but recorder is running; leaving process to complete or you may modify worker to kill it.", username)

            cleanup_finished_processes()
        except Exception:
            logger.exception("Worker loop encountered an error")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    logger.info("Recorder worker starting up")
    main_loop()
