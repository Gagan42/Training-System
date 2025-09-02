import sqlite3

connection = sqlite3.connect("users.db")
cursor = connection.cursor()


command = """CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    userType TEXT CHECK(userType IN ('admin', 'trainer', 'student')) NOT NULL,
    email TEXT,
    phoneNumber TEXT,
    createDate DATE,
    updatedDate DATE,
    lastUpdatedBy TEXT
);"""

cursor.execute(command)
