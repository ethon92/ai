"""SQLite Mini ERP schema, migrations, demo data, and safe query helpers."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", "data/mini_erp.db"))
COURSE_NAMES = ["國中數學", "高中數學", "國中理化", "高中物理", "英文先修"]
BRANCH_SEEDS = [
    ("台北中正分校", "台北"), ("新北板橋分校", "新北"), ("桃園中壢分校", "桃園"),
    ("新竹東區分校", "新竹"), ("台中西屯分校", "台中"), ("彰化員林分校", "彰化"),
    ("台南東區分校", "台南"), ("高雄左營分校", "高雄"), ("基隆仁愛分校", "基隆"),
    ("宜蘭羅東分校", "宜蘭"), ("台北大安分校", "台北"), ("新北新莊分校", "新北"),
    ("桃園桃園分校", "桃園"), ("新竹竹北分校", "新竹"), ("台中北屯分校", "台中"),
    ("彰化彰化分校", "彰化"), ("台南永康分校", "台南"), ("高雄鳳山分校", "高雄"),
    ("基隆中正分校", "基隆"), ("宜蘭宜蘭分校", "宜蘭"), ("台北松山分校", "台北"),
    ("新北中和分校", "新北"), ("桃園龜山分校", "桃園"), ("新竹香山分校", "新竹"),
    ("台中豐原分校", "台中"),
]
LEGACY_BRANCH_LOCATIONS = ["台北", "新北", "桃園", "新竹", "台中", "彰化", "台南", "高雄", "基隆", "宜蘭"]
LEGACY_BRANCH_SUFFIXES = ["中正", "板橋", "桃園", "光復", "西屯", "員林", "東區", "左營", "信義", "羅東"]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _create_students(conn: sqlite3.Connection, name: str = "students", ref: str = "branches") -> None:
    conn.execute(f"""CREATE TABLE {name} (
      student_id INTEGER PRIMARY KEY,
      student_name TEXT NOT NULL,
      branch_id INTEGER NOT NULL REFERENCES {ref}(branch_id)
    )""")


def _create_enrollments(conn: sqlite3.Connection, name: str = "enrollments",
                        students_table: str = "students") -> None:
    conn.execute(f"""CREATE TABLE {name} (
      enrollment_id INTEGER PRIMARY KEY,
      student_id INTEGER NOT NULL REFERENCES {students_table}(student_id),
      course_id INTEGER NOT NULL REFERENCES courses(course_id),
      branch_id INTEGER NOT NULL REFERENCES branches(branch_id),
      enrollment_date TEXT NOT NULL,
      UNIQUE(student_id, course_id, branch_id)
    )""")


def _migrate_legacy_tables(conn: sqlite3.Connection) -> None:
    """Normalize legacy course_name rows and remove old phone/amount/task fields."""
    has_students = _table_exists(conn, "students")
    has_enrollments = _table_exists(conn, "enrollments")
    student_cols = _columns(conn, "students") if has_students else set()
    enrollment_cols = _columns(conn, "enrollments") if has_enrollments else set()
    legacy_enrollments = "course_name" in enrollment_cols

    if not has_students:
        _create_students(conn)
    if not has_enrollments:
        _create_enrollments(conn)
    elif legacy_enrollments:
        # Preserve course names, but keep only the earliest registration for each
        # student/course/branch combination to satisfy the new business rule.
        conn.execute("INSERT OR IGNORE INTO courses(course_name) SELECT DISTINCT course_name FROM enrollments WHERE course_name IS NOT NULL")
        conn.execute("DROP TABLE IF EXISTS students_new")
        conn.execute("DROP TABLE IF EXISTS enrollments_new")
        _create_students(conn, "students_new")
        conn.execute("INSERT INTO students_new(student_id,student_name,branch_id) SELECT student_id,student_name,branch_id FROM students")
        _create_enrollments(conn, "enrollments_new", "students_new")
        conn.execute("""WITH ranked AS (
          SELECT e.enrollment_id, e.student_id, c.course_id, e.branch_id, e.enrollment_date,
                 ROW_NUMBER() OVER (
                   PARTITION BY e.student_id, c.course_id, e.branch_id
                   ORDER BY e.enrollment_date, e.enrollment_id
                 ) AS row_num
          FROM enrollments e JOIN courses c ON c.course_name=e.course_name
        )
        INSERT INTO enrollments_new(enrollment_id,student_id,course_id,branch_id,enrollment_date)
        SELECT enrollment_id,student_id,course_id,branch_id,enrollment_date FROM ranked WHERE row_num=1""")
        conn.execute("DROP TABLE enrollments")
        conn.execute("DROP TABLE students")
        conn.execute("ALTER TABLE students_new RENAME TO students")
        conn.execute("ALTER TABLE enrollments_new RENAME TO enrollments")
    elif "phone" in student_cols:
        conn.execute("DROP TABLE IF EXISTS students_new")
        _create_students(conn, "students_new")
        conn.execute("INSERT INTO students_new(student_id,student_name,branch_id) SELECT student_id,student_name,branch_id FROM students")
        conn.execute("DROP TABLE students")
        conn.execute("ALTER TABLE students_new RENAME TO students")

    # The task workflow has been removed from this MVP.
    if _table_exists(conn, "tasks"):
        conn.execute("DROP TABLE tasks")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_date_branch ON enrollments(enrollment_date, branch_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_enrollment_student_course_branch ON enrollments(student_id, course_id, branch_id)")


def _repair_duplicate_demo_branches(conn: sqlite3.Connection) -> None:
    """Give the original 25-row demo dataset unique branch names without changing IDs."""
    rows = conn.execute("SELECT branch_id,branch_name,location FROM branches ORDER BY branch_id").fetchall()
    if len(rows) != len(BRANCH_SEEDS):
        return
    matches_legacy_seed = all(
        row["branch_id"] == branch_id
        and row["branch_name"] == f"{LEGACY_BRANCH_LOCATIONS[(branch_id-1)%10]}{LEGACY_BRANCH_SUFFIXES[(branch_id-1)%10]}分校"
        and row["location"] == LEGACY_BRANCH_LOCATIONS[(branch_id-1)%10]
        for branch_id, row in enumerate(rows, start=1)
    )
    if matches_legacy_seed:
        conn.executemany("UPDATE branches SET branch_name=?,location=? WHERE branch_id=?",
                         [(name, location, branch_id) for branch_id, (name, location) in enumerate(BRANCH_SEEDS, start=1)])
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_branches_branch_name ON branches(branch_name COLLATE NOCASE)")


def init_db() -> None:
    with connect() as conn:
        # Table rebuilds require FK checks to be deferred until after migration.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("""CREATE TABLE IF NOT EXISTS branches (
          branch_id INTEGER PRIMARY KEY, branch_name TEXT NOT NULL,
          location TEXT NOT NULL, manager TEXT NOT NULL, status TEXT NOT NULL DEFAULT '營運中'
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS courses (
          course_id INTEGER PRIMARY KEY, course_name TEXT NOT NULL UNIQUE
        )""")
        _migrate_legacy_tables(conn)
        _repair_duplicate_demo_branches(conn)

        if conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0] == 0:
            branches = [(i, name, location, f"校主任{i:02d}") for i, (name, location) in enumerate(BRANCH_SEEDS, start=1)]
            conn.executemany("INSERT INTO branches(branch_id,branch_name,location,manager) VALUES(?,?,?,?)", branches)

        if conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
            conn.executemany("INSERT INTO courses(course_name) VALUES(?)", [(name,) for name in COURSE_NAMES])

        # Only initialize sample learners when both transactional tables are empty.
        if (conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0 and
                conn.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0] == 0):
            _seed_demo_data(conn)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


def _seed_demo_data(conn: sqlite3.Connection) -> None:
    branches = [r["branch_id"] for r in conn.execute("SELECT branch_id FROM branches ORDER BY branch_id")]
    course_ids = {r["course_name"]: r["course_id"] for r in conn.execute("SELECT course_id,course_name FROM courses")}
    today = date.today()
    students, enrollments = [], []
    sid = eid = 1
    for branch_id in branches:
        for month_offset in range(6):
            month_index = today.year * 12 + today.month - 1 - month_offset
            month_start = date(month_index // 12, month_index % 12 + 1, 1)
            targeted_decline = branch_id in (4, 9, 17, 22)
            base = 5 if targeted_decline and month_offset == 0 else 10 if targeted_decline and month_offset == 1 else 8
            enrollment_count = base + ((branch_id + month_offset) % 3)
            next_month = date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1)
            month_length = (next_month - timedelta(days=1)).day
            for n in range(enrollment_count):
                student_name = f"示範學生{branch_id:02d}{month_offset}{n:02d}"
                students.append((sid, student_name, branch_id))
                course_name = COURSE_NAMES[(branch_id + n + month_offset) % len(COURSE_NAMES)]
                day = min(month_length, 2 + ((n * 3 + branch_id) % 24))
                enrolled = month_start.replace(day=day)
                enrollments.append((eid, sid, course_ids[course_name], branch_id, enrolled.isoformat()))
                sid += 1
                eid += 1
    conn.executemany("INSERT INTO students(student_id,student_name,branch_id) VALUES(?,?,?)", students)
    conn.executemany("""INSERT INTO enrollments(enrollment_id,student_id,course_id,branch_id,enrollment_date)
                        VALUES(?,?,?,?,?)""", enrollments)


def branch_rows() -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM branches ORDER BY branch_id")]


def search_branches(keyword: str = "", location: str = "") -> list[dict]:
    sql = "SELECT branch_id, branch_name, location, manager, status FROM branches WHERE 1=1"
    args: list = []
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        sql += " AND (branch_name LIKE ? OR manager LIKE ? OR location LIKE ?)"
        args.extend([like, like, like])
    if location.strip():
        sql += " AND location LIKE ?"; args.append(f"%{location.strip()}%")
    sql += " ORDER BY branch_id"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def branch_detail(branch_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("""
          SELECT b.*, COUNT(DISTINCT s.student_id) AS student_count,
                 COUNT(DISTINCT e.enrollment_id) AS enrollment_count
          FROM branches b LEFT JOIN students s USING(branch_id)
          LEFT JOIN enrollments e USING(branch_id)
          WHERE b.branch_id=? GROUP BY b.branch_id
        """, (branch_id,)).fetchone()
        return dict(row) if row else None


def branch_students(branch_id: int) -> list[dict]:
    """Return the students table columns for one branch, without dropped phone data."""
    with connect() as conn:
        return [dict(r) for r in conn.execute("""
          SELECT student_id, student_name, branch_id
          FROM students WHERE branch_id=? ORDER BY student_id
        """, (branch_id,))]


def branch_enrollments(branch_id: int, start_date: str | None = None, end_date: str | None = None,
                       course_name: str = "", limit: int = 100) -> list[dict]:
    sql = """SELECT e.enrollment_id, e.student_id, e.course_id, e.branch_id,
                    e.enrollment_date, c.course_name, s.student_name, b.branch_name
             FROM enrollments e JOIN students s USING(student_id)
             JOIN courses c USING(course_id) JOIN branches b USING(branch_id)
             WHERE e.branch_id=?"""
    args: list = [branch_id]
    if start_date:
        sql += " AND e.enrollment_date>=?"; args.append(start_date)
    if end_date:
        sql += " AND e.enrollment_date<=?"; args.append(end_date)
    if course_name.strip():
        sql += " AND c.course_name LIKE ?"; args.append(f"%{course_name.strip()}%")
    sql += " ORDER BY e.enrollment_date DESC, e.enrollment_id DESC LIMIT ?"; args.append(max(1, min(limit, 500)))
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def branch_monthly_summary(branch_id: int, months: int = 6) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("""
          SELECT strftime('%Y-%m', enrollment_date) AS month,
                 COUNT(*) AS enrollment_count, COUNT(DISTINCT student_id) AS unique_students
          FROM enrollments WHERE branch_id=?
          GROUP BY month ORDER BY month DESC LIMIT ?
        """, (branch_id, months))]


def enrollment_comparison(months: int = 2) -> list[dict]:
    """Compare the latest calendar month with the previous calendar month."""
    with connect() as conn:
        rows = conn.execute("""
          WITH monthly AS (
            SELECT branch_id, strftime('%Y-%m', enrollment_date) AS month, COUNT(*) AS students
            FROM enrollments GROUP BY branch_id, month
          ), recent AS (SELECT MAX(month) AS m FROM monthly),
          periods AS (SELECT m AS current_m, strftime('%Y-%m', date(m || '-01','-1 month')) AS prior_m FROM recent)
          SELECT b.branch_id, b.branch_name, b.location,
            COALESCE(cur.students,0) current_students, COALESCE(prev.students,0) previous_students,
            CASE WHEN COALESCE(prev.students,0)=0 THEN 0
                 ELSE ROUND(100.0*(COALESCE(cur.students,0)-prev.students)/prev.students,1) END change_pct
          FROM branches b CROSS JOIN periods p
          LEFT JOIN monthly cur ON cur.branch_id=b.branch_id AND cur.month=p.current_m
          LEFT JOIN monthly prev ON prev.branch_id=b.branch_id AND prev.month=p.prior_m
          ORDER BY change_pct, b.branch_id
        """).fetchall()
        return [dict(r) for r in rows]
