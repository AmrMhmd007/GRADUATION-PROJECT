"""
One-time local migration adding users.must_change_password (used to force
a user to pick their own password right after an admin approves a
password-reset request).

Run from backend/ with the server stopped:
  python3 migrate_must_change_password.py
Then restart: ./restart.sh
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(users)")
user_cols = {row[1] for row in cur.fetchall()}
if "must_change_password" not in user_cols:
    cur.execute(
        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"
    )
    print("Added users.must_change_password.")
else:
    print("users.must_change_password already exists, skipping.")

conn.commit()
conn.close()
print("Migration done.")
