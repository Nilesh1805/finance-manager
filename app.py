# app.py (replace your current app.py with this)
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import os

# authentication helpers
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'finance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'replace_this_with_a_strong_secret_key'
db = SQLAlchemy(app)

# -------------------------
# Flask-Login setup
# -------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # redirect to login when @login_required

# -------------------------
# Database models
# -------------------------
class User(UserMixin, db.Model):  # user model for authentication
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # link expense to user

    def to_dict(self):
        return {
            "id": self.id,
            "amount": self.amount,
            "category": self.category,
            "description": self.description,
            "date": self.date.isoformat()
        }

# user loader for flask-login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------
# Helpers (slightly modified to use current_user)
# -------------------------
def get_summary():
    today = datetime.now().date()
    start_of_month = today.replace(day=1)
    # monthly total for current user
    month_total = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.date >= start_of_month, Expense.user_id == current_user.id
    ).scalar() or 0.0
    total_all = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.user_id == current_user.id
    ).scalar() or 0.0
    cat_query = db.session.query(Expense.category, db.func.sum(Expense.amount)).filter(
        Expense.user_id == current_user.id
    ).group_by(Expense.category).all()
    category_data = {c: float(s) for c, s in cat_query}
    return {
        "month_total": float(month_total),
        "total_all": float(total_all),
        "category_data": category_data
    }

def prepare_monthly_df():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date).all()
    if not expenses:
        return None
    rows = [{"amount": e.amount, "date": e.date} for e in expenses]
    df = pd.DataFrame(rows)
    df['year_month'] = df['date'].apply(lambda d: d.strftime("%Y-%m"))
    monthly = df.groupby('year_month').agg(total_amount=('amount', 'sum')).reset_index()
    monthly['ym_dt'] = pd.to_datetime(monthly['year_month'] + "-01")
    monthly = monthly.sort_values('ym_dt').reset_index(drop=True)
    monthly['t'] = np.arange(len(monthly))
    return monthly

def predict_next_month():
    monthly = prepare_monthly_df()
    if monthly is None or len(monthly) < 2:
        return None
    X = monthly[['t']].values
    y = monthly['total_amount'].values
    model = LinearRegression()
    model.fit(X, y)
    next_t = np.array([[monthly['t'].max() + 1]])
    pred = model.predict(next_t)[0]
    monthly_series = monthly[['year_month', 'total_amount']].to_dict(orient='records')
    return {"prediction": float(pred), "history": monthly_series}

# -------------------------
# Routes for authentication
# -------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Please provide username and password', 'error')
            return render_template('register.html')
        existing = User.query.filter_by(username=username).first()
        if existing:
            flash('Username already exists', 'error')
            return render_template('register.html')
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

# -------------------------
# Normal routes (index is visible without login but better to require login)
# -------------------------
@app.route('/')
@login_required
def index():
    summary = get_summary()
    # fetch recent expenses for user
    recent = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).limit(10).all()
    recent_list = [r.to_dict() for r in recent]
    # Prepare data for charts
    categories = list(summary['category_data'].keys())
    cat_values = list(summary['category_data'].values())
    monthly_info = prepare_monthly_df()
    if monthly_info is not None:
        months = monthly_info['year_month'].tolist()
        totals = monthly_info['total_amount'].tolist()
    else:
        months = []
        totals = []
    return render_template('index.html',
                           summary=summary,
                           recent=recent_list,
                           categories=categories,
                           cat_values=cat_values,
                           months=months,
                           totals=totals)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        try:
            amount = float(request.form['amount'])
            category = request.form['category']
            description = request.form.get('description', '')
            date_str = request.form.get('date')
            if date_str:
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
            else:
                date = datetime.now().date()
            expense = Expense(amount=amount, category=category, description=description, date=date, user_id=current_user.id)
            db.session.add(expense)
            db.session.commit()
            flash('Expense added.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            return f"Error: {e}", 400
    default_date = datetime.now().strftime("%Y-%m-%d")
    return render_template('add.html', default_date=default_date)

@app.route('/predict')
@login_required
def predict():
    res = predict_next_month()
    if res is None:
        return render_template('predict.html', error="Not enough historical data (need at least 2 months).")
    return render_template('predict.html', prediction=res['prediction'], history=res['history'])


# change username and password

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get("action")

        # Change Username
        if action == "change_username":
            new_username = request.form['new_username'].strip()

            if not new_username:
                flash("Username cannot be empty.", "error")
                return redirect(url_for('profile'))

            # Check if username exists
            existing = User.query.filter_by(username=new_username).first()
            if existing:
                flash("This username is already taken.", "error")
                return redirect(url_for('profile'))

            current_user.username = new_username
            db.session.commit()
            flash("Username updated successfully!", "success")
            return redirect(url_for('profile'))

        # Change Password
        elif action == "change_password":
            old_password = request.form['old_password']
            new_password = request.form['new_password']

            if not current_user.check_password(old_password):
                flash("Old password is incorrect.", "error")
                return redirect(url_for('profile'))

            if len(new_password) < 6:
                flash("Password must be at least 6 characters long.", "error")
                return redirect(url_for('profile'))

            current_user.set_password(new_password)
            db.session.commit()
            flash("Password changed successfully!", "success")
            return redirect(url_for('profile'))

    return render_template('profile.html')


# ADD DELETE ACCOUNT ROUTE IN app.py
@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    password = request.form['password']

    # Check old password
    if not current_user.check_password(password):
        flash("Incorrect password. Account not deleted.", "error")
        return redirect(url_for('profile'))

    # Delete all expenses belonging to the user
    Expense.query.filter_by(user_id=current_user.id).delete()

    # Delete the user itself
    db.session.delete(current_user)
    db.session.commit()

    # Log the user out
    logout_user()
    flash("Your account has been permanently deleted.", "info")
    return redirect(url_for('login'))


# add a Delete Expense feature
@app.route("/delete/<int:id>")
@login_required
def delete_expense(id):
    expense = Expense.query.get_or_404(id)

    # Prevent deleting other users' expenses
    if expense.user_id != current_user.id:
        flash("Not allowed!", "error")
        return redirect("/")

    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted successfully!", "success")
    return redirect("/")



# API endpoint for quick adding (optional)
@app.route('/api/add', methods=['POST'])
@login_required
def api_add():
    data = request.json
    try:
        amount = float(data['amount'])
        category = data['category']
        description = data.get('description', '')
        date = datetime.strptime(data['date'], "%Y-%m-%d").date()
        expense = Expense(amount=amount, category=category, description=description, date=date, user_id=current_user.id)
        db.session.add(expense)
        db.session.commit()
        return jsonify({"status": "ok", "id": expense.id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# simple route to reset DB (useful while developing) - keep it OR remove for final
@app.route('/reset-db')
def reset_db():
    try:
        db.drop_all()
        db.create_all()
        return "DB reset done"
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
