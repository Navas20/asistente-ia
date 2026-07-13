import os
import sys
import json
import subprocess
import urllib.request

REPO = "Navas20/asistente-ia"

def check_for_updates() -> tuple:
    try:
        url = f"https://api.github.com/repos/{REPO}/commits/main"
        req = urllib.request.Request(url, headers={"User-Agent": "artenisa-updater"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        remote_sha = data.get("sha", "")
        try:
            local_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except Exception:
            local_sha = ""
        if local_sha and remote_sha and local_sha[:8] != remote_sha[:8]:
            commit_msg = data.get("commit", {}).get("message", "")
            return True, remote_sha[:8], commit_msg[:100]
        return False, "", ""
    except Exception as e:
        return False, "", str(e)

def do_update() -> tuple:
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            if "Already up to date" in out:
                return True, "Already up to date"
            return True, f"Updated: {out[:200]}"
        return False, result.stderr.strip() or "Git pull failed"
    except subprocess.TimeoutExpired:
        return False, "Git pull timed out"
    except FileNotFoundError:
        return False, "Git not found"
    except Exception as e:
        return False, str(e)

def get_current_version() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()[:12] if result.stdout else "?"
    except:
        return "?"
