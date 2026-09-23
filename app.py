import os
from datetime import date, datetime

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func

from models import DinnerItem, Payment, db


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Secret key:
# Online deployment should provide SECRET_KEY as an environment variable.
# The fallback keeps local development working.
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "dinner-fund-local-secret-key",
)


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------
# LOCAL:
#   If DATABASE_URL is not set, use:
#   instance/dinner.db
#
# ONLINE:
#   If DATABASE_URL is set, use the PostgreSQL database supplied by the
#   hosting provider.
# ---------------------------------------------------------------------------
database_url = os.environ.get("DATABASE_URL")

if database_url:
    # Convert common PostgreSQL URL formats to the psycopg SQLAlchemy format.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

else:
    # Local SQLite database.
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///"
        + os.path.join(
            BASE_DIR,
            "instance",
            "dinner.db",
        )
    )


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Helps recover stale database connections in a hosted environment.
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}


db.init_app(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_date(value, default=None):
    if not value:
        return default

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def clean_text(value):
    return (value or "").strip()


def clean_amount(value):
    """Return (amount, error)."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None, "Please enter a valid amount."

    if amount <= 0:
        return None, "Amount must be greater than zero."

    if amount > 100000000:
        return None, "Amount is too large."

    return round(amount, 2), None


def total_paid():
    return float(
        db.session.query(
            func.coalesce(func.sum(Payment.amount), 0.0)
        ).scalar()
        or 0.0
    )


def total_food():
    return float(
        db.session.query(
            func.coalesce(func.sum(DinnerItem.amount), 0.0)
        ).scalar()
        or 0.0
    )


def current_balance():
    return total_paid() - total_food()


def paid_before(day):
    return float(
        db.session.query(
            func.coalesce(func.sum(Payment.amount), 0.0)
        )
        .filter(Payment.date < day)
        .scalar()
        or 0.0
    )


def food_before(day):
    return float(
        db.session.query(
            func.coalesce(func.sum(DinnerItem.amount), 0.0)
        )
        .filter(DinnerItem.date < day)
        .scalar()
        or 0.0
    )


def balance_before(day):
    return paid_before(day) - food_before(day)


def daily_history():
    """Build the running-balance timeline, grouped by date."""
    payments_by_date = {}

    for day, amount in (
        db.session.query(
            Payment.date,
            func.sum(Payment.amount),
        )
        .group_by(Payment.date)
        .all()
    ):
        payments_by_date[day] = (
            payments_by_date.get(day, 0.0)
            + float(amount or 0)
        )

    food_by_date = {}

    for day, amount in (
        db.session.query(
            DinnerItem.date,
            func.sum(DinnerItem.amount),
        )
        .group_by(DinnerItem.date)
        .all()
    ):
        food_by_date[day] = (
            food_by_date.get(day, 0.0)
            + float(amount or 0)
        )

    all_dates = sorted(
        set(payments_by_date) | set(food_by_date)
    )

    rows = []
    running = 0.0

    for day in all_dates:
        paid = payments_by_date.get(day, 0.0)
        expense = food_by_date.get(day, 0.0)

        previous = running
        running = previous + paid - expense

        rows.append(
            {
                "date": day,
                "previous": previous,
                "paid": paid,
                "expense": expense,
                "remaining": running,
            }
        )

    return rows


def people_summary():
    people = {}

    def entry(name):
        return people.setdefault(
            name,
            {
                "name": name,
                "paid": 0.0,
                "food_count": 0,
                "food_amount": 0.0,
            },
        )

    for person, amount in (
        db.session.query(
            Payment.person_name,
            func.sum(Payment.amount),
        )
        .group_by(Payment.person_name)
        .all()
    ):
        entry(person)["paid"] = float(amount or 0)

    for person, count, amount in (
        db.session.query(
            DinnerItem.person_name,
            func.count(DinnerItem.id),
            func.sum(DinnerItem.amount),
        )
        .group_by(DinnerItem.person_name)
        .all()
    ):
        row = entry(person)
        row["food_count"] = int(count or 0)
        row["food_amount"] = float(amount or 0)

    return sorted(
        people.values(),
        key=lambda item: item["name"].lower(),
    )


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------
@app.template_filter("inr")
def inr(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0.0

    if value == int(value):
        return "\u20b9{:,.0f}".format(value)

    return "\u20b9{:,.2f}".format(value)


@app.template_filter("pretty_date")
def pretty_date(value, fmt="%d %b %Y"):
    if not value:
        return ""

    if isinstance(value, str):
        value = parse_date(value)

    return value.strftime(fmt) if value else ""


@app.context_processor
def inject_globals():
    return {
        "today": date.today(),
        "current_balance": current_balance,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    today = date.today()

    todays_items = (
        DinnerItem.query
        .filter_by(date=today)
        .order_by(
            DinnerItem.created_at.asc(),
            DinnerItem.id.asc(),
        )
        .all()
    )

    todays_expense = sum(
        item.amount for item in todays_items
    )

    recent_payments = (
        Payment.query
        .order_by(
            Payment.created_at.desc(),
            Payment.id.desc(),
        )
        .limit(6)
    )

    recent_dinner = (
        DinnerItem.query
        .order_by(
            DinnerItem.created_at.desc(),
            DinnerItem.id.desc(),
        )
        .limit(6)
    )

    transactions = []

    for payment in recent_payments:
        transactions.append(
            {
                "type": "Payment",
                "title": payment.person_name,
                "amount": payment.amount,
                "date": payment.date,
                "created_at": payment.created_at,
                "note": payment.note,
            }
        )

    for item in recent_dinner:
        transactions.append(
            {
                "type": "Dinner",
                "title": item.food_name,
                "person": item.person_name,
                "amount": item.amount,
                "date": item.date,
                "created_at": item.created_at,
                "note": item.note,
            }
        )

    transactions.sort(
        key=lambda t: t["created_at"],
        reverse=True,
    )

    transactions = transactions[:8]

    # Premium dashboard contributor list + current week's expenses.
    people = people_summary()

    monday = today.fromordinal(
        today.toordinal() - today.weekday()
    )

    weekly_expenses = []

    for offset in range(7):
        day = monday.fromordinal(
            monday.toordinal() + offset
        )

        amount = (
            db.session.query(
                func.coalesce(
                    func.sum(DinnerItem.amount),
                    0.0,
                )
            )
            .filter(DinnerItem.date == day)
            .scalar()
            or 0.0
        )

        weekly_expenses.append(
            {
                "label": day.strftime("%a"),
                "amount": float(amount),
                "date": day,
            }
        )

    return render_template(
        "dashboard.html",
        active="dashboard",
        total_paid=total_paid(),
        todays_items=todays_items,
        todays_expense=todays_expense,
        people_count=len(people),
        people=people,
        weekly_expenses=weekly_expenses,
        transactions=transactions,
    )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@app.route("/payments")
def payments():
    person = clean_text(
        request.args.get("person")
    )

    start = parse_date(
        request.args.get("start")
    )

    end = parse_date(
        request.args.get("end")
    )

    query = Payment.query

    if person:
        query = query.filter(
            Payment.person_name.ilike(
                f"%{person}%"
            )
        )

    if start:
        query = query.filter(
            Payment.date >= start
        )

    if end:
        query = query.filter(
            Payment.date <= end
        )

    records = (
        query
        .order_by(
            Payment.date.desc(),
            Payment.id.desc(),
        )
        .all()
    )

    filtered_total = sum(
        item.amount for item in records
    )

    persons = [
        row["name"]
        for row in people_summary()
    ]

    return render_template(
        "payments.html",
        active="payments",
        payments=records,
        filtered_total=filtered_total,
        total_paid=total_paid(),
        persons=persons,
        filters={
            "person": person,
            "start": request.args.get(
                "start",
                "",
            ),
            "end": request.args.get(
                "end",
                "",
            ),
        },
    )


@app.route(
    "/payments/add",
    methods=["GET", "POST"],
)
def add_payment():
    if request.method == "POST":
        person = clean_text(
            request.form.get("person_name")
        )

        amount, error = clean_amount(
            request.form.get("amount")
        )

        day = parse_date(
            request.form.get("date"),
            date.today(),
        )

        note = clean_text(
            request.form.get("note")
        )

        if not person:
            error = "Person name is required."

        if error:
            flash(error, "error")
            return redirect(
                url_for("add_payment")
            )

        db.session.add(
            Payment(
                person_name=person,
                amount=amount,
                date=day,
                note=note,
            )
        )

        db.session.commit()

        flash(
            f"Payment of {inr(amount)} from {person} added.",
            "success",
        )

        return redirect(
            url_for("payments")
        )

    return render_template(
        "payment_form.html",
        active="payments",
        payment=None,
    )


@app.route(
    "/payments/<int:payment_id>/edit",
    methods=["GET", "POST"],
)
def edit_payment(payment_id):
    payment = Payment.query.get_or_404(
        payment_id
    )

    if request.method == "POST":
        person = clean_text(
            request.form.get("person_name")
        )

        amount, error = clean_amount(
            request.form.get("amount")
        )

        day = parse_date(
            request.form.get("date"),
            date.today(),
        )

        note = clean_text(
            request.form.get("note")
        )

        if not person:
            error = "Person name is required."

        if error:
            flash(error, "error")

            return redirect(
                url_for(
                    "edit_payment",
                    payment_id=payment.id,
                )
            )

        payment.person_name = person
        payment.amount = amount
        payment.date = day
        payment.note = note

        db.session.commit()

        flash(
            "Payment updated successfully.",
            "success",
        )

        return redirect(
            url_for("payments")
        )

    return render_template(
        "payment_form.html",
        active="payments",
        payment=payment,
    )


@app.route(
    "/payments/<int:payment_id>/delete",
    methods=["POST"],
)
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(
        payment_id
    )

    db.session.delete(payment)
    db.session.commit()

    flash(
        "Payment deleted.",
        "success",
    )

    return redirect(
        url_for("payments")
    )


# ---------------------------------------------------------------------------
# Dinner
# ---------------------------------------------------------------------------
@app.route("/dinner")
def dinner():
    selected = parse_date(
        request.args.get("date"),
        date.today(),
    )

    person = clean_text(
        request.args.get("person")
    )

    query = DinnerItem.query

    if selected:
        query = query.filter(
            DinnerItem.date == selected
        )

    if person:
        query = query.filter(
            DinnerItem.person_name.ilike(
                f"%{person}%"
            )
        )

    items = (
        query
        .order_by(
            DinnerItem.created_at.asc(),
            DinnerItem.id.asc(),
        )
        .all()
    )

    day_total = sum(
        item.amount for item in items
    )

    previous = (
        balance_before(selected)
        if selected
        else 0.0
    )

    return render_template(
        "dinner.html",
        active="dinner",
        items=items,
        selected=selected,
        day_total=day_total,
        previous=previous,
        remaining=previous - day_total,
        persons=[
            row["name"]
            for row in people_summary()
        ],
        person_filter=person,
        total_food=total_food(),
    )


@app.route(
    "/dinner/add",
    methods=["GET", "POST"],
)
def add_dinner():
    if request.method == "POST":
        food = clean_text(
            request.form.get("food_name")
        )

        amount, error = clean_amount(
            request.form.get("amount")
        )

        person = clean_text(
            request.form.get("person_name")
        )

        day = parse_date(
            request.form.get("date"),
            date.today(),
        )

        note = clean_text(
            request.form.get("note")
        )

        if not food:
            error = "Food name is required."

        elif not person:
            error = (
                "Please select who bought/brought the food."
            )

        if error:
            flash(error, "error")

            return redirect(
                url_for("add_dinner")
            )

        db.session.add(
            DinnerItem(
                food_name=food,
                amount=amount,
                person_name=person,
                date=day,
                note=note,
            )
        )

        db.session.commit()

        flash(
            f"Dinner item {food} ({inr(amount)}) "
            f"added to {pretty_date(day)}.",
            "success",
        )

        return redirect(
            url_for(
                "dinner",
                date=day.isoformat(),
            )
        )

    return render_template(
        "dinner_form.html",
        active="dinner",
        item=None,
    )


@app.route(
    "/dinner/<int:item_id>/edit",
    methods=["GET", "POST"],
)
def edit_dinner(item_id):
    item = DinnerItem.query.get_or_404(
        item_id
    )

    if request.method == "POST":
        food = clean_text(
            request.form.get("food_name")
        )

        amount, error = clean_amount(
            request.form.get("amount")
        )

        person = clean_text(
            request.form.get("person_name")
        )

        day = parse_date(
            request.form.get("date"),
            date.today(),
        )

        note = clean_text(
            request.form.get("note")
        )

        if not food:
            error = "Food name is required."

        elif not person:
            error = (
                "Please select who bought/brought the food."
            )

        if error:
            flash(error, "error")

            return redirect(
                url_for(
                    "edit_dinner",
                    item_id=item.id,
                )
            )

        item.food_name = food
        item.amount = amount
        item.person_name = person
        item.date = day
        item.note = note

        db.session.commit()

        flash(
            "Dinner item updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "dinner",
                date=day.isoformat(),
            )
        )

    return render_template(
        "dinner_form.html",
        active="dinner",
        item=item,
    )


@app.route(
    "/dinner/<int:item_id>/delete",
    methods=["POST"],
)
def delete_dinner(item_id):
    item = DinnerItem.query.get_or_404(
        item_id
    )

    day = item.date

    db.session.delete(item)
    db.session.commit()

    flash(
        "Dinner item deleted.",
        "success",
    )

    return redirect(
        url_for(
            "dinner",
            date=day.isoformat(),
        )
    )


# ---------------------------------------------------------------------------
# People & History
# ---------------------------------------------------------------------------
@app.route("/people")
def people():
    return render_template(
        "people.html",
        active="people",
        people=people_summary(),
    )


@app.route("/history")
def history():
    rows = daily_history()

    return render_template(
        "history.html",
        active="history",
        rows=rows,
        total_paid=total_paid(),
        total_food=total_food(),
    )


# ---------------------------------------------------------------------------
# Database initialization command
# ---------------------------------------------------------------------------
@app.cli.command("init-db")
def init_db():
    """Create the database tables."""
    db.create_all()
    print("Database initialised.")


# ---------------------------------------------------------------------------
# Create database tables
# ---------------------------------------------------------------------------
with app.app_context():
    # Only needed for local SQLite.
    # For PostgreSQL, the hosting environment provides DATABASE_URL.
    os.makedirs(
        os.path.join(BASE_DIR, "instance"),
        exist_ok=True,
    )

    db.create_all()


# ---------------------------------------------------------------------------
# Local development
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )