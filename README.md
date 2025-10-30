# Expense Tracker (Render-ready) with Auth, PostgreSQL, PDF export, and SMTP notifications

Features:
- PostgreSQL (configured by environment variable DATABASE_URL)
- User registration/login (Flask-Login)
- User-specific expenses (each user only sees their own data)
- Per-user budget (set at registration or in profile)
- Email notification (via SMTP) sent when total expenses exceed the user's budget
- PDF export (ReportLab) - formatted report
- Ready for Render (Procfile + render.yaml)

## Environment variables (set on Render or locally)
- DATABASE_URL = postgres://user:pass@host:port/dbname
- SECRET_KEY = your-secret-key
- MAIL_SERVER = smtp.gmail.com
- MAIL_PORT = 587
- MAIL_USE_TLS = True
- MAIL_USERNAME = your_email@gmail.com
- MAIL_PASSWORD = your_email_app_password

## Run locally (quick)
1. Create virtualenv and install deps:
   ```bash
   python -m venv venv
   source venv/bin/activate   # macOS/Linux
   venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```
2. Set environment variables (or use a local Postgres connection string in DATABASE_URL).
3. Run:
   ```bash
   python app.py
   ```
