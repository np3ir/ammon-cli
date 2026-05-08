"""Download albums via OrpheusDL subprocess."""
import subprocess
import sys
from pathlib import Path

ORPHEUS_DIR = Path("C:/OrpheusDL")


def download_album(apple_id: str, storefront: str = "us") -> tuple[bool, str]:
    """
    Download an album via orpheus CLI.
    Returns (success, message).
    """
    url = f"https://music.apple.com/{storefront}/album/{apple_id}"
    try:
        result = subprocess.run(
            [sys.executable, str(ORPHEUS_DIR / "orpheus.py"), url],
            cwd=str(ORPHEUS_DIR),
            capture_output=False,
            timeout=3600,
        )
        if result.returncode == 0:
            return True, f"Downloaded {apple_id}"
        return False, f"orpheus exited with code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)
