"""Imported first by every test module: offline, isolated state, no Telegram."""
import os
import tempfile

os.environ.setdefault("PX_NETWORK_OFF", "1")
os.environ.setdefault("PX_TELEGRAM_DISABLED", "1")
if not os.environ.get("PX_STATE_DIR"):
    os.environ["PX_STATE_DIR"] = tempfile.mkdtemp(prefix="px_state_test_")
if not os.environ.get("PX_REASONS_PATH"):
    os.environ["PX_REASONS_PATH"] = os.path.join(os.environ["PX_STATE_DIR"], "reasons_site.json")
