"""STEP 1: Creates the database, the 5 tables and sample data (amounts in rupees).

Run once:  python setup_db.py
Running it again RESETS everything.

Demo logins
  Admin:    admin@finance.com  / Admin@123
  Customer: aarav@example.com  / Customer@123
"""
import os
import random
from datetime import date

import bcrypt
import mysql.connector

random.seed(1)  # same sample data every time

# ---------------------------------------------------------------- tables
TABLES = [
    "DROP TABLE IF EXISTS transactions",
    "DROP TABLE IF EXISTS saving",
    "DROP TABLE IF EXISTS expenses",
    "DROP TABLE IF EXISTS income",
    "DROP TABLE IF EXISTS users",
    """CREATE TABLE users (
        user_id       INT AUTO_INCREMENT PRIMARY KEY,
        name          VARCHAR(100) NOT NULL,
        email         VARCHAR(150) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        role          ENUM('Customer', 'Admin') NOT NULL DEFAULT 'Customer',
        status        ENUM('Active', 'Blocked') NOT NULL DEFAULT 'Active',
        created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE income (
        income_id     INT AUTO_INCREMENT PRIMARY KEY,
        user_id       INT NOT NULL,
        income_source ENUM('Salary', 'Freelance', 'Business', 'Other') NOT NULL,
        amount        DECIMAL(12, 2) NOT NULL CHECK (amount > 0),
        income_date   DATE NOT NULL,
        description   VARCHAR(255),
        created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE expenses (
        expense_id     INT AUTO_INCREMENT PRIMARY KEY,
        user_id        INT NOT NULL,
        category       ENUM('Food', 'Rent', 'Shopping', 'Travel', 'Education',
                            'Healthcare', 'Entertainment', 'Other') NOT NULL,
        amount         DECIMAL(12, 2) NOT NULL CHECK (amount > 0),
        expense_date   DATE NOT NULL,
        payment_method ENUM('Cash', 'UPI', 'Credit Card', 'Debit Card', 'Net Banking') NOT NULL,
        description    VARCHAR(255),
        created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE saving (
        saving_id   INT AUTO_INCREMENT PRIMARY KEY,
        user_id     INT NOT NULL,
        amount      DECIMAL(12, 2) NOT NULL CHECK (amount > 0),
        saving_date DATE NOT NULL,
        goal        VARCHAR(100),
        description VARCHAR(255),
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )""",
    # transactions = activity history. It stores a reference, NOT the amount.
    """CREATE TABLE transactions (
        transaction_id   INT AUTO_INCREMENT PRIMARY KEY,
        user_id          INT NOT NULL,
        transaction_type ENUM('Income', 'Expense', 'Saving') NOT NULL,
        reference_id     INT NOT NULL,
        transaction_date DATE NOT NULL,
        description      VARCHAR(255),
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    )""",
]

# ----------------------------------------------------------- sample data
CUSTOMERS = [  # name, email, monthly salary, status
    ("Aarav Sharma", "aarav@example.com", 45000, "Active"),
    ("Priya Verma", "priya@example.com", 62000, "Active"),
    ("Rohan Gupta", "rohan@example.com", 38000, "Active"),
    ("Sneha Patel", "sneha@example.com", 75000, "Active"),
    ("Karan Mehta", "karan@example.com", 30000, "Blocked"),
]
EXPENSE_RANGES = {  # category: (how many per month, min amount, max amount)
    "Food": (8, 150, 900),
    "Travel": (4, 100, 2000),
    "Shopping": (3, 400, 6000),
    "Entertainment": (2, 200, 1800),
    "Healthcare": (1, 300, 3500),
}
PAYMENTS = ["UPI", "UPI", "UPI", "Debit Card", "Credit Card", "Cash"]

INSERT_INCOME = ("INSERT INTO income (user_id, income_source, amount, income_date, description) "
                 "VALUES (%s, %s, %s, %s, %s)")
INSERT_EXPENSE = ("INSERT INTO expenses (user_id, category, amount, expense_date, "
                  "payment_method, description) VALUES (%s, %s, %s, %s, %s, %s)")
INSERT_SAVING = ("INSERT INTO saving (user_id, amount, saving_date, goal, description) "
                 "VALUES (%s, %s, %s, %s, %s)")


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def month_start(months_ago):
    year, month = date.today().year, date.today().month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def pick_date(months_ago, day):
    """A date in that month that is never in the future."""
    last_day = date.today().day if months_ago == 0 else 28
    return month_start(months_ago).replace(day=min(day, last_day))


def add_record(cur, user_id, tx_type, sql, values, tx_date, description):
    """Insert a record AND its matching row in the transactions table."""
    cur.execute(sql, (user_id, *values))
    cur.execute(
        "INSERT INTO transactions (user_id, transaction_type, reference_id, "
        "transaction_date, description) VALUES (%s, %s, %s, %s, %s)",
        (user_id, tx_type, cur.lastrowid, tx_date, description))


def main():
    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""))
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS finance_dashboard CHARACTER SET utf8mb4")
    cur.execute("USE finance_dashboard")
    for statement in TABLES:
        cur.execute(statement)

    cur.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'Admin')",
                ("Admin User", "admin@finance.com", hash_password("Admin@123")))

    for name, email, salary, status in CUSTOMERS:
        cur.execute("INSERT INTO users (name, email, password_hash, role, status) "
                    "VALUES (%s, %s, %s, 'Customer', %s)",
                    (name, email, hash_password("Customer@123"), status))
        uid = cur.lastrowid
        factor = salary / 50000  # richer customers spend more
        for months_ago in range(5, -1, -1):  # 6 months of data
            d = pick_date(months_ago, 1)
            add_record(cur, uid, "Income", INSERT_INCOME,
                       ("Salary", salary, d, "Monthly salary"), d, "Monthly salary")
            d = pick_date(months_ago, 5)
            rent = round(salary * 0.25 / 500) * 500
            add_record(cur, uid, "Expense", INSERT_EXPENSE,
                       ("Rent", rent, d, "Net Banking", "Monthly rent"), d, "Monthly rent")
            for category, (count, low, high) in EXPENSE_RANGES.items():
                for _ in range(count):
                    d = pick_date(months_ago, random.randint(1, 28))
                    amount = max(round(random.uniform(low, high) * factor / 10) * 10, 10)
                    add_record(cur, uid, "Expense", INSERT_EXPENSE,
                               (category, amount, d, random.choice(PAYMENTS),
                                f"{category} expense"), d, f"{category} expense")
            d = pick_date(months_ago, 28)
            saved = max(round(salary * random.uniform(0.04, 0.10) / 100) * 100, 500)
            add_record(cur, uid, "Saving", INSERT_SAVING,
                       (saved, d, "Emergency Fund", "Monthly saving"), d, "Monthly saving")

    conn.commit()
    for table in ("users", "income", "expenses", "saving", "transactions"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"{table}: {cur.fetchone()[0]} rows")
    conn.close()
    print("Done. Now run:  python app.py")


if __name__ == "__main__":
    main()
