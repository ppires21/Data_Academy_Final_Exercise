import csv
import os
import re
from datetime import datetime

# --- Paths ---
data_dir = "data/raw"
log_dir = "logs"
log_file = os.path.join(log_dir, "validation.log")

# --- Make sure log folder exists ---
os.makedirs(log_dir, exist_ok=True)

# --- Helper functions for validation ---


def is_valid_email(email):
    """Check if an email address has a basic valid format."""
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None


def is_valid_date(date_str):
    """Try to parse a date to see if it's in a valid format."""
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(date_str, fmt)
            return True
        except ValueError:
            continue
    return False


def log(message):
    """Append a message to the log file."""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")


# --- Main validation function ---
def validate_csv(filename):
    file_path = os.path.join(data_dir, filename)

    if not os.path.exists(file_path):
        log(f"[ERROR] File not found: {filename}")
        return

    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row_num = 1
        for row in reader:
            # Check for null/empty values
            for field, value in row.items():
                if value == "" or value is None:
                    log(f"[{filename}] Row {row_num}: Null value in '{field}'")

            # Specific file checks (Portuguese field names)
            if filename == "clientes.csv":
                if not is_valid_email(row.get("email", "")):
                    log(
                        f"[{filename}] Row {row_num}: Invalid email '{row.get('email')}'"
                    )
                if not is_valid_date(row.get("data_registo", "")):
                    log(
                        f"[{filename}] Row {row_num}: Invalid date '{row.get('data_registo')}'"
                    )

            elif filename == "produtos.csv":
                try:
                    price = float(row.get("preco", "nan"))
                    if price <= 0:
                        log(f"[{filename}] Row {row_num}: Non-positive price '{price}'")
                except ValueError:
                    log(
                        f"[{filename}] Row {row_num}: Invalid price '{row.get('preco')}'"
                    )

            elif filename == "transacoes.csv":
                if not is_valid_date(row.get("data_hora", "")):
                    log(
                        f"[{filename}] Row {row_num}: Invalid timestamp '{row.get('data_hora')}'"
                    )

            elif filename == "transacao_itens.csv":
                # quantidade
                try:
                    q = int(row.get("quantidade", "0"))
                    if q <= 0:
                        log(f"[{filename}] Row {row_num}: Non-positive quantity '{q}'")
                except ValueError:
                    log(
                        f"[{filename}] Row {row_num}: Invalid quantity '{row.get('quantidade')}'"
                    )
                # preco_unitario
                try:
                    pu = float(row.get("preco_unitario", "nan"))
                    if pu <= 0:
                        log(
                            f"[{filename}] Row {row_num}: Non-positive unit price '{pu}'"
                        )
                except ValueError:
                    log(
                        f"[{filename}] Row {row_num}: Invalid unit price '{row.get('preco_unitario')}'"
                    )

            row_num += 1

    log(f"[OK] Finished validating {filename}")


# --- Run all validations ---
def main():
    open(log_file, "w").close()  # Clear previous log
    log("Starting data validation...\n")

    for filename in [
        "clientes.csv",
        "produtos.csv",
        "transacoes.csv",
        "transacao_itens.csv",
    ]:
        validate_csv(filename)

    log("\nValidation complete.")


if __name__ == "__main__":
    main()
    print("Validation complete! Check logs/validation.log")
