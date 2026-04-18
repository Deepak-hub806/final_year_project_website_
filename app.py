import re
from google import genai
import sqlite3
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = "secret123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

VIT_EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@vitstudent\.ac\.in$'

SLOT_MAP = {
    "A1": ("MON", 1), "F1": ("MON", 2), "D1": ("MON", 3), "TB1": ("MON", 4), "TG1": ("MON", 5),
    "B1": ("TUE", 1), "G1": ("TUE", 2), "E1": ("TUE", 3), "TC1": ("TUE", 4), "TAA1": ("TUE", 5),
    "C1": ("WED", 1), "V1": ("WED", 4), "V2": ("WED", 5),
    "E1": ("FRI", 1), "C1": ("FRI", 2), "TA1": ("FRI", 3), "TF1": ("FRI", 4), "TD1": ("FRI", 5),
    "A2": ("MON", 7), "F2": ("MON", 8), "D2": ("MON", 9), "TB2": ("MON", 10), "TG2": ("MON", 11),
    "B2": ("TUE", 7), "G2": ("TUE", 8), "E2": ("TUE", 9), "TC2": ("TUE", 10), "TAA2": ("TUE", 11),
    "C2": ("WED", 7), "A2": ("WED", 8), "F2": ("WED", 9), "TD2": ("WED", 10), "TBB2": ("WED", 11),
    "D2": ("THU", 7), "B2": ("THU", 8), "G2": ("THU", 9), "TE2": ("THU", 10), "TCC2": ("THU", 11),
    "E2": ("FRI", 7), "C2": ("FRI", 8), "TA2": ("FRI", 9), "TF2": ("FRI", 10), "TDD2": ("FRI", 11),
    "L1": ("MON", 6), "L2": ("MON", 3), "L3": ("MON", 4), "L4": ("MON", 5),
    "L31": ("MON", 8), "L37": ("TUE", 8), "L43": ("WED", 8), "L49": ("THU", 8), "L55": ("FRI", 8),
}

SEMESTER_COURSES = {
    "1": [
        "Python Programming",
        "Software Engineering",
        "Discrete Mathematics",
        "Effective English Communication",
        "Computer Organization and Architecture",
        "Environmental Studies (EVS)",
        "Qualitative Skills - I",
        "Python Lab"
    ],
    "2": [
        "Data Structures and Algorithms",
        "Data Structures and Algorithms Lab",
        "Object Oriented Programming",
        "Object Oriented Programming Lab",
        "Database Management Systems",
        "Database Management Systems Lab",
        "Technical English Communication",
        "Technical English Communication Lab",
        "Probability and Statistics",
        "Indian Constitution",
        "Quantitative Skills - I"
    ],
    "3": [
        "Operating Systems",
        "Operating Systems Lab",
        "Computer Networks",
        "Design and Analysis of Algorithms",
        "Microprocessors and Microcontrollers",
        "Software Project Management",
        "Quantitative Skills - II"
    ],
    "4": [
        "Theory of Computation",
        "Compiler Design",
        "Compiler Design Lab",
        "Artificial Intelligence",
        "Artificial Intelligence Lab",
        "Web Technologies",
        "Web Technologies Lab",
        "Quantitative Skills - III"
    ],
    "5": [
        "Machine Learning",
        "Machine Learning Lab",
        "Cloud Computing",
        "Information Security",
        "Elective - I",
        "Elective - II",
        "Mini Project"
    ]
}

# Timetable plan templates per semester (theory slots per plan)
PLAN_TEMPLATES = {
    "A": {
        "name": "Plan A — Morning Batch",
        "type": "Morning Theory + Afternoon Lab",
        "capacity": 70,
        "desc": "Theory classes in the morning, lab sessions in the afternoon.",
        "theory": {
            "MON": ["A1", "F1", "B1", "C1"],
            "TUE": ["A1", "D1", "G1", "C1"],
            "WED": ["F1", "B1", "A2"],
            "THU": ["A1", "G1", "D1", "B2"],
            "FRI": ["A1", "F1", "B1", "C2"],
        },
        "lab": {
            "MON": "L31", "TUE": "L37", "WED": "L43", "THU": "L49", "FRI": "L55"
        }
    },
    "B": {
        "name": "Plan B — Afternoon Batch",
        "type": "Morning Lab + Afternoon Theory",
        "capacity": 70,
        "desc": "Lab sessions in the morning, theory classes post-lunch.",
        "theory": {
            "MON": ["A2", "F2", "B2", "C2"],
            "TUE": ["A2", "D2", "G2", "E2"],
            "WED": ["C2", "A2", "F2"],
            "THU": ["D2", "B2", "G2", "TE2"],
            "FRI": ["E2", "C2", "TA2", "TDD2"],
        },
        "lab": {
            "MON": "L1", "TUE": "L2", "WED": "L3", "THU": "L4", "FRI": "L55"
        }
    },
    "C": {
        "name": "Plan C — Mixed Batch",
        "type": "Mixed Theory + Lab Schedule",
        "capacity": 70,
        "desc": "Alternating theory and lab throughout the day for balanced scheduling.",
        "theory": {
            "MON": ["A1", "G1", "C1", "C2"],
            "TUE": ["F1", "B1", "B2"],
            "WED": ["A1", "D1", "C2"],
            "THU": ["G1", "A2", "E2"],
            "FRI": ["A1", "F1", "B1", "B2"],
        },
        "lab": {
            "MON": "L4", "TUE": "L37", "WED": "L43", "THU": "L1", "FRI": "L3"
        }
    }
}

CHATBOT_RESPONSES = {
    "exam date": "Final semester exams usually start in April/May. Check official portal for exact schedule.",
    "attendance requirement": "Minimum 75% attendance is required to be eligible for exams.",
    "cgpa formula": "CGPA = Sum(Grade × Credits) ÷ Total Credits.",
    "revaluation": "You can apply for revaluation through the student portal after results are published.",
    "placement eligibility": "Most companies require minimum 6.0 CGPA and no active backlogs.",
    "semester duration": "A semester typically lasts around 4–5 months.",
    "holiday calendar": "Holiday calendar is available on the university portal.",
    "hostel rules": "Hostel entry timings and rules are defined by wardens each semester."
}


# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- TABLE HELPERS ----------------
def init_timetable_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS timetable_courses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            course_code TEXT,
            course_name TEXT NOT NULL,
            faculty     TEXT,
            venue       TEXT,
            color_idx   INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slot_assignments (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            slot_code TEXT NOT NULL,
            course_id INTEGER NOT NULL,
            UNIQUE(user_id, slot_code)
        )
    """)
    conn.commit()


def init_subject_attendance_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subject_attendance (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            subject_name  TEXT NOT NULL,
            total_classes INTEGER DEFAULT 0,
            attended      INTEGER DEFAULT 0,
            UNIQUE(user_id, subject_name)
        )
    """)
    conn.commit()


def init_profile_table(conn):
    """Add extra profile columns to users table if they don't exist."""
    existing = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "semester" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN semester TEXT DEFAULT '1'")
    if "branch" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN branch TEXT DEFAULT ''")
    if "reg_number" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN reg_number TEXT DEFAULT ''")
    if "timetable_plan" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN timetable_plan TEXT DEFAULT ''")
    conn.commit()


def init_smart_timetable_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smart_timetable (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER UNIQUE NOT NULL,
            plan_id     TEXT NOT NULL,
            semester    TEXT NOT NULL,
            subjects_json TEXT NOT NULL
        )
    """)
    conn.commit()


# ---------------- INITIALIZE DATABASE ----------------
@app.route("/init-db")
def init_db():
    conn = get_db_connection()
    conn.execute("DROP TABLE IF EXISTS users")
    conn.execute("DROP TABLE IF EXISTS timetable")

    conn.execute("""
        CREATE TABLE users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            cgpa        REAL DEFAULT NULL,
            attendance  REAL DEFAULT NULL,
            semester    TEXT DEFAULT '1',
            branch      TEXT DEFAULT '',
            reg_number  TEXT DEFAULT '',
            timetable_plan TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE timetable (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            subject  TEXT,
            slot     TEXT
        )
    """)
    init_timetable_tables(conn)
    init_subject_attendance_table(conn)
    init_smart_timetable_table(conn)
    conn.commit()
    conn.close()
    return "Database initialized!"


# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        if not re.match(VIT_EMAIL_PATTERN, email):
            flash("Only VIT student email allowed")
            return redirect(url_for("signup"))

        hashed_password = generate_password_hash(password)
        try:
            conn = get_db_connection()
            init_profile_table(conn)
            conn.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_password)
            )
            conn.commit()
            conn.close()
            flash("Signup successful! Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered")
            return redirect(url_for("signup"))

    return render_template("signup.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        init_profile_table(conn)
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["semester"] = user["semester"] or "1"
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password")

    return render_template("login.html")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    init_profile_table(conn)
    user = conn.execute(
        "SELECT username, cgpa, attendance, semester, branch, reg_number, timetable_plan FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()

    # Get today's classes from smart timetable
    import datetime
    day_map = {0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT", 6: "SUN"}
    today = day_map.get(datetime.datetime.now().weekday(), "MON")

    today_classes = []
    timetable_plan = user["timetable_plan"] if user["timetable_plan"] else None

    if timetable_plan:
        smart = conn.execute(
            "SELECT * FROM smart_timetable WHERE user_id=?",
            (session["user_id"],)
        ).fetchone()
        if smart:
            subjects = json.loads(smart["subjects_json"])
            plan = PLAN_TEMPLATES.get(smart["plan_id"], {})
            theory_slots = plan.get("theory", {}).get(today, [])
            lab_slot = plan.get("lab", {}).get(today)

            SLOT_TIMES = {
                "A1": "8:00–8:50", "F1": "8:50–9:40", "D1": "9:45–10:35",
                "B1": "10:50–11:40", "G1": "11:40–12:30", "A2": "12:30–1:20",
                "C1": "2:00–2:50", "H1": "2:50–3:40", "B2": "3:45–4:35",
                "C2": "4:50–5:40", "E2": "5:40–6:30",
                "L1": "8:00–9:50", "L2": "8:00–9:50", "L3": "9:45–11:35",
                "L4": "9:45–11:35", "L31": "2:00–3:50", "L37": "2:00–3:50",
                "L43": "2:00–3:50", "L49": "2:00–3:50", "L55": "2:00–3:50",
            }

            for i, slot in enumerate(theory_slots):
                subj = subjects[i] if i < len(subjects) else "Theory Class"
                today_classes.append({
                    "subject": subj, "slot": slot,
                    "time": SLOT_TIMES.get(slot, "—"), "type": "Theory"
                })
            if lab_slot and len(subjects) > len(theory_slots):
                today_classes.append({
                    "subject": subjects[len(theory_slots)],
                    "slot": lab_slot,
                    "time": SLOT_TIMES.get(lab_slot, "—"), "type": "Lab"
                })

    # Subject-wise attendance summary
    subj_attendance = conn.execute(
        "SELECT subject_name, total_classes, attended FROM subject_attendance WHERE user_id=? ORDER BY subject_name",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    data = {
        "cgpa": user["cgpa"],
        "attendance": user["attendance"],
        "classes_today": len(today_classes),
        "today_classes": today_classes,
        "timetable_plan": timetable_plan,
        "today": today,
        "subj_attendance": [dict(s) for s in subj_attendance]
    }

    return render_template("dashboard.html", user=user, data=data)


# ---------------- CGPA PAGE ----------------
@app.route("/cgpa")
def cgpa_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("cgpa.html")


# ---------------- UPDATE CGPA ----------------
@app.route("/update-cgpa", methods=["POST"])
def update_cgpa():
    if "user_id" not in session:
        return redirect(url_for("login"))

    grade_map = {"S": 10, "A": 9, "B": 8, "C": 7, "D": 6, "E": 5, "F": 0, "N": 0}
    total_points = 0
    total_credits = 0

    for i in range(1, 11):
        grade = request.form.get(f"grade_{i}")
        credit = request.form.get(f"credit_{i}")
        if grade and credit:
            grade_value = grade_map.get(grade, 0)
            credit_value = float(credit)
            total_points += grade_value * credit_value
            total_credits += credit_value

    cgpa = round(total_points / total_credits, 2) if total_credits > 0 else None

    conn = get_db_connection()
    conn.execute("UPDATE users SET cgpa = ? WHERE id = ?", (cgpa, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


# ---------------- ATTENDANCE CALCULATOR ----------------
@app.route("/update-attendance", methods=["GET", "POST"])
def update_attendance():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    init_subject_attendance_table(conn)

    # Load semester subjects for the dropdown
    user_sem = session.get("semester", "1")
    sem_subjects = SEMESTER_COURSES.get(user_sem, [])

    subj_rows = conn.execute(
        "SELECT * FROM subject_attendance WHERE user_id=? ORDER BY subject_name",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    subj_data = []
    for s in subj_rows:
        pct = round((s["attended"] / s["total_classes"]) * 100, 1) if s["total_classes"] > 0 else 0
        status = "safe" if pct >= 75 else ("warning" if pct >= 65 else "danger")
        subj_data.append({**dict(s), "percentage": pct, "status": status})

    if request.method == "POST":
        form_type = request.form.get("form_type", "overall")

        if form_type == "overall":
            total = request.form.get("total_classes")
            attended = request.form.get("attended_classes")
            if not total or not attended:
                flash("Please enter all fields")
                return redirect(url_for("update_attendance"))
            total = int(total)
            attended = int(attended)
            if total <= 0:
                flash("Total classes must be greater than 0")
                return redirect(url_for("update_attendance"))
            attendance = round((attended / total) * 100, 2)
            conn = get_db_connection()
            conn.execute("UPDATE users SET attendance = ? WHERE id = ?", (attendance, session["user_id"]))
            conn.commit()
            conn.close()
            return redirect(url_for("dashboard"))

        elif form_type == "subject":
            subject_name = request.form.get("subject_name", "").strip()
            total = int(request.form.get("total_classes", 0))
            attended = int(request.form.get("attended_classes", 0))
            if not subject_name or total <= 0:
                flash("Please fill in all subject fields")
                return redirect(url_for("update_attendance"))
            conn = get_db_connection()
            init_subject_attendance_table(conn)
            conn.execute("""
                INSERT INTO subject_attendance (user_id, subject_name, total_classes, attended)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, subject_name)
                DO UPDATE SET total_classes=excluded.total_classes, attended=excluded.attended
            """, (session["user_id"], subject_name, total, attended))
            conn.commit()
            conn.close()
            flash(f"✓ Attendance saved for {subject_name}")
            return redirect(url_for("update_attendance"))

    return render_template("attendance.html", subj_data=subj_data, sem_subjects=sem_subjects)


# ---------------- DELETE SUBJECT ATTENDANCE ----------------
@app.route("/attendance/delete-subject", methods=["POST"])
def delete_subject_attendance():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401
    data = request.get_json()
    subject_name = data.get("subject_name")
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM subject_attendance WHERE user_id=? AND subject_name=?",
        (session["user_id"], subject_name)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ---------------- PROFILE ----------------
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    init_profile_table(conn)

    if request.method == "POST":
        branch = request.form.get("branch", "").strip()
        reg_number = request.form.get("reg_number", "").strip()
        semester = request.form.get("semester", "1")

        conn.execute(
            "UPDATE users SET branch=?, reg_number=?, semester=? WHERE id=?",
            (branch, reg_number, semester, session["user_id"])
        )
        conn.commit()
        session["semester"] = semester
        flash("✓ Profile updated successfully!")
        conn.close()
        return redirect(url_for("profile"))

    user = conn.execute(
        "SELECT username, email, cgpa, attendance, semester, branch, reg_number FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()
    conn.close()
    return render_template("profile.html", user=user, semesters=list(SEMESTER_COURSES.keys()))


# ---------------- CHATBOT ----------------
@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():
    if "user_id" not in session:
        return redirect(url_for("login"))

    reply = None

    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        if msg:
            conn = get_db_connection()
            init_profile_table(conn)
            user = conn.execute(
                "SELECT username, cgpa, attendance, semester, branch FROM users WHERE id=?",
                (session["user_id"],)
            ).fetchone()
            conn.close()

            cgpa       = user["cgpa"]       if user["cgpa"]       else "Not calculated yet"
            attendance = user["attendance"] if user["attendance"] else "Not calculated yet"
            username   = user["username"]

            if isinstance(attendance, (int, float)) and attendance < 65:
                att_status = f"⚠️ CRITICAL: {username}'s attendance is {attendance}%, below 65%. Detained risk."
            elif isinstance(attendance, (int, float)) and attendance < 75:
                att_status = f"⚠️ WARNING: {username}'s attendance is {attendance}%, below 75%. May not be eligible for FAT."
            elif isinstance(attendance, (int, float)) and attendance >= 75:
                att_status = f"✅ {username}'s attendance is {attendance}%, meets the 75% requirement."
            else:
                att_status = f"{username} has not calculated their attendance yet."

            if isinstance(cgpa, (int, float)) and cgpa < 6.0:
                cgpa_status = f"⚠️ {username}'s CGPA is {cgpa}, below 6.0 placement minimum."
            elif isinstance(cgpa, (int, float)) and cgpa >= 6.0:
                cgpa_status = f"✅ {username}'s CGPA is {cgpa}, meets placement eligibility."
            else:
                cgpa_status = f"{username} has not calculated their CGPA yet."

            system_prompt = f"""You are an intelligent and friendly academic assistant for VIT (Vellore Institute of Technology) students.
You are currently helping a student named {username}.

Their personal academic data:
- CGPA: {cgpa}
- Attendance: {attendance}%
- Semester: {user['semester'] or 'Not set'}
- Branch: {user['branch'] or 'Not set'}

Attendance Status: {att_status}
CGPA Status: {cgpa_status}

Use this personal data naturally when answering relevant questions.

VIT ACADEMIC CALENDAR — WINTER SEMESTER 2025-26:

1. CAT 1: Tuesday, 27th January 2026 to Sunday, 2nd February 2026. Closed book. Part of internal assessment.
2. CAT 2: 15th March 2026 to 23rd March 2026. OPEN BOOK — physical books and handwritten notes allowed. No electronic devices.
3. FAT: Starts Monday, 20th April 2026. Closed book. 60% weightage. Min 75% attendance required.
4. RIVIERA 2026: 26th February to 1st March 2026 at VIT Vellore. Cultural fest with celebrity performances, competitions, workshops.
5. ATTENDANCE RULES: Min 75% per subject for FAT eligibility. 65-74% can apply for condonation. Below 65% is detained.
6. CGPA: S=10, A=9, B=8, C=7, D=6, E=5, F=0, N=0. Minimum 6.0 for placements.
7. REVALUATION: Apply via VTOP → Academics → Exam → Apply for Revaluation. Opens 2-3 weeks after results.
8. PREVIOUS PAPERS: VTOP → Academics → Course Page → Digital Learning → Previous Year Question Papers.
9. VTOP: vtop.vit.ac.in — use for attendance, marks, exam timetable, fee payment, course registration.

Be friendly, clear and professional. Use {username}'s name occasionally. Keep responses concise."""

            try:
                client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
                response = client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=msg,
                    config={"system_instruction": system_prompt}
                )
                reply = response.text
            except Exception as e:
                reply = f"Sorry, I'm having trouble connecting right now. Please try again later. (Error: {str(e)})"

    return render_template("chatbot.html", reply=reply)


# ---------------- TIMETABLE ----------------

# ---------------- TIMETABLE ----------------
@app.route("/timetable")
def timetable():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    init_timetable_tables(conn)
    init_profile_table(conn)
    init_smart_timetable_table(conn)

    user = conn.execute(
        "SELECT semester, timetable_plan FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()
    user_semester = user["semester"] or "1"
    user_plan = user["timetable_plan"] or ""

    # Load saved smart timetable if exists
    smart = conn.execute(
        "SELECT * FROM smart_timetable WHERE user_id=?",
        (session["user_id"],)
    ).fetchone()

    # Count seats per plan (number of students on each plan)
    seat_counts = {}
    for pid in ["A", "B", "C"]:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM smart_timetable WHERE plan_id=? AND semester=?",
            (pid, user_semester)
        ).fetchone()
        seat_counts[pid] = count["cnt"] if count else 0

    courses = conn.execute(
        "SELECT * FROM timetable_courses WHERE user_id=? ORDER BY id",
        (session["user_id"],)
    ).fetchall()
    slots = conn.execute(
        "SELECT slot_code, course_id FROM slot_assignments WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    course_dict = {c["id"]: dict(c) for c in courses}
    slot_map_data = {}
    for s in slots:
        cid = s["course_id"]
        if cid in course_dict:
            slot_map_data[s["slot_code"]] = course_dict[cid]

    sem_subjects = SEMESTER_COURSES.get(user_semester, [])

    return render_template(
        "timetable.html",
        courses=[dict(c) for c in courses],
        slot_map=slot_map_data,
        username=session.get("username", ""),
        user_semester=user_semester,
        user_plan=user_plan,
        smart_timetable=dict(smart) if smart else None,
        seat_counts=seat_counts,
        sem_subjects=sem_subjects,
        semester_courses=SEMESTER_COURSES,
        plan_templates=PLAN_TEMPLATES,
    )


# ---------------- SMART TIMETABLE SAVE ----------------
@app.route("/timetable/select-plan", methods=["POST"])
def timetable_select_plan():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    data = request.get_json()
    plan_id = data.get("plan_id")
    semester = data.get("semester", "1")
    subjects = data.get("subjects", [])

    conn = get_db_connection()
    init_smart_timetable_table(conn)
    init_profile_table(conn)

    conn.execute("""
        INSERT INTO smart_timetable (user_id, plan_id, semester, subjects_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            plan_id=excluded.plan_id,
            semester=excluded.semester,
            subjects_json=excluded.subjects_json
    """, (session["user_id"], plan_id, semester, json.dumps(subjects)))

    conn.execute(
        "UPDATE users SET timetable_plan=?, semester=? WHERE id=?",
        (plan_id, semester, session["user_id"])
    )
    conn.commit()
    conn.close()
    session["semester"] = semester
    return jsonify({"success": True})


# ---------------- TIMETABLE SAVE (legacy) ----------------
@app.route("/timetable/save", methods=["POST"])
def timetable_save():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    data = request.get_json()
    action = data.get("action")
    uid = session["user_id"]

    conn = get_db_connection()
    init_timetable_tables(conn)

    if action == "add_course":
        cursor = conn.execute(
            """INSERT INTO timetable_courses
               (user_id, course_code, course_name, faculty, venue, color_idx)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uid, data.get("courseCode", ""), data["courseName"],
             data.get("faculty", ""), data.get("venue", ""), data.get("colorIdx", 0))
        )
        course_id = cursor.lastrowid
        for slot_code in data.get("slotCodes", []):
            conn.execute(
                """INSERT INTO slot_assignments (user_id, slot_code, course_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, slot_code) DO UPDATE SET course_id=excluded.course_id""",
                (uid, slot_code, course_id)
            )
        conn.commit()
        course = conn.execute("SELECT * FROM timetable_courses WHERE id=?", (course_id,)).fetchone()
        conn.close()
        return jsonify({"success": True, "course": dict(course)})

    elif action == "assign_slot":
        conn.execute(
            """INSERT INTO slot_assignments (user_id, slot_code, course_id)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, slot_code) DO UPDATE SET course_id=excluded.course_id""",
            (uid, data["slotCode"], data["courseId"])
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    conn.close()
    return jsonify({"error": "unknown action"}), 400


# ---------------- TIMETABLE DELETE ----------------
@app.route("/timetable/delete", methods=["POST"])
def timetable_delete():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    data = request.get_json()
    action = data.get("action")
    uid = session["user_id"]
    conn = get_db_connection()

    if action == "clear_slot":
        conn.execute("DELETE FROM slot_assignments WHERE user_id=? AND slot_code=?", (uid, data["slotCode"]))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif action == "delete_course":
        cid = data["courseId"]
        conn.execute("DELETE FROM slot_assignments WHERE user_id=? AND course_id=?", (uid, cid))
        conn.execute("DELETE FROM timetable_courses WHERE id=? AND user_id=?", (cid, uid))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    conn.close()
    return jsonify({"error": "unknown action"}), 400


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------------- RUN APP ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)