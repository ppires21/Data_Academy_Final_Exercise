#!/usr/bin/env python3
# =========================================
# 📄 File: scripts/db_setup.py
# Purpose: Create Shopflow database schema and views, using YAML config loader
# Iteration: 2 (Configuration Management Integration)
# =========================================

import os
import sys
import logging
import argparse
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    text,
    Integer,
    String,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    Column,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

# --- NEW IMPORT ---
# We import our config helper functions from config/config_loader.py
from config.config_loader import get_config, build_db_url


# -----------------------
# Configuration & Logging
# -----------------------

# 1️⃣ Load the YAML configuration (dev.yaml or prod.yaml)
#    - It automatically detects the environment from ENV variable (ENV=dev or ENV=prod)
cfg = get_config()

# 2️⃣ Setup logging based on config values
logging.basicConfig(
    level=cfg["log_level"],  # Uses "DEBUG" or "INFO" from YAML
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# 3️⃣ Get the schema name from the configuration file
SCHEMA = cfg["db_schema"]

# 4️⃣ Initialize SQLAlchemy base class for ORM mapping
Base = declarative_base()


# -----------------------
# ORM Models (Portuguese)
# -----------------------


class Cliente(Base):
    """Table for customers"""

    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("email", name="uq_clientes_email"),  # Ensure unique emails
        {"schema": SCHEMA},  # Use schema from YAML (e.g., "public" or "shopflow")
    )

    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False)
    data_registo = Column(Date, nullable=False)
    distrito = Column(String, nullable=False)
    version_timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),  # auto-fill with current timestamp on insert
    )

    transacoes = relationship(
        "Transacao", back_populates="cliente", cascade="all, delete-orphan"
    )


class Produto(Base):
    """Table for products"""

    __tablename__ = "produtos"
    __table_args__ = ({"schema": SCHEMA},)

    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    categoria = Column(String, index=True, nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    fornecedor = Column(String, nullable=False)
    version_timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),  # auto-fill with current timestamp on insert
    )

    itens_transacao = relationship(
        "TransacaoItem", back_populates="produto", cascade="all, delete-orphan"
    )


class Transacao(Base):
    """Table for transactions (main order table)"""

    __tablename__ = "transacoes"
    __table_args__ = (
        Index("ix_transacoes_id_cliente", "id_cliente"),
        Index("ix_transacoes_data_hora", "data_hora"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True)
    id_cliente = Column(
        Integer, ForeignKey(f"{SCHEMA}.clientes.id", ondelete="CASCADE"), nullable=False
    )
    data_hora = Column(DateTime, nullable=False)
    metodo_pagamento = Column(String, nullable=False)
    version_timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),  # auto-fill with current timestamp on insert
    )

    cliente = relationship("Cliente", back_populates="transacoes")
    itens = relationship(
        "TransacaoItem", back_populates="transacao", cascade="all, delete-orphan"
    )


class TransacaoItem(Base):
    """Table for transaction items (each product per transaction)"""

    __tablename__ = "transacao_itens"
    __table_args__ = (
        Index("ix_transacao_itens_id_transacao", "id_transacao"),
        Index("ix_transacao_itens_id_produto", "id_produto"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True)
    id_transacao = Column(
        Integer,
        ForeignKey(f"{SCHEMA}.transacoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    id_produto = Column(
        Integer, ForeignKey(f"{SCHEMA}.produtos.id", ondelete="CASCADE"), nullable=False
    )
    quantidade = Column(Integer, nullable=False)
    preco_unitario = Column(Numeric(10, 2), nullable=False)
    version_timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),  # auto-fill with current timestamp on insert
    )

    transacao = relationship("Transacao", back_populates="itens")
    produto = relationship("Produto", back_populates="itens_transacao")


# -----------------------
# Engine / helpers
# -----------------------


def get_engine(echo: bool = False):
    """
    Create SQLAlchemy engine using the connection string built from YAML config.
    """
    # Build DB URL using our helper from config_loader.py
    db_url = build_db_url(cfg)

    # Mask password for safe logging
    masked_url = db_url.replace(cfg["database"]["password"], "***")

    log.info(f"Connecting to database at: {masked_url}")
    return create_engine(db_url, echo=echo, pool_pre_ping=True, future=True)


@contextmanager
def begin_conn(engine):
    """
    Context manager for starting and closing DB connections safely.
    """
    with engine.begin() as conn:
        yield conn


def ensure_schema(engine):
    """
    Ensure the schema defined in the config exists.
    """
    if SCHEMA.lower() != "public":
        log.info(f"Ensuring schema '{SCHEMA}' exists…")
        with begin_conn(engine) as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    else:
        log.info("Using default schema 'public'.")


def drop_tables(engine):
    """
    Drop all tables if the --recreate flag is used.
    """
    log.warning("Dropping tables (clientes, produtos, transacoes, transacao_itens)…")
    Base.metadata.drop_all(engine, checkfirst=True)


def create_tables(engine):
    """
    Create all tables if they don't exist yet.
    """
    log.info("Creating tables (clientes, produtos, transacoes, transacao_itens)…")
    Base.metadata.create_all(engine, checkfirst=True)


# -----------------------
# View creation using SQL file
# -----------------------
def create_views_from_file(engine, sql_file_path="sql/data_analytics.sql"):
    """
    Reads your Iteration 1 SQL file and executes each query block (separated by semicolons).
    """
    if not os.path.exists(sql_file_path):
        log.error(f"SQL file not found: {sql_file_path}")
        return

    log.info(f"Loading analytics SQL from {sql_file_path}")

    with open(sql_file_path, "r", encoding="utf-8") as f:
        raw_sql = f.read()

    # Remove comments and blank lines
    clean_sql = [
        line for line in raw_sql.splitlines() if not line.strip().startswith("--")
    ]
    sql_content = "\n".join(clean_sql)

    # Split into multiple statements by semicolon
    queries = [q.strip() for q in sql_content.split(";") if q.strip()]

    # Execute each query sequentially
    with begin_conn(engine) as conn:
        for i, query in enumerate(queries, 1):
            try:
                conn.execute(text(query))
                log.info(f"Executed SQL block {i}")
            except Exception as e:
                log.error(f"Failed to execute SQL block {i}: {e}")

    log.info("✅ All analytics queries executed successfully.")


# -----------------------
# CLI interface
# -----------------------
def parse_args():
    """
    Command-line interface options for flexibility:
    --echo      : print SQL statements being executed
    --recreate  : drop and recreate all tables
    --sql-file  : specify the analytics SQL file
    """
    p = argparse.ArgumentParser(
        description="Shopflow DB setup (multi-item transactions, YAML config enabled)"
    )
    p.add_argument("--echo", action="store_true", help="Print SQL statements")
    p.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate all tables before running",
    )
    p.add_argument(
        "--sql-file",
        type=str,
        default="sql/data_analytics.sql",
        help="Path to analytics SQL file",
    )
    return p.parse_args()


def main():
    """
    Main execution flow:
    - Reads config
    - Creates engine
    - Ensures schema
    - Creates/drops tables
    - Creates views
    """
    args = parse_args()
    try:
        engine = get_engine(echo=args.echo)
        ensure_schema(engine)

        if args.recreate:
            drop_tables(engine)

        create_tables(engine)
        create_views_from_file(engine, args.sql_file)

        log.info("✅ Database setup complete.")
        return 0
    except Exception as e:
        log.exception(f"❌ DB setup failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
