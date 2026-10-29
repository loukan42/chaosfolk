"""QA check catalog: field detection, test data and the checks assigned to users.

The catalog in checks.json holds concrete test values and expected behavior for
common fields (names, phones, postal codes, dates, amounts...) and for security,
accessibility and form behavior. `chaosfolk fields` classifies the controls of a
live page; `draw --checks` hands a seeded share of the matching checks to each
user; `vary` and `compare` replay them without a model.
"""
import argparse
from contextlib import closing
import json
import random
import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

CATALOGUE = Path(__file__).resolve().parent / "checks.json"
SELECTIONS = ("auto", "all", "none")
VALUES_PER_CLASS = {"valid": 4, "invalid": 3}
PERSONAL_KINDS = {"email", "phone", "first-name", "last-name", "full-name", "address", "city", "postal-code",
                  "birth-date", "country"}
NUMERIC_TEXT_KINDS = {"postal-code", "phone", "iban", "company-id", "otp"}
MIN_MAXLENGTH = {"first-name": 35, "last-name": 35, "full-name": 70, "email": 100, "address": 60, "city": 45}
SESSION_COOKIE = re.compile(r"sess|token|auth|jwt|sid|remember", re.I)
SECRET_QUERY = re.compile(r"(?:^|&)(password|passwd|pwd|mdp|token|access_token|session|sessionid|jwt|api_?key|secret|"
                          r"email|e-mail|mail)=", re.I)
LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}

WORDS = {
    "login": r"\b(se connecter|connexion|log ?in|sign ?in|identifiez|s identifier|connectez)\b",
    "signup": r"\b(creer (un|mon|votre) compte|inscription|s inscrire|inscrivez|sign ?up|register|create (an |your )?account)\b",
    "password-reset": r"(mot de passe oublie|reinitialis|forgot|reset (your )?password|password reset|recuperer (votre|mon) mot de passe|nouveau mot de passe)",
    "logged-in": r"\b(deconnexion|se deconnecter|deconnecter|log ?out|sign ?out)\b",
    "delete": r"\b(supprimer|suppression|delete|remove|retirer|effacer)\b",
    "edit": r"\b(modifier|editer|edit|update|mettre a jour|renommer|rename)\b",
}

# Collected in the user's current tab by `chaosfolk fields`. Values typed by the
# user are never read: only structure, labels and attributes.
FIELDS_JS = r"""() => {
  const clip = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const byId = id => id && document.getElementById(id);
  const labelOf = el => {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    if (ids.length) return {text: clip(ids.map(i => (byId(i) || {}).textContent || '').join(' '), 120), source: 'aria-labelledby'};
    if (el.getAttribute('aria-label')) return {text: clip(el.getAttribute('aria-label'), 120), source: 'aria-label'};
    if (el.labels && el.labels.length) return {text: clip([...el.labels].map(l => l.textContent).join(' '), 120), source: 'label'};
    if (el.title) return {text: clip(el.title, 120), source: 'title'};
    if (el.placeholder) return {text: clip(el.placeholder, 120), source: 'placeholder'};
    return {text: '', source: ''};
  };
  const skip = new Set(['hidden', 'submit', 'button', 'reset', 'image', 'checkbox', 'radio']);
  const controls = [...document.querySelectorAll('input,select,textarea,[role=textbox],[role=searchbox],[role=combobox],[contenteditable=true]')]
    .filter(el => !skip.has((el.type || '').toLowerCase()) && (visible(el) || el.type === 'file')).slice(0, 60);
  const fields = controls.map(el => {
    const label = labelOf(el); const form = el.form || el.closest('form');
    const described = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    return {tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(), role: el.getAttribute('role') || '',
      name: clip(el.getAttribute('name'), 80), id: clip(el.id, 80), label: label.text, label_source: label.source,
      placeholder: clip(el.getAttribute('placeholder'), 80), autocomplete: clip(el.getAttribute('autocomplete'), 60).toLowerCase(),
      inputmode: (el.getAttribute('inputmode') || '').toLowerCase(), required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      maxlength: el.maxLength > 0 ? el.maxLength : null, minlength: el.minLength > 0 ? el.minLength : null,
      pattern: clip(el.getAttribute('pattern'), 120), min: el.getAttribute('min'), max: el.getAttribute('max'),
      invalid: el.getAttribute('aria-invalid') === 'true', describedby: described.length,
      form_method: form ? (form.getAttribute('method') || 'get').toLowerCase() : null,
      form_has_action: !!(form && form.getAttribute('action'))};
  });
  const actions = [...document.querySelectorAll('button,a[href],[role=button],[role=link],input[type=submit],input[type=button]')]
    .filter(visible).map(el => clip(el.innerText || el.value || el.getAttribute('aria-label') || el.title, 60)).filter(Boolean).slice(0, 80);
  const headings = [...document.querySelectorAll('h1,h2,h3,legend,[role=heading]')].filter(visible)
    .map(el => clip(el.innerText, 80)).filter(Boolean).slice(0, 20);
  const rows = document.querySelectorAll('table tr, [role=row]').length;
  const pagination = !!document.querySelector('nav[aria-label*="pagin" i], [class*="pagination" i], [aria-label*="page suivante" i], [aria-label*="next page" i]');
  const links = [...new Set([...document.querySelectorAll('a[href]')].map(a => { try { const u = new URL(a.href, location.href);
    return u.origin === location.origin ? u.pathname + u.search : null; } catch (e) { return null; } }).filter(Boolean))].slice(0, 120);
  const cookies = document.cookie ? document.cookie.split(';').map(c => c.split('=')[0].trim()).filter(Boolean).slice(0, 40) : [];
  return {url: location.href, title: clip(document.title, 120), headings, actions, rows, pagination, cookies, fields, links,
          text: clip(document.body ? document.body.innerText : '', 1500)};
}"""


def load():
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


def normalize(text):
    """Lowercase ASCII words: accents removed, camelCase and separators split."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text or ""))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _match_length(keyword, words):
    """Number of words of `keyword` if it appears as whole words in `words`, else 0."""
    keyword = normalize(keyword)
    return len(keyword.split()) if keyword and re.search(rf"(?:^| ){re.escape(keyword)}(?: |$)", words) else 0


def classify(field, catalog=None):
    """Kind of a form control and the evidence used: (kind, reason). Labels win over name and id attributes,
    and the longest matching keyword wins, so "Nom complet" is a full name and "Nom" a last name."""
    kinds = (catalog or load())["kinds"]
    by_id = {kind["id"]: kind for kind in kinds}
    ftype = (field.get("type") or "").lower()
    if ftype == "file":
        return "file", "type=file"
    auto = (field.get("autocomplete") or "").lower().split()
    if ftype == "password":
        wording = normalize(" ".join(str(field.get(k) or "") for k in ("label", "name", "id", "placeholder")))
        new = "new-password" in auto or any(_match_length(k, wording) for k in by_id["new-password"]["keywords"])
        return ("new-password" if new else "password"), "type=password"
    for kind in kinds:
        if auto and auto[-1] in kind.get("autocomplete", []):
            return kind["id"], f"autocomplete={auto[-1]}"
    for sources in (("label", "placeholder"), ("name", "id")):
        words = normalize(" ".join(str(field.get(k) or "") for k in sources))
        best, length = None, 0
        for kind in kinds:
            for keyword in kind["keywords"]:
                found = _match_length(keyword, words)
                if found > length:
                    best, length = kind["id"], found
        if best:
            return best, f"{sources[0]} mentions {by_id[best]['label'].lower()}"
    for kind in kinds:
        if ftype and ftype in kind.get("types", []):
            return kind["id"], f"type={ftype}"
        if field.get("role") and field["role"] in kind.get("roles", []):
            return kind["id"], f"role={field['role']}"
        if field.get("tag") in kind.get("tags", []):
            return kind["id"], f"<{field['tag']}>"
    return "text", "no specific signal"


def features(page, kinds):
    """Page features used to select checks, from wording, controls and detected field kinds."""
    words = normalize(" ".join([page.get("title") or "", page.get("url") or "", *(page.get("headings") or []),
                                *(page.get("actions") or []), page.get("text") or ""]))
    actions = normalize(" ".join(page.get("actions") or []))
    found = set()
    if "password" in kinds and re.search(WORDS["login"], words):
        found.add("login")
    if "new-password" in kinds or ("email" in kinds and re.search(WORDS["signup"], words)):
        found.add("signup")
    if re.search(WORDS["password-reset"], words):
        found.add("password-reset")
    for name in ("logged-in", "delete", "edit"):
        if re.search(WORDS[name], actions):
            found.add(name)
    if any(kind not in ("search",) for kind in kinds):
        found.add("form")
    if "search" in kinds:
        found.add("search")
    if "file" in kinds:
        found.add("upload")
    if (page.get("rows") or 0) > 2 or page.get("pagination"):
        found.add("list")
    return found


def observations(page, fields):
    """Problems visible from structure alone, before any input. Each one names its check."""
    notes = []

    def note(severity, check, message):
        notes.append({"severity": severity, "check": check, "message": message})

    url = urlsplit(page.get("url") or "")
    for field in fields:
        kind, name = field["kind"], field.get("label") or field.get("name") or field.get("id") or field.get("tag")
        ftype = field.get("type") or ""
        if kind in ("password", "new-password"):
            if ftype != "password":
                note("blocking", "password-field-hygiene", f'"{name}" looks like a password field but is not masked (type={ftype or "text"})')
            if field.get("form_method") == "get" and field.get("form_has_action"):
                note("blocking", "password-field-hygiene", f'"{name}" is in a form submitted with GET: the password would appear in the URL')
            if field.get("autocomplete") == "off":
                note("minor", "password-field-hygiene", f'"{name}" disables autocomplete, which blocks password managers')
            if url.scheme == "http" and (url.hostname or "") not in LOOPBACK:
                note("blocking", "password-field-hygiene", f'"{name}" is served over plain HTTP outside localhost')
        if kind in NUMERIC_TEXT_KINDS and ftype == "number":
            note("annoying", "postal-code-formats" if kind == "postal-code" else "phone-formats",
                 f'"{name}" uses type=number: leading zeros, spaces and "+" can be lost, and the wheel changes the value')
        if kind == "phone" and ftype != "tel" and field.get("inputmode") != "tel":
            note("minor", "autocomplete-attributes", f'"{name}" does not open a phone keypad on mobile (no type=tel or inputmode=tel)')
        if kind == "email" and ftype != "email" and field.get("inputmode") != "email":
            note("minor", "autocomplete-attributes", f'"{name}" does not open an email keyboard on mobile (no type=email)')
        if not field.get("label"):
            note("annoying", "field-labels-and-errors", f"a {field.get('tag')} field ({field.get('name') or field.get('id') or 'no name'}) has no accessible name")
        elif field.get("label_source") == "placeholder":
            note("minor", "field-labels-and-errors", f'"{name}" is labelled only by its placeholder, which disappears while typing')
        if kind in PERSONAL_KINDS and not field.get("autocomplete"):
            note("minor", "autocomplete-attributes", f'"{name}" ({kind}) has no autocomplete token')
        limit = MIN_MAXLENGTH.get(kind)
        if limit and field.get("maxlength") and field["maxlength"] < limit:
            note("minor", "first-name-formats" if "name" in kind else "email-formats" if kind == "email" else "address-formats",
                 f'"{name}" accepts only {field["maxlength"]} characters; real {kind.replace("-", " ")}s can be longer')
    leaked = sorted({match.group(1).lower() for match in SECRET_QUERY.finditer(url.query or "")})
    if leaked:
        note("annoying", "secrets-in-url", f"the address carries {', '.join(leaked)} in its query string")
    readable = [name for name in page.get("cookies") or [] if SESSION_COOKIE.search(name)]
    if readable:
        note("annoying", "logout-session", f"session-like cookies are readable by JavaScript (not HttpOnly): {', '.join(readable)}")
    return notes


def analyze_page(page, catalog=None):
    """Classify one page collected by FIELDS_JS: fields with kinds, features, observations and matching checks."""
    catalog = catalog or load()
    fields = []
    for field in page.get("fields") or []:
        kind, reason = classify(field, catalog)
        fields.append(dict(field, kind=kind, reason=reason))
    kinds = {field["kind"] for field in fields}
    found = features(page, kinds)
    notes = observations(page, fields)
    matched = [check["id"] for check in applicable(catalog["checks"], kinds, found, scopes=None)]
    return {"url": page.get("url"), "title": page.get("title"), "links": page.get("links") or [],
            "features": sorted(found), "kinds": sorted(kinds),
            "fields": fields, "observations": notes, "checks": matched}


def applicable(checks, kinds, found, scopes=("safe",)):
    """Checks whose kinds or features were detected; checks without conditions always apply."""
    result = []
    for check in checks:
        if scopes is not None and check["scope"] not in scopes:
            continue
        need = check.get("applies") or {}
        if not need or set(need.get("kinds", [])) & set(kinds) or set(need.get("features", [])) & set(found):
            result.append(check)
    return result


REPEAT = re.compile(r"\{\{repeat:(.+?):(\d+)\}\}")


def expand(value, seed=0, today=None, repeat=True):
    """Expand {{repeat:TEXT:N}}, {{date:+DAYS}} (dd/mm/yyyy) and {{seed}}. Other braces stay literal.
    repeat=False keeps repetitions as macros, so a sheet can describe them instead of printing them."""
    today = today or date.today()
    if repeat:
        value = REPEAT.sub(lambda m: m.group(1) * min(int(m.group(2)), 2000), value)
    value = re.sub(r"\{\{date:([+-]\d+)\}\}", lambda m: (today + timedelta(days=int(m.group(1)))).strftime("%d/%m/%Y"), value)
    return value.replace("{{seed}}", str(seed))


def show(value, limit=60):
    """Readable form of a test value for a sheet: quoted, with repetitions written out as instructions."""
    repeated = REPEAT.fullmatch(value)
    if repeated:
        return f"{json.dumps(repeated.group(1), ensure_ascii=False)} repeated {repeated.group(2)} times"
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else f"{text[:limit - 12]}...\" ({len(value)} characters)"


def known_pages(folder):
    """Kinds and features recorded by `fields --save` in this session, or None when nothing was recorded."""
    saved = Path(folder) / "fields.json"
    if not saved.is_file():
        return None
    from .private_state import read_json
    data = read_json(saved)
    pages = data.get("pages") or []
    return ({kind for page in pages for kind in page.get("kinds", [])},
            {name for page in pages for name in page.get("features", [])})


def select(selection, themes, catalog=None, detected=None, themes_given=True):
    """Checks for a draw. auto: the selected themes (functional and ux when no theme was given), safe scope only,
    restricted to detected pages when `fields --save` ran. all: every check. Otherwise a list of check ids."""
    catalog = catalog or load()
    checks = catalog["checks"]
    if selection == "none":
        return []
    if selection == "all":
        return list(checks)
    if selection == "auto":
        wanted = set(themes) if themes_given else {"functional", "ux"}
        pool = [check for check in checks if check["theme"] in wanted and check["scope"] == "safe"]
        if detected is not None:
            pool = applicable(pool, *detected, scopes=None)
        return pool
    names = [name.strip() for name in selection.split(",") if name.strip()]
    known = {check["id"]: check for check in checks}
    unknown = [name for name in names if name not in known]
    if unknown or not names:
        raise ValueError(f"Unknown checks: {', '.join(unknown) or selection}. Use chaosfolk checks to list them.")
    return [known[name] for name in dict.fromkeys(names)]


def per_user(budget):
    """Checks handed to each user: about one per seven actions, between one and six."""
    return max(1, min(6, budget // 7))


def countries(value, catalog=None):
    """Validate a comma-separated list of country codes; None or "all" keeps every country of the catalog."""
    if value is None or str(value).strip().lower() == "all":
        return None
    known = (catalog or load())["countries"]
    codes = [code.strip().upper() for code in str(value).split(",") if code.strip()]
    unknown = [code for code in codes if code not in known]
    if unknown or not codes:
        raise ValueError(f"Unknown countries: {', '.join(unknown) or value}. Known: {', '.join(known)}")
    return codes


def candidates(check, name, selected=None):
    """(value, country) pairs of one class: universal values, then each selected country's values."""
    items = [(value, None) for value in check.get(name) or []]
    for country, sets in (check.get("by_country") or {}).items():
        if selected is None or country in selected:
            items += [(value, country) for value in sets.get(name) or []]
    return items


def parts(item):
    """(value, country) of a stored test value, written as a string or as {"value", "country"}."""
    return (item["value"], item.get("country")) if isinstance(item, dict) else (item, None)


def assign(seed, pool, count, budget, selected=None):
    """Seeded share of `pool` for each of `count` users, spreading distinct checks across the squad first.
    Each user gets its own sample of test values, mixing universal values and the selected countries.
    Uses its own random stream, so the persona draw is unchanged."""
    if not pool:
        return [[] for _ in range(count)]
    rng = random.Random(f"checks:{seed}")
    order = list(pool)
    rng.shuffle(order)
    size = min(per_user(budget), len(order))
    shares = []
    for user in range(count):
        picked = [order[(user * size + k) % len(order)] for k in range(size)]
        share = []
        for check in picked:
            entry = {"id": check["id"]}
            for name, limit in VALUES_PER_CLASS.items():
                values = candidates(check, name, selected)
                entry[name] = [{"value": expand(v, seed, repeat=False), "country": c} if c else expand(v, seed, repeat=False)
                               for v, c in rng.sample(values, k=min(limit, len(values)))]
            share.append(entry)
        shares.append(share)
    return shares


def sheet_text(assigned, catalog=None):
    """QA CHECKS section of a user sheet."""
    if not assigned:
        return "None assigned. Explore freely."
    known = {check["id"]: check for check in (catalog or load())["checks"]}
    lines = ["Run each check when your journey reaches a matching screen; say so if none appears.",
             "Start a flag about a check with its id in brackets, for example [phone-formats].",
             "A value marked (GB) belongs to that country: choose it in any country selector first."]
    for entry in assigned:
        check = known.get(entry.get("id"))
        if check is None:
            continue
        lines.append(f"- [{check['id']}] {check['title']}. {expand(check['try'])}")
        for name in ("valid", "invalid"):
            if entry.get(name):
                shown = [show(value) + (f" ({country})" if country else "") for value, country in map(parts, entry[name])]
                lines.append(f"  {'Should be accepted' if name == 'valid' else 'Should be refused'}: " + " | ".join(shown))
        lines.append(f"  Expected: {check['expect']}")
    return "\n".join(lines)


def values(check_id, catalog=None, seed=0, selected=None):
    """Every test value of a check for the selected countries, expanded: [(value, "valid"|"invalid", country)]."""
    known = {check["id"]: check for check in (catalog or load())["checks"]}
    if check_id not in known:
        raise ValueError(f"Unknown check: {check_id}. Use chaosfolk checks to list them.")
    check = known[check_id]
    result = [(expand(v, seed), name, country) for name in ("valid", "invalid")
              for v, country in candidates(check, name, selected)]
    if not result:
        raise ValueError(f"{check_id} has no test values; pass --values instead")
    return result


def page_report(analysis, catalog=None):
    """Plain text summary of analyze_page for the coordinator."""
    known = {check["id"]: check for check in (catalog or load())["checks"]}
    lines = [f"Page: {analysis['url']}", f"Features: {', '.join(analysis['features']) or 'none'}", "Fields:"]
    for field in analysis["fields"]:
        attrs = [f"{field['tag']}" + (f"[{field['type']}]" if field.get("type") else "")]
        for key in ("name", "autocomplete", "inputmode", "maxlength", "pattern"):
            if field.get(key):
                attrs.append(f"{key}={field[key]}")
        if field.get("required"):
            attrs.append("required")
        lines.append(f'  "{field.get("label") or "(no name)"}" -> {field["kind"]} ({field["reason"]}); ' + " ".join(attrs))
    if not analysis["fields"]:
        lines.append("  none visible")
    lines.append("Observations from structure (verify before reporting):")
    for note in analysis["observations"]:
        lines.append(f"  [{note['severity']}] {note['message']} -> {note['check']}")
    if not analysis["observations"]:
        lines.append("  none")
    lines.append("Matching checks:")
    for check_id in analysis["checks"]:
        check = known[check_id]
        scope = "" if check["scope"] == "safe" else f" (needs {check['scope']})"
        lines.append(f"  {check_id} [{check['theme']}]{scope}: {check['title']}")
    return "\n".join(lines)


def save_page(folder_file, analysis):
    """Add or replace one analysed page (by URL) in fields.json."""
    from .private_state import read_json, secure, write_json
    path = Path(folder_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize the entire merge across CLI processes as well as threads. Keep
    # this lock file stable; deleting it would let another writer lock a new inode.
    lock = path.with_name("." + path.name + ".lock.sqlite3")
    if lock.is_symlink() or lock.is_junction() or (lock.exists() and lock.stat().st_nlink > 1):
        raise ValueError("Inventory lock must be a private file")
    with closing(sqlite3.connect(lock, timeout=10)) as db, db:
        secure(lock)
        db.execute("BEGIN IMMEDIATE")
        data = read_json(path) if path.is_file() else {"pages": []}
        pages = [page for page in data.get("pages", []) if page.get("url") != analysis["url"]]
        pages.append(analysis)
        # Readers see a complete inventory even while a writer replaces it.
        write_json(path, {"pages": pages})
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk checks", description="List the QA check catalog.")
    parser.add_argument("--theme", help="only checks of this theme")
    parser.add_argument("--kind", help="only checks for this field kind, such as phone or postal-code")
    parser.add_argument("--feature", help="only checks for this page feature, such as password-reset")
    parser.add_argument("--id", help="show one check in full, with all its test values")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    catalog = load()
    checks = catalog["checks"]
    if args.id:
        checks = [check for check in checks if check["id"] == args.id]
        if not checks:
            print(f"Unknown check: {args.id}")
            return 1
    if args.theme:
        checks = [check for check in checks if check["theme"] == args.theme]
    if args.kind:
        checks = [check for check in checks if args.kind in (check.get("applies") or {}).get("kinds", [])]
    if args.feature:
        checks = [check for check in checks if args.feature in (check.get("applies") or {}).get("features", [])]
    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0
    for check in checks:
        scope = "" if check["scope"] == "safe" else f" (needs {check['scope']})"
        wcag = f" WCAG {', '.join(check['wcag'])}" if check.get("wcag") else ""
        print(f"{check['id']} [{check['theme']}]{scope}{wcag}: {check['title']}")
        if args.id:
            print(f"  Try: {expand(check['try'])}")
            for name in ("valid", "invalid"):
                items = candidates(check, name)
                if items:
                    print(f"  {name}: " + " | ".join(show(expand(v), 200) + (f" ({c})" if c else "") for v, c in items))
            print(f"  Expected: {check['expect']}")
            print(f"  Proof: {check['proof']}")
    if not args.id:
        print(f"{len(checks)} checks. Field kinds: {', '.join(kind['id'] for kind in catalog['kinds'])}.")
        print("Use --id NAME for test values. Run chaosfolk fields <user> on a live page to see which checks apply.")
    return 0
