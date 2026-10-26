"""Choose a default report language without guessing in automated runs."""
import sys


def choose_language(language=None):
    if language in ("en", "fr"):
        return language
    if language is not None:
        raise ValueError("Choose --lang en or --lang fr")
    if not sys.stdin.isatty():
        raise ValueError("Choose a report language with --lang en or --lang fr")
    try:
        answer = input("Report language / Langue du rapport [en/fr]: ").strip().lower()
    except EOFError:
        answer = ""
    if answer not in ("en", "fr"):
        raise ValueError("Choose --lang en or --lang fr")
    return answer
