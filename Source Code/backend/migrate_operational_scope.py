"""
Phase 3: OperationalScope — the minimum abstraction for non-academic
operational areas (HVAC, Electrical, Residential, Administrative,
Engineering/Technical), unified into the SAME admin_scopes grant table the
academic hierarchy already uses (adds operational_scope_id there, and makes
its faculty_id nullable so a pure-infrastructure grant doesn't need one).

Does NOT touch the existing Faculty/Department/Course/CourseAssignment
tables or data. Purely additive.

Run from backend/ with the server stopped:
    python3 migrate_operational_scope.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS operational_scopes (
        scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(160) NOT NULL,
        scope_type VARCHAR(20) NOT NULL,
        faculty_id INTEGER REFERENCES faculties(faculty_id),
        building_id INTEGER REFERENCES buildings(building_id),
        description VARCHAR(255),
        CHECK (scope_type IN ('ACADEMIC','HVAC','ELECTRICAL','RESIDENTIAL','ADMINISTRATIVE','ENGINEERING'))
    )
""")

cur.execute("PRAGMA table_info(admin_scopes)")
cols = {row[1] for row in cur.fetchall()}
if "operational_scope_id" not in cols:
    cur.execute("ALTER TABLE admin_scopes ADD COLUMN operational_scope_id INTEGER REFERENCES operational_scopes(scope_id)")
    print("  + admin_scopes.operational_scope_id")
else:
    print("  = admin_scopes.operational_scope_id already present")

# SQLite can't make an existing NOT NULL column nullable via ALTER TABLE.
# admin_scopes.faculty_id was created NOT NULL by migrate_org_hierarchy.py;
# rebuild the table with it nullable, preserving all existing rows exactly.
cur.execute("PRAGMA table_info(admin_scopes)")
faculty_col = next((row for row in cur.fetchall() if row[1] == "faculty_id"), None)
if faculty_col is not None and faculty_col[3] == 1:  # notnull flag
    print("Relaxing admin_scopes.faculty_id to nullable (rebuilding table)...")
    cur.execute("""
        CREATE TABLE admin_scopes_new (
            scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            faculty_id INTEGER REFERENCES faculties(faculty_id),
            department_id INTEGER REFERENCES departments(department_id),
            operational_scope_id INTEGER REFERENCES operational_scopes(scope_id),
            created_at TIMESTAMP,
            CHECK ((faculty_id IS NOT NULL) OR (operational_scope_id IS NOT NULL))
        )
    """)
    cur.execute("""
        INSERT INTO admin_scopes_new (scope_id, user_id, faculty_id, department_id, operational_scope_id, created_at)
        SELECT scope_id, user_id, faculty_id, department_id, operational_scope_id, created_at FROM admin_scopes
    """)
    cur.execute("DROP TABLE admin_scopes")
    cur.execute("ALTER TABLE admin_scopes_new RENAME TO admin_scopes")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_admin_scopes_user_id ON admin_scopes (user_id)")
    print("  done.")
else:
    print("  = admin_scopes.faculty_id already nullable (or table not yet created)")

conn.commit()
conn.close()
print("Operational scope tables/columns ready.")
