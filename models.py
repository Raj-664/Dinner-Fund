from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    person_name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    note = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f"<Payment {self.person_name} {self.amount}>"


class DinnerItem(db.Model):
    __tablename__ = "dinner_items"

    id = db.Column(db.Integer, primary_key=True)
    food_name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    person_name = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    note = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    quantities = db.relationship(
        "FoodQuantity",
        backref="dinner_item",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<DinnerItem {self.food_name} {self.amount}>"


class FoodQuantity(db.Model):
    __tablename__ = "food_quantities"

    id = db.Column(db.Integer, primary_key=True)

    dinner_item_id = db.Column(
        db.Integer,
        db.ForeignKey("dinner_items.id"),
        nullable=False
    )

    person_name = db.Column(
        db.String(120),
        nullable=False
    )

    quantity = db.Column(
        db.Float,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now
    )

    def __repr__(self):
        return f"<FoodQuantity {self.person_name} {self.quantity}>"