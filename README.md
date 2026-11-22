# Financial Management & Statistical Dashboard (Simple Version)

Customers track income, expenses and savings. Admins monitor all customers with KPIs, statistics, charts and CSV reports.

## Files (only 4)
| File | Job |
|---|---|
| `setup_db.py` | Creates the database, 5 tables and sample data (run once) |
| `app.py` | The whole web app (6 parts, top to bottom) |
| `requirements.txt` | Libraries to install |
| `README.md` | This file |

## Run
```
cd finance_simple
python -m venv venv
source venv/Scripts/activate      (Command Prompt: venv\Scripts\activate)
pip install -r requirements.txt
export DB_PASSWORD="your_mysql_password"    (Command Prompt: set DB_PASSWORD=your_mysql_password)
python setup_db.py
streamlit run app.py
```

## Demo logins
- Admin tab: `admin@finance.com` / `Admin@123`
- Customer tab: `aarav@example.com` / `Customer@123`

## Database (5 tables)
`users` has many `income`, `expenses`, `saving` and `transactions` rows (linked by `user_id`).
`transactions` stores only a reference (type + id), never the amount.
Net savings = Income - Expenses. Recorded savings come from the `saving` table (kept separate).

## Tech stack
Python, Streamlit, MySQL, SQL, Pandas, NumPy, Plotly, bcrypt.
