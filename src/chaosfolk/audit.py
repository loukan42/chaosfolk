"""UI, responsive and accessibility audit of a user's current tab, without a model.

For each viewport the page is resized, measured and photographed: horizontal
overflow, controls outside the screen or covered, small targets, clipped text,
unreachable submit buttons. Accessibility signals (names, alt text, contrast,
headings, language, zoom) and failed resources are collected at the same time.
An optional keyboard pass tabs through the page. Results are review signals with
evidence, not a conformance certificate: confirm each one before reporting it.
"""
import json
import re
from pathlib import Path

from chaosfolk import engine

TARGET_MIN = 24  # WCAG 2.2 AA target size (2.5.8), in CSS pixels
DEFAULT_VIEWPORTS = "320x640,375x812,768x1024,1440x900"

AUDIT_JS = r"""(target) => {
  const W = innerWidth, H = innerHeight, LIMIT = 8;
  const clip = (s, n = 60) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  // This synchronous, read-only pass sees one layout snapshot. Reuse each measurement.
  const styles = new WeakMap(), boxes = new WeakMap();
  const style = el => { if (!styles.has(el)) styles.set(el, getComputedStyle(el)); return styles.get(el); };
  const box = el => { if (!boxes.has(el)) boxes.set(el, el.getBoundingClientRect()); return boxes.get(el); };
  const shown = el => { const r = box(el), s = style(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0; };
  const nameOf = el => {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    if (ids.length) return clip(ids.map(i => (document.getElementById(i) || {}).textContent || '').join(' '));
    if (el.getAttribute('aria-label')) return clip(el.getAttribute('aria-label'));
    if (el.labels && el.labels.length) return clip([...el.labels].map(l => l.textContent).join(' '));
    if (el.tagName === 'IMG' || (el.tagName === 'INPUT' && el.type === 'image')) return clip(el.alt);
    if (['submit', 'button', 'reset'].includes(el.type) && el.value) return clip(el.value);
    const inner = clip(el.innerText || el.textContent);
    if (inner) return inner;
    const img = el.querySelector && el.querySelector('img[alt]:not([alt=""]), svg title');
    if (img) return clip(img.alt || img.textContent);
    return clip(el.title || el.getAttribute('placeholder') || '');
  };
  const describe = el => {
    const r = box(el);
    return {element: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.classList[0] ? '.' + el.classList[0] : ''),
            name: nameOf(el), box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]};
  };
  const inScroller = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const s = style(p); if (/(auto|scroll)/.test(s.overflowX) && p.scrollWidth > p.clientWidth + 1) return true; } return false; };
  const INTERACTIVE = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=tab],[role=menuitem],[role=switch],[tabindex]:not([tabindex="-1"])';
  const controls = [...document.querySelectorAll(INTERACTIVE)].filter(el => shown(el) && !el.matches(':disabled') && !el.closest('[inert]'));
  const result = {viewport: W + 'x' + H};

  const docWidth = document.documentElement.scrollWidth;
  if (docWidth > W + 1) {
    const wide = [...document.body.querySelectorAll('*')].slice(0, 4000).filter(el => shown(el)
      && box(el).right > W + 1 && !inScroller(el)
      && !(el.parentElement && el.parentElement !== document.body && box(el.parentElement).right > W + 1));
    result.horizontal_overflow = {document_width: docWidth, causes: wide.slice(0, LIMIT).map(describe)};
  }
  result.offscreen_controls = controls.filter(el => { const r = box(el);
    return (r.right > W + 1 || r.left < -1) && !inScroller(el); }).slice(0, LIMIT).map(describe);
  result.covered_controls = controls.filter(el => { const r = box(el);
    if (r.top < 0 || r.bottom > H || r.left < 0 || r.right > W) return false;
    // A covered centre alone does not make a control unreachable (icons, badges, overlays).
    return [[.5,.5],[.2,.2],[.8,.2],[.2,.8],[.8,.8]].every(([x,y]) => {
      const top = document.elementFromPoint(r.left + r.width * x, r.top + r.height * y);
      return top && !el.contains(top) && !top.contains(el) && !(top.tagName === 'LABEL' && top.control === el);
    });
  }).slice(0, LIMIT).map(el => { const r = box(el);
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return Object.assign(describe(el), {covered_by: describe(top).element}); });
  const inline = el => el.tagName === 'A' && el.parentElement && clip(el.parentElement.innerText, 400).length > clip(el.innerText, 400).length + 20;
  // WCAG 2.5.8: an undersized target fails only when a 24 px circle on its centre reaches another target.
  const pointers = controls.filter(el => !inline(el) && !['text', 'email', 'tel', 'password', 'search', 'number', 'url', 'date']
    .includes(el.type) && !['TEXTAREA', 'SELECT'].includes(el.tagName));
  const small = el => { const r = box(el); return r.width < target || r.height < target; };
  const reach = (el, other) => { const r = box(el), o = box(other);
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (small(other) && Math.hypot(cx - o.left - o.width / 2, cy - o.top - o.height / 2) < target) return true;
    const dx = Math.max(o.left - cx, 0, cx - o.right), dy = Math.max(o.top - cy, 0, cy - o.bottom);
    return Math.hypot(dx, dy) < target / 2; };
  result.small_targets = pointers.filter(el => small(el) && pointers.some(o => o !== el && !o.contains(el) && !el.contains(o) && reach(el, o)))
    .slice(0, LIMIT).map(describe);
  result.clipped_text = [...document.querySelectorAll('button,a,label,th,td,h1,h2,h3,[role=button],[role=tab]')].filter(el => {
    if (!shown(el) || !clip(el.innerText)) return false; const s = style(el);
    return el.scrollWidth > el.clientWidth + 1 && /(hidden|clip)/.test(s.overflowX + s.overflow);
  }).slice(0, LIMIT).map(describe);
  result.unreachable_submit = [...document.forms].map(form => {
    const submit = form.querySelector('[type=submit],button:not([type])');
    if (!submit || !shown(submit)) return null; const r = box(submit);
    return (r.right > W + 1 || r.left < -1) && !inScroller(submit) ? describe(submit) : null;
  }).filter(Boolean).slice(0, LIMIT);

  result.unnamed_controls = controls.filter(el => !nameOf(el) && !['submit', 'reset'].includes(el.type)).slice(0, LIMIT).map(describe);
  const images = [...document.images].filter(shown);
  result.images_without_alt = images.filter(img => !img.hasAttribute('alt')).slice(0, LIMIT).map(describe);
  result.broken_images = [...document.images].filter(img => img.complete && img.naturalWidth === 0 && (img.currentSrc || img.src))
    .slice(0, LIMIT).map(img => Object.assign(describe(img), {src: clip(img.currentSrc || img.src, 160)}));
  result.failed_resources = performance.getEntriesByType('resource').filter(e => e.responseStatus >= 400)
    .slice(0, LIMIT).map(e => ({url: clip(e.name, 160), status: e.responseStatus, type: e.initiatorType}));
  result.lang = document.documentElement.getAttribute('lang') || '';
  result.title = clip(document.title, 120);
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading][aria-level]')].filter(shown)
    .map(h => ({level: +(h.getAttribute('aria-level') || h.tagName.slice(1)), text: clip(h.innerText)}));
  result.h1_count = headings.filter(h => h.level === 1).length;
  result.heading_skips = headings.slice(1).map((h, i) => h.level > headings[i].level + 1 ? `h${headings[i].level} "${headings[i].text}" then h${h.level} "${h.text}"` : null).filter(Boolean).slice(0, LIMIT);
  const ids = Object.create(null); document.querySelectorAll('[id]').forEach(el => { ids[el.id] = (ids[el.id] || 0) + 1; });
  result.duplicate_ids = Object.keys(ids).filter(id => ids[id] > 1).slice(0, LIMIT);
  result.positive_tabindex = [...document.querySelectorAll('[tabindex]')].filter(el => el.tabIndex > 0).slice(0, LIMIT).map(describe);
  result.aria_hidden_focusable = [...document.querySelectorAll('[aria-hidden=true]')].flatMap(el => [...el.querySelectorAll(INTERACTIVE)])
    .filter(el => shown(el) && el.tabIndex >= 0 && !el.matches(':disabled') && !el.closest('[inert]')).slice(0, LIMIT).map(describe);
  result.frames_without_title = [...document.querySelectorAll('iframe')].filter(f => shown(f) && !f.title && !f.getAttribute('aria-label')).slice(0, LIMIT).map(describe);
  const meta = (document.querySelector('meta[name=viewport]') || {}).content || '';
  const maxScale = /maximum-scale\s*=\s*([\d.]+)/i.exec(meta);
  result.zoom_blocked = /user-scalable\s*=\s*(no|0)/i.test(meta) || (maxScale && parseFloat(maxScale[1]) < 2) ? meta : '';
  result.vague_links = [...document.querySelectorAll('a[href]')].filter(a => shown(a) && !a.getAttribute('aria-label')
    && /^(click here|here|read more|more|learn more|cliquez ici|ici|en savoir plus|lire la suite|plus|voir plus|hier|mehr)$/i.test(clip(a.innerText)))
    .slice(0, LIMIT).map(describe);
  const rgba = c => { const m = /rgba?\(([^)]+)\)/.exec(c); if (!m) return null; const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const background = el => { for (let p = el; p; p = p.parentElement) { const s = style(p);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const c = rgba(s.backgroundColor); if (c && c[3] >= 0.99) return c; if (c && c[3] > 0.01) return null; }
    return [255, 255, 255, 1]; };
  const seen = new Set(), low = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(), n = 0; node && n < 600; node = walker.nextNode()) {
    const el = node.parentElement; if (!el || seen.has(el) || node.textContent.trim().length < 2 || !shown(el)) continue;
    seen.add(el); n++;
    const s = style(el), fg = rgba(s.color), bg = background(el);
    if (!fg || !bg || fg[3] < 0.99) continue;
    const a = lum(fg), b = lum(bg), ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const size = parseFloat(s.fontSize), large = size >= 24 || (size >= 18.66 && parseInt(s.fontWeight) >= 700);
    if (ratio < (large ? 3 : 4.5)) low.push(Object.assign(describe(el), {ratio: Math.round(ratio * 100) / 100, required: large ? 3 : 4.5, text: clip(node.textContent, 40)}));
  }
  result.low_contrast = low.slice(0, LIMIT);
  result.mouse_only = [...document.querySelectorAll('div,span,li,img,svg,td,p')].slice(0, 4000).filter(el => shown(el)
    && style(el).cursor === 'pointer' && !el.closest(INTERACTIVE + ',label') && !el.querySelector(INTERACTIVE)
    && !(el.parentElement && style(el.parentElement).cursor === 'pointer' && !el.parentElement.closest(INTERACTIVE)))
    .slice(0, LIMIT).map(describe);
  return result;
}"""

FOCUS_JS = r"""() => {
  const store = window.__chaosfolkFocus = window.__chaosfolkFocus || {keys: new WeakMap(), next: 1};
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return {body: true};
  if (!store.keys.has(el)) store.keys.set(el, store.next++);
  const r = el.getBoundingClientRect(), s = getComputedStyle(el);
  const name = (el.getAttribute('aria-label') || el.innerText || el.value || el.title || el.getAttribute('placeholder') || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const modal = [...document.querySelectorAll('dialog[open],[aria-modal=true]')].find(d => d.getBoundingClientRect().height > 0);
  return {key: store.keys.get(el), element: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''), name,
          visible: r.width > 1 && r.height > 1 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth
            && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0,
          indicator: (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none',
          modal_open: !!modal, inside_modal: !!(modal && modal.contains(el))};
}"""

UNREACHED_JS = r"""() => {
  const store = window.__chaosfolkFocus || {keys: new WeakMap()};
  const shown = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  return [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[tabindex]:not([tabindex="-1"])')]
    .filter(el => shown(el) && !el.matches(':disabled') && !el.closest('[inert]') && el.tabIndex >= 0 && !store.keys.has(el)
      && !(el.type === 'radio' && el.name && document.querySelector(`input[type=radio][name="${CSS.escape(el.name)}"]:checked`) !== el && [...document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)].some(r => store.keys.has(r))))
    .slice(0, 8).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + ' "' + (el.getAttribute('aria-label') || el.innerText || el.value || '').replace(/\s+/g, ' ').trim().slice(0, 50) + '"');
}"""


def parse_viewports(text):
    sizes = []
    for item in (text or "").split(","):
        match = re.fullmatch(r"\s*(\d{3,4})x(\d{3,4})\s*", item)
        if not match:
            raise ValueError(f"Viewport {item.strip()!r} must look like 390x844")
        sizes.append((int(match.group(1)), int(match.group(2))))
    if not sizes or len(sizes) > 8:
        raise ValueError("Give between one and eight viewports")
    return sizes


async def keyboard_pass(page, limit=150):
    """Tab through the page from the top until focus leaves the document or comes back to a seen element."""
    await page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); window.scrollTo(0, 0); "
                        "delete window.__chaosfolkFocus; }")
    steps, seen, stuck = [], set(), 0
    for _ in range(limit):
        await page.keyboard.press("Tab")
        state = await engine.borne(page.evaluate(FOCUS_JS))
        if state.get("body"):
            if steps:
                break
            continue
        if steps and state["key"] == steps[-1]["key"]:
            stuck += 1
            if stuck >= 2:
                break
            continue
        if state["key"] in seen:
            steps.append(dict(state, repeat=True))
            break
        seen.add(state["key"])
        steps.append(state)
    unreached = await engine.borne(page.evaluate(UNREACHED_JS))
    cycled = bool(steps) and steps[-1].get("repeat")
    modal = any(step.get("modal_open") for step in steps)
    return {"tab_stops": len([s for s in steps if not s.get("repeat")]),
            "focus_stuck": stuck >= 2 and (steps[-1]["element"] if steps else ""),
            "focus_cycle_without_modal": cycled and not modal and bool(unreached),
            "unreached_controls": unreached,
            "invisible_focus_targets": [f'{s["element"]} "{s["name"]}"' for s in steps if not s["visible"]][:8],
            "no_focus_indicator": [f'{s["element"]} "{s["name"]}"' for s in steps if s["visible"] and not s["indicator"]][:8],
            "focus_left_modal": [f'{s["element"]} "{s["name"]}"' for s in steps if s.get("modal_open") and not s.get("inside_modal")][:8]}


def slug(url):
    text = re.sub(r"^https?://[^/]+", "", url or "") or "home"
    return (re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-") or "home")[:60]


async def audit_world(m, viewports, keyboard, folder, name=None):
    """Run the audit in a user's current tab and restore its viewport. Returns the text summary."""
    page = m.page
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = name or slug(page.url)
    original = page.viewport_size
    errors_before = len(m.erreurs_page)
    results, keys = [], None
    try:
        for width, height in viewports or [(original["width"], original["height"])]:
            await page.set_viewport_size({"width": width, "height": height})
            await m.calme()
            data = await engine.borne(page.evaluate(AUDIT_JS, TARGET_MIN), engine.DELAI_LECTURE)
            shot = folder / f"{name}-{width}x{height}.jpg"
            try:
                await page.screenshot(path=str(shot), type="jpeg", quality=55, full_page=True, timeout=8000)
                data["screenshot"] = shot.as_posix()
            except Exception:
                data["screenshot"] = None
            results.append(data)
        if original:
            await page.set_viewport_size(original)
            await m.calme()
        if keyboard:
            keys = await keyboard_pass(page)
    finally:
        if original and page.viewport_size != original:
            await page.set_viewport_size(original)
    audit = {"url": page.url, "viewports": results, "keyboard": keys,
             "javascript_errors": m.erreurs_page[errors_before:errors_before + 10], "errors_before_audit": errors_before,
             "note": "Review signals measured in Chromium. Confirm each one; this is not a conformance audit."}
    target = folder / f"{name}.json"
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary(audit, target)


RESPONSIVE = [("horizontal_overflow", "layout-overflow", "horizontal scrolling"),
              ("offscreen_controls", "responsive-controls", "controls outside the screen"),
              ("covered_controls", "responsive-controls", "controls covered by another element"),
              ("unreachable_submit", "layout-overflow", "submit buttons outside the screen"),
              ("clipped_text", "responsive-controls", "clipped text"),
              ("small_targets", "target-size", f"targets under {TARGET_MIN}x{TARGET_MIN} px")]
PAGE_WIDE = [("unnamed_controls", "accessible-names", "controls without an accessible name"),
             ("images_without_alt", "accessible-names", "images without alt"),
             ("low_contrast", "color-contrast", "low-contrast text (estimated)"),
             ("broken_images", "broken-resources", "broken images"),
             ("failed_resources", "broken-resources", "resources answered 4xx/5xx"),
             ("heading_skips", "page-structure", "skipped heading levels"),
             ("duplicate_ids", "page-structure", "duplicate ids"),
             ("positive_tabindex", "page-structure", "positive tabindex"),
             ("aria_hidden_focusable", "keyboard-reachability", "focusable elements inside aria-hidden"),
             ("frames_without_title", "accessible-names", "frames without title"),
             ("vague_links", "accessible-names", "links named only 'click here' or similar"),
             ("mouse_only", "keyboard-reachability", "clickable-looking elements unreachable by keyboard")]


def example(item):
    if isinstance(item, str):
        return item
    if "status" in item:
        return f'{item["status"]} {item["url"]}'
    text = f'{item.get("element")} "{item.get("name", "")}"'
    if item.get("ratio"):
        text += f' {item["ratio"]}:1 < {item["required"]}:1'
    if item.get("covered_by"):
        text += f' under {item["covered_by"]}'
    if item.get("box") and item.get("element", "").split("#")[0] in ("button", "a", "input", "select", "textarea"):
        text += f' {item["box"][2]}x{item["box"][3]}px'
    return text


def summary(audit, target):
    """Compact text for the coordinator: one line per signal, with the check that covers it."""
    lines = [f"Audit of {audit['url']}"]
    for data in audit["viewports"]:
        found = []
        for key, check, label in RESPONSIVE:
            value = data.get(key)
            if key == "horizontal_overflow" and value:
                found.append(f"  [{check}] {label}: page is {value['document_width']} px wide; caused by "
                             + ", ".join(example(x) for x in value["causes"][:3]))
            elif value:
                found.append(f"  [{check}] {len(value)} {label}: " + "; ".join(example(x) for x in value[:3]))
        lines.append(f"Viewport {data['viewport']}: " + ("no layout signal" if not found else f"{len(found)} layout signal(s)")
                     + (f" (screenshot {data['screenshot']})" if data.get("screenshot") else ""))
        lines += found
    lines.append("Page-wide signals:")
    merged = {}
    for key, check, label in PAGE_WIDE:
        items = {json.dumps({k: v for k, v in x.items() if k != "box"} if isinstance(x, dict) else x, sort_keys=True): x
                 for data in audit["viewports"] for x in data.get(key) or []}
        if items:
            merged[key] = list(items.values())
            lines.append(f"  [{check}] {len(items)} {label}: " + "; ".join(example(x) for x in list(items.values())[:3]))
    first = audit["viewports"][0] if audit["viewports"] else {}
    if not first.get("lang"):
        lines.append("  [page-structure] the page does not declare its language (html lang)")
    if not first.get("title"):
        lines.append("  [page-structure] the page has no title")
    if first and first.get("h1_count") == 0:
        lines.append("  [page-structure] no h1 heading")
    if first.get("zoom_blocked"):
        lines.append(f"  [page-structure] browser zoom is limited: viewport meta \"{first['zoom_blocked']}\"")
    if not merged and first.get("lang") and first.get("title"):
        lines.append("  none")
    keys = audit.get("keyboard")
    if keys:
        lines.append(f"Keyboard: {keys['tab_stops']} tab stops")
        for key, check, label in [("unreached_controls", "keyboard-reachability", "visible controls never reached by Tab"),
                                  ("invisible_focus_targets", "keyboard-reachability", "focus lands on invisible elements"),
                                  ("no_focus_indicator", "keyboard-reachability", "no outline or shadow on focus (check visually)"),
                                  ("focus_left_modal", "keyboard-reachability", "focus escapes an open modal")]:
            if keys.get(key):
                lines.append(f"  [{check}] {len(keys[key])} {label}: " + "; ".join(keys[key][:3]))
        if keys.get("focus_stuck"):
            lines.append(f"  [keyboard-reachability] focus is stuck on {keys['focus_stuck']}")
        if keys.get("focus_cycle_without_modal"):
            lines.append("  [keyboard-reachability] focus loops without reaching every control")
    if audit["javascript_errors"]:
        lines.append(f"  [javascript-errors] {len(audit['javascript_errors'])} errors during the audit: {audit['javascript_errors'][0][:160]}")
    if audit.get("errors_before_audit"):
        lines.append(f"  [javascript-errors] {audit['errors_before_audit']} JavaScript errors were recorded for this user before "
                     "the audit; chaosfolk analyze lists them with the action that raised them")
    lines.append(f"Evidence: {target.as_posix()}. Signals are measured, not judged: confirm each before reporting.")
    return "\n".join(lines)


def command_audit(opts):
    """audit: send the audit request for a user's current tab and print the summary."""
    viewports = parse_viewports(opts.viewports)
    reply = engine.envoyer({"cmd": "audit", "h": opts.humain, "viewports": viewports, "clavier": opts.keyboard,
                            "nom": opts.nom}, delai=300)
    print(reply.get("texte", ""))
    return 0 if reply.get("ok") else 1
