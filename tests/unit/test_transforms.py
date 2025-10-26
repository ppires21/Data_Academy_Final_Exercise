# tests/unit/test_transforms.py
# ------------------------------------------------------------
# Purpose: Unit tests for pure DataFrame transforms in
#          src/etl/transform_pipeline.py (no DB/S3).
# Notes:   We construct tiny DataFrames that exercise the logic
#          without any external dependencies.
# ------------------------------------------------------------

import pandas as pd

# Import only the pure transform functions we need.
from src.etl.transform_pipeline import (
    _prepare_transaction_fact,
    transform_clv,
    transform_recommendations,
    transform_time_aggregations,
)


def test_prepare_transaction_fact_and_followups():
    # Build a minimal products table with ids and prices.
    produtos = pd.DataFrame(
        {
            "id": [101, 102],            # product ids
            "nome": ["P1", "P2"],        # not used by the function but realistic
            "categoria": ["C", "C"],     # not used
            "preco": [10.0, 5.0],        # unit prices
            "fornecedor": ["F", "F"],    # not used
        }
    )

    # Build a minimal transactions table (two transactions, two customers).
    transacoes = pd.DataFrame(
        {
            "id": [1, 2],                          # transaction ids
            "id_cliente": [11, 22],                # customer ids
            "data_hora": ["2025-10-01 10:00:00", "2025-10-02 12:00:00"],  # timestamps
            "metodo_pagamento": ["Card", "MB Way"],                       # not used here
        }
    )

    # Build a minimal items table (each transaction buys one product).
    itens = pd.DataFrame(
        {
            "id": [1, 2],                 # item ids (not used in the fact)
            "id_transacao": [1, 2],       # link to transacoes.id
            "id_produto": [101, 102],     # link to produtos.id
            "quantidade": [2, 3],         # quantities
            "preco_unitario": [10.0, 5.0] # not used directly (we recompute from produtos)
        }
    )

    # Build the transaction fact using the pipeline helper.
    fact = _prepare_transaction_fact(transacoes, itens, produtos)

    # The fact must have these columns exactly (order matters in the function output).
    expected_cols = [
        "transaction_id",
        "customer_id",
        "product_id",
        "quantidade",
        "preco",
        "total_linha",
        "data_hora",
        "date",
    ]
    assert list(fact.columns) == expected_cols

    # Check a couple of derived values:
    # - For transaction 1: quantity 2 * price 10 = total 20
    # - For transaction 2: quantity 3 * price 5  = total 15
    assert fact.loc[fact["transaction_id"] == 1, "total_linha"].iloc[0] == 20.0
    assert fact.loc[fact["transaction_id"] == 2, "total_linha"].iloc[0] == 15.0

    # Compute CLV to ensure grouping works.
    clv = transform_clv(fact)
    # We expect two customers with totals 20 and 15 respectively.
    totals = dict(zip(clv["customer_id"], clv["customer_lifetime_value"]))
    assert totals[11] == 20.0
    assert totals[22] == 15.0

    # Compute recommendations to ensure pair counting runs (with one item per txn, there are no pairs).
    recs = transform_recommendations(fact)
    # With only 1 product per transaction, there are no co-occurrence pairs.
    assert recs.empty

    # Compute daily/weekly/monthly aggregations to ensure time grouping works.
    daily, weekly, monthly = transform_time_aggregations(fact)
    # Daily totals should be [20, 15] for the two dates.
    assert sorted(daily["daily_revenue"].tolist()) == [15.0, 20.0]
    # Weekly/monthly aggregations should each have a single row in this tiny dataset.
    assert len(weekly) == 1
    assert len(monthly) == 1
