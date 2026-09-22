"""
One-time local migration adding password_reset_requests.request_token and
.password_set — needed for the "waiting room" forgot-password flow (the
browser that submitted the request polls with this token, and later uses it
to set its own new password once an admin approves — no relayed temp
password involved).

Run from backend/ with the server stopped:
  python3 migrate_password_reset_token.py
Then restart: ./restart.sh
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='password_reset_requests'")
if cur.fetchone() is None:
    print(
        "password_reset_requests table doesn't exist yet — nothing to migrate; "
        "it'll be created with the right columns the next time the backend starts."
    )
else:
    cur.execute("PRAGMA table_info(password_reset_requests)")
    cols = {row[1] for row in cur.fetchall()}

    if "request_token" not in cols:
        cur.execute("ALTER TABLE password_reset_requests ADD COLUMN request_token VARCHAR(64)")
        print("Added password_reset_requests.request_token.")
    else:
        print("password_reset_requests.request_token already exists, skipping.")

    if "password_set" not in cols:
        cur.execute("ALTER TABLE password_reset_requests ADD COLUMN password_set BOOLEAN NOT NULL DEFAULT 0")
        print("Added password_reset_requests.password_set.")
    else:
        print("password_reset_requests.password_set already exists, skipping.")

conn.commit()
conn.close()
print("Migration done.")
