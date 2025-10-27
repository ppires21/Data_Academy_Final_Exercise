import csv
import os
import random
from datetime import datetime, timedelta
import sys

# === Funções auxiliares ===


def save_csv(filename, data, headers):
    """Guarda uma lista de dicionários num ficheiro CSV com tratamento de erros."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
        print(f"[OK] Ficheiro guardado: {filename}")
    except PermissionError:
        print(f"[ERRO] Sem permissões para escrever em {filename}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] Falha ao guardar {filename}: {e}")
        sys.exit(1)


def generate_data():
    """Gera os ficheiros de clientes, produtos e transações com dados portugueses."""
    try:
        # --- Listas de apoio ---
        first_names = [
            "Ana",
            "Bruno",
            "Carla",
            "Diogo",
            "Eduardo",
            "Filipa",
            "Gonçalo",
            "Helena",
            "Inês",
            "João",
            "Luís",
            "Marta",
            "Nuno",
            "Patrícia",
            "Rui",
            "Sara",
            "Tiago",
            "Vera",
            "Pedro",
        ]
        last_names = [
            "Silva",
            "Santos",
            "Ferreira",
            "Pereira",
            "Oliveira",
            "Costa",
            "Rodrigues",
            "Martins",
            "Jesus",
            "Sousa",
            "Fernandes",
            "Gonçalves",
            "Almeida",
            "Ribeiro",
            "Pires",
        ]
        countries = ["Portugal"]
        districts = [
            "Lisboa",
            "Porto",
            "Braga",
            "Coimbra",
            "Faro",
            "Setúbal",
            "Aveiro",
            "Leiria",
            "Viseu",
            "Évora",
        ]
        categories = [
            "Eletrónica",
            "Livros",
            "Vestuário",
            "Casa",
            "Brinquedos",
            "Mercearia",
            "Desporto",
        ]
        suppliers = [
            "Sonae Distribuição",
            "Jerónimo Martins",
            "FNAC Portugal",
            "Worten",
            "Continente",
            "Pingo Doce",
            "Leroy Merlin",
        ]
        payment_methods = [
            "Cartão de Crédito",
            "MB Way",
            "Transferência Bancária",
            "PayPal",
        ]

        # --- Gerar clientes ---
        customers = []
        for i in range(1, 1001):
            name = f"{random.choice(first_names)} {random.choice(last_names)}"  # nosec B311
            # 👇 Garante emails únicos ao incluir o ID
            email = name.lower().replace(" ", ".") + f".{i}@exemplo.pt"
            registration_date = (
                datetime.now() - timedelta(days=random.randint(0, 1000))  # nosec B311
            ).strftime("%Y-%m-%d")
            district = random.choice(districts)  # nosec B311
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
            category = random.choice(categories)  # nosec B311
            name = f"{category} {i}"
            price = round(random.uniform(5, 500), 2)  # nosec B311
            supplier = random.choice(suppliers)  # nosec B311
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
        transaction_items = []  # 🔹 new table data

        for i in range(1, 5001):
            customer_id = random.randint(1, 1000)  # nosec B311
            product_id = random.randint(1, 500)  # nosec B311
            quantity = random.randint(1, 5)  # nosec B311
            timestamp = (
                datetime.now() - timedelta(days=random.randint(0, 365))  # nosec B311
            ).strftime("%Y-%m-%d %H:%M:%S")
            payment_method = random.choice(payment_methods)  # nosec B311

            # find product price
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

            # 🔹 create normalized transaction item
            transaction_items.append(
                {
                    "id": i,  # same ID for simplicity (1-to-1 in this generator)
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

        # 🔹 NEW: save normalized transaction items
        save_csv(
            "data/raw/transacao_itens.csv",
            transaction_items,
            transaction_items[0].keys(),
        )

        print("✅ Dados portugueses gerados com sucesso!")

    except Exception as e:
        print(f"[ERRO] Falha na geração de dados: {e}")
        sys.exit(1)


if __name__ == "__main__":
    generate_data()
