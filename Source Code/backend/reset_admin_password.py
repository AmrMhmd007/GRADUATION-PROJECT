"""
Resets the admin account's password directly in the database, bypassing
login entirely. Use this when you're locked out and can't remember the
current password.

Run from inside the backend/ folder (with the venv activated so `bcrypt`
is available):

    python reset_admin_password.py
"""
import sqlite3
import bcrypt

DB_PATH = "access_control.db"
ADMIN_EMAIL = "admin@aiu.is"   # change this if your admin uses a different email
NEW_PASSWORD = "Admin123!"     # change this to whatever you want your new password to be

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT user_id, email, role FROM users WHERE email = ?", (ADMIN_EMAIL,))
row = cur.fetchone()

if row is None:
    print(f"No user found with email {ADMIN_EMAIL!r}. Check the ADMIN_EMAIL value at the top of this script.")
else:
    user_id, email, role = row
    new_hash = bcrypt.hashpw(NEW_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, user_id))
    conn.commit()
    print(f"Password reset for {email} (role: {role}).")
    print(f"New password: {NEW_PASSWORD}")
    print("Log in with this, then change it to something only you know via the account menu.")

conn.close()
