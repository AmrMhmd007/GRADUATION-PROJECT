"""
One-time local migration adding users.photo_url (profile photo).

Run from backend/ with the server stopped:
  python3 migrate_photo_url.py
Then restart: ./restart.sh
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(users)")
user_cols = {row[1] for row in cur.fetchall()}
if "photo_url" not in user_cols:
    cur.execute("ALTER TABLE users ADD COLUMN photo_url VARCHAR(255)")
    print("Added users.photo_url.")
else:
    print("users.photo_url already exists, skipping.")

conn.commit()
conn.close()
print("Migration done.")
