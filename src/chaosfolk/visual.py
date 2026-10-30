"""Explicit screenshot baselines and deterministic pixel comparisons."""
import argparse
import asyncio
import hashlib
import json
import shutil
from pathlib import Path


def compare(before, after, output, threshold=20, max_ratio=0.001):
    from PIL import Image, ImageChops
    if not 0 <= threshold <= 255 or not 0 <= max_ratio <= 1:
        raise ValueError("Threshold must be 0..255 and max-diff-ratio 0..1")
    before, after, output = Path(before).resolve(), Path(after).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory")
    with Image.open(before) as a, Image.open(after) as b:
        # Header sizes are known before any pixel is decoded; refuse decompression bombs first.
        if a.width * a.height > 20_000_000 or b.width * b.height > 20_000_000:
            raise ValueError("Images must contain at most 20 million pixels")
        a, b = a.convert("RGB"), b.convert("RGB")
        output.mkdir(parents=True, exist_ok=True)
        a.save(output / "before.png")
        b.save(output / "after.png")
        same_size = a.size == b.size
        if same_size:
            delta = ImageChops.difference(a, b)
            channels = delta.split()
            maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
            mask = maximum.point(lambda x: 255 if x > threshold else 0)
            changed = mask.histogram()[255]
            difference = Image.new("RGB", a.size, "#ff3355")
            faded = Image.blend(a, Image.new("RGB", a.size, "white"), .65)
            Image.composite(difference, faded, mask).save(output / "diff.png")
            ratio = changed / (a.width * a.height)
        else:
            changed, ratio = max(a.width * a.height, b.width * b.height), 1.0
            b.save(output / "diff.png")
        result = {"schema_version": 1, "same_size": same_size, "before_size": a.size, "after_size": b.size,
                  "changed_pixels": changed, "changed_ratio": ratio, "threshold": threshold,
                  "max_diff_ratio": max_ratio, "passed": same_size and ratio <= max_ratio,
                  "interpretation": "Pixel difference to review, not an automatic product-bug verdict.",
                  "before_sha256": hashlib.sha256(before.read_bytes()).hexdigest(),
                  "after_sha256": hashlib.sha256(after.read_bytes()).hexdigest()}
    (output / "visual.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "index.html").write_text("""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Chaosfolk visual comparison</title><style>body{font:16px system-ui;background:#101612;color:#eef4e8;margin:24px}
main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}img{width:100%}figure{margin:0}
@media(max-width:700px){main{grid-template-columns:1fr}}</style><h1>Visual comparison</h1>
<p>Review the change before updating the baseline. A pixel difference is not necessarily a bug.</p><main>
<figure><figcaption>Before</figcaption><img src="before.png" alt="Approved reference"></figure>
<figure><figcaption>After</figcaption><img src="after.png" alt="New capture"></figure>
<figure><figcaption>Difference</figcaption><img src="diff.png" alt="Changed pixels highlighted"></figure>
</main></html>""", encoding="utf-8")
    return result


async def capture(url, output, browser="chromium", masks=(), width=1280, height=800, state=None):
    from playwright.async_api import async_playwright
    from .engine import lancer_navigateur
    from .privacy import screenshot_masks
    from urllib.parse import urlsplit
    if urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).hostname:
        raise ValueError("Use an explicit HTTP(S) test URL")
    output = Path(output)
    if output.exists():
        raise ValueError("Capture already exists; choose a new file")
    if not (320 <= width <= 3840 and 200 <= height <= 2160):
        raise ValueError("Viewport out of bounds")
    async with async_playwright() as pw:
        instance, engine = await lancer_navigateur(pw, canal=browser)
        try:
            context = await instance.new_context(viewport={"width": width, "height": height},
                                                 storage_state=state, service_workers="block")
            page = await context.new_page()
            response = await page.goto(url, wait_until="load", timeout=30000)
            if not response or not response.ok:
                raise ValueError("Target did not return a successful HTTP response")
            await page.evaluate("document.fonts.ready")
            output.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(output), animations="disabled", caret="hide",
                                  mask=screenshot_masks(page, masks), timeout=10000)
            # Deliberately omit URL and authentication contents from public metadata.
            output.with_suffix(output.suffix + ".json").write_text(json.dumps(
                {"browser": engine, "viewport": {"width": width, "height": height},
                 "masks": list(masks), "animations": "disabled"}, indent=2), encoding="utf-8")
        finally:
            await instance.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk visual")
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("capture")
    c.add_argument("url")
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    c.add_argument("--mask", action="append", default=[])
    c.add_argument("--state", help="local Playwright storage state; never copied into the result")
    c.add_argument("--width", type=int, default=1280)
    c.add_argument("--height", type=int, default=800)
    c = commands.add_parser("compare")
    c.add_argument("before", type=Path)
    c.add_argument("after", type=Path)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--threshold", type=int, default=20)
    c.add_argument("--max-diff-ratio", type=float, default=.001)
    c = commands.add_parser("approve")
    c.add_argument("--candidate", type=Path, required=True)
    c.add_argument("--baseline", type=Path, required=True)
    c.add_argument("--reviewed", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            asyncio.run(capture(args.url, args.output, args.browser, args.mask, args.width, args.height, args.state))
        elif args.command == "compare":
            result = compare(args.before, args.after, args.output, args.threshold, args.max_diff_ratio)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        else:
            from PIL import Image
            with Image.open(args.candidate) as image:
                image.verify()
            if args.candidate.resolve() == args.baseline.resolve():
                raise ValueError("Candidate and baseline must differ")
            args.baseline.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.candidate, args.baseline)
            args.baseline.with_suffix(args.baseline.suffix + ".approval.json").write_text(json.dumps(
                {"reviewed": True, "sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest()}), encoding="utf-8")
        return 0
    except ImportError:
        print('Install the visual extra: python -m pip install "chaosfolk[visual]" (or ".[visual]" from source).')
        return 2
    except (OSError, ValueError, RuntimeError) as error:
        print(f"visual: {error}")
        return 2
