import csv
import io
import os
import sqlite3
from datetime import date
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-for-local-development")

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


@app.route("/")
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
def delete_patient(patient_id):
    with get_db() as db:
        db.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        db.commit()
    flash("Patient and associated demo records deleted.", "success")
    return redirect(url_for("dashboard") + "#patients")


@app.route("/prescriptions/add", methods=["POST"])
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
