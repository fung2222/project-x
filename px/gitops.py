"""Optional commit + push of generated data (used with `run.py <job> --push`)."""
import subprocess

from .config import BASE_DIR

DATA_PATHS = ["data", "portfolio.json", "daily_report.json", "signals.json", "profiles.json", "Reports", "state",
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


def pull():
    return _git("pull", "--rebase", "--autostash", "-q", "origin", "main", check=False).returncode == 0


def commit_paths_and_push(paths, message):
    """Commit ONLY `paths` (e.g. data/futu_positions.json after `run.py pos ... --push`) and push to main.
    Never force-pushes; rebases on origin/main first."""
    _git("add", "--", *paths, check=False)
    if _git("diff", "--cached", "--quiet", "--", *paths, check=False).returncode == 0:
        print("[git] nothing to commit (already committed/pushed?)")
        return True
    cm = _git("commit", "-m", message, "--", *paths, check=False)
    if cm.returncode != 0:
        print("[git] commit failed:", cm.stderr.strip()[:200])
        return False
    for i in range(3):
        _git("pull", "--rebase", "--autostash", "origin", "main", check=False)
        ps = _git("push", "origin", "HEAD:main", check=False)
        if ps.returncode == 0:
            print("[git] pushed:", message)
            return True
        print(f"[git] push attempt {i+1} failed: {ps.stderr.strip()[:200]}")
    return False
