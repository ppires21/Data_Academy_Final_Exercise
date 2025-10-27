# =========================================
# 📄 File: src/etl/transform_pipeline.py
# Purpose: Advanced ETL Pipeline (Iteration 3, Task 1)
# - Extract from CSV, Database (RDS), and S3
# - Transform: CLV, recommendation features, daily/weekly/monthly metrics, SCD Type 2
# - Load into a warehouse schema (star/snowflake)
# =========================================

import os  # Used for path handling and environment access
import io  # Used to read S3 object byte streams into pandas
import time  # Used to measure processing time for performance metrics
import logging  # Used for structured logging of pipeline stages
from datetime import datetime, timezone  # timezone-aware UTC
from typing import Tuple, Dict  # Type hints for readability
import pandas as pd  # Core data manipulation library
from sqlalchemy import (
    create_engine,
    text,
    MetaData,  # 🔁 NEW: for table reflection in updates
    Table,  # 🔁 NEW: reflected table for safe UPDATE
    update,  # 🔁 NEW: SQLAlchemy Core UPDATE
)
import boto3  # AWS SDK to extract CSVs from S3
from botocore.exceptions import BotoCoreError, ClientError  # S3 error handling
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))


# --- Config loader (from Iteration 2) ---
from config.config_loader import (
    get_config,
    build_db_url,
)  # Load YAML config and build DB URL


# -----------------------
# Setup
# -----------------------

cfg = get_config()  # Load configuration from config/{ENV}.yaml
logging.basicConfig(  # Configure logging based on config
    level=cfg["log_level"],  # DEBUG in dev, INFO in prod
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)  # Module-level logger

DB_URL = build_db_url(cfg)  # Build SQLAlchemy DB URL using config
ENGINE = create_engine(
    DB_URL, future=True
)  # Create a DB engine (used for DB extract + warehouse load)
WAREHOUSE_SCHEMA = (
    "warehouse"  # Name of data-warehouse schema for outputs (star/snowflake)
)
RAW_DIR = "data/raw"  # Local CSV directory for the CSV source
S3_BUCKET = cfg["s3_bucket"]  # Bucket name for S3 source
AWS_REGION = cfg["aws_region"]  # Region for making the S3 client
S3 = boto3.client("s3", region_name=AWS_REGION)  # S3 client configured with region


# -----------------------
# Select fact source - dev vs prod
# -----------------------


def select_fact_source(
    env: str,
    csv_data: Dict[str, pd.DataFrame],
    db_data: Dict[str, pd.DataFrame],
    s3_data: Dict[str, pd.DataFrame] | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Decide de onde vêm os DataFrames base para montar a fact, consoante o ambiente.

    Regras:
      - DEV  -> usar CSV locais (data/raw/*) para facilitar o desenvolvimento.
      - PROD -> usar DB (RDS) como fonte "verdadeira".
      - S3   -> opcional; se fornecido, pode ser usado em DEV (quando não há CSV)
               ou em PROD para validação (não obrigatório para a fact).

    Retorna: (transacoes_df, itens_df, produtos_df)
    """
    # Normaliza o nome do ambiente para evitar surpresas (e.g., "Prod" vs "prod")
    env = (env or "").lower()

    # DEV: preferir CSV (mais rápido e sem dependência de DB)
    if env == "dev":
        # Valida que temos as peças necessárias nos CSV
        if not all(
            k in csv_data for k in ("transacoes", "transacao_itens", "produtos")
        ):
            # Se faltar algo nos CSV, tenta cair para S3 (se existir) antes de falhar
            if s3_data and all(k in s3_data for k in ("transacoes", "produtos")):
                # Em S3 não temos "transacao_itens" no teu código — avisa e falha explicitamente
                raise RuntimeError(
                    "DEV: CSV em falta e S3 não contém 'transacao_itens'. Adiciona CSV local de itens."
                )
            raise RuntimeError(
                "DEV: Faltam CSVs necessários (transacoes, transacao_itens, produtos) em data/raw."
            )
        return csv_data["transacoes"], csv_data["transacao_itens"], csv_data["produtos"]

    # PROD: usar DB (RDS) como fonte principal
    # Garante que as três tabelas existem

    if not all(k in db_data for k in ("transacoes", "transacao_itens", "produtos")):
        raise RuntimeError(
            "PROD: Tabelas necessárias em DB em falta (transacoes, transacao_itens, produtos)."
        )

    return db_data["transacoes"], db_data["transacao_itens"], db_data["produtos"]


# -----------------------
# Extract
# -----------------------


def extract_from_csv() -> Dict[str, pd.DataFrame]:
    """
    Extract raw datasets from local CSV files (Iteration 3 requires CSV source).
    Expects files in data/raw: clientes.csv, produtos.csv, transacoes.csv, transacao_itens.csv
    Returns a dict of DataFrames keyed by logical table name.
    """
    log.info("Extracting from CSV (local files)…")  # Log extraction start

    # Build file paths for each expected CSV
    clientes_path = os.path.join(RAW_DIR, "clientes.csv")  # Path to customers CSV
    produtos_path = os.path.join(RAW_DIR, "produtos.csv")  # Path to products CSV
    transacoes_path = os.path.join(
        RAW_DIR, "transacoes.csv"
    )  # Path to transactions CSV
    itens_path = os.path.join(
        RAW_DIR, "transacao_itens.csv"
    )  # Path to transaction items CSV

    # Read CSVs into DataFrames
    clientes = pd.read_csv(clientes_path)  # Load customers CSV
    produtos = pd.read_csv(produtos_path)  # Load products CSV
    transacoes = pd.read_csv(transacoes_path)  # Load transactions CSV
    itens = pd.read_csv(itens_path)  # Load transaction items CSV

    # Return dictionary keyed by entity
    return {
        "clientes": clientes,  # Customers DF
        "produtos": produtos,  # Products DF
        "transacoes": transacoes,  # Transactions DF
        "transacao_itens": itens,  # Transaction items DF
    }


def extract_from_db(engine) -> Dict[str, pd.DataFrame]:
    """
    Extract cleaned/structured data from PostgreSQL RDS (Iteration 3 requires DB source).
    Reads the same four entities created in Iteration 2.
    """
    log.info("Extracting from Database (RDS)…")  # Log extraction start

    # 🔁 CHANGED: avoid f-string SQL by using read_sql_table with schema=
    schema = cfg["db_schema"]  # Source normalized schema
    clientes = pd.read_sql_table("clientes", engine, schema=schema)  # customers
    produtos = pd.read_sql_table("produtos", engine, schema=schema)  # products
    transacoes = pd.read_sql_table("transacoes", engine, schema=schema)  # transactions
    itens = pd.read_sql_table("transacao_itens", engine, schema=schema)  # items

    # Return dictionary keyed by entity
    return {
        "clientes": clientes,  # Customers DF
        "produtos": produtos,  # Products DF
        "transacoes": transacoes,  # Transactions DF
        "transacao_itens": itens,  # Transaction items DF
    }


def _read_s3_csv(key: str) -> pd.DataFrame:
    """
    Helper to read a CSV object from S3 into a pandas DataFrame.
    The 'key' must point to an object in the configured bucket.
    """
    obj = S3.get_object(Bucket=S3_BUCKET, Key=key)  # Fetch object from S3
    body = obj["Body"].read()  # Read bytes from streaming body
    return pd.read_csv(io.BytesIO(body))  # Parse CSV bytes into DataFrame


def extract_from_s3(partition_prefix: str) -> Dict[str, pd.DataFrame]:
    """
    Extract raw CSVs from S3 under a partition path like:
      raw/year=YYYY/month=MM/day=DD/{customers|products|transactions}/<file>.csv
    The caller provides the partition (e.g., 'raw/year=2025/month=10/day=26').
    """
    log.info(
        f"Extracting from S3 at prefix: s3://{S3_BUCKET}/{partition_prefix}"
    )  # Log which prefix we use

    # Construct typical object keys for each entity folder (one recent file assumed per folder)
    # In a real system you'd list_objects_v2, sort by LastModified, and pick the newest.
    customers_key = f"{partition_prefix}/customers/"  # Folder for customers
    products_key = f"{partition_prefix}/products/"  # Folder for products
    transactions_key = f"{partition_prefix}/transactions/"  # Folder for transactions

    # List and pick one object per folder (minimal requirement: extract exists)
    def _pick_first_key(prefix: str) -> str:
        resp = S3.list_objects_v2(
            Bucket=S3_BUCKET, Prefix=prefix
        )  # List objects under prefix
        contents = resp.get("Contents", [])  # Get list of objects
        if not contents:  # If empty, error (fulfills extract requirement)
            raise FileNotFoundError(f"No objects under s3://{S3_BUCKET}/{prefix}")
        return contents[0]["Key"]  # Return the first object's key

    # Resolve specific object keys
    cust_obj_key = _pick_first_key(customers_key)  # Pick a customers CSV key
    prod_obj_key = _pick_first_key(products_key)  # Pick a products CSV key
    trans_obj_key = _pick_first_key(transactions_key)  # Pick a transactions CSV key

    # Read DataFrames
    clientes = _read_s3_csv(cust_obj_key)  # Load customers DF from S3
    produtos = _read_s3_csv(prod_obj_key)  # Load products DF from S3
    transacoes = _read_s3_csv(trans_obj_key)  # Load transactions DF from S3

    # There may not be items on S3 in the exercise text—keep minimal to spec (3 folders).
    # Return dictionary of what we extracted from S3
    return {
        "clientes": clientes,  # Customers DF from S3
        "produtos": produtos,  # Products DF from S3
        "transacoes": transacoes,  # Transactions DF from S3
    }


# -----------------------
# Transform
# -----------------------


def _prepare_transaction_fact(
    transacoes: pd.DataFrame, itens: pd.DataFrame, produtos: pd.DataFrame
) -> pd.DataFrame:
    """
    Create a transaction fact table with total line amounts by joining items + products (price) + transaction time.
    """
    t = transacoes.copy()  # Copy to avoid mutating input
    i = itens.copy()  # Copy items
    p = produtos.copy()  # Copy products

    t["data_hora"] = pd.to_datetime(
        t["data_hora"], errors="coerce"
    )  # Parse transaction timestamp
    i = i.merge(
        p[["id", "preco"]], left_on="id_produto", right_on="id", how="left"
    )  # Bring in product price
    i["total_linha"] = i["quantidade"] * i["preco"]  # Compute line total

    fact = i.merge(
        t[["id", "id_cliente", "data_hora"]],  # Join items to transactions
        left_on="id_transacao",
        right_on="id",
        how="left",
        suffixes=("_item", "_trans"),
    )
    fact.rename(
        columns={
            "id_cliente": "customer_id",
            "id_produto": "product_id",
            "id_transacao": "transaction_id",
        },
        inplace=True,
    )  # Rename columns to DW-friendly names

    fact["date"] = fact["data_hora"].dt.date  # Extract date for aggregations
    return fact[
        [
            "transaction_id",
            "customer_id",
            "product_id",
            "quantidade",
            "preco",
            "total_linha",
            "data_hora",
            "date",
        ]
    ]
    # Return a clean fact-like frame


def transform_clv(fact: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Customer Lifetime Value (CLV) as total spending per customer.
    """
    clv = (
        fact.groupby("customer_id")["total_linha"]  # Group by customer_id
        .sum()  # Sum all line totals
        .reset_index(name="customer_lifetime_value")
    )  # Output column is CLV
    return clv  # Return CLV dimension


def transform_recommendations(fact: pd.DataFrame) -> pd.DataFrame:
    """
    Create simple product co-occurrence pairs for "customers who bought X also bought Y".
    """
    # Build item pairs by joining fact to itself on transaction_id
    pairs = fact.merge(
        fact, on="transaction_id", suffixes=("_x", "_y")
    )  # Self-join on transaction
    pairs = pairs[pairs["product_id_x"] != pairs["product_id_y"]]  # Exclude self-pairs
    rec = (
        pairs.groupby(["product_id_x", "product_id_y"])  # Count co-purchases
        .size()
        .reset_index(name="co_purchase_count")
    )
    return rec  # Return recommendation pairs


def transform_time_aggregations(
    fact: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Aggregate daily, weekly, and monthly revenue metrics.
    """
    f = fact.copy()  # Copy to avoid side-effects
    f["date"] = pd.to_datetime(f["date"])  # Ensure date type
    f["week"] = f["date"].dt.isocalendar().week  # Compute ISO week number
    f["month"] = f["date"].dt.to_period("M").astype(str)  # Compute YYYY-MM month label

    daily = (
        f.groupby("date")["total_linha"]  # Sum revenue by date
        .sum()
        .reset_index(name="daily_revenue")
    )

    weekly = (
        f.groupby("week")["total_linha"]  # Sum revenue by ISO week
        .sum()
        .reset_index(name="weekly_revenue")
    )

    monthly = (
        f.groupby("month")["total_linha"]  # Sum revenue by month
        .sum()
        .reset_index(name="monthly_revenue")
    )

    return daily, weekly, monthly  # Return three aggregation tables


def scd2_upsert_dim_products(engine, source_products: pd.DataFrame):
    """
    Handle Slowly Changing Dimension (SCD Type 2) for products (track price changes historically).
    Creates/maintains a warehouse.dim_products table with:
      - id (business key), nome, categoria, fornecedor, preco
      - start_date, end_date, is_current
    """
    # Ensure warehouse schema exists (idempotent)
    with engine.begin() as conn:  # Begin DB transaction
        conn.execute(
            text(f"CREATE SCHEMA IF NOT EXISTS {WAREHOUSE_SCHEMA}")
        )  # Create warehouse schema if needed
        # Create dimension table if not exists
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {WAREHOUSE_SCHEMA}.dim_products (
                id              INT         NOT NULL,
                nome            TEXT        NOT NULL,
                categoria       TEXT        NOT NULL,
                fornecedor      TEXT        NOT NULL,
                preco           NUMERIC(10,2) NOT NULL,
                start_date      TIMESTAMPTZ NOT NULL,
                end_date        TIMESTAMPTZ,
                is_current      BOOLEAN     NOT NULL,
                PRIMARY KEY (id, start_date)
            )
        """
            )
        )  # Define SCD2 structure with composite PK

    # 🔁 CHANGED: use read_sql_table instead of f-string SELECT
    current_dim = pd.read_sql_table("dim_products", ENGINE, schema=WAREHOUSE_SCHEMA)
    now = datetime.now(timezone.utc)  # Use timezone-aware UTC

    # If dimension empty, insert all as current versions
    if current_dim.empty:  # First load case
        init = source_products.copy()  # Copy source
        init["start_date"] = now  # All rows start now
        init["end_date"] = pd.NaT  # No end date yet
        init["is_current"] = True  # Mark as current
        init.to_sql(
            "dim_products",
            engine,
            schema=WAREHOUSE_SCHEMA,
            if_exists="append",
            index=False,
        )  # Insert all
        log.info("Initialized dim_products (SCD2) with current snapshot.")  # Log init
        return  # Done for initial load

    # Join source to current to detect changes in preco (price)
    merged = source_products.merge(  # Align source with current rows
        current_dim[current_dim["is_current"] == True],  # Only current versions
        on=[
            "id",
            "nome",
            "categoria",
            "fornecedor",
        ],  # Match on natural keys except preco
        how="left",
        suffixes=("_src", "_cur"),
    )

    # Identify new price versions (where current exists and price changed) OR brand new products (no current row)
    changed_price = merged[
        (~merged["preco_cur"].isna()) & (merged["preco_src"] != merged["preco_cur"])
    ]  # Price changed
    new_products = merged[merged["preco_cur"].isna()]  # Not in dimension

    # Close current versions for changed products
    with engine.begin() as conn:  # Transaction for updates/inserts
        # 🔁 CHANGED: build a safe UPDATE via SQLAlchemy Core instead of f-string
        meta = MetaData()
        dim = Table("dim_products", meta, schema=WAREHOUSE_SCHEMA, autoload_with=conn)

        for pid in changed_price["id"].unique():  # For each product whose price changed
            stmt = (
                update(dim)
                .where(dim.c.id == int(pid), dim.c.is_current == True)
                .values(end_date=now, is_current=False)  # bound values are safe
            )
            conn.execute(stmt)

        # Insert new current versions for changed products
        if not changed_price.empty:
            new_rows = changed_price[
                ["id", "nome", "categoria", "fornecedor", "preco_src"]
            ].copy()  # Build new current rows
            new_rows.rename(
                columns={"preco_src": "preco"}, inplace=True
            )  # Rename to target col
            new_rows["start_date"] = now  # Start now
            new_rows["end_date"] = pd.NaT  # Open-ended
            new_rows["is_current"] = True  # Mark as current
            new_rows.to_sql(
                "dim_products",
                engine,
                schema=WAREHOUSE_SCHEMA,
                if_exists="append",
                index=False,
            )  # Insert

        # Insert brand new products as current
        if not new_products.empty:
            ins = new_products[
                ["id", "nome", "categoria", "fornecedor", "preco_src"]
            ].copy()  # Prepare insert
            ins.rename(columns={"preco_src": "preco"}, inplace=True)  # Fix column name
            ins["start_date"] = now  # Valid from now
            ins["end_date"] = pd.NaT  # No end yet
            ins["is_current"] = True  # Current
            ins.to_sql(
                "dim_products",
                engine,
                schema=WAREHOUSE_SCHEMA,
                if_exists="append",
                index=False,
            )  # Insert

    log.info("SCD Type 2 upsert completed for dim_products.")  # Log completion


# -----------------------
# Load (Warehouse)
# -----------------------


def ensure_warehouse(engine):
    """
    Ensure the warehouse schema and core fact/dim tables exist.
    """
    with engine.begin() as conn:  # Begin transaction
        conn.execute(
            text(f"CREATE SCHEMA IF NOT EXISTS {WAREHOUSE_SCHEMA}")
        )  # Create schema if missing
        # Create basic fact tables (daily/weekly/monthly; minimal star)
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {WAREHOUSE_SCHEMA}.fact_daily_sales (
                date            DATE PRIMARY KEY,
                daily_revenue   NUMERIC(14,2) NOT NULL
            )
        """
            )
        )  # Daily fact
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {WAREHOUSE_SCHEMA}.fact_weekly_sales (
                week            INT PRIMARY KEY,
                weekly_revenue  NUMERIC(14,2) NOT NULL
            )
        """
            )
        )  # Weekly fact
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {WAREHOUSE_SCHEMA}.fact_monthly_sales (
                month           TEXT PRIMARY KEY,
                monthly_revenue NUMERIC(14,2) NOT NULL
            )
        """
            )
        )  # Monthly fact
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {WAREHOUSE_SCHEMA}.dim_customer_value (
                customer_id                 INT PRIMARY KEY,
                customer_lifetime_value     NUMERIC(14,2) NOT NULL
            )
        """
            )
        )  # CLV dimension
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {WAREHOUSE_SCHEMA}.fact_recommendations (
                product_id_x        INT NOT NULL,
                product_id_y        INT NOT NULL,
                co_purchase_count   INT NOT NULL,
                PRIMARY KEY (product_id_x, product_id_y)
            )
        """
            )
        )  # Recommendation pairs fact-like table


def load_warehouse(
    engine,
    clv: pd.DataFrame,
    recs: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
):
    """
    Load transformed dataframes into the warehouse tables (replace full snapshots).
    """
    ensure_warehouse(engine)  # Ensure target tables exist first
    clv.to_sql(
        "dim_customer_value",
        engine,
        schema=WAREHOUSE_SCHEMA,
        if_exists="replace",
        index=False,
    )  # Load CLV
    recs.to_sql(
        "fact_recommendations",
        engine,
        schema=WAREHOUSE_SCHEMA,
        if_exists="replace",
        index=False,
    )  # Load recs
    daily.to_sql(
        "fact_daily_sales",
        engine,
        schema=WAREHOUSE_SCHEMA,
        if_exists="replace",
        index=False,
    )  # Load daily
    weekly.to_sql(
        "fact_weekly_sales",
        engine,
        schema=WAREHOUSE_SCHEMA,
        if_exists="replace",
        index=False,
    )  # Load weekly
    monthly.to_sql(
        "fact_monthly_sales",
        engine,
        schema=WAREHOUSE_SCHEMA,
        if_exists="replace",
        index=False,
    )  # Load monthly
    log.info(
        "Loaded CLV, recommendations, and time aggregations into warehouse."
    )  # Log success


# -----------------------
# Orchestration (single entry point)
# -----------------------


def run():
    """
    Orquestração com ramificação por ambiente:
      - DEV: usa CSV locais para montar a fact (rápido e simples).
      - PROD: usa DB (RDS) para a fact e lê S3 (opcional) para validações/integrações.

    Passos:
      1) Extract (CSV + DB; S3 opcional em ambos; em PROD é mais relevante).
      2) Escolha da fonte para a fact (DEV=CSV, PROD=DB).
      3) Transform (CLV, recomendações, agregações).
      4) SCD2 em produtos (dim_products).
      5) Load para schema de warehouse (star/snowflake minimalista).
      6) Métricas de desempenho (logging).
    """
    # Inicia cronómetro para medir desempenho total
    started = time.time()

    # Lê o ambiente a partir da config carregada (dev/prod)
    env = cfg.get("environment", "dev").lower()

    # ---------------------------------
    # 1) EXTRACT
    # ---------------------------------
    # Extrai sempre CSV locais (úteis em DEV, ou como referência em PROD)
    csv_data = extract_from_csv()

    # Extrai sempre do DB (em DEV pode falhar se não tiveres DB a correr — se for o caso, ignora exceção conforme precisares)
    db_data = extract_from_db(ENGINE)

    # Em PROD, tenta também S3 (opcional) — por defeito vamos usar a partição "hoje" (UTC)
    s3_data = None
    try:
        # Constrói prefixo no formato raw/year=YYYY/month=MM/day=DD
        today = datetime.now(timezone.utc).date()
        partition_prefix = f"raw/year={today.year}/month={today:%m}/day={today:%d}"
        # Chama extract_from_s3 com o prefixo construído
        s3_data = extract_from_s3(partition_prefix)
    except Exception as e:
        # Não falhar a pipeline por falta de S3; regista apenas aviso (sobretudo útil em DEV)
        log.warning(f"S3 extract skipped or failed: {e}")

    # ---------------------------------
    # 2) ESCOLHER FONTE PARA FACT
    # ---------------------------------
    # Usa a função de seleção para decidir de onde vêm transações/itens/produtos
    transacoes_df, itens_df, produtos_df = select_fact_source(
        env, csv_data, db_data, s3_data
    )

    # Monta a fact de transações (junta itens + preço do produto + timestamp/cliente da transação)
    fact = _prepare_transaction_fact(transacoes_df, itens_df, produtos_df)

    # ---------------------------------
    # 3) TRANSFORM
    # ---------------------------------
    # CLV por cliente (soma do total_linha)
    clv = transform_clv(fact)

    # Pares de co-ocorrência para recomendações (X comprou com Y)
    recs = transform_recommendations(fact)

    # Agregações por dia/semana/mês
    daily, weekly, monthly = transform_time_aggregations(fact)

    # ---------------------------------
    # 4) SCD TYPE 2 (produtos)
    # ---------------------------------
    # Mantém a dimensão de produtos com histórico de preço
    scd2_upsert_dim_products(
        ENGINE,
        produtos_df[["id", "nome", "categoria", "fornecedor", "preco"]],
    )

    # ---------------------------------
    # 5) LOAD (WAREHOUSE)
    # ---------------------------------
    load_warehouse(ENGINE, clv, recs, daily, weekly, monthly)

    # ---------------------------------
    # 6) MÉTRICAS / LOGS
    # ---------------------------------
    elapsed = time.time() - started
    log.info(
        f"[{env.upper()}] ETL completed in {elapsed:.2f}s | "
        f"CLV={len(clv)} RECS={len(recs)} DAILY={len(daily)} WEEKLY={len(weekly)} MONTHLY={len(monthly)}"
    )


if __name__ == "__main__":  # Standard Python entry point guard
    run()  # Run orchestration when invoked as a script
