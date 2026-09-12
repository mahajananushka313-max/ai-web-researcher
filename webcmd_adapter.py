import os
import urllib.request
import json

WEBCMD_DAEMON_PORT = int(os.getenv("WEBCMD_PORT", "9777"))
WEBCMD_DAEMON_URL = f"http://127.0.0.1:{WEBCMD_DAEMON_PORT}"

def is_webcmd_daemon_active(timeout: float = 1.0) -> bool:
    """Checks if the local Webcmd / CloakBrowser daemon is running on port 9777."""
    try:
        req = urllib.request.Request(f"{WEBCMD_DAEMON_URL}/health", headers={"User-Agent": "WebcmdAdapter/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False

def extract_article_content(url: str, fallback_playwright_fn=None):
    """Attempts to scrape via the local Webcmd daemon; falls back gracefully to Playwright."""
    if is_webcmd_daemon_active():
        try:
            payload = json.dumps({"url": url}).encode("utf-8")
            req = urllib.request.Request(
                f"{WEBCMD_DAEMON_URL}/extract",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("text", "")
                if text:
                    return text
        except Exception:
            pass

    # Graceful fallback to Playwright for Cloud deployment
    if fallback_playwright_fn:
        return fallback_playwright_fn(url)
    return ""