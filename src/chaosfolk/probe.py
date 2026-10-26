"""Small, local-only browser concurrency probe; no AI model is used."""
import argparse
import asyncio
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


def local_url(value):
    parts = urlsplit(value)
    if (parts.scheme not in ("http", "https") or parts.hostname not in ("localhost", "127.0.0.1", "::1")
            or parts.username is not None or parts.password is not None):
        raise argparse.ArgumentTypeError("Use an HTTP(S) loopback URL without credentials")
    try:
        parts.port
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid port") from None
    return value


def limit(low, high):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("Expected a whole number") from None
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"Choose a value between {low} and {high}")
        return number
    return parse


def origin(url):
    parts = urlsplit(url)
    return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


async def run(args, folder):
    from playwright.async_api import async_playwright
    from . import engine
    engine.charger_moteur()
    attempts = []
    async with async_playwright() as pw:
        browser, channel = await engine.lancer_navigateur(pw, False)
        try:
            async def visit(round_number, client):
                context = await browser.new_context(service_workers="block", accept_downloads=False)
                errors = []
                try:
                    async def route(request_route):
                        request = request_route.request
                        if request.method not in ("GET", "HEAD") or origin(request.url) != origin(args.url):
                            await request_route.abort()
                        else:
                            await request_route.continue_()

                    await context.route("**/*", route)
                    await context.route_web_socket("**/*", lambda ws: ws.close())
                    page = await context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)[:300]))
                    start = time.perf_counter()
                    response = await page.goto(args.url, wait_until="load", timeout=15000)
                    elapsed_ms = round((time.perf_counter() - start) * 1000)
                    status = response.status if response else None
                    outcome = "ok" if status is not None and status < 400 else "http-error"
                    evidence = {"round": round_number, "client": client, "elapsed_ms": elapsed_ms,
                                "http_status": status, "outcome": outcome, "page_errors": errors}
                    if round_number == 1 and client == 1 and response:
                        headers = await response.all_headers()
                        evidence["header_presence"] = {
                            name: name in headers for name in ("content-security-policy", "x-content-type-options",
                                "x-frame-options", "referrer-policy", "strict-transport-security")
                        }
                        # Counts are review prompts, not a comprehensive accessibility audit.
                        evidence["review_signals"] = await page.evaluate("""() => {
                          const visible = e => e.getClientRects().length > 0;
                          const named = e => (e.labels && e.labels.length) || e.getAttribute('aria-label') ||
                            e.getAttribute('aria-labelledby') || e.getAttribute('title');
                          return { images_without_alt: [...document.querySelectorAll('img:not([alt])')].filter(visible).length,
                            inputs_without_label: [...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e => visible(e) && !named(e)).length,
                            buttons_without_name: [...document.querySelectorAll('button')].filter(e => visible(e) && !named(e) && !e.textContent.trim()).length };
                        }""")
                        await page.screenshot(path=str(folder / "screen.png"))
                        evidence["screenshot"] = "screen.png"
                    return evidence
                except Exception as error:
                    return {"round": round_number, "client": client, "outcome": "inconclusive",
                            "error": str(error).split("\n")[0][:300], "page_errors": errors}
                finally:
                    await context.close()

            for round_number in range(1, args.rounds + 1):
                attempts.extend(await asyncio.gather(*(visit(round_number, client) for client in range(1, args.clients + 1))))
        finally:
            await browser.close()
    valid = [attempt["elapsed_ms"] for attempt in attempts if "elapsed_ms" in attempt]
    ordered = sorted(valid)
    result = {"url": args.url, "clients": args.clients, "rounds": args.rounds, "browser": channel,
              "attempts": attempts, "valid_count": len(valid),
              "inconclusive_count": sum(a["outcome"] == "inconclusive" for a in attempts),
              "http_error_count": sum(a["outcome"] == "http-error" for a in attempts),
              "median_ms": round(statistics.median(valid)) if valid else None,
              "p95_ms": ordered[math.ceil(len(ordered) * .95) - 1] if ordered else None,
              "note": "Navigation timing is a local smoke measurement, not a load capacity or accessibility certification."}
    (folder / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk probe", description=__doc__)
    parser.add_argument("url", type=local_url, help="explicitly authorized loopback test app URL")
    parser.add_argument("--clients", type=limit(1, 8), default=2)
    parser.add_argument("--rounds", type=limit(1, 5), default=2)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    folder = args.output or Path(".horde") / ("probe-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        parser.error("Output is not empty; choose a new directory")
    folder.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(args, folder.resolve()))
    print(f"Probe: {result['valid_count']} completed, {result['inconclusive_count']} inconclusive, "
          f"{result['http_error_count']} HTTP errors. Median {result['median_ms']} ms. {folder / 'probe.json'}")
    return 2 if result["inconclusive_count"] else 1 if result["http_error_count"] else 0
