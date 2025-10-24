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

            # Specific file checks
            if filename == "customers.csv":
                if not is_valid_email(row["email"]):
                    log(f"[{filename}] Row {row_num}: Invalid email '{row['email']}'")
                if not is_valid_date(row["registration_date"]):
                    log(f"[{filename}] Row {row_num}: Invalid date '{row['registration_date']}'")

            elif filename == "products.csv":
                try:
                    price = float(row["price"])
                    if price <= 0:
                        log(f"[{filename}] Row {row_num}: Non-positive price '{price}'")
                except ValueError:
                    log(f"[{filename}] Row {row_num}: Invalid price '{row['price']}'")

            elif filename == "transactions.csv":
                if not is_valid_date(row["timestamp"]):
                    log(f"[{filename}] Row {row_num}: Invalid timestamp '{row['timestamp']}'")

            row_num += 1

    log(f"[OK] Finished validating {filename}")

# --- Run all validations ---
def main():
    open(log_file, "w").close()  # Clear previous log
    log("Starting data validation...\n")

    for filename in ["customers.csv", "products.csv", "transactions.csv"]:
        validate_csv(filename)

    log("\nValidation complete.")

if __name__ == "__main__":
    main()
    print("Validation complete! Check logs/validation.log")