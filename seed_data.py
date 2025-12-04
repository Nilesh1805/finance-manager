# seed_data.py (updated)
from app import db, Expense, User, app
from datetime import date
import random

def seed():
    with app.app_context():
        db.create_all()
        # Clear previous data
        Expense.query.delete()
        User.query.delete()
        db.session.commit()

        # create a default user
        user = User(username='admin')
        user.set_password('admin')  # change password if you like
        db.session.add(user)
        db.session.commit()

        user_id = user.id

        categories = ['Food', 'Travel', 'Bills', 'Shopping', 'Entertainment']

        base_months = [
            ('2025-05-05', 8000),
            ('2025-06-03', 9500),
            ('2025-07-04', 11000),
            ('2025-08-06', 7000),
            ('2025-09-08', 12500),
            ('2025-10-10', 9000)
        ]

        for mdate, total in base_months:
            for i in range(12):
                amt = round(max(30, random.gauss(total/12, 200)), 2)
                cat = random.choice(categories)
                ex = Expense(amount=amt, category=cat, description=f"Sample {cat}", date=date.fromisoformat(mdate), user_id=user_id)
                db.session.add(ex)
        db.session.commit()
        print("Seeded sample data and created user 'admin' with password 'admin'")

if __name__ == "__main__":
    seed()
