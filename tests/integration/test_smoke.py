# tests/integration/test_smoke.py
# ------------------------------------------------------------
# Purpose: Extremely light "smoke" integration test to make sure
#          key modules can be imported and basic configuration
#          helpers exist. This test is SKIPPED by default to avoid
#          accidental DB/S3 usage during CI; opt-in by setting
#          RUN_INTEGRATION=1 in the environment.
# ------------------------------------------------------------

import os
import pytest


# Mark the whole module as "integration" for clarity.
pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION", "0") != "1",
    reason="Set RUN_INTEGRATION=1 to enable integration smoke tests.",
)
def test_imports_and_config_helpers_exist():
    # Import inside the test (lazy) so normal unit runs don't even load modules.
    from src.config.config_loader import get_config, build_db_url

    # Ensure config can be loaded (it can be any environment; we just call it).
    cfg = get_config()
    # Config must be a dict with at least the expected keys.
    assert isinstance(cfg, dict)
    assert "db_schema" in cfg

    # Ensure a DB URL string can be built (we don't connect).
    url = build_db_url(cfg)
    assert isinstance(url, str)
    # A Postgres URL should start with the SQLAlchemy/psycopg2 scheme by default.
    assert "postgresql" in url
