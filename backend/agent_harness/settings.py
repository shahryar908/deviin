"""Runtime configuration for agent_harness, loaded from .env."""

import os

from dotenv import load_dotenv

load_dotenv()

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.environ.get("GITHUB_REDIRECT_URI", "http://localhost:8787/github/callback")
GITHUB_TOKEN_ENCRYPTION_KEY = os.environ.get("GITHUB_TOKEN_ENCRYPTION_KEY", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:4000")
