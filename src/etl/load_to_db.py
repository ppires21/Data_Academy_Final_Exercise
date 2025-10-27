#!/usr/bin/env python3
"""
Data Loading Pipeline
---------------------
 - Loads generated CSV data into PostgreSQL (local or RDS)
 - Implements UPSERT logic to handle duplicates
 - Uses audit table (with timestamps) for data versioning visibility
"""

import os
import sys
import logging
from datetime import datetime, timezone
from sqlalchemy import create_engine, text  # keep text for DDL
import pandas as pd

# NEW imports for safe SQL construction
from sqlalchemy import MetaData, Table, select, cast
from sqlalchemy.types import Date, DateTime
from sqlalchemy.dialects.postgresql import insert as pg_insert  # PostgreSQL UPSERT

# 🔗 NEW: pull env-aware config (dev/prod) so schema/DB/bucket stay consistent
from config.config_loader import get_config, build_db_url

# Load YAML (ENV=dev|prod) once
cfg = get_config()

# -----------------------
# Logging setup
# -----------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# -----------------------
# Configuration
# -----------------------
DATA_DIR = "data/raw"
TABLES = {
    "clientes": "clientes.csv",
    "produtos": "produtos.csv",
    "transacoes": "transacoes.csv",
    "transacao_itens": "transacao_itens.csv",
}
SCHEMA = cfg["db_schema"]


# -----------------------
# Database helpers
# -----------------------
def get_engine():
    url = build_db_url(cfg)
    #mask actual password from logs using cfg
    pwd = str(cfg["database"]["password"])
    safe_url = url.replace(pwd, "***")
    log.info(f"Connecting to: {safe_url}")
    return create_engine(url, future=True)


def ensure_audit_table(engine):
    """Create audit table for tracking loads if it doesn’t exist (DDL left as text)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.audit_loads (
            id SERIAL PRIMARY KEY,
            tabela TEXT NOT NULL,
            ficheiro TEXT NOT NULL,
            data_inicio TIMESTAMPTZ NOT NULL,
            data_fim TIMESTAMPTZ NOT NULL,
            linhas_carregadas INT NOT NULL,
            sucesso BOOLEAN NOT NULL,
            erro TEXT
        );
        """
            )
        )
    log.info("Ensured audit_loads table exists.")


# -----------------------
# Data preparation
# -----------------------
def read_csv(filename: str) -> pd.DataFrame:
    """Read CSV file from data/raw."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    log.info(f"Loaded {len(df)} rows from {filename}")
    return df


def prepare_dataframe(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only columns that exist in the target table (normalized schema)
    and parse types for date/timestamp columns.
    """
    cols_map = {
        "clientes": ["id", "nome", "email", "data_registo", "distrito"],
        "produtos": ["id", "nome", "categoria", "preco", "fornecedor"],
        "transacoes": ["id", "id_cliente", "data_hora", "metodo_pagamento"],
        "transacao_itens": [
            "id",
            "id_transacao",
            "id_produto",
            "quantidade",
            "preco_unitario",
        ],
    }
    cols = cols_map[table]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{table}: missing required columns in CSV: {missing}")

    out = df[cols].copy()

    # parse to correct types (DB casts are also applied during INSERT)
    if table == "clientes":
        out["data_registo"] = pd.to_datetime(
            out["data_registo"], errors="coerce"
        ).dt.date
    elif table == "transacoes":
        out["data_hora"] = pd.to_datetime(out["data_hora"], errors="coerce")

    return out


# -----------------------
# Data loading (UPSERT)
# -----------------------
def upsert_dataframe(df: pd.DataFrame, table: str, engine):
    """
    Upsert DataFrame into PostgreSQL target table using SQLAlchemy Core.

    Key points:
      - Creates a staging table and bulk-loads the CSV into it.
      - INSERT ... ON CONFLICT DO UPDATE into the real table.
      - Explicitly sets version_timestamp = NOW() on both INSERT and UPDATE
        to avoid NULLs even if the DB default is missing.
      - Temporarily disables FK checks to simplify load ordering.

    Returns:
      Number of rows processed from the DataFrame.
    """
    if df.empty:
        log.warning(f"Skipping {table}: no data.")
        return 0

    tmp_table = f"_tmp_{table}"

    with engine.begin() as conn:
        conn.execute(text("SET session_replication_role = replica"))

        conn.execute(text(f"DROP TABLE IF EXISTS {SCHEMA}.{tmp_table}"))
        df.head(0).to_sql(tmp_table, conn, schema=SCHEMA, index=False, if_exists="replace")
        df.to_sql(tmp_table, conn, schema=SCHEMA, index=False, if_exists="append", method="multi")

        md = MetaData()
        target = Table(table, md, schema=SCHEMA, autoload_with=conn)
        staging = Table(tmp_table, md, schema=SCHEMA, autoload_with=conn)

        # -- if table == "clientes":
        # --     conflict_key = [target.c.email]
        # ++ Always upsert by primary key id (including clientes) to avoid PK conflicts
        conflict_key = [target.c.id]

        pk = "id"

        insert_cols = list(df.columns)
        selectable_cols = []
        for c in df.columns:
            col_expr = getattr(staging.c, c)
            if table == "clientes" and c == "data_registo":
                col_expr = cast(col_expr, Date)
            elif table == "transacoes" and c == "data_hora":
                col_expr = cast(col_expr, DateTime)
            selectable_cols.append(col_expr)

        insert_cols.append("version_timestamp")
        selectable_cols.append(text("NOW()"))

        insert_stmt = pg_insert(target).from_select(insert_cols, select(*selectable_cols))

        update_map = {c: getattr(insert_stmt.excluded, c) for c in df.columns if c != pk}
        update_map["version_timestamp"] = text("NOW()")

        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=conflict_key,
            set_=update_map,
        )

        conn.execute(upsert_stmt)

        conn.execute(text("SET session_replication_role = DEFAULT"))
        conn.execute(text(f"DROP TABLE IF EXISTS {SCHEMA}.{tmp_table}"))

        log.info(f"Upserted {len(df)} rows into {table}")

    return len(df)




# -----------------------
# Audit logging
# -----------------------
def audit(engine, table, file, start, end, rows, success=True, error=None):
    """Record audit trail for every load using SQLAlchemy Core insert()."""
    with engine.begin() as conn:
        md = MetaData()
        audit_tbl = Table("audit_loads", md, schema=SCHEMA, autoload_with=conn)
        ins = audit_tbl.insert().values(
            tabela=table,
            ficheiro=file,
            data_inicio=start,
            data_fim=end,
            linhas_carregadas=rows,
            sucesso=success,
            erro=error,
        )
        conn.execute(ins)


# -----------------------
# Main ETL logic
# -----------------------
def main():
    engine = get_engine()
    ensure_audit_table(engine)

    for table, filename in TABLES.items():
        start = datetime.now(timezone.utc)
        try:
            raw = read_csv(filename)
            core = prepare_dataframe(table, raw)
            count = upsert_dataframe(core, table, engine)
            audit(
                engine,
                table,
                filename,
                start,
                datetime.now(timezone.utc),
                count,
                success=True,
            )
        except Exception as e:
            logging.exception(f"Failed to load {table}: {e}")
            audit(
                engine,
                table,
                filename,
                start,
                datetime.now(timezone.utc),
                0,
                success=False,
                error=str(e),
            )

    log.info("✅ Data loading pipeline completed.")


if __name__ == "__main__":
    sys.exit(main())
