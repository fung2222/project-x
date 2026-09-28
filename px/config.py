"""Settings + secrets loading.

Secrets are read from environment variables FIRST, then (fallback) from the
local, git-ignored json files that the Grok Bot box still uses:
    FINNHUB_API_KEY    <- finnhub_config.json   {"api_key": ...}
    MARKETAUX_API_KEY  <- marketaux_config.json {"api_key": ...}
    TELEGRAM_BOT_TOKEN <- telegram_config.json  {"bot_token": ...}
    TELEGRAM_CHAT_ID   <- telegram_config.json  {"chat_id": ...}
Each name may also be given with a PX_ prefix (PX_TELEGRAM_CHAT_ID ...), which wins.
Env files loaded (real environment variables always win): $PX_ENV_FILE (e.g. Hermes
/opt/data/.env), then the repo-root `.env` (git-ignored). Simple KEY=VALUE lines.
NEVER print secret values.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(BASE_DIR, "config", "settings.json")
STATE_DIR = os.environ.get("PX_STATE_DIR") or os.path.join(BASE_DIR, "state")  # tests point this at a temp dir
REPORTS_DIR = os.path.join(BASE_DIR, "Reports")

_SECRET_FALLBACK = {
    "FINNHUB_API_KEY": ("finnhub_config.json", ("api_key",)),
    "MARKETAUX_API_KEY": ("marketaux_config.json", ("api_key",)),
    "TELEGRAM_BOT_TOKEN": ("telegram_config.json", ("bot_token", "token")),
    "TELEGRAM_CHAT_ID": ("telegram_config.json", ("chat_id",)),
}

_settings_cache = None
_dotenv_loaded = False


def path(*parts):
    return os.path.join(BASE_DIR, *parts)


def load_settings(reload=False):
    global _settings_cache
    if _settings_cache is None or reload:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            _settings_cache = json.load(f)
    return _settings_cache


def _load_dotenv():
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    # Precedence: real environment > PX_ENV_FILE (e.g. Hermes /opt/data/.env) > repo-root .env
    for p in [os.environ.get("PX_ENV_FILE", "").strip(), path(".env")]:
        if not p or not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:].strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


def get_secret(name, required=False):
    """Return secret value (env first, then local json fallback) or ''."""
    _load_dotenv()
    # PX_<NAME> wins over <NAME>, so a shared env file (e.g. Hermes /opt/data/.env, whose
    # TELEGRAM_CHAT_ID may be a DM) can never silently redirect Project X pushes.
    val = os.environ.get("PX_" + name, "").strip() or os.environ.get(name, "").strip()
    if not val and name in _SECRET_FALLBACK:
        fname, keys = _SECRET_FALLBACK[name]
        fp = path(fname)
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    cfg = json.load(f)
                for k in keys:
                    if cfg.get(k):
                        val = str(cfg.get(k)).strip()
                        break
            except Exception:
                val = ""
    if required and not val:
        raise RuntimeError(f"Missing secret {name} (set env var {name}; see .env.example)")
    return val


def secret_status():
    """Names + whether present (never values)."""
    return {k: bool(get_secret(k)) for k in _SECRET_FALLBACK}


def is_dry_run():
    return os.environ.get("PX_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def network_off():
    """PX_NETWORK_OFF=1 (set by the test suite): no external data calls at all (Yahoo / Finnhub / Marketaux)."""
    return os.environ.get("PX_NETWORK_OFF", "").strip().lower() in ("1", "true", "yes")


def telegram_disabled():
    s = load_settings()
    if not s.get("telegram", {}).get("enabled", True):
        return True
    return os.environ.get("PX_TELEGRAM_DISABLED", "").strip().lower() in ("1", "true", "yes")


def universe_all(include_opportunity=True):
    u = load_settings()["universe"]
    t = list(u["core"]) + list(u["secondary"])
    if include_opportunity:
        t += list(u["opportunity"])
    return t


def theme_of(ticker):
    for theme, members in load_settings()["themes"].items():
        if ticker in members:
            return theme
    return "OTHER"


def bucket_of(ticker):
    u = load_settings()["universe"]
    for b in ("core", "secondary", "opportunity"):
        if ticker in u[b]:
            return b
    return "other"
