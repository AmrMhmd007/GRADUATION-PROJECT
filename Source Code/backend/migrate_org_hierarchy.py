"""
One-time local migration for the organizational hierarchy:
    University -> College (Faculty, already existed) -> Department -> Staff
    (User, role doctor/instructor) -> Course -> CourseAssignment
plus AdminScope (College/Department-scoped admin authorization) and two
additive columns (users.department_id, schedules.course_ref_id).

Nothing here touches existing data: every new column is nullable, every new
table is independent, and no existing row is modified. Admins created before
this migration have zero AdminScope rows, which app/security.py treats as
"unrestricted" (today's exact behavior) — see AdminScope's docstring.

Run from backend/ with the server stopped:
    python3 migrate_org_hierarchy.py
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


cur.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        department_id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id INTEGER NOT NULL REFERENCES faculties(faculty_id),
        name VARCHAR(160) NOT NULL,
        CHECK (length(name) > 0)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_departments_faculty_id ON departments (faculty_id)")

cur.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        course_id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL REFERENCES departments(department_id),
        code VARCHAR(40) NOT NULL,
        name VARCHAR(160) NOT NULL,
        CHECK (length(code) > 0)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_courses_department_id ON courses (department_id)")

cur.execute("""
    CREATE TABLE IF NOT EXISTS course_assignments (
        assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL REFERENCES courses(course_id),
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        assigned_at TIMESTAMP
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_course_assignments_course_id ON course_assignments (course_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_course_assignments_user_id ON course_assignments (user_id)")

cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_scopes (
        scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        faculty_id INTEGER NOT NULL REFERENCES faculties(faculty_id),
        department_id INTEGER REFERENCES departments(department_id),
        created_at TIMESTAMP
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_admin_scopes_user_id ON admin_scopes (user_id)")

print("Adding additive columns:")
_add_column("users", "department_id", "department_id INTEGER REFERENCES departments(department_id)")
_add_column("schedules", "course_ref_id", "course_ref_id INTEGER REFERENCES courses(course_id)")

conn.commit()
conn.close()
print("Organizational hierarchy tables/columns ready.")
