"""Optional commit + push of generated data (used with `run.py <job> --push`)."""
import subprocess

from .config import BASE_DIR

DATA_PATHS = ["portfolio.json", "daily_report.json", "signals.json", "profiles.json", "Reports", "state",
              "_last_open_monitor.json", "_last_hourly_check.json", ".last_hourly_quiet_hkt"]


def _git(*args, check=True):
    return subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, check=check)


def commit_and_push(message):
    _git("add", "-A", "--", *DATA_PATHS, check=False)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("[git] nothing to commit")
        return True
    _git("commit", "-m", message)
    for i in range(3):
        pr = _git("pull", "--rebase", "--autostash", "origin", "main", check=False)
        ps = _git("push", "origin", "HEAD:main", check=False)
        if ps.returncode == 0:
            print("[git] pushed:", message)
            return True
        print(f"[git] push attempt {i+1} failed: {ps.stderr.strip()[:200]}")
    return False
