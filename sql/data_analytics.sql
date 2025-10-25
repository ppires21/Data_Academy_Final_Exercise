-- sql/data_analytics.sql
-- 📊 Análises Básicas — Iteração 2 (PostgreSQL, esquema normalizado)
-- Tabelas: clientes, produtos, transacoes, transacao_itens

-- 1️⃣ Top 10 clientes por valor total gasto
--     Valor total = soma(quantidade * preco_unitario) em todas as suas transações.
WITH receita_linha AS (
  SELECT
    ti.id_transacao,
    t.id_cliente,
    (ti.quantidade * ti.preco_unitario) AS receita
  FROM transacao_itens ti
  JOIN transacoes t ON t.id = ti.id_transacao
)
SELECT
  c.id AS id_cliente,
  c.nome AS nome_cliente,
  c.email,
  c.distrito,
  ROUND(SUM(r.receita)::numeric, 2) AS total_gasto
FROM receita_linha r
JOIN clientes c ON c.id = r.id_cliente
GROUP BY c.id, c.nome, c.email, c.distrito
ORDER BY total_gasto DESC
LIMIT 10;

-- 2️⃣ Produtos mais vendidos por categoria (por unidades vendidas)
--     Usa uma função de janela para escolher o #1 por categoria.
WITH unidades_produto AS (
  SELECT
    p.categoria,
    p.id AS id_produto,
    p.nome AS nome_produto,
    SUM(ti.quantidade) AS unidades_vendidas
  FROM transacao_itens ti
  JOIN produtos p ON p.id = ti.id_produto
  GROUP BY p.categoria, p.id, p.nome
),
classificados AS (
  SELECT
    categoria,
    id_produto,
    nome_produto,
    unidades_vendidas,
    RANK() OVER (PARTITION BY categoria ORDER BY unidades_vendidas DESC, nome_produto ASC) AS posicao
  FROM unidades_produto
)
SELECT categoria, id_produto, nome_produto, unidades_vendidas
FROM classificados
WHERE posicao = 1
ORDER BY categoria;

-- 3️⃣ Tendências mensais de receita
--     Agrupa por mês e soma a receita total (com base em preco_unitario).
SELECT
  date_trunc('month', t.data_hora) AS mes,
  ROUND(SUM(ti.quantidade * ti.preco_unitario)::numeric, 2) AS receita
FROM transacoes t
JOIN transacao_itens ti ON ti.id_transacao = t.id
GROUP BY 1
ORDER BY 1;

-- 4️⃣ Valor médio por encomenda (AOV) por distrito
--     AOV = receita total / número de encomendas.
--     Cada transação (t.id) pode ter vários itens.
WITH encomendas AS (
  SELECT
    t.id AS id_encomenda,
    c.distrito,
    SUM(ti.quantidade * ti.preco_unitario) AS receita_encomenda
  FROM transacoes t
  JOIN clientes c ON c.id = t.id_cliente
  JOIN transacao_itens ti ON ti.id_transacao = t.id
  GROUP BY t.id, c.distrito
)
SELECT
  distrito,
  ROUND(AVG(receita_encomenda)::numeric, 2) AS valor_medio_encomenda,
  COUNT(*) AS num_encomendas,
  ROUND(SUM(receita_encomenda)::numeric, 2) AS receita_total
FROM encomendas
GROUP BY distrito
ORDER BY valor_medio_encomenda DESC;
