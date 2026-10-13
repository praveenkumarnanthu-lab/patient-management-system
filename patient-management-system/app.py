import csv
import hmac
import io
import os
import re
import secrets
import sqlite3
from functools import wraps
from datetime import date
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-only-change-this-secret-before-deploying")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,  # 8 hours
)
def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.before_request
def protect_post_requests_with_csrf():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not submitted or not hmac.compare_digest(submitted, expected):
            abort(400, description="Invalid or missing security token. Refresh the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DATABASE = os.environ.get("DATABASE_PATH", str(INSTANCE_DIR / "hospital.db"))


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            age INTEGER NOT NULL CHECK(age BETWEEN 0 AND 120),
            gender TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT DEFAULT '',
            address TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            diagnosis TEXT NOT NULL,
            medicines TEXT NOT NULL,
            doctor_notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            payment_status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
        );
        """)
        db.commit()


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(name) < 2 or len(name) > 80:
            flash("Name must be between 2 and 80 characters.", "error")
        elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 8 or len(password) > 128:
            flash("Password must be 8 to 128 characters long.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            try:
                with get_db() as db:
                    db.execute(
                        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                        (name, email, generate_password_hash(password), date.today().isoformat()),
                    )
                    db.commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists. Please log in.", "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    search = request.args.get("q", "").strip()
    edit_id = request.args.get("edit", type=int)

    with get_db() as db:
        totals = {
            "patients": db.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
            "prescriptions": db.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0],
            "bills": db.execute("SELECT COUNT(*) FROM bills").fetchone()[0],
            "pending": db.execute("SELECT COUNT(*) FROM bills WHERE payment_status = 'Pending'").fetchone()[0],
        }

        if search:
            patients = db.execute("""
                SELECT * FROM patients
                WHERE full_name LIKE ? OR phone LIKE ? OR email LIKE ?
                ORDER BY id DESC
            """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
        else:
            patients = db.execute("SELECT * FROM patients ORDER BY id DESC").fetchall()

        prescriptions = db.execute("""
            SELECT prescriptions.*, patients.full_name AS patient_name
            FROM prescriptions JOIN patients ON patients.id = prescriptions.patient_id
            ORDER BY prescriptions.id DESC LIMIT 50
        """).fetchall()

        bills = db.execute("""
            SELECT bills.*, patients.full_name AS patient_name
            FROM bills JOIN patients ON patients.id = bills.patient_id
            ORDER BY bills.id DESC LIMIT 50
        """).fetchall()

        patient_options = db.execute(
            "SELECT id, full_name FROM patients ORDER BY full_name"
        ).fetchall()

        edit_patient = None
        if edit_id:
            edit_patient = db.execute(
                "SELECT * FROM patients WHERE id = ?", (edit_id,)
            ).fetchone()
            if edit_patient is None:
                flash("Patient record not found.", "error")
                return redirect(url_for("dashboard"))

    return render_template(
        "index.html",
        totals=totals,
        patients=patients,
        prescriptions=prescriptions,
        bills=bills,
        patient_options=patient_options,
        edit_patient=edit_patient,
        search=search,
        today=date.today().isoformat(),
    )


@app.route("/patients/save", methods=["POST"])
@login_required
def save_patient():
    patient_id = request.form.get("patient_id", "").strip()
    full_name = request.form.get("full_name", "").strip()
    age_text = request.form.get("age", "").strip()
    gender = request.form.get("gender", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    address = request.form.get("address", "").strip()

    if not full_name or not age_text or not gender or not phone:
        flash("Please fill in all required patient fields.", "error")
        return redirect(url_for("dashboard") + "#patients")

    try:
        age = int(age_text)
        if not 0 <= age <= 120:
            raise ValueError
    except ValueError:
        flash("Age must be a number between 0 and 120.", "error")
        return redirect(url_for("dashboard") + "#patients")

    with get_db() as db:
        if patient_id:
            db.execute("""
                UPDATE patients
                SET full_name=?, age=?, gender=?, phone=?, email=?, address=?
                WHERE id=?
            """, (full_name, age, gender, phone, email, address, patient_id))
            flash("Patient details updated.", "success")
        else:
            db.execute("""
                INSERT INTO patients (full_name, age, gender, phone, email, address, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (full_name, age, gender, phone, email, address, date.today().isoformat()))
            flash("Patient registered successfully.", "success")
        db.commit()

    return redirect(url_for("dashboard") + "#patients")


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
@login_required
def delete_patient(patient_id):
    with get_db() as db:
        db.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        db.commit()
    flash("Patient and associated demo records deleted.", "success")
    return redirect(url_for("dashboard") + "#patients")


@app.route("/prescriptions/add", methods=["POST"])
@login_required
def add_prescription():
    patient_id = request.form.get("patient_id", type=int)
    diagnosis = request.form.get("diagnosis", "").strip()
    medicines = request.form.get("medicines", "").strip()
    doctor_notes = request.form.get("doctor_notes", "").strip()

    if not patient_id or not diagnosis or not medicines:
        flash("Choose a patient and complete diagnosis and medicines.", "error")
        return redirect(url_for("dashboard") + "#prescriptions")

    with get_db() as db:
        exists = db.execute("SELECT id FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if not exists:
            flash("Please choose a valid patient.", "error")
            return redirect(url_for("dashboard") + "#prescriptions")
        db.execute("""
            INSERT INTO prescriptions (patient_id, diagnosis, medicines, doctor_notes, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, diagnosis, medicines, doctor_notes, date.today().isoformat()))
        db.commit()

    flash("Prescription saved.", "success")
    return redirect(url_for("dashboard") + "#prescriptions")


@app.route("/billing/add", methods=["POST"])
@login_required
def add_bill():
    patient_id = request.form.get("patient_id", type=int)
    description = request.form.get("description", "").strip()
    amount_text = request.form.get("amount", "").strip()
    status = request.form.get("payment_status", "Pending")

    if not patient_id or not description or not amount_text:
        flash("Please complete all required billing fields.", "error")
        return redirect(url_for("dashboard") + "#billing")

    try:
        amount = float(amount_text)
        if amount < 0 or amount > 100000000:
            raise ValueError
    except ValueError:
        flash("Enter a valid non-negative bill amount.", "error")
        return redirect(url_for("dashboard") + "#billing")

    if status not in ("Paid", "Pending"):
        status = "Pending"

    with get_db() as db:
        exists = db.execute("SELECT id FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if not exists:
            flash("Please choose a valid patient.", "error")
            return redirect(url_for("dashboard") + "#billing")
        db.execute("""
            INSERT INTO bills (patient_id, description, amount, payment_status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (patient_id, description, amount, status, date.today().isoformat()))
        db.commit()

    flash("Bill created successfully.", "success")
    return redirect(url_for("dashboard") + "#billing")


@app.route("/bills/<int:bill_id>/status", methods=["POST"])
@login_required
def update_bill_status(bill_id):
    status = request.form.get("payment_status", "Pending")
    if status not in ("Paid", "Pending"):
        status = "Pending"
    with get_db() as db:
        db.execute("UPDATE bills SET payment_status=? WHERE id=?", (status, bill_id))
        db.commit()
    flash("Bill payment status updated.", "success")
    return redirect(url_for("dashboard") + "#billing")


@app.route("/export/patients.csv")
@login_required
def export_patients():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Patient ID", "Full Name", "Age", "Gender", "Phone", "Email", "Address", "Registered Date"])

    with get_db() as db:
        rows = db.execute("""
            SELECT id, full_name, age, gender, phone, email, address, created_at
            FROM patients ORDER BY id
        """).fetchall()
        for row in rows:
            writer.writerow(list(row))

    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    data.seek(0)
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name="patient_report.csv")


@app.route("/health")
def health():
    return {"status": "ok"}


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
