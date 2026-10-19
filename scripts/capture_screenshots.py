"""Capture full-page screenshots of every dashboard page for the submission guide.

Starts Streamlit, drives headless Chrome via the DevTools protocol, clicks
through the sidebar navigation (real UI interaction), waits for each page's
known headline to appear in the live DOM, then captures a full-page screenshot
into docs/screenshots/.
"""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
PORT = 8806
CDP_PORT = 9226

CHROME = shutil.which("chrome") or shutil.which("google-chrome")

# nav label -> text that must appear in the live DOM before capture
PAGES: list[tuple[str, str]] = [
    ("Overview", "Where financial resilience"),
    ("Financial inclusion", "Verified indicators, connected"),
    ("Poverty insights", "what the evidence can"),
    ("Geographic insights", "geography of exclusion"),
    ("Resilience lab", "most exposed to the next shock"),
    ("Data quality", "what was checked"),
    ("Data explorer", "Keep the evidence one click"),
    ("Methods & sources", "traceable route"),
    ("About the build", "competition-ready decision tool"),
]


def start_streamlit() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
         "--server.headless=true", f"--server.port={PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2) as resp:
                if resp.read() == b"ok":
                    return proc
        except Exception:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("Streamlit did not become healthy")


def page_target_url() -> str:
    with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json", timeout=5) as resp:
        targets = json.loads(resp.read().decode())
    return next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")


CLICK_JS = """
(() => {
  const options = document.querySelectorAll('[data-testid="stRadioOption"]');
  if (options.length !== %d) return 'OPTIONS_%d_EXPECTED_' + options.length;
  options[%d].click();
  return 'CLICKED_%d';
})()
"""


def slug(nav: str) -> str:
    return nav.lower().replace(" & ", "_").replace(" ", "_") or nav


async def main() -> int:
    import websockets

    SHOTS.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    async with websockets.connect(page_target_url(), max_size=100 * 1024 * 1024) as ws:
        next_id = 0

        async def call(method: str, params: dict | None = None, timeout: float = 20) -> dict:
            nonlocal next_id
            next_id += 1
            await ws.send(json.dumps({"id": next_id, "method": method, "params": params or {}}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if message.get("id") == next_id:
                    return message

        _state: dict[str, str] = {}

        async def poll_text() -> None:
            message = await call("Runtime.evaluate", {"expression":
                "document.body ? document.body.innerText.slice(0, 15000) : 'EMPTY'",
                "returnByValue": True})
            _state["text"] = message["result"]["result"].get("value", "")

        await call("Page.enable")
        await call("Runtime.enable")
        await call("Page.navigate", {"url": f"http://localhost:{PORT}"})
        await asyncio.sleep(12)  # first render incl. pipeline load

        for index, (nav, marker) in enumerate(PAGES):
            result = await call("Runtime.evaluate", {"expression": CLICK_JS % (9, 9, index, index), "returnByValue": True})
            click_note = result["result"].get("result", {}).get("value", "no-result")
            await asyncio.sleep(2)
            deadline = time.monotonic() + 60
            rendered = False
            while time.monotonic() < deadline:
                await poll_text()
                text = _state.get("text", "")
                if marker in text and "Running" not in text[:120]:
                    rendered = True
                    break
                await asyncio.sleep(2)
            await asyncio.sleep(2)  # let charts settle
            shot = await call("Page.captureScreenshot", {"captureBeyondViewport": True, "format": "png"})
            png_bytes = base64.b64decode(shot["result"]["data"])
            out = SHOTS / f"{slug(nav)}.png"
            out.write_bytes(png_bytes)
            size_kb = len(png_bytes) // 1024
            status = "OK" if rendered and size_kb > 60 else "FAIL"
            if status == "FAIL":
                failures.append(nav)
            print(f"  {status}  {nav}: rendered={rendered}, screenshot={size_kb} KB -> {out.name} (click: {click_note})")

    if failures:
        print(f"\nCAPTURE FAILED for: {failures}")
        return 1
    print("\nCAPTURE PASSED: 9/9 pages.")
    return 0


if __name__ == "__main__":
    streamlit = start_streamlit()
    chrome = subprocess.Popen(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={CDP_PORT}", "--window-size=1600,2200",
         "--user-data-dir=/tmp/chrome_shot_profile", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    exit_code = 1
    try:
        time.sleep(4)
        exit_code = asyncio.run(main())
    finally:
        chrome.terminate()
        streamlit.terminate()
    sys.exit(exit_code)
