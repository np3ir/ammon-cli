"""Download albums via gamdl subprocess."""
import subprocess
from pathlib import Path


def download_track(apple_id: str, storefront: str = "us") -> tuple[bool, str]:
    """Download a single track via gamdl CLI."""
    url = f"https://music.apple.com/{storefront}/song/{apple_id}"
    try:
        result = subprocess.run(
            ["gamdl", url],
            capture_output=False,
            timeout=600,
        )
        if result.returncode == 0:
            return True, f"Downloaded {apple_id}"
        return False, f"gamdl exited with code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def download_album(apple_id: str, storefront: str = "us") -> tuple[bool, str]:
    """
    Download an album via gamdl CLI.
    Returns (success, message).
    Always uses 'us' storefront for downloading regardless of discovery storefront —
    Apple Music metadata (isSingle, trackCount, release type) is consistent in 'us'.
    Falls back to the discovery storefront if 'us' fails.
    """
    for sf in (["us", storefront] if storefront != "us" else ["us"]):
        url = f"https://music.apple.com/{sf}/album/{apple_id}"
        try:
            result = subprocess.run(
                ["gamdl", url],
                capture_output=False,
                timeout=3600,
            )
            if result.returncode == 0:
                return True, f"Downloaded {apple_id}"
            if sf == "us" and storefront != "us":
                continue  # try discovery storefront as fallback
            return False, f"gamdl exited with code {result.returncode}"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    return False, "All storefronts failed"
