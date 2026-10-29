"""Provide minimal environment so settings load without a live database or IdP."""

import os

os.environ.setdefault("CHUSKY_DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("CHUSKY_JWT_JWKS_URL", "http://localhost/jwks")
os.environ.setdefault("CHUSKY_JWT_ISSUER", "http://localhost/issuer")
os.environ.setdefault("CHUSKY_LOAD_MANIFESTS_ON_START", "false")
