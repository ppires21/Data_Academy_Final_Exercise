# Shopflow Pipeline — Iteration 1

### 🧠 Overview
This iteration generates, validates and analyses synthetic Portuguese retail data.

### 📂 Structure
```
src/
 ├─ data_generator.py
 └─ data_validator.py
sql/
 └─ basic_analytics.sql
logs/
data/
 └─ raw/
```

### ⚙️ Requirements
- Python ≥ 3.8  
- PostgreSQL (for running the SQL queries)

### 🚀 Usage

#### 1. Generate data
```bash
python src/data_generator.py
```
Creates:
- `data/raw/clientes.csv`
- `data/raw/produtos.csv`
- `data/raw/transacoes.csv`

#### 2. Validate data
```bash
python src/data_validator.py
```
Outputs validation messages to `logs/validation.log`.

#### 3. Run analytics
Open `sql/basic_analytics.sql` in PostgreSQL and execute:
```sql
\i sql/basic_analytics.sql
```

### 📈 Outputs
- Clean CSV files under `data/raw/`
- Validation log in `logs/validation.log`
- Example query results in the PostgreSQL console

### 🧾 Notes
All names and suppliers are Portuguese for realism.
