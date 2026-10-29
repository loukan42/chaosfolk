"""Measure real Chromium RSS and CPU before/after releasing finished users.

Uses a deterministic loopback fixture, no model calls and no external site.
Run: python scripts/benchmark_browser_resources.py --users 4 --repeat 3
RSS is the sum of Chromium process working sets, not unique physical memory.
"""
import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import tempfile
import threading
import time

import psutil
from playwright.async_api import async_playwright

from chaosfolk import engine


PAGE = b"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Resource fixture</title>
<body><button id="save">Save synthetic record</button><p id="result">Ready</p>
<script>
// Touch 16 MiB per renderer, and simulate a polling UI that consumes 3 ms / 25 ms.
window.fixtureHeap = new Uint8Array(16 * 1024 * 1024);
window.fixtureHeap.fill(7);
window.fixtureTicks = 0;
setInterval(() => {
  const until = performance.now() + 3;
  while (performance.now() < until) window.fixtureTicks += 1;
}, 25);
document.querySelector('#save').onclick = () => {
  localStorage.setItem('synthetic', 'saved');
  document.querySelector('#result').textContent = 'Saved';
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


def chromium_processes():
    observations = {}
    for process in psutil.Process(os.getpid()).children(recursive=True):
        try:
            if not any(name in process.name().lower() for name in ("chrome", "chromium", "headless_shell")):
                continue
            cpu = process.cpu_times()
            observations[(process.pid, process.create_time())] = {
                "rss": process.memory_info().rss, "cpu": cpu.user + cpu.system}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return observations


async def sample(seconds):
    before = chromium_processes()
    started = time.perf_counter()
    await asyncio.sleep(seconds)
    after = chromium_processes()
    elapsed = time.perf_counter() - started
    cpu = sum(max(0, value["cpu"] - before[key]["cpu"]) for key, value in after.items() if key in before)
    return {"rss_mib": sum(item["rss"] for item in after.values()) / 1024**2,
            "processes": len(after), "cpu_seconds": cpu, "sample_seconds": elapsed,
            "cpu_percent_one_core": cpu / elapsed * 100}


async def trial(url, folder, users, seconds):
    opts = engine.construire_parseur().parse_args(["serve", "--url", url, "--folder", str(folder)])
    horde = engine.Horde(opts)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        version = browser.version
        try:
            for index in range(users):
                hid = f"h{index + 1:02d}"
                world = await engine.nouveau_monde(browser, hid, {}, url, folder, journal=horde.journal)
                await world.nouvelle_page(url)
                await world.page.locator("#save").click()
                horde.humains[hid] = world
                horde.verrous[hid] = asyncio.Lock()
                if index < users - 1:
                    world.statut = "fini"
                    horde.journal({"type": "action", "h": hid, "n": 1, "action": "done", "ecran": ["Saved"]})
            await asyncio.sleep(0.3)
            retained = await sample(seconds)
            retained["contexts"] = len(browser.contexts)
            for index in range(users - 1):
                hid = f"h{index + 1:02d}"
                response = await horde.liberer_humain({"h": hid})
                assert response["ok"], response
                state = json.loads(horde.humains[hid].released_state.read_text(encoding="utf-8"))
                assert any(entry == {"name": "synthetic", "value": "saved"}
                           for origin in state["origins"] for entry in origin["localStorage"])
            await asyncio.sleep(0.3)
            released = await sample(seconds)
            released["contexts"] = len(browser.contexts)
            survivor = horde.humains[f"h{users:02d}"]
            assert await survivor.page.locator("#result").inner_text() == "Saved"
            assert len([event for event in engine.iterer_journal(folder) if event["type"] == "action"]) == users - 1
            return {"chromium_version": version, "retained": retained, "released": released,
                    "storage_and_trace_preserved": True, "active_user_works": True}
        finally:
            await browser.close()
            horde.journal_f.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 2 <= args.users <= 20 or not 1 <= args.repeat <= 10 or not 0.5 <= args.seconds <= 10:
        parser.error("Use 2–20 users, 1–10 repeats and 0.5–10 seconds per sample")
    engine.charger_moteur()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        with tempfile.TemporaryDirectory(prefix="chaosfolk-browser-benchmark-") as directory:
            runs = [asyncio.run(trial(url, Path(directory) / f"run-{index}", args.users, args.seconds))
                    for index in range(args.repeat)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    medians = {phase: {metric: round(statistics.median(run[phase][metric] for run in runs), 4)
                       for metric in ("rss_mib", "processes", "contexts", "cpu_seconds", "cpu_percent_one_core")}
               for phase in ("retained", "released")}
    result = {"platform": platform.platform(), "python": platform.python_version(),
              "playwright": importlib.metadata.version("playwright"), "users": args.users,
              "released_users": args.users - 1, "repeats": args.repeat,
              "fixture": "16 MiB touched heap and 3 ms of work every 25 ms per user",
              "measurement": "Sum of Chromium descendant RSS (shared pages may count multiple times); CPU across processes, 100% = one core",
              "scope": "Synthetic local polling UI. No model, tokens, energy, or production traffic measured.",
              "median": medians, "runs": runs}
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
