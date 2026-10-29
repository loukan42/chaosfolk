"""Compare Chromium heap for inline and lazy local reports with identical evidence.

Both variants use the current UI and a fresh browser process. The lazy run
visits every chunk, then forces GC through CDP to measure retained JS heap.
This measures local browser memory and latency, not energy or model cost.
"""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import time

from playwright.sync_api import sync_playwright

from chaosfolk import engine, reporting


def measure(path, events):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, remote = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: remote.append(request.url) if request.url.startswith(("https:", "http:")) else None)
        started = time.perf_counter()
        page.goto(path.as_uri())
        page.wait_for_function("evidenceStore.stats().pending === 0")
        ready = time.perf_counter() - started
        client = page.context.new_cdp_session(page)
        client.send("HeapProfiler.collectGarbage")
        initial = client.send("Runtime.getHeapUsage")
        walked = page.evaluate("""async count => {
          const started=performance.now();
          const positions=data.journal_details?.chunks.map(chunk=>chunk.start)||Array.from({length:Math.ceil(count/128)},(_,i)=>i*128);
          for(const index of positions){
            const event=await evidenceStore.event(data.journal[index]);
            if(event.n!==index||!event.pense.startsWith('Reaction '+index+':'))throw new Error('evidence mismatch');
          }
          const last=await evidenceStore.event(data.journal[count-1]);
          if(last.custom_evidence.id!==count-1)throw new Error('last evidence lost');
          return {seconds:(performance.now()-started)/1000,cache:evidenceStore.stats(),events:data.journal.length,visited_chunks:positions.length};
        }""", events)
        client.send("HeapProfiler.collectGarbage")
        after = client.send("Runtime.getHeapUsage")
        assert not errors and not remote, (errors, remote)
        browser.close()
        return {"ready_seconds": ready, "initial_heap_bytes": initial["usedSize"],
                "after_all_chunks_heap_bytes": after["usedSize"], "walk": walked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=12000)
    parser.add_argument("--text-bytes", type=int, default=2048)
    parser.add_argument("--temp-root", type=Path)
    args = parser.parse_args()
    if args.events < 1 or args.text_bytes < 0:
        parser.error("Use a positive event count and non-negative text size")
    with tempfile.TemporaryDirectory(prefix="chaosfolk-browser-bench-", dir=args.temp_root) as temporary:
        root = Path(temporary)
        results = {}
        for variant in ("inline", "lazy"):
            folder = root / variant
            folder.mkdir()
            engine.ecrire_json(folder / "personas.json", {"humains": [{"id": "h01", "nom": "Alex", "appareil": "desktop"}]})
            engine.ecrire_json(folder / "constats.json", {"constats": []})
            shutil.copyfile(Path(engine.__file__).parent / "templates/mascot.png", folder / "shot.png")
            with (folder / "journal.jsonl").open("w", encoding="utf-8") as stream:
                for index in range(args.events):
                    event = {"type": "action", "h": "h01", "n": index, "t": index * 100,
                             "action": "click", "resultat": "ok", "capture": "shot.png", "cible": {"nom": "Save"},
                             "args": {"texte": f"Original input {index}"}, "url": "http://localhost/test",
                             "pense": f"Reaction {index}:" + "x" * args.text_bytes, "custom_evidence": {"id": index}}
                    stream.write(json.dumps(event) + "\n")
            previous = reporting.INLINE_JOURNAL_BYTES
            try:
                reporting.INLINE_JOURNAL_BYTES = 10 ** 12 if variant == "inline" else 1
                with redirect_stdout(io.StringIO()):
                    engine.rapport(folder)
            finally:
                reporting.INLINE_JOURNAL_BYTES = previous
            path = folder / "report-en.html"
            results[variant] = dict(measure(path, args.events), html_bytes=path.stat().st_size,
                                    detail_files=len(list((folder / "assets/journal").glob("*.js"))))
        print(json.dumps({"events": args.events, "text_bytes_per_event": args.text_bytes, "variants": results,
                          "scope": "Fresh Chromium processes, local file://, heap after explicit GC; every chunk visited; no remote requests."}, indent=2))


if __name__ == "__main__":
    main()
