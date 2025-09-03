import sqlite3

connection = sqlite3.connect("users.db")
cursor = connection.cursor()

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
            uploaded_by TEXT,
            upload_date DATE DEFAULT (datetime('now','localtime'))
        )
    """)

connection.commit()
connection.close()
