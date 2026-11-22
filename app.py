"""Financial Management & Statistical Dashboard (simple version).

Run:  streamlit run app.py
The file has 6 parts, top to bottom:
  1. Database helpers      4. Customer pages
  2. Calculations          5. Admin pages
  3. Login / register      6. Main program
"""
import os
from datetime import date
from decimal import Decimal

import bcrypt
import mysql.connector
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Financial Dashboard", page_icon="💰", layout="wide")

INCOME_SOURCES = ["Salary", "Freelance", "Business", "Other"]
CATEGORIES = ["Food", "Rent", "Shopping", "Travel", "Education",
              "Healthcare", "Entertainment", "Other"]
PAYMENTS = ["Cash", "UPI", "Credit Card", "Debit Card", "Net Banking"]
TX_TYPES = ["Income", "Expense", "Saving"]
# transaction type -> (table, id column). Used when deleting a record.
TABLES = {"Income": ("income", "income_id"),
          "Expense": ("expenses", "expense_id"),
          "Saving": ("saving", "saving_id")}


# =====================================================================
# PART 1: DATABASE HELPERS
# =====================================================================
def get_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database="finance_dashboard")


def query(sql, params=()):
    """Run a SELECT and return the result as a Pandas table (DataFrame)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [[float(v) if isinstance(v, Decimal) else v for v in row]
                for row in cur.fetchall()]
        df = pd.DataFrame(rows, columns=cur.column_names)
        cur.close()
    finally:
        conn.close()
    return df


def run(sql, params=()):
    """Run an INSERT / UPDATE / DELETE."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
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
        if row:
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


# =====================================================================
# PART 2: CALCULATIONS (SQL + Pandas + NumPy)
# =====================================================================
def rupee(value):
    return f"₹{float(value):,.2f}"


def total(table, user_id=None):
    """SUM of the amount column. user_id=None means all customers."""
    sql = f"SELECT COALESCE(SUM(amount), 0) AS t FROM {table}"
    params = ()
    if user_id is not None:
        sql += " WHERE user_id = %s"
        params = (user_id,)
    return float(query(sql, params)["t"][0])


def savings_percent(income, expenses):
    """Savings % = (Income - Expenses) / Income x 100 (only if income > 0)."""
    return (income - expenses) / income * 100 if income > 0 else 0.0


def month_sql(column):
    """SQL that turns a date into 'YYYY-MM' (year AND month together)."""
    return f"CONCAT(YEAR({column}), '-', LPAD(MONTH({column}), 2, '0'))"


def monthly_summary(user_id=None):
    """One row per month: income, expenses, net savings."""
    where, params = ("WHERE user_id = %s", (user_id,)) if user_id is not None else ("", ())
    inc = query(f"SELECT {month_sql('income_date')} AS `month`, SUM(amount) AS income "
                f"FROM income {where} GROUP BY `month`", params)
    exp = query(f"SELECT {month_sql('expense_date')} AS `month`, SUM(amount) AS expenses "
                f"FROM expenses {where} GROUP BY `month`", params)
    df = inc.merge(exp, on="month", how="outer")
    if df.empty:
        return pd.DataFrame(columns=["month", "income", "expenses", "net_savings"])
    df[["income", "expenses"]] = df[["income", "expenses"]].fillna(0).astype(float)
    df = df.sort_values("month").reset_index(drop=True)
    df["net_savings"] = df["income"] - df["expenses"]
    return df


def category_summary(user_id=None):
    where, params = ("WHERE user_id = %s", (user_id,)) if user_id is not None else ("", ())
    return query("SELECT category, SUM(amount) AS total FROM expenses "
                 f"{where} GROUP BY category ORDER BY total DESC", params)


def history(user_id=None, start=None, end=None, tx_type="All"):
    """Transaction history. The amount is READ from the source table, not copied."""
    conditions, params = [], []
    if user_id is not None:
        conditions.append("t.user_id = %s")
        params.append(user_id)
    if start:
        conditions.append("t.transaction_date >= %s")
        params.append(start)
    if end:
        conditions.append("t.transaction_date <= %s")
        params.append(end)
    if tx_type != "All":
        conditions.append("t.transaction_type = %s")
        params.append(tx_type)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
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
        f"{where} ORDER BY t.transaction_date DESC, t.transaction_id DESC", tuple(params))


def show_chart(fig_or_none):
    if fig_or_none is None:
        st.info("No data yet.")
    else:
        st.plotly_chart(fig_or_none)


def income_vs_expense_chart(df):
    if df.empty:
        return None
    long_df = df.melt(id_vars="month", value_vars=["income", "expenses"],
                      var_name="Type", value_name="Amount (₹)")
    return px.bar(long_df, x="month", y="Amount (₹)", color="Type", barmode="group",
                  title="Monthly Income vs Expenses", template="plotly_white")


def savings_trend_chart(df):
    if df.empty:
        return None
    return px.line(df, x="month", y="net_savings", markers=True,
                   title="Monthly Net Savings (Income − Expenses)",
                   labels={"net_savings": "Net savings (₹)"}, template="plotly_white")


def category_pie_chart(df):
    if df.empty:
        return None
    return px.pie(df, names="category", values="total", hole=0.4,
                  title="Expenses by Category", template="plotly_white")


def download_button(df, file_name, key):
    st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=file_name, mime="text/csv", key=key)


# =====================================================================
# PART 3: LOGIN AND REGISTER
# =====================================================================
def register(name, email, password):
    name, email = name.strip(), email.strip().lower()
    if len(name) < 2:
        return False, "Please enter your name."
    if "@" not in email or "." not in email:
        return False, "Please enter a valid email."
    if (len(password) < 8 or len(password) > 64 or not any(c.isdigit() for c in password)
            or not any(c.isalpha() for c in password)):
        return False, "Password needs 8-64 characters with letters and numbers."
    if not query("SELECT user_id FROM users WHERE email = %s", (email,)).empty:
        return False, "This email is already registered."
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    run("INSERT INTO users (name, email, password_hash, role, status) "
        "VALUES (%s, %s, %s, 'Customer', 'Active')", (name, email, hashed))
    return True, "Registered! Please log in."


def login(email, password, role):
    """Returns (user, None) if correct, else (None, error message)."""
    bad = (None, "Invalid email or password.")
    df = query("SELECT user_id, name, password_hash, role, status FROM users "
               "WHERE email = %s", (email.strip().lower(),))
    if df.empty or len(password) > 72:
        return bad
    row = df.iloc[0]
    if row["role"] != role or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return bad
    if row["status"] != "Active":
        return None, "Your account is blocked. Contact the administrator."
    return {"user_id": int(row["user_id"]), "name": row["name"], "role": row["role"]}, None


def login_form(form_name, role):
    with st.form(form_name):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user, error = login(email, password, role)
        if error:
            st.error(error)
        else:
            st.session_state["user"] = user
            st.rerun()


def login_screen():
    st.title("💰 Financial Management & Statistical Dashboard")
    tab1, tab2, tab3 = st.tabs(["Customer Login", "Register", "Admin Login"])
    with tab1:
        login_form("customer_login", "Customer")
    with tab2:
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password (8+ characters, letters and numbers)",
                                     type="password", key="reg_pw")
            submitted = st.form_submit_button("Create account")
        if submitted:
            ok, message = register(name, email, password)
            (st.success if ok else st.error)(message)
    with tab3:
        login_form("admin_login", "Admin")


# =====================================================================
# PART 4: CUSTOMER PAGES
# =====================================================================
def customer_dashboard(uid, name):
    st.header(f"Welcome, {name}")
    income, expenses = total("income", uid), total("expenses", uid)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total income", rupee(income))
    c2.metric("Total expenses", rupee(expenses))
    c3.metric("Net savings", rupee(income - expenses))
    c4.metric("Savings %", f"{savings_percent(income, expenses):.2f}%")
    st.metric("Recorded savings (money set aside)", rupee(total("saving", uid)))
    st.caption("Net savings = Income − Expenses (calculated). "
               "Recorded savings are deposits you added, tracked separately.")

    monthly = monthly_summary(uid)
    categories = category_summary(uid)
    col1, col2 = st.columns(2)
    if categories.empty:
        col1.metric("Highest spending category", "N/A")
    else:
        top = categories.iloc[0]
        col1.metric("Highest spending category", f"{top['category']} ({rupee(top['total'])})")
    spent = monthly[monthly["expenses"] > 0]["expenses"]
    col2.metric("Average monthly expenses", rupee(spent.mean() if len(spent) else 0))

    show_chart(income_vs_expense_chart(monthly))
    show_chart(savings_trend_chart(monthly))
    show_chart(category_pie_chart(categories))


def add_income_page(uid):
    st.header("Add Income")
    with st.form("income_form", clear_on_submit=True):
        source = st.selectbox("Income source", INCOME_SOURCES)
        amount = st.number_input("Amount (₹)", min_value=0.0, step=500.0, format="%.2f")
        d = st.date_input("Date", value=date.today())
        desc = st.text_input("Description", max_chars=255)
        submitted = st.form_submit_button("Save income")
    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        elif d > date.today():
            st.error("Date cannot be in the future.")
        else:
            add_record(uid, "Income",
                       "INSERT INTO income (user_id, income_source, amount, income_date, description) "
                       "VALUES (%s, %s, %s, %s, %s)",
                       (source, round(amount, 2), d, desc or None), d, desc or f"Income: {source}")
            st.success("Income saved.")


def add_expense_page(uid):
    st.header("Add Expense")
    with st.form("expense_form", clear_on_submit=True):
        category = st.selectbox("Category", CATEGORIES)
        amount = st.number_input("Amount (₹)", min_value=0.0, step=100.0, format="%.2f")
        d = st.date_input("Date", value=date.today())
        method = st.selectbox("Payment method", PAYMENTS)
        desc = st.text_input("Description", max_chars=255)
        submitted = st.form_submit_button("Save expense")
    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        elif d > date.today():
            st.error("Date cannot be in the future.")
        else:
            add_record(uid, "Expense",
                       "INSERT INTO expenses (user_id, category, amount, expense_date, "
                       "payment_method, description) VALUES (%s, %s, %s, %s, %s, %s)",
                       (category, round(amount, 2), d, method, desc or None), d,
                       desc or f"Expense: {category}")
            st.success("Expense saved.")


def savings_page(uid):
    st.header("Savings")
    with st.form("saving_form", clear_on_submit=True):
        goal = st.text_input("Goal name (for example: New Laptop)", value="General", max_chars=100)
        amount = st.number_input("Amount (₹)", min_value=0.0, step=500.0, format="%.2f")
        d = st.date_input("Date", value=date.today())
        submitted = st.form_submit_button("Save savings")
    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        elif d > date.today():
            st.error("Date cannot be in the future.")
        else:
            goal = goal.strip() or "General"
            add_record(uid, "Saving",
                       "INSERT INTO saving (user_id, amount, saving_date, goal, description) "
                       "VALUES (%s, %s, %s, %s, %s)",
                       (round(amount, 2), d, goal, f"Saved for {goal}"), d, f"Saved for {goal}")
            st.success("Savings saved.")
    st.subheader("Savings by goal")
    by_goal = query("SELECT goal, SUM(amount) AS saved FROM saving WHERE user_id = %s "
                    "GROUP BY goal ORDER BY saved DESC", (uid,))
    st.dataframe(by_goal, hide_index=True)
    if not by_goal.empty:
        show_chart(px.bar(by_goal, x="goal", y="saved", title="Savings by Goal",
                          labels={"saved": "Saved (₹)"}, template="plotly_white"))


def history_page(uid):
    st.header("Transaction History")
    c1, c2, c3 = st.columns(3)
    start = c1.date_input("From date", value=None, key="h_from")
    end = c2.date_input("To date", value=None, key="h_to")
    tx_type = c3.selectbox("Type", ["All"] + TX_TYPES)
    df = history(uid, start, end, tx_type).drop(columns="customer")
    st.write(f"{len(df)} record(s)")
    st.dataframe(df, hide_index=True)
    if not df.empty:
        st.subheader("Delete a record")
        tid = int(st.selectbox("Transaction ID", df["transaction_id"].tolist()))
        if st.button("Delete this record"):
            delete_transaction(uid, tid)
            st.rerun()


# =====================================================================
# PART 5: ADMIN PAGES
# =====================================================================
def admin_dashboard():
    st.header("Admin Dashboard")
    counts = query("SELECT COUNT(*) AS total, "
                   "COALESCE(SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END), 0) AS active "
                   "FROM users WHERE role = 'Customer'")
    customers, active = int(counts["total"][0]), int(counts["active"][0])
    income, expenses, saved = total("income"), total("expenses"), total("saving")
    highest = float(query("SELECT COALESCE(MAX(amount), 0) AS m FROM expenses")["m"][0])

    c = st.columns(4)
    c[0].metric("Registered customers", customers)
    c[1].metric("Active customers", active)
    c[2].metric("Total income", rupee(income))
    c[3].metric("Total expenses", rupee(expenses))
    c = st.columns(4)
    c[0].metric("Total recorded savings", rupee(saved))
    c[1].metric("Avg customer income", rupee(income / customers if customers else 0))
    c[2].metric("Avg customer expenses", rupee(expenses / customers if customers else 0))
    c[3].metric("Highest expense", rupee(highest))

    monthly = monthly_summary()
    show_chart(income_vs_expense_chart(monthly))
    show_chart(savings_trend_chart(monthly))
    show_chart(category_pie_chart(category_summary()))

    top5 = query("SELECT u.name, SUM(e.amount) AS total_expense FROM users u "
                 "INNER JOIN expenses e ON u.user_id = e.user_id "
                 "GROUP BY u.user_id, u.name ORDER BY total_expense DESC LIMIT 5")
    if not top5.empty:
        show_chart(px.bar(top5, x="name", y="total_expense", title="Top 5 Customers by Expenses",
                          labels={"total_expense": "Expenses (₹)", "name": "Customer"},
                          template="plotly_white"))
    income_by_customer = query("SELECT u.name, SUM(i.amount) AS total_income FROM users u "
                               "INNER JOIN income i ON u.user_id = i.user_id "
                               "GROUP BY u.user_id, u.name ORDER BY total_income DESC")
    if not income_by_customer.empty:
        show_chart(px.bar(income_by_customer, x="name", y="total_income",
                          title="Customer-wise Income", template="plotly_white",
                          labels={"total_income": "Income (₹)", "name": "Customer"}))


def admin_customers():
    st.header("Customer Management")
    search = st.text_input("Search by name or email")
    like = f"%{search.strip()}%"
    df = query("SELECT user_id, name, email, status, created_at FROM users "
               "WHERE role = 'Customer' AND (name LIKE %s OR email LIKE %s) ORDER BY name",
               (like, like))
    st.dataframe(df, hide_index=True)
    if df.empty:
        return
    labels = {f"{r.name} (ID {r.user_id})": int(r.user_id) for r in df.itertuples()}
    uid = labels[st.selectbox("Select a customer", list(labels))]
    status = df[df["user_id"] == uid].iloc[0]["status"]
    income, expenses = total("income", uid), total("expenses", uid)
    c1, c2, c3 = st.columns(3)
    c1.metric("Income", rupee(income))
    c2.metric("Expenses", rupee(expenses))
    c3.metric("Savings %", f"{savings_percent(income, expenses):.2f}%")
    new_status = "Blocked" if status == "Active" else "Active"
    if st.button(f"{'Block' if status == 'Active' else 'Activate'} this customer"):
        run("UPDATE users SET status = %s WHERE user_id = %s AND role = 'Customer'",
            (new_status, uid))
        st.rerun()


def admin_transactions():
    st.header("Financial Monitoring")
    customers = query("SELECT user_id, name FROM users WHERE role = 'Customer' ORDER BY name")
    options = {"All customers": None}
    options.update({f"{r.name} (ID {r.user_id})": int(r.user_id) for r in customers.itertuples()})
    c1, c2, c3, c4 = st.columns(4)
    uid = options[c1.selectbox("Customer", list(options))]
    start = c2.date_input("From date", value=None, key="a_from")
    end = c3.date_input("To date", value=None, key="a_to")
    tx_type = c4.selectbox("Type", ["All"] + TX_TYPES, key="a_type")
    df = history(uid, start, end, tx_type)
    st.write(f"{len(df)} record(s)")
    st.dataframe(df, hide_index=True)
    download_button(df, "transactions.csv", "dl_tx")


def admin_statistics():
    st.header("Statistical Analysis of Expenses")
    df = query("SELECT category, amount FROM expenses")
    if df.empty:
        st.info("No expenses yet.")
        return
    amounts = df["amount"].to_numpy(dtype=float)
    mean, median = np.mean(amounts), np.median(amounts)
    std, var = np.std(amounts, ddof=1), np.var(amounts, ddof=1)

    c = st.columns(4)
    c[0].metric("Total", rupee(amounts.sum()))
    c[1].metric("Mean (average)", rupee(mean))
    c[2].metric("Median (middle)", rupee(median))
    c[3].metric("Mode (top category)", df["category"].mode()[0])
    c = st.columns(4)
    c[0].metric("Minimum", rupee(amounts.min()))
    c[1].metric("Maximum", rupee(amounts.max()))
    c[2].metric("Standard deviation", rupee(std))
    c[3].metric("Variance (₹²)", f"{var:,.2f}")

    st.subheader("How to read this")
    if mean > median * 1.1:
        st.write("- Mean is higher than median: a few large expenses pull the average up, "
                 "so the median is a better 'typical expense'.")
    else:
        st.write("- Mean and median are close: spending is fairly balanced.")
    st.write(f"- Standard deviation is {std / mean * 100:.0f}% of the mean: "
             f"{'expense sizes vary a lot.' if std > mean else 'expenses are fairly consistent.'}")

    show_chart(px.histogram(df, x="amount", nbins=20, title="Distribution of Expense Amounts",
                            labels={"amount": "Amount (₹)"}, template="plotly_white"))


def admin_reports():
    st.header("Reports")
    tab1, tab2, tab3 = st.tabs(["Monthly report", "Customer summary", "Expense categories"])
    with tab1:
        df = monthly_summary()
        df["savings_pct"] = np.where(df["income"] > 0,
                                     df["net_savings"] / df["income"] * 100, 0).round(2)
        st.dataframe(df, hide_index=True)
        download_button(df, "monthly_report.csv", "dl_monthly")
    with tab2:
        df = query(
            "SELECT u.name, COALESCE(i.total, 0) AS total_income, "
            "COALESCE(e.total, 0) AS total_expenses FROM users u "
            "LEFT JOIN (SELECT user_id, SUM(amount) AS total FROM income GROUP BY user_id) i "
            "ON u.user_id = i.user_id "
            "LEFT JOIN (SELECT user_id, SUM(amount) AS total FROM expenses GROUP BY user_id) e "
            "ON u.user_id = e.user_id WHERE u.role = 'Customer' ORDER BY u.name")
        df["net_savings"] = df["total_income"] - df["total_expenses"]
        df["savings_pct"] = np.where(df["total_income"] > 0,
                                     df["net_savings"] / df["total_income"] * 100, 0).round(2)
        st.dataframe(df, hide_index=True)
        download_button(df, "customer_summary.csv", "dl_customers")
    with tab3:
        df = category_summary()
        st.dataframe(df, hide_index=True)
        download_button(df, "expense_categories.csv", "dl_categories")


# =====================================================================
# PART 6: MAIN PROGRAM
# =====================================================================
def main():
    user = st.session_state.get("user")
    if user is None:
        login_screen()
        return

    # A customer blocked by the admin is logged out on the next click.
    status = query("SELECT status FROM users WHERE user_id = %s", (user["user_id"],))
    if status.empty or status["status"][0] != "Active":
        st.session_state.clear()
        st.rerun()

    st.sidebar.write(f"**{user['name']}**  \nRole: {user['role']}")
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()

    uid = user["user_id"]
    if user["role"] == "Customer":
        page = st.sidebar.radio("Menu", ["Dashboard", "Add Income", "Add Expense",
                                         "Savings", "Transaction History"])
        if page == "Dashboard":
            customer_dashboard(uid, user["name"])
        elif page == "Add Income":
            add_income_page(uid)
        elif page == "Add Expense":
            add_expense_page(uid)
        elif page == "Savings":
            savings_page(uid)
        else:
            history_page(uid)
    elif user["role"] == "Admin":
        page = st.sidebar.radio("Admin menu", ["Dashboard", "Customers", "Transactions",
                                               "Statistics", "Reports"])
        if page == "Dashboard":
            admin_dashboard()
        elif page == "Customers":
            admin_customers()
        elif page == "Transactions":
            admin_transactions()
        elif page == "Statistics":
            admin_statistics()
        else:
            admin_reports()


main()
