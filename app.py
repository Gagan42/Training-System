from flask import send_from_directory
from flask import Flask, render_template, request, redirect, url_for, session, flash, get_flashed_messages
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3
from werkzeug.utils import secure_filename
from datetime import datetime

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'pptx', 'txt'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = "your_secret_key"  # Change this for production

DB_NAME = "users.db"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ----------------- Initialize Database -----------------


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create users table
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

    # Create documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            uploaded_by INTEGER,
            upload_date DATE DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
    """)

    # Create training completions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS training_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            status TEXT CHECK(status IN ('pending','completed','failed')) DEFAULT 'pending',
            completed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (document_id) REFERENCES documents(id),
            UNIQUE(user_id, document_id) 
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized!")

# Check allowed extensions


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------- Home Page -----------------


@app.route("/")
def home():
    if "user" in session:
        # Get user info
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, email, phoneNumber, userType FROM users WHERE username = ?",
            (session['user'],)
        )
        user_info = cursor.fetchone()
        conn.close()

        # Check if user exists
        if not user_info:
            flash("User not found. Please login again.", "danger")
            session.clear()
            return redirect(url_for("login"))

        # Set session values correctly
        session['user_id'] = user_info[0]   # id (int)
        session['user'] = user_info[1]      # username (string)
        session['userType'] = user_info[4]  # admin/trainer/student

        # Get all documents
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.id, d.title, d.filename, u.username, d.upload_date, u.userType
            FROM documents d
            JOIN users u ON d.uploaded_by = u.id
            ORDER BY d.upload_date DESC
        """)
        documents = cursor.fetchall()

        # Fetch training status for current user
        training_status = {}
        cursor.execute(
            "SELECT document_id, status FROM training_completions WHERE user_id=?",
            (session['user_id'],)
        )
        for doc_id, status in cursor.fetchall():
            training_status[doc_id] = status
        conn.close()

        # For admin: fetch all trainers and students
        user_tables = {}
        if session['userType'] == 'admin':
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, email, phoneNumber, createDate FROM users WHERE userType='trainer'"
            )
            user_tables['trainers'] = cursor.fetchall()

            cursor.execute(
                "SELECT id, username, email, phoneNumber, createDate FROM users WHERE userType='student'"
            )
            user_tables['students'] = cursor.fetchall()
            conn.close()

        return render_template(
            "home.html",
            user=session["user"],
            documents=documents,
            training_status=training_status,
            user_tables=user_tables if session['userType'] == 'admin' else None
        )

    flash("Please login first.", "info")
    return redirect(url_for("login"))

# ----------------- Login -----------------


@app.route("/login", methods=["GET", "POST"])
def login():
    # Clear old flashes
    get_flashed_messages()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password, email, phoneNumber, userType FROM users WHERE username = ?",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user'] = user[1]
            session['email'] = user[3] or "N/A"
            session['phoneNumber'] = user[4] or "N/A"
            session['userType'] = user[5]

            flash("Login successful!", "success")
            return redirect(url_for("home"))
        else:
            flash("Invalid username or password!", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


# ----------------- Register -----------------


@app.route("/register", methods=["GET", "POST"])
def register():
    # Clear old flashes
    get_flashed_messages()

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


# ---------Upload Document (Admin/Trainer)-----


@app.route('/upload', methods=['POST'])
def upload_document():
    # Only admin/trainer can upload
    if 'user' not in session or session.get('userType') not in ['admin', 'trainer']:
        flash("Access denied!", "danger")
        return redirect(url_for('login'))

    title = request.form.get('title')
    file = request.files.get('file')

    if not title or not file:
        flash("Please provide both title and file.", "danger")
        return redirect(url_for('home'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Make sure the upload folder exists
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        # Save the file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Insert into documents table
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, userType FROM users WHERE username = ?", (session['user'],))
        user = cursor.fetchone()
        if not user:
            flash("User not found in database.", "danger")
            conn.close()
            return redirect(url_for('home'))

        user_id, user_type = user
        upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            "INSERT INTO documents (title, filename, uploaded_by, upload_date) VALUES (?, ?, ?, ?)",
            (title, filename, user_id, upload_date)
        )
        conn.commit()
        conn.close()

        flash("Document uploaded successfully!", "success")
    else:
        flash("Invalid file type! Allowed: pdf, docx, pptx, txt.", "danger")

    # Redirect back to home to show the document list
    return redirect(url_for('home'))


# -------------View Documents (Students)--------
@app.route('/documents')
def view_documents():
    if 'user' not in session:
        flash("Please login first!", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Example query
    cursor.execute("""
    SELECT d.title, d.filename, u.username, d.upload_date, u.userType
    FROM documents d
    JOIN users u ON d.uploaded_by = u.id
    ORDER BY d.upload_date DESC
""")
    documents = cursor.fetchall()

    conn.close()

    return render_template('home.html', documents=documents)


# --------download documents------


@app.route('/download/<filename>')
def download_file(filename):
    if 'user' not in session:
        flash("Please login first!", "danger")
        return redirect(url_for('login'))

    # Security check: only allow files from uploads folder
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True  # <-- forces download
    )

# ----------complete-training--------------------------


@app.route('/complete_training/<int:doc_id>', methods=['POST'])
def complete_training(doc_id):
    if 'user' not in session or session.get('userType') != 'student':
        flash("Only students can complete training.", "danger")
        return redirect(url_for('home'))

    answer = request.form.get('answer')
    correct_answer = "4"  # Example: placeholder question/answer

    if answer.strip() == correct_answer:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Get user_id
        cursor.execute("SELECT id FROM users WHERE username = ?",
                       (session['user'],))
        user_id = cursor.fetchone()[0]

        # Insert completion
        cursor.execute("""
            "INSERT INTO training_completions (user_id, document_id, status) VALUES (?, ?, ?)",
            (session['userType'], doc_id, "pending")
        """, (user_id, doc_id))

        conn.commit()
        conn.close()

        flash("🎉 Training completed successfully!", "success")
    else:
        flash("❌ Wrong answer. Try again!", "danger")

    return redirect(url_for('home'))


# -----------start-training-----------------

@app.route('/start_training/<int:doc_id>', methods=['GET', 'POST'])
def start_training(doc_id):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Fetch the document info
    cursor.execute("SELECT id, title FROM documents WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    if not doc:
        flash("Document not found!", "danger")
        conn.close()
        return redirect(url_for('home'))

    # Example quiz question
    question = {
        "text": "What is 2 + 2?",
        "options": ["3", "4", "5", "6"],
        "correct": "4"
    }

    if request.method == "POST":
        answer = request.form.get('answer')
        status = "pending"
        if answer == question['correct']:
            status = "completed"
        else:
            status = "re-take"

        # Insert or update training completion
        cursor.execute("""
            SELECT id FROM training_completions WHERE user_id=? AND document_id=?
        """, (session['user_id'], doc_id))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE training_completions
                SET status=?, completed_at=CURRENT_TIMESTAMP
                WHERE user_id=? AND document_id=?
            """, ('completed', session['user_id'], doc_id))

        else:
            cursor.execute("""
                INSERT INTO training_completions (user_id, document_id, status)
                VALUES (?, ?, ?)
            """, (session['user_id'], doc_id, 'pending'))

        conn.commit()
        conn.close()
        flash(f"Training marked as '{status}'", "success")
        return redirect(url_for('home'))

    conn.close()
    return render_template('training.html', document={"id": doc[0], "title": doc[1]}, question=question)


# -----------submit-training--------------------

@app.route("/submit_training/<int:doc_id>", methods=["POST"])
def submit_training(doc_id):
    if "user" not in session or session.get("userType") != "student":
        flash("Only students can submit training.", "danger")
        return redirect(url_for("home"))

    # Get the submitted answer from the form
    answer = request.form.get("answer")

    if not answer:
        flash("Please answer the question before submitting.", "warning")
        return redirect(url_for("start_training", doc_id=doc_id))

    # Here you can define the correct answer for simplicity
    correct_answer = "42"  # Example correct answer

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Determine training status
    if answer.strip() == correct_answer:
        status = "completed"
    else:
        status = "re-take"

    # Update or insert record in training_completions
    cursor.execute(
        """
        INSERT INTO training_completions (user_id, document_id, status, completed_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, document_id)
        DO UPDATE SET status=excluded.status, completed_at=CURRENT_TIMESTAMP
        """,
        (session['user_id'], doc_id, status)
    )

    conn.commit()
    conn.close()

    flash(f"Training marked as '{status}'.", "success")
    return redirect(url_for("home"))


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
