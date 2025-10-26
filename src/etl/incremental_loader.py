# =========================================
# File: src/etl/incremental_loader.py
# Purpose: Incremental Processing (Iteration 3, Task 3)
# - Implement CDC (Change Data Capture) logic on transacoes
# - Process only new/modified records
# - Maintain processing checkpoints
# - Handle late-arriving data (overlap window)
# =========================================

import os
import sys

sys.path.append(
    os.path.join(os.path.dirname(__file__), "../..")
)  # ✅ Add project root early

import json
import logging
from datetime import datetime, timedelta
import pandas as pd

# 🔁 NEW: import SQLAlchemy Core objects to build queries safely (no f-strings in SQL)
from sqlalchemy import create_engine, text, MetaData, Table, select, bindparam

from config.config_loader import (
    get_config,
    build_db_url,
)  # ✅ Now it can find this module


# --- Setup logging ---
cfg = get_config()  # Load environment-specific config
logging.basicConfig(
    level=cfg["log_level"],  # Configure log level (DEBUG/INFO)
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)  # Module logger

ENGINE = create_engine(build_db_url(cfg), future=True)  # DB engine for queries/loads
SCHEMA = cfg["db_schema"]  # Source schema for transacoes
CHECKPOINT_DIR = "checkpoints"  # Folder to store state
CHECKPOINT_FILE = os.path.join(
    CHECKPOINT_DIR, "transacoes_checkpoint.json"
)  # File for last processed time
LATE_WINDOW_DAYS = 2  # Overlap days to catch late-arriving events


def _load_checkpoint() -> datetime:
    """
    Load the last processed timestamp from checkpoint file.
    If not found, default to epoch (process all).
    """
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)  # Ensure checkpoint folder exists
    if not os.path.exists(CHECKPOINT_FILE):  # If no checkpoint yet
        return datetime(1970, 1, 1)  # Start from epoch
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:  # Read JSON
        data = json.load(f)  # Parse JSON
    return datetime.fromisoformat(data["last_processed"])  # Return datetime object


def _save_checkpoint(ts: datetime) -> None:
    """
    Save the last processed timestamp to checkpoint file in ISO format.
    """
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:  # Open file for writing
        json.dump({"last_processed": ts.isoformat()}, f)  # Write ISO timestamp


def _fetch_increment(engine, since: datetime) -> pd.DataFrame:
    """
    Fetch only new/modified transacoes since (since - overlap window).
    Overlap window handles late-arriving data by re-reading a small recent period.
    """
    window_start = since - timedelta(days=LATE_WINDOW_DAYS)  # Compute overlap start

    # 🔁 CHANGED: build a safe SQLAlchemy Select instead of an f-string.
    # - MetaData() holds table definitions for reflection
    # - Table('transacoes', ..., autoload_with=engine) reflects columns from DB
    # - select(...) creates SELECT id, id_cliente, data_hora, metodo_pagamento, version_timestamp
    # - bindparam('window_start') creates a named parameter for the WHERE clause
    # - No schema/table names are interpolated into a string; Bandit B608 is satisfied.
    meta = MetaData()
    transacoes = Table("transacoes", meta, schema=SCHEMA, autoload_with=engine)
    stmt = (
        select(
            transacoes.c.id,
            transacoes.c.id_cliente,
            transacoes.c.data_hora,
            transacoes.c.metodo_pagamento,
            transacoes.c.version_timestamp,
        )
        .where(transacoes.c.data_hora >= bindparam("window_start"))
        .order_by(transacoes.c.data_hora.asc())
    )

    # pandas can execute a SQLAlchemy Select; pass the parameter safely
    df = pd.read_sql(stmt, engine, params={"window_start": window_start})
    return df  # Return increment batch


def _merge_into_dw(engine, df: pd.DataFrame) -> None:
    """
    Example upsert into a warehouse incremental fact table:
      - Deduplicate by id (latest version_timestamp wins)
      - Replace matching ids (idempotent upsert).
    """
    if df.empty:  # If nothing to process
        log.info("No incremental records to process.")  # Log and return
        return

    # Prepare target table in warehouse schema
    with engine.begin() as conn:  # Transaction block
        conn.execute(
            text("CREATE SCHEMA IF NOT EXISTS warehouse")
        )  # Ensure warehouse schema
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS warehouse.fact_transactions_incremental (
                id                INT PRIMARY KEY,
                id_cliente        INT NOT NULL,
                data_hora         TIMESTAMPTZ NOT NULL,
                metodo_pagamento  TEXT NOT NULL,
                version_timestamp TIMESTAMPTZ NOT NULL
            )
        """
            )
        )  # Target incremental fact

    # Deduplicate by id using the latest version_timestamp
    df = df.sort_values(["id", "version_timestamp"]).drop_duplicates(
        subset=["id"], keep="last"
    )
    # Keep the newest version per id

    # Load increment to a temp table
    with engine.begin() as conn:  # Transaction block for upsert
        df.head(0).to_sql(
            "_tmp_increment", conn, schema="warehouse", if_exists="replace", index=False
        )  # Create temp
        df.to_sql(
            "_tmp_increment", conn, schema="warehouse", if_exists="append", index=False
        )  # Fill temp

        # Upsert using ON CONFLICT (id)
        conn.execute(
            text(
                """
            INSERT INTO warehouse.fact_transactions_incremental (id, id_cliente, data_hora, metodo_pagamento, version_timestamp)
            SELECT id, id_cliente, data_hora, metodo_pagamento, version_timestamp
            FROM warehouse._tmp_increment
            ON CONFLICT (id) DO UPDATE
              SET id_cliente = EXCLUDED.id_cliente,
                  data_hora = EXCLUDED.data_hora,
                  metodo_pagamento = EXCLUDED.metodo_pagamento,
                  version_timestamp = EXCLUDED.version_timestamp
        """
            )
        )  # Upsert new/updated rows
        conn.execute(text("DROP TABLE warehouse._tmp_increment"))  # Clean up temp table

    log.info(
        f"Incremental upsert completed: {len(df)} rows processed."
    )  # Log processed count


def run():
    """
    Main incremental workflow:
      1) Load checkpoint
      2) Query only new/changed rows (with late-arrival overlap)
      3) Merge into DW fact (idempotent upsert)
      4) Advance checkpoint to max(data_hora) processed
    """
    last = _load_checkpoint()  # Load last processed timestamp
    log.info(f"Last checkpoint: {last.isoformat()}")  # Log checkpoint

    incr = _fetch_increment(ENGINE, since=last)  # Fetch only recent/changed rows
    _merge_into_dw(ENGINE, incr)  # Merge increment into DW table

    if not incr.empty:  # If any rows processed
        new_checkpoint = (
            pd.to_datetime(incr["data_hora"]).max().to_pydatetime()
        )  # Compute latest data_hora
        _save_checkpoint(new_checkpoint)  # Save checkpoint forward
        log.info(
            f"Checkpoint advanced to: {new_checkpoint.isoformat()}"
        )  # Log advancement
    else:
        log.info("No new rows; checkpoint unchanged.")  # No advancement if no data


if __name__ == "__main__":  # Standard entry point
    run()  # Execute the incremental loader
