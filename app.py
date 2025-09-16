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

    # Create quiz_questions table
    # cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS quiz_questions (
    #         id INTEGER PRIMARY KEY AUTOINCREMENT,
    #         document_id INTEGER NOT NULL,
    #         question_text TEXT NOT NULL,
    #         options TEXT NOT NULL, -- store as comma-separated or JSON
    #         correct_answer TEXT NOT NULL,
    #         FOREIGN KEY (document_id) REFERENCES documents(id)
    #     )
    # """)

    # Create quizzes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option1 TEXT NOT NULL,
            option2 TEXT NOT NULL,
            option3 TEXT,
            option4 TEXT,
            correct_answer TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id)
)
""")

# Create quiz_submissions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            selected_answer TEXT,
            status TEXT CHECK(status IN ('completed','failed')) DEFAULT 'failed',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(quiz_id, user_id)
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
    if "user" not in session:
        flash("Please login first.", "info")
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Fetch user info
    cursor.execute(
        "SELECT id, username, email, phoneNumber, userType FROM users WHERE username = ?",
        (session['user'],)
    )
    user_info = cursor.fetchone()
    if not user_info:
        flash("User not found. Please login again.", "danger")
        session.clear()
        conn.close()
        return redirect(url_for("login"))

    session['user_id'] = user_info[0]
    session['user'] = user_info[1]
    session['userType'] = user_info[4]
    session['email'] = user_info[2] or "N/A"
    session['phoneNumber'] = user_info[3] or "N/A"

    # Fetch all documents
    cursor.execute("""
        SELECT d.id, d.title, d.filename, u.username, d.upload_date, u.userType
        FROM documents d
        JOIN users u ON d.uploaded_by = u.id
        ORDER BY d.upload_date DESC
    """)
    documents = cursor.fetchall()

    # Quiz status for current student
    doc_quiz_status = {}
    if session['userType'] == 'student':
        cursor.execute("""
            SELECT q.document_id, qs.status
            FROM quizzes q
            LEFT JOIN quiz_submissions qs 
                ON q.id = qs.quiz_id AND qs.user_id = ?
        """, (session['user_id'],))
        for doc_id, status in cursor.fetchall():
            if status is None:
                doc_quiz_status[doc_id] = 'not_started'
            elif status == 'completed':
                doc_quiz_status[doc_id] = 'completed'
            else:
                doc_quiz_status[doc_id] = 'failed'

    # Default values for everyone
    user_tables = None
    quiz_summary = {}

    # Admin: fetch all trainers, students, and quiz summary
    if session['userType'] == 'admin':
        cursor.execute(
            "SELECT id, username, email, phoneNumber, createDate FROM users WHERE userType='trainer'"
        )
        trainers = cursor.fetchall()

        cursor.execute(
            "SELECT id, username, email, phoneNumber, createDate FROM users WHERE userType='student'"
        )
        students = cursor.fetchall()

        user_tables = {"trainers": trainers, "students": students}

        # Quiz summary (all student attempts)
        cursor.execute("""
            SELECT d.title, u.username, qs.status, qs.submitted_at
            FROM quiz_submissions qs
            JOIN quizzes q ON qs.quiz_id = q.id
            JOIN documents d ON q.document_id = d.id
            JOIN users u ON qs.user_id = u.id
            ORDER BY d.title, qs.submitted_at DESC
        """)
        rows = cursor.fetchall()

        for title, username, status, submitted_at in rows:
            if title not in quiz_summary:
                quiz_summary[title] = []
            quiz_summary[title].append({
                "username": username,
                "status": status,
                "submitted_at": submitted_at
            })

    conn.close()

    return render_template(
        "home.html",
        user=session['user'],
        documents=documents,
        doc_quiz_status=doc_quiz_status,
        user_tables=user_tables,
        quiz_summary=quiz_summary
    )


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


# ----------------add_quiz--------------------------------

@app.route("/add_quiz/<int:doc_id>", methods=["GET", "POST"])
def add_quiz(doc_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Fetch document title
    cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if not row:
        flash("Document not found!", "danger")
        conn.close()
        return redirect(url_for("home"))

    document_title = row[0]
    conn.close()

    if request.method == "POST":
        questions = request.form.getlist("questions[]")
        option1 = request.form.getlist("option1[]")
        option2 = request.form.getlist("option2[]")
        option3 = request.form.getlist("option3[]")
        option4 = request.form.getlist("option4[]")
        correct_answers = request.form.getlist("correct_answers[]")

        if not questions:
            flash("Please add at least one question.", "warning")
            return redirect(url_for("add_quiz", doc_id=doc_id))

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for i in range(len(questions)):
            q = questions[i]
            a = option1[i]
            b = option2[i]
            c = option3[i] if option3[i] else None
            d = option4[i] if option4[i] else None
            correct = correct_answers[i]

            # Insert quiz question into quizzes table
            cursor.execute("""
                INSERT INTO quizzes (document_id, question, option1, option2, option3, option4, correct_answer)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, q, a, b, c, d, correct))

        conn.commit()
        conn.close()

        flash("Quiz questions added successfully!", "success")
        return redirect(url_for("home"))

    return render_template("add_quiz.html", document_id=doc_id, document_title=document_title)

# -------------------start_quiz--------------------


@app.route('/start_quiz/<int:doc_id>', methods=['GET', 'POST'])
def start_quiz(doc_id):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Fetch document title
    cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    if not doc:
        flash("Document not found!", "danger")
        conn.close()
        return redirect(url_for('home'))
    document_title = doc[0]

    # Fetch all quiz questions for this document
    cursor.execute("""
        SELECT id, question, option1, option2, option3, option4, correct_answer
        FROM quizzes WHERE document_id = ?
    """, (doc_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        flash("Quiz not created yet for this document!", "warning")
        return redirect(url_for('home'))

    quiz = []
    for row in rows:
        quiz.append({
            "id": row[0],
            "question": row[1],
            "option1": row[2],
            "option2": row[3],
            "option3": row[4],
            "option4": row[5],
            "correct": row[6]
        })

    if request.method == 'POST':
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for q in quiz:
            selected = request.form.get(f"question_{q['id']}")
            status = "completed" if selected == q['correct'] else "failed"

            # Insert or update quiz submission
            cursor.execute("""
                INSERT INTO quiz_submissions (quiz_id, user_id, selected_answer, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(quiz_id, user_id)
                DO UPDATE SET selected_answer=excluded.selected_answer, status=excluded.status, submitted_at=CURRENT_TIMESTAMP
            """, (q['id'], session['user_id'], selected, status))

        conn.commit()
        conn.close()

        flash("Quiz submitted successfully!", "success")
        return redirect(url_for('home'))

    return render_template("start_quiz.html", document_title=document_title, quiz=quiz)

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
