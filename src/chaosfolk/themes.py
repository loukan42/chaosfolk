"""Selectable exploration themes and the evidence each can produce."""
import argparse
import json


THEMES = {
    "functional": {"label": "Functional journeys", "focus": "Check the expected result, persistence after reload, validation, cancellation and recovery across the supplied goals.", "method": "agent exploration and replay assertions"},
    "ux": {"label": "Usability", "focus": "Look for confusing labels, unclear feedback, discoverability and unexpected interaction outcomes.", "method": "simulated user exploration"},
    "accessibility": {"label": "Accessibility signals", "focus": "Try keyboard navigation, focus order and accessible names; flag barriers and verify each observation. Do not claim conformance.", "method": "agent keyboard exploration and optional basic probe signals"},
    "resilience": {"label": "Resilience", "focus": "Observe whether inputs and state survive authorized fault conditions; compare treatment and control replays.", "method": "authorized fault injection and control replay"},
    "security": {"label": "Security observations", "focus": "Observe exposed secrets or unsafe UI behavior only within the authorized test account and scope. Do not attempt unauthorized access or destructive payloads.", "method": "passive UI review and optional header observations; dedicated security testing remains separate"},
    "performance": {"label": "Performance signals", "focus": "Observe delays and responsiveness during journeys. Do not infer capacity from one user.", "method": "agent observations and optional bounded local concurrency probe"},
    "compatibility": {"label": "Web compatibility", "focus": "Check the assigned viewport and input mode for clipped content or blocked controls; record which device and browser were tested.", "method": "Chromium contexts with desktop, tablet and mobile viewport emulation"},
}


def resolve(value):
    """Validate an explicit comma-separated selection. Preserve canonical order."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Choose one or more themes")
    selected = [item.strip().lower() for item in value.split(",")]
    if any(not item for item in selected):
        raise ValueError("Theme names cannot be empty")
    if selected == ["all"]:
        return list(THEMES)
    unknown = set(selected) - set(THEMES)
    if unknown:
        raise ValueError(f"Unknown themes: {', '.join(sorted(unknown))}. Use chaosfolk themes to list them.")
    return [name for name in THEMES if name in selected]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk themes", description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(THEMES, ensure_ascii=False, indent=2))
    else:
        for name, theme in THEMES.items():
            print(f"{name}: {theme['label']} — {theme['method']}")
        print("Select one or more with draw --themes, or use --themes all. Selection is not proof of coverage.")
    return 0
