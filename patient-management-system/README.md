# CarePoint — Patient Management System

A responsive educational hospital-management demo built with Python, Flask, SQLite, HTML, CSS and JavaScript.

## Features
- Register, view, search, edit and delete patient records
- Save prescription records linked to patients
- Create bills and update payment status
- Export patient records to CSV
- Responsive dashboard with summary cards
- SQLite database initialised automatically

## Requirements
- Python 3.10 or newer
- pip
- A web browser

## Run locally (Windows)
1. Extract the project ZIP and open its folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use Command Prompt and run:

   ```bat
   .venv\Scripts\activate.bat
   ```

4. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

5. Start the app:

   ```bash
   python app.py
   ```

6. Open http://127.0.0.1:5000 in your browser.

The database is created automatically at `instance/hospital.db`. Do not commit the database file to GitHub.

## Deploy to Render
1. Push this project to a GitHub repository.
2. In Render, choose **New → Web Service** and connect the repository.
3. Set:
   - Runtime / Language: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Add an environment variable named `SECRET_KEY` with a long random value.
5. Create the web service and wait for the deploy to finish.

### Important database note
The default SQLite database is stored in the app's local `instance/` directory. On hosting platforms with an ephemeral filesystem, saved records can disappear after a restart or redeploy. For durable hosted storage, configure a persistent disk and set `DATABASE_PATH` to a file on that disk, or migrate to a managed database. Do not use this demo for real patient information.

## Safety and privacy
This is a learning/demo application, not a production hospital system. It does not include user login, role-based access, audit trails, CSRF protection or production-grade medical-data safeguards. Use fictional sample data only. Before handling real health information, obtain appropriate professional security and privacy review and add authentication, authorisation, CSRF protection, secure configuration, backups and applicable legal compliance.

## Suggested resume description
**Patient Management System | Python Flask, SQLite, HTML, CSS, JavaScript**
- Developed a responsive web-based patient management application for registration, search, update and record maintenance.
- Implemented prescription record keeping and billing workflows with payment-status tracking.
- Added CSV export for patient reporting and used SQLite for persistent local data storage.
