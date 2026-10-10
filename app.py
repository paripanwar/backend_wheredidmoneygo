
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import date

app = Flask(__name__)
CORS(app)

DATABASE = "money_tracker.db"

CATEGORIES = [
    "Food", "Shopping", "Travel", "Entertainment",
    "Education", "Bills", "Health", "Other"
]


def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def initialize_database():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                expense_date TEXT NOT NULL,
                note TEXT DEFAULT ''
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                monthly_budget REAL DEFAULT 0,
                savings_goal REAL DEFAULT 0,
                savings_goal_name TEXT DEFAULT 'My savings goal'
            )
        """)

        db.execute("""
            INSERT OR IGNORE INTO settings (id)
            VALUES (1)
        """)


@app.route("/")
def home():
    return jsonify({
        "message": "Where Did My Money Go? API is running!",
        "endpoints": [
            "GET /api/expenses",
            "POST /api/expenses",
            "PUT /api/expenses/<id>",
            "DELETE /api/expenses/<id>",
            "GET /api/summary",
            "GET /api/settings",
            "PUT /api/settings"
        ]
    })


# Get all expenses
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    month = request.args.get("month")

    with get_db() as db:
        if month:
            rows = db.execute("""
                SELECT * FROM expenses
                WHERE substr(expense_date, 1, 7) = ?
                ORDER BY expense_date DESC, id DESC
            """, (month,)).fetchall()
        else:
            rows = db.execute("""
                SELECT * FROM expenses
                ORDER BY expense_date DESC, id DESC
            """).fetchall()

    return jsonify([dict(row) for row in rows])


# Add a new expense
@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.get_json(silent=True) or {}

    title = str(data.get("title", "")).strip()
    category = data.get("category", "Other")
    note = str(data.get("note", "")).strip()
    expense_date = data.get(
        "expense_date", date.today().isoformat()
    )

    try:
        amount = float(data.get("amount", 0))
        date.fromisoformat(expense_date)
    except (ValueError, TypeError):
        return jsonify({"error": "Enter a valid amount and date."}), 400

    if not title:
        return jsonify({"error": "Expense title is required."}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400

    if category not in CATEGORIES:
        return jsonify({"error": "Invalid expense category."}), 400

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO expenses
            (title, amount, category, expense_date, note)
            VALUES (?, ?, ?, ?, ?)
        """, (title, round(amount, 2), category, expense_date, note))

        row = db.execute(
            "SELECT * FROM expenses WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

    return jsonify(dict(row)), 201


# Edit an expense
@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    data = request.get_json(silent=True) or {}

    with get_db() as db:
        old = db.execute(
            "SELECT * FROM expenses WHERE id = ?",
            (expense_id,)
        ).fetchone()

        if not old:
            return jsonify({"error": "Expense not found."}), 404

        title = str(data.get("title", old["title"])).strip()
        category = data.get("category", old["category"])
        note = str(data.get("note", old["note"] or "")).strip()
        expense_date = data.get(
            "expense_date", old["expense_date"]
        )

        try:
            amount = float(data.get("amount", old["amount"]))
            date.fromisoformat(expense_date)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid amount or date."}), 400

        if not title or amount <= 0 or category not in CATEGORIES:
            return jsonify({"error": "Check the expense details."}), 400

        db.execute("""
            UPDATE expenses
            SET title = ?, amount = ?, category = ?,
                expense_date = ?, note = ?
            WHERE id = ?
        """, (
            title, round(amount, 2), category,
            expense_date, note, expense_id
        ))

        updated = db.execute(
            "SELECT * FROM expenses WHERE id = ?",
            (expense_id,)
        ).fetchone()

    return jsonify(dict(updated))


# Delete an expense
@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    with get_db() as db:
        cursor = db.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,)
        )

    if cursor.rowcount == 0:
        return jsonify({"error": "Expense not found."}), 404

    return jsonify({"message": "Expense deleted successfully."})


# Monthly spending summary and category breakdown
@app.route("/api/summary", methods=["GET"])
def get_summary():
    month = request.args.get(
        "month", date.today().strftime("%Y-%m")
    )

    with get_db() as db:
        total = db.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_spent,
                   COUNT(*) AS transaction_count
            FROM expenses
            WHERE substr(expense_date, 1, 7) = ?
        """, (month,)).fetchone()

        categories = db.execute("""
            SELECT category, ROUND(SUM(amount), 2) AS total
            FROM expenses
            WHERE substr(expense_date, 1, 7) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (month,)).fetchall()

        settings = db.execute(
            "SELECT * FROM settings WHERE id = 1"
        ).fetchone()

    spent = round(float(total["total_spent"]), 2)
    budget = float(settings["monthly_budget"])

    return jsonify({
        "month": month,
        "total_spent": spent,
        "transaction_count": total["transaction_count"],
        "monthly_budget": budget,
        "budget_remaining": round(budget - spent, 2),
        "category_breakdown": [
            dict(row) for row in categories
        ]
    })


# View budget and savings goal
@app.route("/api/settings", methods=["GET"])
def get_settings():
    with get_db() as db:
        settings = db.execute(
            "SELECT * FROM settings WHERE id = 1"
        ).fetchone()

    return jsonify(dict(settings))


# Update budget and savings goal
@app.route("/api/settings", methods=["PUT"])
def update_settings():
    data = request.get_json(silent=True) or {}

    with get_db() as db:
        old = db.execute(
            "SELECT * FROM settings WHERE id = 1"
        ).fetchone()

        try:
            budget = float(data.get(
                "monthly_budget", old["monthly_budget"]
            ))
            goal = float(data.get(
                "savings_goal", old["savings_goal"]
            ))
        except (ValueError, TypeError):
            return jsonify({"error": "Enter valid numbers."}), 400

        if budget < 0 or goal < 0:
            return jsonify({"error": "Values cannot be negative."}), 400

        goal_name = str(data.get(
            "savings_goal_name", old["savings_goal_name"]
        )).strip() or "My savings goal"

        db.execute("""
            UPDATE settings
            SET monthly_budget = ?, savings_goal = ?,
                savings_goal_name = ?
            WHERE id = 1
        """, (budget, goal, goal_name))

        updated = db.execute(
            "SELECT * FROM settings WHERE id = 1"
        ).fetchone()

    return jsonify(dict(updated))


initialize_database()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
