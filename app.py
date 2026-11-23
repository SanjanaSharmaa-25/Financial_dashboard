"""Financial Management & Statistical Dashboard - Flask backend.

Run:  python app.py      then open  http://127.0.0.1:5000

The file has 9 parts, top to bottom:
  1 Setup               4 Calculations        7 Auth API
  2 Database helpers    5 Login protection    8 Customer API
  3 Input validation    6 Page routes         9 Admin API
"""
import math
import os
import re
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

import bcrypt
import mysql.connector
import numpy as np
import pandas as pd
from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

# =====================================================================
# PART 1: SETUP
# =====================================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

INCOME_SOURCES = ["Salary", "Freelance", "Business", "Other"]
CATEGORIES = ["Food", "Rent", "Shopping", "Travel", "Education",
              "Healthcare", "Entertainment", "Other"]
PAYMENTS = ["Cash", "UPI", "Credit Card", "Debit Card", "Net Banking"]
TX_TYPES = ["Income", "Expense", "Saving"]
# transaction type -> (table, id column). Used when deleting a record.
TABLES = {"Income": ("income", "income_id"),
          "Expense": ("expenses", "expense_id"),
          "Saving": ("saving", "saving_id")}
DATE_COLUMNS = {"income": "income_date", "expenses": "expense_date", "saving": "saving_date"}
EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


class ApiError(Exception):
    """An error we want to show to the user as a clear message."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"error": error.message}), error.status


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.exception(error)
    return jsonify({"error": "Server error. Please try again."}), 500


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# =====================================================================
# PART 2: DATABASE HELPERS
# =====================================================================
def get_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database="finance_dashboard")


def _clean(value):
    """Convert database values into things JSON understands."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return value


def query(sql, params=()):
    """Run a SELECT. Returns a list of dictionaries (one per row)."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, tuple(params))
        rows = [{key: _clean(val) for key, val in row.items()} for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return rows


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def run(sql, params=()):
    """Run an INSERT / UPDATE / DELETE."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def add_record(user_id, tx_type, insert_sql, values, tx_date, description):
    """Save a record AND its history row together. If one fails, both are undone."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(insert_sql, (user_id, *values))
        cur.execute(
            "INSERT INTO transactions (user_id, transaction_type, reference_id, "
            "transaction_date, description) VALUES (%s, %s, %s, %s, %s)",
            (user_id, tx_type, cur.lastrowid, tx_date, description))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_transaction(user_id, transaction_id):
    """Delete the history row AND the income/expense/saving row it points to."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT transaction_type, reference_id FROM transactions "
                    "WHERE transaction_id = %s AND user_id = %s", (transaction_id, user_id))
        row = cur.fetchone()
        if row is None:
            raise ApiError("Record not found.", 404)
        table, id_column = TABLES[row[0]]
        cur.execute(f"DELETE FROM {table} WHERE {id_column} = %s AND user_id = %s",
                    (row[1], user_id))
        cur.execute("DELETE FROM transactions WHERE transaction_id = %s", (transaction_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def where_clause(date_col, user_id=None, start=None, end=None, prefix="", extra=None):
    """Build an optional WHERE clause. Returns (sql_text, params_list)."""
    conditions, params = [], []
    if user_id is not None:
        conditions.append(f"{prefix}user_id = %s")
        params.append(user_id)
    if start:
        conditions.append(f"{prefix}{date_col} >= %s")
        params.append(start)
    if end:
        conditions.append(f"{prefix}{date_col} <= %s")
        params.append(end)
    for condition, values in (extra or []):
        conditions.append(condition)
        params.extend(values)
    return ("WHERE " + " AND ".join(conditions) if conditions else ""), params


def month_sql(column):
    """SQL that turns a date into 'YYYY-MM' (year AND month together)."""
    return f"CONCAT(YEAR({column}), '-', LPAD(MONTH({column}), 2, '0'))"


# =====================================================================
# PART 3: INPUT VALIDATION
# =====================================================================
def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Invalid request.")
    return data


def clean_text(value, max_length=255):
    text = str(value if value is not None else "").strip()
    if len(text) > max_length:
        raise ApiError(f"Text is too long (maximum {max_length} characters).")
    return text


def parse_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ApiError("Amount must be a number.")
    if not math.isfinite(amount) or amount <= 0:
        raise ApiError("Amount must be greater than zero.")
    if amount > 100_000_000:
        raise ApiError("Amount is too large.")
    return round(amount, 2)


def parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ApiError("Please enter a valid date.")


def parse_past_date(value):
    parsed = parse_date(value)
    if parsed > date.today():
        raise ApiError("Date cannot be in the future.")
    return parsed


def parse_choice(value, options, label):
    if value not in options:
        raise ApiError(f"Please choose a valid {label}.")
    return value


def get_filters():
    """Read ?start=&end=&customer_id= from the URL."""
    start = request.args.get("start") or None
    end = request.args.get("end") or None
    start = parse_date(start) if start else None
    end = parse_date(end) if end else None
    if start and end and start > end:
        raise ApiError("'From date' must not be after 'To date'.")
    customer_id = request.args.get("customer_id") or None
    if customer_id is not None:
        try:
            customer_id = int(customer_id)
        except ValueError:
            raise ApiError("Invalid customer.")
    return start, end, customer_id


def csv_safe(value):
    """Stop spreadsheet formula injection: text starting with = + - @ is prefixed."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def respond(rows, filename):
    """Send rows as JSON, or as a CSV download when ?format=csv is in the URL."""
    if request.args.get("format") == "csv":
        df = pd.DataFrame(rows)
        for column in df.columns:
            df[column] = df[column].map(csv_safe)
        return Response(df.to_csv(index=False), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={filename}.csv"})
    return jsonify({"rows": rows})


# =====================================================================
# PART 4: CALCULATIONS (SQL + Pandas + NumPy)
# =====================================================================
def total(table, user_id=None, start=None, end=None):
    where, params = where_clause(DATE_COLUMNS[table], user_id, start, end)
    row = query_one(f"SELECT COALESCE(SUM(amount), 0) AS t FROM {table} {where}", params)
    return float(row["t"])


def savings_percent(income, expenses):
    """Savings % = (Income - Expenses) / Income x 100, only when income > 0."""
    return round((income - expenses) / income * 100, 2) if income > 0 else 0.0


def get_totals(user_id=None, start=None, end=None):
    income = total("income", user_id, start, end)
    expenses = total("expenses", user_id, start, end)
    return {
        "income": income,
        "expenses": expenses,
        "net_savings": round(income - expenses, 2),        # calculated
        "savings_pct": savings_percent(income, expenses),
        "recorded_savings": total("saving", user_id, start, end),  # tracked separately
    }


def monthly_summary(user_id=None, start=None, end=None):
    """One row per month (YYYY-MM): income, expenses, recorded savings, net savings."""
    frames = []
    for table, value in (("income", "income"), ("expenses", "expenses"),
                         ("saving", "recorded_savings")):
        column = DATE_COLUMNS[table]
        where, params = where_clause(column, user_id, start, end)
        rows = query(f"SELECT {month_sql(column)} AS `month`, SUM(amount) AS {value} "
                     f"FROM {table} {where} GROUP BY `month`", params)
        frame = pd.DataFrame(rows, columns=["month", value])
        frame[value] = frame[value].astype(float)
        frames.append(frame)
    df = frames[0].merge(frames[1], on="month", how="outer").merge(frames[2], on="month", how="outer")
    if df.empty:
        return []
    df = df.fillna(0).sort_values("month").reset_index(drop=True)
    df["net_savings"] = df["income"] - df["expenses"]
    df["savings_pct"] = np.where(df["income"] > 0, df["net_savings"] / df["income"] * 100, 0)
    return df.round(2).to_dict("records")


def category_summary(user_id=None, start=None, end=None):
    where, params = where_clause("expense_date", user_id, start, end)
    rows = query("SELECT category, SUM(amount) AS total, COUNT(*) AS records, "
                 f"AVG(amount) AS average FROM expenses {where} "
                 "GROUP BY category ORDER BY total DESC", params)
    grand_total = sum(row["total"] for row in rows)
    for row in rows:
        row["average"] = round(row["average"], 2)
        row["share_pct"] = round(row["total"] / grand_total * 100, 2) if grand_total else 0
    return rows


def history(user_id=None, start=None, end=None, tx_type=None):
    """Transaction history. The amount is READ from the source table, not copied."""
    extra = [("t.transaction_type = %s", [tx_type])] if tx_type else None
    where, params = where_clause("transaction_date", user_id, start, end, prefix="t.", extra=extra)
    return query(
        "SELECT t.transaction_id, u.name AS customer, t.transaction_date AS date, "
        "t.transaction_type AS type, "
        "CASE t.transaction_type WHEN 'Income' THEN i.amount "
        "WHEN 'Expense' THEN e.amount ELSE s.amount END AS amount, t.description "
        "FROM transactions t "
        "INNER JOIN users u ON t.user_id = u.user_id "
        "LEFT JOIN income i ON t.transaction_type = 'Income' AND t.reference_id = i.income_id "
        "LEFT JOIN expenses e ON t.transaction_type = 'Expense' AND t.reference_id = e.expense_id "
        "LEFT JOIN saving s ON t.transaction_type = 'Saving' AND t.reference_id = s.saving_id "
        f"{where} ORDER BY t.transaction_date DESC, t.transaction_id DESC", params)


def admin_kpis(start, end, customer_id):
    counts = query_one("SELECT COUNT(*) AS total, "
                       "COALESCE(SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END), 0) AS active "
                       "FROM users WHERE role = 'Customer'")
    totals = get_totals(customer_id, start, end)
    where, params = where_clause("expense_date", customer_id, start, end)
    highest = query_one(f"SELECT COALESCE(MAX(amount), 0) AS m FROM expenses {where}", params)
    people = 1 if customer_id is not None else (int(counts["total"]) or 1)
    return {
        "total_customers": int(counts["total"]),
        "active_customers": int(counts["active"]),
        "total_income": totals["income"],
        "total_expenses": totals["expenses"],
        "total_savings": totals["recorded_savings"],
        "avg_income": round(totals["income"] / people, 2),
        "avg_expenses": round(totals["expenses"] / people, 2),
        "highest_expense": float(highest["m"]),
    }


def customer_wise(table, value_name, start, end, customer_id):
    where, params = where_clause(DATE_COLUMNS[table], customer_id, start, end, prefix="t.")
    return query(f"SELECT u.user_id, u.name, SUM(t.amount) AS {value_name} "
                 f"FROM users u INNER JOIN {table} t ON u.user_id = t.user_id {where} "
                 f"GROUP BY u.user_id, u.name ORDER BY {value_name} DESC", params)


def customer_summary_report(start, end, customer_id):
    """One row per customer. Uses LEFT JOIN with subqueries so customers with no data appear."""
    iw, ip = where_clause("income_date", None, start, end)
    ew, ep = where_clause("expense_date", None, start, end)
    sw, sp = where_clause("saving_date", None, start, end)
    params = ip + ep + sp
    outer = ""
    if customer_id is not None:
        outer = "AND u.user_id = %s"
        params.append(customer_id)
    rows = query(
        "SELECT u.user_id, u.name, u.email, u.status, "
        "COALESCE(i.total, 0) AS total_income, COALESCE(e.total, 0) AS total_expenses, "
        "COALESCE(s.total, 0) AS recorded_savings FROM users u "
        f"LEFT JOIN (SELECT user_id, SUM(amount) AS total FROM income {iw} GROUP BY user_id) i ON u.user_id = i.user_id "
        f"LEFT JOIN (SELECT user_id, SUM(amount) AS total FROM expenses {ew} GROUP BY user_id) e ON u.user_id = e.user_id "
        f"LEFT JOIN (SELECT user_id, SUM(amount) AS total FROM saving {sw} GROUP BY user_id) s ON u.user_id = s.user_id "
        f"WHERE u.role = 'Customer' {outer} ORDER BY u.name", params)
    for row in rows:
        row["net_savings"] = round(row["total_income"] - row["total_expenses"], 2)
        row["savings_pct"] = savings_percent(row["total_income"], row["total_expenses"])
    return rows


# =====================================================================
# PART 5: LOGIN PROTECTION
# =====================================================================
def current_user():
    """The logged-in user, read fresh from the database (so blocking works at once)."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = query_one("SELECT user_id, name, role, status FROM users WHERE user_id = %s", (user_id,))
    if row is None or row["status"] != "Active":
        session.clear()
        return None
    return row


def api_required(role):
    """Protect an API route: must be logged in with the right role."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"error": "Please log in."}), 401
            if user["role"] != role:
                return jsonify({"error": "Access denied."}), 403
            g.user = user
            return view(*args, **kwargs)
        return wrapper
    return decorator


def page_required(role):
    """Protect a web page: others are sent back to the login page."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None or user["role"] != role:
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


# =====================================================================
# PART 6: PAGE ROUTES
# =====================================================================
@app.route("/")
def index():
    user = current_user()
    if user:
        return redirect(url_for("admin_page" if user["role"] == "Admin" else "customer_page"))
    return render_template("index.html")


@app.route("/customer")
@page_required("Customer")
def customer_page():
    return render_template("customer.html")


@app.route("/admin")
@page_required("Admin")
def admin_page():
    return render_template("admin.html")


# =====================================================================
# PART 7: AUTH API
# =====================================================================
@app.post("/api/register")
def api_register():
    data = json_body()
    name = clean_text(data.get("name"), 100)
    email = clean_text(data.get("email"), 150).lower()
    password = str(data.get("password") or "")
    if len(name) < 2:
        raise ApiError("Please enter your name.")
    if not EMAIL_PATTERN.match(email):
        raise ApiError("Please enter a valid email.")
    if (len(password) < 8 or len(password) > 64 or not any(c.isdigit() for c in password)
            or not any(c.isalpha() for c in password)):
        raise ApiError("Password needs 8-64 characters with letters and numbers.")
    if query_one("SELECT user_id FROM users WHERE email = %s", (email,)):
        raise ApiError("This email is already registered.")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        run("INSERT INTO users (name, email, password_hash, role, status) "
            "VALUES (%s, %s, %s, 'Customer', 'Active')", (name, email, hashed))
    except mysql.connector.IntegrityError:
        raise ApiError("This email is already registered.")
    return jsonify({"message": "Registered! Please log in."})


@app.post("/api/login")
def api_login():
    data = json_body()
    email = clean_text(data.get("email"), 150).lower()
    password = str(data.get("password") or "")
    role = data.get("role")
    bad = ApiError("Invalid email or password.")  # same message for every failure
    if role not in ("Customer", "Admin") or len(password) > 72:
        raise bad
    row = query_one("SELECT user_id, name, password_hash, role, status FROM users "
                    "WHERE email = %s", (email,))
    if row is None or row["role"] != role:
        raise bad
    if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        raise bad
    if row["status"] != "Active":
        raise ApiError("Your account is blocked. Contact the administrator.", 403)
    session.clear()
    session["user_id"] = row["user_id"]
    return jsonify({"redirect": "/admin" if role == "Admin" else "/customer"})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def api_me():
    user = current_user()
    if user is None:
        return jsonify({"error": "Please log in."}), 401
    return jsonify({"name": user["name"], "role": user["role"]})


# =====================================================================
# PART 8: CUSTOMER API
# =====================================================================
@app.get("/api/customer/summary")
@api_required("Customer")
def customer_summary():
    uid = g.user["user_id"]
    categories = category_summary(uid)
    monthly = monthly_summary(uid)
    spent = [m["expenses"] for m in monthly if m["expenses"] > 0]
    return jsonify({
        "totals": get_totals(uid),
        "monthly": monthly,
        "categories": categories,
        "highest_category": categories[0] if categories else None,
        "avg_monthly_expense": round(sum(spent) / len(spent), 2) if spent else 0,
    })


@app.post("/api/customer/income")
@api_required("Customer")
def add_income():
    data = json_body()
    source = parse_choice(data.get("source"), INCOME_SOURCES, "income source")
    amount = parse_amount(data.get("amount"))
    when = parse_past_date(data.get("date"))
    description = clean_text(data.get("description"))
    add_record(g.user["user_id"], "Income",
               "INSERT INTO income (user_id, income_source, amount, income_date, description) "
               "VALUES (%s, %s, %s, %s, %s)",
               (source, amount, when, description or None), when, description or f"Income: {source}")
    return jsonify({"message": "Income saved."})


@app.post("/api/customer/expense")
@api_required("Customer")
def add_expense():
    data = json_body()
    category = parse_choice(data.get("category"), CATEGORIES, "category")
    method = parse_choice(data.get("payment_method"), PAYMENTS, "payment method")
    amount = parse_amount(data.get("amount"))
    when = parse_past_date(data.get("date"))
    description = clean_text(data.get("description"))
    add_record(g.user["user_id"], "Expense",
               "INSERT INTO expenses (user_id, category, amount, expense_date, "
               "payment_method, description) VALUES (%s, %s, %s, %s, %s, %s)",
               (category, amount, when, method, description or None), when,
               description or f"Expense: {category}")
    return jsonify({"message": "Expense saved."})


@app.post("/api/customer/saving")
@api_required("Customer")
def add_saving():
    data = json_body()
    goal = clean_text(data.get("goal"), 100) or "General"
    amount = parse_amount(data.get("amount"))
    when = parse_past_date(data.get("date"))
    add_record(g.user["user_id"], "Saving",
               "INSERT INTO saving (user_id, amount, saving_date, goal, description) "
               "VALUES (%s, %s, %s, %s, %s)",
               (amount, when, goal, f"Saved for {goal}"), when, f"Saved for {goal}")
    return jsonify({"message": "Savings saved."})


@app.get("/api/customer/savings-by-goal")
@api_required("Customer")
def savings_by_goal():
    rows = query("SELECT goal, SUM(amount) AS saved FROM saving WHERE user_id = %s "
                 "GROUP BY goal ORDER BY saved DESC", (g.user["user_id"],))
    return jsonify({"rows": rows})


@app.get("/api/customer/history")
@api_required("Customer")
def customer_history():
    start, end, _ = get_filters()
    tx_type = request.args.get("type") or None
    if tx_type:
        parse_choice(tx_type, TX_TYPES, "type")
    return jsonify({"rows": history(g.user["user_id"], start, end, tx_type)})


@app.delete("/api/customer/transactions/<int:transaction_id>")
@api_required("Customer")
def remove_transaction(transaction_id):
    delete_transaction(g.user["user_id"], transaction_id)
    return jsonify({"message": "Record deleted."})


# =====================================================================
# PART 9: ADMIN API
# =====================================================================
@app.get("/api/admin/overview")
@api_required("Admin")
def admin_overview():
    start, end, customer_id = get_filters()
    where, params = where_clause("expense_date", customer_id, start, end)
    amounts = query(f"SELECT amount FROM expenses {where}", params)
    return jsonify({
        "kpis": admin_kpis(start, end, customer_id),
        "monthly": monthly_summary(customer_id, start, end),
        "categories": category_summary(customer_id, start, end),
        "top_customers": customer_wise("expenses", "total_expense", start, end, customer_id)[:5],
        "income_by_customer": customer_wise("income", "total_income", start, end, customer_id),
        "expense_amounts": [row["amount"] for row in amounts],
    })


@app.get("/api/admin/customers")
@api_required("Admin")
def admin_customers():
    search = (request.args.get("search") or "").strip()
    like = f"%{search}%"
    rows = query("SELECT user_id, name, email, status, created_at FROM users "
                 "WHERE role = 'Customer' AND (name LIKE %s OR email LIKE %s) ORDER BY name",
                 (like, like))
    return jsonify({"rows": rows})


@app.get("/api/admin/customers/<int:customer_id>/summary")
@api_required("Admin")
def admin_customer_summary(customer_id):
    info = query_one("SELECT user_id, name, email, status, created_at FROM users "
                     "WHERE user_id = %s AND role = 'Customer'", (customer_id,))
    if info is None:
        raise ApiError("Customer not found.", 404)
    return jsonify({"info": info, "totals": get_totals(customer_id)})


@app.post("/api/admin/customers/<int:customer_id>/status")
@api_required("Admin")
def admin_set_status(customer_id):
    status = parse_choice(json_body().get("status"), ["Active", "Blocked"], "status")
    run("UPDATE users SET status = %s WHERE user_id = %s AND role = 'Customer'",
        (status, customer_id))
    return jsonify({"message": f"Customer is now {status}."})


@app.get("/api/admin/transactions")
@api_required("Admin")
def admin_transactions():
    start, end, customer_id = get_filters()
    tx_type = request.args.get("type") or None
    if tx_type:
        parse_choice(tx_type, TX_TYPES, "type")
    return respond(history(customer_id, start, end, tx_type), "transactions")


@app.get("/api/admin/statistics")
@api_required("Admin")
def admin_statistics():
    start, end, customer_id = get_filters()
    where, params = where_clause("expense_date", customer_id, start, end)
    rows = query(f"SELECT category, amount FROM expenses {where}", params)
    per_customer = customer_wise("expenses", "total_expense", start, end, customer_id)
    if not rows:
        return jsonify({"stats": None, "notes": [], "per_customer": per_customer,
                        "expense_amounts": []})
    amounts = np.array([row["amount"] for row in rows], dtype=float)
    mode_category = pd.Series([row["category"] for row in rows]).mode().iloc[0]
    ddof = 1 if len(amounts) > 1 else 0  # sample standard deviation and variance
    mean, median = float(np.mean(amounts)), float(np.median(amounts))
    std, variance = float(np.std(amounts, ddof=ddof)), float(np.var(amounts, ddof=ddof))
    notes = []
    if median > 0 and mean > median * 1.1:
        notes.append("The mean is higher than the median, so a few large expenses pull the "
                     "average up. The median is the better 'typical expense'.")
    elif median > 0 and mean < median * 0.9:
        notes.append("The mean is lower than the median, so a few very small expenses pull "
                     "the average down.")
    else:
        notes.append("The mean and median are close, so spending is fairly balanced.")
    if mean > 0:
        cv = std / mean * 100
        level = "very high" if cv > 100 else "moderate" if cv > 50 else "low"
        notes.append(f"Variation is {level}: the standard deviation is {cv:.0f}% of the mean.")
    stats = {"count": int(len(amounts)), "total": float(amounts.sum()), "mean": mean,
             "median": median, "mode_category": mode_category, "min": float(amounts.min()),
             "max": float(amounts.max()), "std_dev": std, "variance": variance}
    return jsonify({"stats": {k: round(v, 2) if isinstance(v, float) else v
                              for k, v in stats.items()},
                    "notes": notes, "per_customer": per_customer,
                    "expense_amounts": amounts.tolist()})


@app.get("/api/admin/reports/<name>")
@api_required("Admin")
def admin_reports(name):
    start, end, customer_id = get_filters()
    if name == "monthly":
        rows = monthly_summary(customer_id, start, end)
        return respond(rows, "monthly_report")
    if name == "customers":
        return respond(customer_summary_report(start, end, customer_id), "customer_summary")
    if name == "categories":
        return respond(category_summary(customer_id, start, end), "expense_categories")
    raise ApiError("Unknown report.", 404)


if __name__ == "__main__":
    # debug is OFF by default because the debugger lets anyone run code.
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
