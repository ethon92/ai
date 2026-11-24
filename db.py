"""SQLite Mini ERP schema, seed data, and safe business queries."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", "data/mini_erp.db"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS branches (
          branch_id INTEGER PRIMARY KEY, branch_name TEXT NOT NULL,
          location TEXT NOT NULL, manager TEXT NOT NULL, status TEXT NOT NULL DEFAULT '營運中'
        );
        CREATE TABLE IF NOT EXISTS students (
          student_id INTEGER PRIMARY KEY, student_name TEXT NOT NULL,
          phone TEXT, branch_id INTEGER NOT NULL REFERENCES branches(branch_id)
        );
        CREATE TABLE IF NOT EXISTS enrollments (
          enrollment_id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(student_id),
          branch_id INTEGER NOT NULL REFERENCES branches(branch_id), course_name TEXT NOT NULL,
          enrollment_date TEXT NOT NULL, amount INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrollments_date_branch ON enrollments(enrollment_date, branch_id);
        """)
        if conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0]:
            return
        locations = ["台北","新北","桃園","新竹","台中","彰化","台南","高雄","基隆","宜蘭"]
        branches = [(i, f"{locations[(i-1)%len(locations)]}{['中正','板橋','桃園','光復','西屯','員林','東區','左營','信義','羅東'][(i-1)%10]}分校", locations[(i-1)%10], f"校主任{i:02d}") for i in range(1,26)]
        conn.executemany("INSERT INTO branches(branch_id,branch_name,location,manager) VALUES(?,?,?,?)", branches)
        students = []
        enrollments = []
        today = date.today()
        eid = sid = 1
        courses = ["國中數學","高中數學","國中理化","高中物理","英文先修"]
        for b in range(1, 26):
            for n in range(1, 9):
                students.append((sid, f"示範學生{b:02d}{n:02d}", f"09{b:02d}{n:06d}", b))
                for month_offset in range(6):
                    month_index = today.year * 12 + today.month - 1 - month_offset
                    month_start = date(month_index // 12, month_index % 12 + 1, 1)
                    # A few branches intentionally dip in the latest month for a useful demo.
                    base = (1 if month_offset == 0 else 2) if b in (4, 9, 17, 22) and month_offset < 2 else 1
                    count = base + ((b + n + month_offset) % 2)
                    for k in range(count):
                        month_length = (date(month_start.year + (month_start.month == 12), month_start.month % 12 + 1, 1) - timedelta(days=1)).day
                        day = min(month_length, 2 + ((n * 3 + k * 5 + b) % 24))
                        enrolled = month_start.replace(day=day)
                        enrollments.append((eid, sid, b, courses[(b+n+k)%len(courses)], enrolled.isoformat(), [9800,12800,15800,18800,21800][(b+n+k)%5]))
                        eid += 1
                sid += 1
        conn.executemany("INSERT INTO students VALUES(?,?,?,?)", students)
        conn.executemany("INSERT INTO enrollments VALUES(?,?,?,?,?,?)", enrollments)


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
    """Return a branch roster without student contact details."""
    with connect() as conn:
        return [dict(r) for r in conn.execute("""
          SELECT s.student_id, s.student_name, b.branch_name
          FROM students s JOIN branches b USING(branch_id)
          WHERE s.branch_id=? ORDER BY s.student_id
        """, (branch_id,))]


def branch_enrollments(branch_id: int, start_date: str | None = None, end_date: str | None = None,
                       course_name: str = "", limit: int = 100) -> list[dict]:
    sql = """SELECT e.enrollment_id, e.enrollment_date, e.course_name, e.amount,
                    s.student_name, b.branch_name
             FROM enrollments e JOIN students s USING(student_id)
             JOIN branches b USING(branch_id) WHERE e.branch_id=?"""
    args: list = [branch_id]
    if start_date:
        sql += " AND e.enrollment_date>=?"; args.append(start_date)
    if end_date:
        sql += " AND e.enrollment_date<=?"; args.append(end_date)
    if course_name.strip():
        sql += " AND e.course_name LIKE ?"; args.append(f"%{course_name.strip()}%")
    sql += " ORDER BY e.enrollment_date DESC, e.enrollment_id DESC LIMIT ?"; args.append(max(1, min(limit, 500)))
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def branch_monthly_summary(branch_id: int, months: int = 6) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("""
          SELECT strftime('%Y-%m', enrollment_date) AS month,
                 COUNT(*) AS enrollment_count, COUNT(DISTINCT student_id) AS unique_students,
                 SUM(amount) AS revenue
          FROM enrollments WHERE branch_id=?
          GROUP BY month ORDER BY month DESC LIMIT ?
        """, (branch_id, months))]


def enrollment_comparison(months: int = 2) -> list[dict]:
    """Compare the latest calendar month with the previous calendar month."""
    with connect() as conn:
        rows = conn.execute("""
          WITH monthly AS (
            SELECT branch_id, strftime('%Y-%m', enrollment_date) AS month, COUNT(*) AS students,
                   SUM(amount) AS revenue
            FROM enrollments GROUP BY branch_id, month
          ), recent AS (SELECT MAX(month) AS m FROM monthly),
          periods AS (SELECT m AS current_m, strftime('%Y-%m', date(m || '-01','-1 month')) AS prior_m FROM recent)
          SELECT b.branch_id, b.branch_name, b.location,
            COALESCE(cur.students,0) current_students, COALESCE(prev.students,0) previous_students,
            COALESCE(cur.revenue,0) current_revenue, COALESCE(prev.revenue,0) previous_revenue,
            CASE WHEN COALESCE(prev.students,0)=0 THEN 0
                 ELSE ROUND(100.0*(COALESCE(cur.students,0)-prev.students)/prev.students,1) END change_pct
          FROM branches b CROSS JOIN periods p
          LEFT JOIN monthly cur ON cur.branch_id=b.branch_id AND cur.month=p.current_m
          LEFT JOIN monthly prev ON prev.branch_id=b.branch_id AND prev.month=p.prior_m
          ORDER BY change_pct, b.branch_id
        """).fetchall()
        return [dict(r) for r in rows]


