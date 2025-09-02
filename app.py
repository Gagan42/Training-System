from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change this for production

DB_NAME = "users.db"

# ----------------- Initialize Database -----------------


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            userType TEXT CHECK(userType IN ('admin', 'trainer', 'student')) NOT NULL,
            email TEXT,
            phoneNumber TEXT,
            createDate DATE,
            updatedDate DATE,
            lastUpdatedBy TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("Database initialized!")

# ----------------- Home Page -----------------


@app.route("/")
def home():
    if "user" in session:
        return render_template("home.html", user=session["user"])
    flash("Please login first.", "info")
    return redirect(url_for("login"))

# ----------------- Register -----------------


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        userType = request.form.get("userType")
        email = request.form.get("email")
        phoneNumber = request.form.get("phoneNumber")

        # Validation
        if not username or not password or not userType:
            flash("Username, password, and user type are required.", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, password, userType, email, phoneNumber, createDate, updatedDate, lastUpdatedBy)
                VALUES (?, ?, ?, ?, ?, DATE('now'), DATE('now'), ?)
            """, (username, hashed_pw, userType, email, phoneNumber, username))
            conn.commit()
            conn.close()

            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Username already exists!", "danger")
            return redirect(url_for("register"))

    return render_template("register.html")

# ----------------- Login -----------------


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user"] = username
            flash("Login successful!", "success")
            return redirect(url_for("home"))
        else:
            flash("Invalid username or password!", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

# ----------------- Logout -----------------


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ----------------- Run App -----------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
