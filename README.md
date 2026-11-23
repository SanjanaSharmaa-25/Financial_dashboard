# Financial Management & Statistical Dashboard

A web application where **customers** track income, expenses and savings, and **admins** monitor all customers with KPIs, statistics, interactive charts and CSV reports.

**Frontend:** HTML, CSS, JavaScript (Plotly.js charts)
**Backend:** Python, Flask
**Database:** MySQL and SQL
**Analysis:** Pandas, NumPy
**Security:** bcrypt password hashing, role-based access control

## Objectives
1. Build a web app with a Customer module and an Admin module.
2. Let customers record income, expenses and savings.
3. Calculate net savings and savings percentage correctly.
4. Design a normalized MySQL database with keys and constraints.
5. Use SQL joins, GROUP BY and subqueries for analysis.
6. Apply statistics (mean, median, mode, std deviation, variance) with Python.
7. Show results in interactive charts.
8. Secure the app with password hashing and role-based access.
9. Let the admin export reports as CSV.

## How it works
```
Browser (HTML + CSS + JavaScript)
        |  fetch() sends JSON
        v
Flask (app.py)  - login check, validation, calculations (Pandas / NumPy)
        |  SQL
        v
MySQL (5 tables)
```

## Project structure
```
finance_web/
  app.py            Flask backend: all routes and calculations (9 labelled parts)
  setup_db.py       Creates the database, 5 tables and sample data (run once)
  requirements.txt  Python libraries
  templates/
    index.html      Login and register page
    customer.html   Customer dashboard
    admin.html      Admin dashboard
  static/
    style.css       Styling
    common.js       Shared helpers: API calls, tables, charts
    auth.js         Login and register behaviour
    customer.js     Customer dashboard behaviour
    admin.js        Admin dashboard behaviour
```

## Run it (Git Bash)
MySQL must be installed and running first.
```bash
cd finance_web
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

export DB_PASSWORD="your_mysql_password"
export SECRET_KEY="any-long-random-text"
python setup_db.py
python app.py
```
Open **http://127.0.0.1:5000** in your browser. Stop with Ctrl + C.

Next time you only need: `cd finance_web`, `source venv/Scripts/activate`, the two `export` lines, and `python app.py`.

## Demo logins
| Tab | Email | Password |
|---|---|---|
| Admin Login | admin@finance.com | Admin@123 |
| Customer Login | aarav@example.com | Customer@123 |

All sample customers use `Customer@123`. Karan Mehta is Blocked to demonstrate account blocking.

## Database (5 tables)
`users` has many `income`, `expenses`, `saving` and `transactions` rows (linked by `user_id`).
`transactions` stores only a reference (type + id), never the amount, so money is never duplicated.
Net savings = Income - Expenses (calculated). Recorded savings come from the `saving` table (tracked separately).

## Security features
- Passwords stored only as bcrypt hashes
- All SQL uses parameters (protects against SQL injection)
- Role checks on every page and API route; account status re-checked on every request
- Same error message for any failed login
- User text is escaped before it is shown (protects against XSS)
- CSV export neutralises spreadsheet formula injection
- Database password and secret key come from environment variables

## Limitations and future improvements
Records cannot be edited (delete and add again); savings goals have no target amount; no login attempt limit; runs locally only. Future: editing, budgets, recurring transactions, forecasting, deployment.
