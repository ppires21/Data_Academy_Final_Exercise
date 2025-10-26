# =========================================
# 📄 File: src/quality/quality_checks.py
# Purpose: Data Quality Framework (Iteration 3, Task 2)
# - Define expectation suites (custom)
# - Create data quality report (markdown)
# - Set up alerting (fail on critical issues)
# - Document data lineage in the report
# =========================================

import os  # Used for paths
import logging  # Used for logging
from datetime import datetime  # Used to timestamp reports
from typing import Dict, List  # Type hints for clarity
import pandas as pd  # Data manipulation for checks
from sqlalchemy import create_engine  # To fetch data from DB for checks
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from config.config_loader import get_config, build_db_url  # Use YAML config

# --- Setup logging ---
cfg = get_config()  # Load config (dev/prod)
logging.basicConfig(
    level=cfg["log_level"],  # Configure logging level from YAML
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)  # Module logger

REPORT_DIR = "logs"  # Place reports under logs/
REPORT_PATH = os.path.join(
    REPORT_DIR, "quality_report.md"
)  # Output markdown report path
ENGINE = create_engine(
    build_db_url(cfg), future=True
)  # DB engine for reading tables to validate


def _expect_not_null(df: pd.DataFrame, cols: List[str]) -> List[str]:
    """
    Expectation: specified columns must have no nulls.
    Returns list of error messages (empty if all good).
    """
    errs = []  # Collect any violations here
    for c in cols:  # Check each requested column
        if df[c].isna().any():  # If any null found in column
            errs.append(f"Nulls found in column '{c}'")  # Record violation message
    return errs  # Return list of errors (if any)


def _expect_positive(df: pd.DataFrame, cols: List[str]) -> List[str]:
    """
    Expectation: numeric columns must be > 0.
    """
    errs = []  # Initialize error list
    for c in cols:
        if (df[c] <= 0).any():  # If any non-positive value found
            errs.append(f"Non-positive values in column '{c}'")  # Add message
    return errs  # Return violations


def _expect_valid_email(df: pd.DataFrame, col: str) -> List[str]:
    """
    Expectation: email column must contain '@' (simple check adequate for exercise scope).
    """
    errs = []  # Errors collection
    bad = ~df[col].astype(str).str.contains("@")  # Rows without '@'
    if bad.any():  # If any invalid emails present
        errs.append(f"Invalid email addresses in '{col}'")  # Add message
    return errs  # Return list (possibly empty)


def run_quality_checks() -> None:
    """
    Runs expectation suites on source tables and writes a markdown report:
      - clientes: no nulls in id, email; email contains '@'
      - produtos: positive price
      - transacoes: non-null foreign keys, valid timestamp
      - transacao_itens: positive quantity and price
    Also logs a simple lineage section and raises if critical issues exist (alerting).
    """
    os.makedirs(REPORT_DIR, exist_ok=True)  # Ensure logs/ exists
    ts = datetime.utcnow().strftime(
        "%Y-%m-%d %H:%M:%SZ"
    )  # Current UTC timestamp for report header

    # Read data to validate
    schema = cfg["db_schema"]  # Source normalized schema

    # CHANGED: use read_sql_table(..., schema=schema) to avoid f-string SQL and satisfy Bandit B608
    clientes = pd.read_sql_table(
        "clientes", ENGINE, schema=schema
    )  # Load customers (safe, no raw SQL)
    produtos = pd.read_sql_table(
        "produtos", ENGINE, schema=schema
    )  # Load products (safe)
    transacoes = pd.read_sql_table(
        "transacoes", ENGINE, schema=schema
    )  # Load transactions (safe)
    itens = pd.read_sql_table(
        "transacao_itens", ENGINE, schema=schema
    )  # Load items (safe)

    # Run expectation suites
    errors: Dict[str, List[str]] = {}  # Map table -> list of errors

    # clientes expectations
    clients_errs = []
    clients_errs += _expect_not_null(clientes, ["id", "email"])  # id & email not null
    clients_errs += _expect_valid_email(clientes, "email")  # email contains '@'
    errors["clientes"] = clients_errs  # Record errors

    # produtos expectations
    prod_errs = []
    prod_errs += _expect_not_null(produtos, ["id", "preco"])  # id & preco not null
    prod_errs += _expect_positive(produtos, ["preco"])  # preco > 0
    errors["produtos"] = prod_errs  # Record errors

    # transacoes expectations
    trx_errs = []
    trx_errs += _expect_not_null(
        transacoes, ["id", "id_cliente", "data_hora"]
    )  # keys & timestamp not null
    # Simple parse check: if parsing yields NaT, it's invalid (vectorized)
    if (
        pd.to_datetime(transacoes["data_hora"], errors="coerce").isna().any()
    ):  # Any invalid timestamp?
        trx_errs.append("Invalid timestamps in 'data_hora'")  # Record issue
    errors["transacoes"] = trx_errs  # Record errors

    # transacao_itens expectations
    item_errs = []
    item_errs += _expect_not_null(
        itens, ["id", "id_transacao", "id_produto", "quantidade", "preco_unitario"]
    )  # not nulls
    item_errs += _expect_positive(
        itens, ["quantidade", "preco_unitario"]
    )  # quantities and price > 0
    errors["transacao_itens"] = item_errs  # Record errors

    # Summarize results
    total_issues = sum(
        len(v) for v in errors.values()
    )  # Total count of issues across tables

    # Write markdown report including lineage notes
    with open(REPORT_PATH, "w", encoding="utf-8") as f:  # Open report file
        f.write(f"# Data Quality Report\n\n")  # Title
        f.write(f"- Generated at: {ts}\n")  # Timestamp
        f.write(f"- Environment: **{cfg['environment']}**\n\n")  # Show environment
        f.write("## Lineage (simplified)\n")  # Lineage header
        f.write(
            "- Source: PostgreSQL normalized schema (Iteration 2 load)\n"
        )  # Source lineage
        f.write(
            f"- Schema: `{schema}` → Validated tables: clientes, produtos, transacoes, transacao_itens\n"
        )
        f.write(
            "- Downstream targets: warehouse schema tables (Iteration 3)\n\n"
        )  # Downstream lineage
        f.write("## Expectations Summary\n\n")  # Summary header
        for table, errs in errors.items():  # For each table
            f.write(f"### {table}\n")  # Table header
            if not errs:  # If no errors
                f.write("- ✅ No issues found\n\n")  # Mark as OK
            else:  # If issues present
                for e in errs:  # List each issue
                    f.write(f"- ❌ {e}\n")
                f.write("\n")
        f.write(f"**Total issues:** {total_issues}\n")  # Overall count

    # Alerting: if critical issues found, log error and raise to make CI/CD or orchestration fail fast
    if total_issues > 0:  # If there are any issues
        log.error(
            f"Data quality failed with {total_issues} issues. See {REPORT_PATH}"
        )  # Log location
        raise SystemExit(1)  # Non-zero exit to trigger alerting
    else:
        log.info(f"Data quality passed. Report at {REPORT_PATH}")  # Success log


if __name__ == "__main__":  # Entry point for running checks directly
    run_quality_checks()  # Execute quality validations and report creation
