import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from flask_mail import Mail, Message
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Database - expect DATABASE_URL in environment (Postgres)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mail (SMTP) settings
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') in ['True', 'true', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Note: in production hash passwords!
    budget = db.Column(db.Float, default=0.0)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(80), nullable=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def create_tables():
    db.create_all()

# Routes - auth
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password').strip()
        budget = request.form.get('budget', '').strip()
        try:
            budget_val = float(budget) if budget else 0.0
        except ValueError:
            budget_val = 0.0
        if not email or not password:
            flash('Email and password required.', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        # NOTE: In production, hash the password (e.g., werkzeug.security.generate_password_hash)
        user = User(email=email, password=password, budget=budget_val)
        db.session.add(user)
        db.session.commit()
        flash('Registered. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password').strip()
        user = User.query.filter_by(email=email).first()
        if not user or user.password != password:
            flash('Invalid credentials.', 'error')
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'success')
    return redirect(url_for('login'))

# Routes - expenses
@app.route('/')
@login_required
def index():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    total = sum(e.amount for e in expenses)
    return render_template('index.html', expenses=expenses, total=total)

@app.route('/add', methods=['GET','POST'])
@login_required
def add():
    if request.method == 'POST':
        title = request.form.get('title').strip()
        amount = request.form.get('amount').strip()
        category = request.form.get('category').strip()
        date_str = request.form.get('date').strip()
        if not title or not amount:
            flash('Title and amount required.', 'error')
            return redirect(url_for('add'))
        try:
            amount_val = float(amount)
        except ValueError:
            flash('Invalid amount.', 'error')
            return redirect(url_for('add'))
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except Exception:
            date_obj = datetime.utcnow().date()
        expense = Expense(title=title, amount=amount_val, category=category or None, date=date_obj, user_id=current_user.id)
        db.session.add(expense)
        db.session.commit()

        # After adding, check if total exceeds user's budget and send email if so
        expenses = Expense.query.filter_by(user_id=current_user.id).all()
        total = sum(e.amount for e in expenses)
        try:
            user_budget = float(current_user.budget or 0.0)
        except Exception:
            user_budget = 0.0

        if user_budget > 0 and total > user_budget and app.config.get('MAIL_USERNAME'):
            try:
                msg = Message(subject="Budget exceeded - Expense Tracker",
                              recipients=[current_user.email])
                msg.body = f"Hello\\n\\nYour total expenses (₹{total:.2f}) have exceeded your budget (₹{user_budget:.2f}).\\n\\n- Expense Tracker"
                mail.send(msg)
            except Exception as e:
                app.logger.error('Failed to send email: %s', e)

        flash('Expense added.', 'success')
        return redirect(url_for('index'))
    return render_template('add.html')

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    exp = Expense.query.get_or_404(id)
    if exp.user_id != current_user.id:
        flash('Not allowed.', 'error')
        return redirect(url_for('index'))
    db.session.delete(exp)
    db.session.commit()
    flash('Expense deleted.', 'success')
    return redirect(url_for('index'))

@app.route('/download-pdf')
@login_required
def download_pdf():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.asc()).all()
    total = sum(e.amount for e in expenses)

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    p.setFont('Helvetica-Bold', 18)
    p.drawString(180, height - 50, 'Expense Report')
    p.setFont('Helvetica', 12)
    p.drawString(50, height - 70, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    p.drawString(50, height - 90, f'User: {current_user.email}')

    y = height - 130
    p.setFont('Helvetica-Bold', 12)
    headers = ['Date', 'Title', 'Category', 'Amount (₹)']
    x_positions = [50, 150, 350, 470]
    for i, h in enumerate(headers):
        p.drawString(x_positions[i], y, h)
    y -= 15
    p.line(45, y, 550, y)
    y -= 20
    p.setFont('Helvetica', 11)

    for e in expenses:
        if y < 80:
            p.showPage()
            y = height - 100
            p.setFont('Helvetica-Bold', 12)
            for i, h in enumerate(headers):
                p.drawString(x_positions[i], y, h)
            y -= 30
            p.setFont('Helvetica', 11)
        p.drawString(x_positions[0], y, e.date.strftime('%Y-%m-%d'))
        p.drawString(x_positions[1], y, e.title)
        p.drawString(x_positions[2], y, e.category or '-')
        p.drawRightString(x_positions[3] + 50, y, f'{e.amount:.2f}')
        y -= 20

    y -= 10
    p.line(45, y, 550, y)
    y -= 25
    p.setFont('Helvetica-Bold', 12)
    p.drawString(50, y, f'Total: ₹{total:.2f}')

    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='Expense_Report.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)