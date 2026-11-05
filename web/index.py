"""Vercel entry point: Vercel looks for a FastAPI instance named `app` in index.py."""
from chaosfolk_web.app import create_app

app = create_app()
