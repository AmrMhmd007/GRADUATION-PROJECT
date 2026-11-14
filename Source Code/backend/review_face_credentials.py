"""
READ-ONLY review of Face ID credentials by source. Changes nothing.

Phase 1A closed the API path that let a client-supplied embedding be recorded
as REAL, so any REAL row created before that fix may have come from such an
embedding. Run this to list them, then decide per row (see
Documents/DATABASE_MIGRATIONS.md, "Reviewing existing REAL Face ID credentials").

Run from backend/:  python3 review_face_credentials.py
Honours DATABASE_URL (SQLite or PostgreSQL). Prints metadata only: never a
template, embedding or key. Opens the database read-only where supported.
"""
from sqlalchemy import text

from app.database import engine

QUERY = text("""
    SELECT f.face_id, f.user_id, u.email, f.status, f.enrolled_source, f.enrolled_at,
           f.enrolled_by_id, f.model_version, f.liveness_checked, f.liveness_passed
    FROM face_credentials f LEFT JOIN users u ON u.user_id = f.user_id
    ORDER BY f.enrolled_source, f.face_id
""")


def main() -> int:
    with engine.connect() as conn:
        rows = conn.execute(QUERY).fetchall()
    real_active = [r for r in rows if r.enrolled_source == "REAL" and r.status == "ENROLLED"]
    print(f"face_credentials rows: {len(rows)}  REAL: {sum(r.enrolled_source == 'REAL' for r in rows)}  "
          f"REAL and still ENROLLED (usable at the door): {len(real_active)}")
    for r in rows:
        if r.enrolled_source != "REAL":
            continue
        self_enrolled = "yes" if r.enrolled_by_id == r.user_id else "no"
        print(f"  face_id={r.face_id} user={r.email} status={r.status} enrolled_at={r.enrolled_at} "
              f"self_enrolled={self_enrolled} model_version={r.model_version} "
              f"liveness_passed={r.liveness_passed}")
    if real_active:
        print("\nREAL rows that are still ENROLLED came from the pre-Phase-1A API or another path and have not "
              "been verified by any trusted pipeline. Nothing was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
