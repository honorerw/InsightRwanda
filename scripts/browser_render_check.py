"""Real-browser render check for the InsightRwanda dashboard.

Starts Streamlit, launches headless Chrome with a DevTools debugging port,
navigates to the app, waits in *real* time for the websocket-driven render
(plain --screenshot fires far too early), captures a screenshot through the
DevTools protocol, then verifies the branded sidebar colour and textual
markers appear in the DOM.
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

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PORT = 8805
CDP_PORT = 9225
OUT = Path("/tmp/insightrwanda_render.png")

CHROME = shutil.which("chrome") or shutil.which("google-chrome")
assert CHROME is not None, "Chrome binary not found"


def start_streamlit() -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
            "--server.headless=true", f"--server.port={PORT}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


async def cdp_screenshot_and_dom() -> tuple[bytes, str]:
    http_port_page = None
    with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json", timeout=5) as resp:
        targets = json.loads(resp.read().decode())
    http_port_page = next(t for t in targets if t["type"] == "page")
    import websockets

    async with websockets.connect(http_port_page["webSocketDebuggerUrl"], max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        await ws.send(json.dumps({"id": 2, "method": "Page.navigate", "params": {"url": f"http://localhost:{PORT}"}}))
        await ws.recv()

        # Real-time wait so the Streamlit websocket can deliver a full render.
        deadline = time.monotonic() + 45
        dom = ""
        while time.monotonic() < deadline:
            await asyncio.sleep(3)
            await ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {
                "expression": "document.body ? document.body.innerText.slice(0, 5000) : 'LOADING'", "returnByValue": True,
            }}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if message.get("id") == 3:
                    dom = message["result"]["result"].get("value", "")
                    break
            if "InsightRwanda" in dom and "Running" not in dom[:200]:
                break

        await ws.send(json.dumps({"id": 4, "method": "Page.captureScreenshot"}))
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if message.get("id") == 4:
                return base64.b64decode(message["result"]["data"]), dom
        return b"", dom  # pragma: no cover


def verify(png: bytes, dom: str) -> bool:
    OUT.write_bytes(png)
    img = Image.open(OUT).convert("RGB")
    w, h = img.size

    def is_dark_green(px) -> bool:
        r, g, b = px
        return r < 70 and 60 < g < 140 and b < 100 and g > r and g > b

    sidebar = [img.getpixel((30, y)) for y in (60, 300, 800)]
    green_hits = sum(is_dark_green(px) for px in sidebar)
    markers = {
        "InsightRwanda in DOM": "InsightRwanda" in dom,
        "page headline in DOM": "financial resilience" in dom,
        "KPI label in DOM": "Active formal access" in dom,
        "sidebar green pixels": green_hits >= 2,
    }
    print(f"Screenshot: {OUT} ({w}x{h}, {len(png):,} bytes)")
    for name, ok in markers.items():
        print(f"  {'OK' if ok else 'FAIL'}  {name}")
    all_ok = all(markers.values())
    print(f"REAL-BROWSER RENDER {'PASSED' if all_ok else 'FAILED'}")
    return all_ok


def main() -> int:
    streamlit = start_streamlit()
    chrome = subprocess.Popen(
        [
            CHROME, "--headless", "--disable-gpu", "--no-sandbox",
            f"--remote-debugging-port={CDP_PORT}", "--window-size=1600,2200",
            "--user-data-dir=/tmp/chrome_cdp_profile", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4)
        png, dom = asyncio.run(cdp_screenshot_and_dom())
        ok = verify(png, dom)
    finally:
        chrome.terminate()
        streamlit.terminate()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
