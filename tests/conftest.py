# tests/conftest.py
# ------------------------------------------------------------
# Purpose: Provide a safe, dummy config for tests so importing
# modules that call get_config()/build_db_url on import does not
# crash CI or require real secrets.
# ------------------------------------------------------------

import sys
import types

# Minimal configuration that satisfies your modules during import.
_DUMMY_CFG = {
    "environment": "test",               # used in logs/reports
    "log_level": "WARNING",              # keep test output quiet
    "db_schema": "public",               # used by loaders/quality code
    "s3_bucket": "dummy-bucket",         # used to build S3 client (not called)
    "aws_region": "eu-west-1",           # boto3 client is fine without creds
    "database": {                        # present so validators don’t complain
        "user": "u",
        "password": "p",
        "host": "localhost",
        "port": 5432,
        "name": "db",
    },
}

def get_config():
    """
    Return a dummy config dict that has all keys your app expects.
    This prevents config validation from failing during import time.
    """
    return _DUMMY_CFG

def build_db_url(cfg=None):
    """
    Return a lightweight, local SQLAlchemy URL so create_engine() succeeds
    during imports without requiring Postgres.
    """
    return "sqlite:///:memory:"

# Create a dummy module object exposing get_config/build_db_url.
_config_loader_stub = types.SimpleNamespace(get_config=get_config, build_db_url=build_db_url)

# Inject it so `from config.config_loader import ...` resolves to this stub.
sys.modules["config.config_loader"] = _config_loader_stub
