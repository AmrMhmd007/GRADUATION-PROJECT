"""
One-time local migration for the "final hardening pass" Academic
Administration depth: additive columns on faculties/departments/users/
courses/course_assignments (see app/models.py for the full rationale on each
field — this script only adds the columns, it doesn't change behavior).

Nothing here touches existing data: every new column is nullable (or has a
safe default like status='active'), no existing row is modified, and no
existing table/relationship is renamed or dropped.

Run from backend/ with the server stopped:
    python3 migrate_academic_admin_depth.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()


def _add_column(table, column, ddl):
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"  + {table}.{column}")
    else:
        print(f"  = {table}.{column} already present")


print("Faculties (College):")
_add_column("faculties", "code", "code VARCHAR(20)")
_add_column("faculties", "description", "description TEXT")
_add_column("faculties", "status", "status VARCHAR(20) NOT NULL DEFAULT 'active'")
_add_column("faculties", "created_at", "created_at TIMESTAMP")
_add_column("faculties", "updated_at", "updated_at TIMESTAMP")

print("Departments:")
_add_column("departments", "code", "code VARCHAR(20)")
_add_column("departments", "description", "description TEXT")
_add_column("departments", "status", "status VARCHAR(20) NOT NULL DEFAULT 'active'")
_add_column("departments", "created_at", "created_at TIMESTAMP")
_add_column("departments", "updated_at", "updated_at TIMESTAMP")

print("Users (staff profile fields):")
_add_column("users", "staff_id", "staff_id VARCHAR(40)")
_add_column("users", "academic_title", "academic_title VARCHAR(40)")
_add_column("users", "specialization", "specialization VARCHAR(160)")
_add_column("users", "phone", "phone VARCHAR(30)")
_add_column("users", "status", "status VARCHAR(20) NOT NULL DEFAULT 'active'")
cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_staff_id ON users (staff_id) WHERE staff_id IS NOT NULL")

print("Courses:")
_add_column("courses", "credit_hours", "credit_hours INTEGER")
_add_column("courses", "level", "level VARCHAR(20)")
_add_column("courses", "semester", "semester VARCHAR(20)")
_add_column("courses", "description", "description TEXT")
_add_column("courses", "status", "status VARCHAR(20) NOT NULL DEFAULT 'active'")
_add_column("courses", "created_at", "created_at TIMESTAMP")
_add_column("courses", "updated_at", "updated_at TIMESTAMP")

print("Course assignments:")
_add_column("course_assignments", "section", "section VARCHAR(20)")
_add_column("course_assignments", "semester", "semester VARCHAR(20)")
_add_column("course_assignments", "academic_year", "academic_year VARCHAR(20)")
_add_column("course_assignments", "status", "status VARCHAR(20) NOT NULL DEFAULT 'active'")
_add_column("course_assignments", "schedule_id", "schedule_id INTEGER REFERENCES schedules(schedule_id)")
_add_column("course_assignments", "updated_at", "updated_at TIMESTAMP")

conn.commit()
conn.close()
print("Academic Administration depth columns ready.")
