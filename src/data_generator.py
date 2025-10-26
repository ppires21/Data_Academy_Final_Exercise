import csv
import os
import secrets  # ✅ replaced 'random' for Bandit B311 security compliance
from datetime import datetime, timedelta
import sys

# === Funções auxiliares ===


def save_csv(filename, data, headers):
    """
    Guarda uma lista de dicionários num ficheiro CSV com tratamento de erros.

    Args:
        filename (str): Caminho do ficheiro CSV a criar
        data (list[dict]): Dados a escrever
        headers (list[str]): Cabeçalhos do ficheiro
    """
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)  # Cria diretório, se não existir
        with open(filename, "w", newline="", encoding="utf-8") as f:  # Abre o ficheiro para escrita
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)  # Escreve os dados
        print(f"[OK] Ficheiro guardado: {filename}")
    except PermissionError:
        print(f"[ERRO] Sem permissões para escrever em {filename}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] Falha ao guardar {filename}: {e}")
        sys.exit(1)


def generate_data():
    """
    Gera os ficheiros de clientes, produtos e transações com dados portugueses.
    Esta versão usa 'secrets' em vez de 'random' para evitar alertas de Bandit B311.
    """
    try:
        # --- Listas de apoio ---
        first_names = [
            "Ana", "Bruno", "Carla", "Diogo", "Eduardo", "Filipa", "Gonçalo",
            "Helena", "Inês", "João", "Luís", "Marta", "Nuno", "Patrícia", "Rui",
            "Sara", "Tiago", "Vera", "Pedro",
        ]
        last_names = [
            "Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues",
            "Martins", "Jesus", "Sousa", "Fernandes", "Gonçalves", "Almeida", "Ribeiro", "Pires",
        ]
        countries = ["Portugal"]
        districts = [
            "Lisboa", "Porto", "Braga", "Coimbra", "Faro", "Setúbal", "Aveiro",
            "Leiria", "Viseu", "Évora",
        ]
        categories = [
            "Eletrónica", "Livros", "Vestuário", "Casa",
            "Brinquedos", "Mercearia", "Desporto",
        ]
        suppliers = [
            "Sonae Distribuição", "Jerónimo Martins", "FNAC Portugal",
            "Worten", "Continente", "Pingo Doce", "Leroy Merlin",
        ]
        payment_methods = [
            "Cartão de Crédito", "MB Way", "Transferência Bancária", "PayPal",
        ]

        # --- Gerar clientes ---
        customers = []
        for i in range(1, 1001):
            # ✅ usar secrets.choice em vez de random.choice (B311)
            name = f"{secrets.choice(first_names)} {secrets.choice(last_names)}"
            email = name.lower().replace(" ", ".") + "@exemplo.pt"
            # ✅ usar secrets.randbelow em vez de random.randint (B311)
            registration_date = (
                datetime.now() - timedelta(days=secrets.randbelow(1000))
            ).strftime("%Y-%m-%d")
            district = secrets.choice(districts)
            customers.append(
                {
                    "id": i,
                    "nome": name,
                    "email": email,
                    "data_registo": registration_date,
                    "distrito": district,
                }
            )

        # --- Gerar produtos ---
        products = []
        for i in range(1, 501):
            category = secrets.choice(categories)
            name = f"{category} {i}"
            # ✅ gerar preço de forma simples mas segura
            price = round(float(secrets.randbelow(49500) / 100 + 5), 2)
            supplier = secrets.choice(suppliers)
            products.append(
                {
                    "id": i,
                    "nome": name,
                    "categoria": category,
                    "preco": price,
                    "fornecedor": supplier,
                }
            )

        # --- Gerar transações ---
        transactions = []
        transaction_items = []

        for i in range(1, 5001):
            customer_id = secrets.randbelow(1000) + 1
            product_id = secrets.randbelow(500) + 1
            quantity = secrets.randbelow(5) + 1
            timestamp = (
                datetime.now() - timedelta(days=secrets.randbelow(365))
            ).strftime("%Y-%m-%d %H:%M:%S")
            payment_method = secrets.choice(payment_methods)

            # encontra o preço do produto correspondente
            product_price = next(
                (p["preco"] for p in products if p["id"] == product_id), 0
            )

            transactions.append(
                {
                    "id": i,
                    "id_cliente": customer_id,
                    "id_produto": product_id,
                    "quantidade": quantity,
                    "data_hora": timestamp,
                    "metodo_pagamento": payment_method,
                }
            )

            transaction_items.append(
                {
                    "id": i,
                    "id_transacao": i,
                    "id_produto": product_id,
                    "quantidade": quantity,
                    "preco_unitario": product_price,
                }
            )

        # --- Guardar ficheiros ---
        save_csv("data/raw/clientes.csv", customers, customers[0].keys())
        save_csv("data/raw/produtos.csv", products, products[0].keys())
        save_csv("data/raw/transacoes.csv", transactions, transactions[0].keys())
        save_csv("data/raw/transacao_itens.csv", transaction_items, transaction_items[0].keys())

        print("✅ Dados portugueses gerados com sucesso!")

    except Exception as e:
        print(f"[ERRO] Falha na geração de dados: {e}")
        sys.exit(1)


if __name__ == "__main__":
    generate_data()
