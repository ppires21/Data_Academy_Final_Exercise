#!/usr/bin/env python3

# Database setup for Shopflow (Iteration 2 - Improved)
# - Creates schema and normalized tables (Portuguese naming, matching your CSVs)
# - Adds indexes for query performance
# - Supports multi-item transactions (Transacao + TransacaoItem)
# - Creates views for common analytics (reads SQL from sql/data_analytics.sql)

import os
import sys
import logging
import argparse
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, text, Integer, String, Date, DateTime, Numeric, ForeignKey,
    Column, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship

# -----------------------
# Logging
# -----------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# -----------------------
# Config / ENV
# -----------------------
def build_database_url() -> str:
    """
    DATABASE_URL takes precedence (e.g., postgresql+psycopg2://user:pass@host:5432/dbname)
    Otherwise, compose from PG* variables.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    db   = os.getenv("PGDATABASE", "shopflow_db")
    user = os.getenv("PGUSER", "postgres")
    pwd  = os.getenv("PGPASSWORD", "")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


SCHEMA = os.getenv("DB_SCHEMA", "public")  # can be changed to "shopflow"
Base = declarative_base()

# -----------------------
# ORM Models (Portuguese)
# -----------------------

class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("email", name="uq_clientes_email"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False)
    data_registo = Column(Date, nullable=False)
    distrito = Column(String, nullable=False)
    # per-row versioning
    version_timestamp = Column(DateTime(timezone=True), nullable=False)

    transacoes = relationship("Transacao", back_populates="cliente", cascade="all, delete-orphan")


class Produto(Base):
    __tablename__ = "produtos"
    __table_args__ = ({"schema": SCHEMA},)

    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    categoria = Column(String, index=True, nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    fornecedor = Column(String, nullable=False)
    # per-row versioning
    version_timestamp = Column(DateTime(timezone=True), nullable=False)

    itens_transacao = relationship("TransacaoItem", back_populates="produto", cascade="all, delete-orphan")


class Transacao(Base):
    __tablename__ = "transacoes"
    __table_args__ = (
        Index("ix_transacoes_id_cliente", "id_cliente"),
        Index("ix_transacoes_data_hora", "data_hora"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True)
    id_cliente = Column(Integer, ForeignKey(f"{SCHEMA}.clientes.id", ondelete="CASCADE"), nullable=False)
    data_hora = Column(DateTime, nullable=False)
    metodo_pagamento = Column(String, nullable=False)
    # per-row versioning
    version_timestamp = Column(DateTime(timezone=True), nullable=False)

    cliente = relationship("Cliente", back_populates="transacoes")
    itens = relationship("TransacaoItem", back_populates="transacao", cascade="all, delete-orphan")


class TransacaoItem(Base):
    __tablename__ = "transacao_itens"
    __table_args__ = (
        Index("ix_transacao_itens_id_transacao", "id_transacao"),
        Index("ix_transacao_itens_id_produto", "id_produto"),
        {"schema": SCHEMA},
    )

    id = Column(Integer, primary_key=True)
    id_transacao = Column(Integer, ForeignKey(f"{SCHEMA}.transacoes.id", ondelete="CASCADE"), nullable=False)
    id_produto = Column(Integer, ForeignKey(f"{SCHEMA}.produtos.id", ondelete="CASCADE"), nullable=False)
    quantidade = Column(Integer, nullable=False)
    preco_unitario = Column(Numeric(10, 2), nullable=False)
    # per-row versioning
    version_timestamp = Column(DateTime(timezone=True), nullable=False)

    transacao = relationship("Transacao", back_populates="itens")
    produto = relationship("Produto", back_populates="itens_transacao")

# -----------------------
# Engine / helpers
# -----------------------
def get_engine(echo: bool = False):
    url = build_database_url()
    masked_url = url.replace(os.getenv("PGPASSWORD", ""), "***")
    log.info(f"Connecting to: {masked_url}")
    return create_engine(url, echo=echo, pool_pre_ping=True, future=True)


@contextmanager
def begin_conn(engine):
    with engine.begin() as conn:
        yield conn


def ensure_schema(engine):
    if SCHEMA.lower() != "public":
        log.info(f"Ensuring schema '{SCHEMA}' exists…")
        with begin_conn(engine) as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    else:
        log.info("Using default schema 'public'.")


def drop_tables(engine):
    log.warning("Dropping tables (clientes, produtos, transacoes, transacao_itens)…")
    Base.metadata.drop_all(engine, checkfirst=True)


def create_tables(engine):
    log.info("Creating tables (clientes, produtos, transacoes, transacao_itens)…")
    Base.metadata.create_all(engine, checkfirst=True)

# -----------------------
# View creation using SQL file
# -----------------------
def create_views_from_file(engine, sql_file_path="sql/data_analytics.sql"):
    """
    Reads your Iteration 1 SQL file and executes each query.
    Each query block is separated by semicolon (;)
    """
    if not os.path.exists(sql_file_path):
        log.error(f"SQL file not found: {sql_file_path}")
        return

    log.info(f"Loading analytics SQL from {sql_file_path}")

    with open(sql_file_path, "r", encoding="utf-8") as f:
        raw_sql = f.read()

    # Clean up comments and blank lines
    clean_sql = []
    for line in raw_sql.splitlines():
        if not line.strip().startswith("--"):
            clean_sql.append(line)
    sql_content = "\n".join(clean_sql)

    # Split queries by semicolon
    queries = [q.strip() for q in sql_content.split(";") if q.strip()]

    with begin_conn(engine) as conn:
        for i, query in enumerate(queries, 1):
            try:
                conn.execute(text(query))
                log.info(f"Executed SQL block {i}")
            except Exception as e:
                log.error(f"Failed to execute SQL block {i}: {e}")

    log.info("✅ All analytics queries executed.")

# -----------------------
# CLI
# -----------------------
def parse_args():
    p = argparse.ArgumentParser(description="Shopflow DB setup (multi-item transactions)")
    p.add_argument("--echo", action="store_true", help="Print SQL statements")
    p.add_argument("--recreate", action="store_true", help="Drop and recreate all tables before running")
    p.add_argument("--sql-file", type=str, default="sql/data_analytics.sql", help="Path to analytics SQL file")
    return p.parse_args()


def main():
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
