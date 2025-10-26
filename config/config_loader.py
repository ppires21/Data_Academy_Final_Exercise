# =========================================
# 📄 File: config/config_loader.py
# Purpose: Load YAML config (dev/prod), substitute ${ENV_VARS}, validate, and expose helpers
# =========================================

import os                      # Used to read ENV to pick dev/prod and to resolve ${VAR} placeholders
import re                      # Used to find and replace ${VAR} patterns inside YAML text
import sys                     # Used to exit early with a clear error message on invalid config
from typing import Dict, Any   # Type hints for better readability and tooling
import yaml                    # Safe YAML parsing (install: PyYAML)

def _substitute_env_placeholders(yaml_text: str) -> str:
    """
    Replace ${VAR} placeholders in YAML text with their environment variable values.
    If an env var is missing, mark it as <MISSING:VAR> to fail validation cleanly.
    """
    # Compile a regex to match ${SOME_NAME} patterns
    pattern = re.compile(r"\$\{([^}^{]+)\}")
    # Define a replacement function that receives the regex match
    def repl(match):
        var_name = match.group(1)                              # Extract VAR name from ${VAR}
        return os.getenv(var_name, f"<MISSING:{var_name}>")    # Return env value or a sentinel
    # Run the substitution across the entire YAML text
    return pattern.sub(repl, yaml_text)

def _load_yaml_file(path: str) -> Dict[str, Any]:
    """
    Read a YAML file from disk, perform ${VAR} substitution, and parse it to a dict.
    """
    if not os.path.exists(path):                               # Ensure the path exists
        print(f"❌ Configuration file not found: {path}")       # Clear error message
        sys.exit(1)                                            # Fail fast (exercise asks for validation)

    with open(path, "r", encoding="utf-8") as f:               # Open the YAML file safely
        raw = f.read()                                         # Read the entire file into a string

    substituted = _substitute_env_placeholders(raw)            # Replace ${VAR} with env values

    try:
        cfg = yaml.safe_load(substituted)                      # Parse YAML text into Python dict
    except yaml.YAMLError as e:                                # Catch YAML syntax errors
        print(f"❌ YAML parsing error in {path}: {e}")          # Print where and why it failed
        sys.exit(1)                                            # Exit to force a fix

    return cfg                                                 # Return the parsed dict

def _validate_config(cfg: Dict[str, Any]) -> None:
    """
    Validate presence of required keys and ensure no <MISSING:...> placeholders remain.
    """
    # Required top-level keys expected by the pipeline
    required_top = ["environment", "debug", "log_level", "db_schema", "aws_region", "s3_bucket", "database"]
    # Determine which top-level keys are absent or empty
    missing_top = [k for k in required_top if k not in cfg or cfg[k] in (None, "")]
    if missing_top:
        print(f"❌ Missing top-level config keys: {', '.join(missing_top)}")  # Tell exactly which keys
        sys.exit(1)                                                          # Exit to prevent undefined behavior

    # Required nested DB keys used to build the connection URL
    required_db = ["host", "port", "name", "user", "password"]
    # Pull DB section once for convenience
    db = cfg.get("database", {})
    # Identify nested DB fields that are missing or still marked <MISSING:...>
    missing_db = [f"database.{k}" for k in required_db
                  if k not in db or db[k] in (None, "") or "MISSING:" in str(db[k])]
    if missing_db:
        print(f"❌ Missing/invalid DB config keys: {', '.join(missing_db)}")  # Pinpoint the exact offenders
        sys.exit(1)                                                          # Exit so the user fixes env/secrets

    # Validate S3 bucket string (must not contain <MISSING:...>)
    if "MISSING:" in str(cfg["s3_bucket"]):                                  # Check final S3 value
        print("❌ S3 bucket not provided (or placeholder unresolved).")       # Clear guidance
        sys.exit(1)                                                          # Exit until fixed

def get_config() -> Dict[str, Any]:
    """
    Public API: pick env from ENV (default 'dev'), load YAML, validate, return dict.
    """
    env = os.getenv("ENV", "dev").lower()                     # Choose 'dev' or 'prod' by ENV variable
    path = f"config/{env}.yaml"                               # Build path like config/dev.yaml
    cfg = _load_yaml_file(path)                               # Load + parse YAML file to dict
    _validate_config(cfg)                                     # Validate presence of required keys
    return cfg                                                # Return configuration dictionary

def build_db_url(cfg: Dict[str, Any]) -> str:
    """
    Helper to build a SQLAlchemy-friendly PostgreSQL URL string from cfg dict.
    """
    db = cfg["database"]                                      # Access nested DB configuration
    user = db["user"]                                         # Username for PostgreSQL
    pwd  = db["password"]                                     # Password for PostgreSQL
    host = db["host"]                                         # Hostname or IP
    port = db["port"]                                         # Port (usually 5432)
    name = db["name"]                                         # Database name/schema container
    # Compose a driver URL usable by SQLAlchemy's create_engine
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"
