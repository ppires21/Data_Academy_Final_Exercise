# tests/unit/test_transforms.py
# ------------------------------------------------------------
# Unit tests for pure DataFrame transforms (no DB/S3 calls).
# conftest.py stubs config/build_db_url, so importing the module is safe.
# ------------------------------------------------------------

import pandas as pd
from src.etl.transform_pipeline import (
    _prepare_transaction_fact,
    transform_clv,
    transform_recommendations,
    transform_time_aggregations,
)

def test_prepare_transaction_fact_and_followups():
    produtos = pd.DataFrame(
        {"id": [101, 102], "nome": ["P1", "P2"], "categoria": ["C", "C"], "preco": [10.0, 5.0], "fornecedor": ["F", "F"]}
    )
    transacoes = pd.DataFrame(
        {"id": [1, 2], "id_cliente": [11, 22], "data_hora": ["2025-10-01 10:00:00", "2025-10-02 12:00:00"], "metodo_pagamento": ["Card", "MB Way"]}
    )
    itens = pd.DataFrame(
        {"id": [1, 2], "id_transacao": [1, 2], "id_produto": [101, 102], "quantidade": [2, 3], "preco_unitario": [10.0, 5.0]}
    )

    fact = _prepare_transaction_fact(transacoes, itens, produtos)

    expected_cols = [
        "transaction_id", "customer_id", "product_id", "quantidade",
        "preco", "total_linha", "data_hora", "date",
    ]
    assert list(fact.columns) == expected_cols
    assert fact.loc[fact["transaction_id"] == 1, "total_linha"].iloc[0] == 20.0
    assert fact.loc[fact["transaction_id"] == 2, "total_linha"].iloc[0] == 15.0

    clv = transform_clv(fact)
    totals = dict(zip(clv["customer_id"], clv["customer_lifetime_value"]))
    assert totals[11] == 20.0
    assert totals[22] == 15.0

    recs = transform_recommendations(fact)
    assert recs.empty

    daily, weekly, monthly = transform_time_aggregations(fact)
    assert sorted(daily["daily_revenue"].tolist()) == [15.0, 20.0]
    assert len(weekly) == 1
    assert len(monthly) == 1
