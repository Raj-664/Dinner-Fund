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

from models import DinnerItem, FoodQuantity, Payment, db


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


def get_food_quantities_from_form():
    """Read optional person/quantity rows from the dinner form.

    No person or quantity is created automatically. Rows are saved only when
    the user provides both a person name and a quantity.
    """
    people = request.form.getlist("quantity_person[]")
    quantities = request.form.getlist("quantity[]")

    rows = []
    max_rows = max(len(people), len(quantities))

    for index in range(max_rows):
        person = clean_text(people[index] if index < len(people) else "")
        raw_quantity = quantities[index] if index < len(quantities) else ""
        raw_quantity = clean_text(raw_quantity)

        # Completely empty rows are ignored.
        if not person and not raw_quantity:
            continue

        # A partially completed row is invalid.
        if not person:
            return None, "Please select/enter a person for every quantity row."

        if not raw_quantity:
            return None, f"Please enter a quantity for {person}."

        try:
            quantity = float(raw_quantity)
        except (TypeError, ValueError):
            return None, f"Please enter a valid quantity for {person}."

        if quantity <= 0:
            return None, f"Quantity for {person} must be greater than zero."

        if quantity > 1000000:
            return None, f"Quantity for {person} is too large."

        rows.append(
            {
                "person_name": person,
                "quantity": quantity,
            }
        )

    return rows, None


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
    """Build per-person payment and dinner-purchase summary.

    The People page intentionally exposes only:
    - Total paid
    - Food purchases
    - Food amount brought

    Food quantities are shown in the Dinner/History views, not here.
    """
    people = {}

    def entry(name):
        name = clean_text(name)
        if not name:
            return None
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
        row = entry(person)
        if row is not None:
            row["paid"] = float(amount or 0)

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
        if row is not None:
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

    # FoodQuantity records are linked to each DinnerItem through
    # item.quantities. No person or quantity is created automatically.
    for item in items:
        item.quantities = list(item.quantities)

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

        quantity_rows, quantity_error = get_food_quantities_from_form()

        if not food:
            error = "Food name is required."

        elif not person:
            error = (
                "Please select who bought/brought the food."
            )

        elif quantity_error:
            error = quantity_error

        if error:
            flash(error, "error")

            return redirect(
                url_for("add_dinner")
            )

        # Create the main dinner item first.
        dinner_item = DinnerItem(
            food_name=food,
            amount=amount,
            person_name=person,
            date=day,
            note=note,
        )

        db.session.add(dinner_item)
        db.session.flush()

        # Save only the quantity rows explicitly entered by the user.
        for row in quantity_rows:
            db.session.add(
                FoodQuantity(
                    dinner_item_id=dinner_item.id,
                    person_name=row["person_name"],
                    quantity=row["quantity"],
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
        persons=[
            row["name"]
            for row in people_summary()
        ],
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

        quantity_rows, quantity_error = get_food_quantities_from_form()

        if not food:
            error = "Food name is required."

        elif not person:
            error = (
                "Please select who bought/brought the food."
            )

        elif quantity_error:
            error = quantity_error

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

        # Replace the old quantity rows with exactly what the user
        # entered during this edit.
        FoodQuantity.query.filter_by(
            dinner_item_id=item.id
        ).delete(
            synchronize_session=False
        )

        for row in quantity_rows:
            db.session.add(
                FoodQuantity(
                    dinner_item_id=item.id,
                    person_name=row["person_name"],
                    quantity=row["quantity"],
                )
            )

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
        persons=[
            row["name"]
            for row in people_summary()
        ],
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
@app.route("/people/<path:person_name>/edit", methods=["GET", "POST"])
def edit_person(person_name):
    old_name = clean_text(person_name)

    if not old_name:
        flash("Person name is required.", "error")
        return redirect(url_for("people"))

    if request.method == "POST":
        new_name = clean_text(request.form.get("person_name"))

        if not new_name:
            flash("Person name is required.", "error")
            return redirect(url_for("edit_person", person_name=old_name))

        if new_name.lower() != old_name.lower():
            existing = people_summary()

            if any(
                row["name"].lower() == new_name.lower()
                for row in existing
            ):
                flash(
                    f"Person '{new_name}' already exists. "
                    "Use a different name.",
                    "error",
                )
                return redirect(
                    url_for("edit_person", person_name=old_name)
                )

        # Rename this person everywhere in the application.
        Payment.query.filter_by(person_name=old_name).update(
            {"person_name": new_name},
            synchronize_session=False,
        )

        DinnerItem.query.filter_by(person_name=old_name).update(
            {"person_name": new_name},
            synchronize_session=False,
        )

        FoodQuantity.query.filter_by(person_name=old_name).update(
            {"person_name": new_name},
            synchronize_session=False,
        )

        db.session.commit()

        flash(
            f"Person '{old_name}' renamed to '{new_name}'.",
            "success",
        )
        return redirect(url_for("people"))

    return render_template(
        "person_form.html",
        active="people",
        person_name=old_name,
    )


@app.route("/people/<path:person_name>/delete", methods=["POST"])
def delete_person(person_name):
    name = clean_text(person_name)

    if not name:
        flash("Person name is required.", "error")
        return redirect(url_for("people"))

    # Remove quantity rows where this person is a consumer/requester.
    FoodQuantity.query.filter_by(
        person_name=name
    ).delete(synchronize_session=False)

    # DinnerItem is the parent of FoodQuantity. Because this is a bulk
    # delete, SQLAlchemy's relationship cascade is not triggered, so first
    # collect and remove all quantity rows belonging to dinners bought by
    # this person.
    dinner_ids = [
        row[0]
        for row in db.session.query(DinnerItem.id)
        .filter(DinnerItem.person_name == name)
        .all()
    ]

    if dinner_ids:
        FoodQuantity.query.filter(
            FoodQuantity.dinner_item_id.in_(dinner_ids)
        ).delete(synchronize_session=False)

        DinnerItem.query.filter(
            DinnerItem.id.in_(dinner_ids)
        ).delete(synchronize_session=False)

    # Finally remove this person's payment records.
    Payment.query.filter_by(
        person_name=name
    ).delete(synchronize_session=False)

    db.session.commit()

    flash(
        f"Person '{name}' and all of their records were deleted.",
        "success",
    )

    return redirect(url_for("people"))


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

    quantity_records = (
        db.session.query(FoodQuantity, DinnerItem)
        .join(
            DinnerItem,
            FoodQuantity.dinner_item_id == DinnerItem.id,
        )
        .order_by(
            DinnerItem.date.desc(),
            DinnerItem.id.desc(),
            FoodQuantity.id.asc(),
        )
        .all()
    )

    # Group quantity records by the actual dinner date. The History template
    # can show the date once and then list all food/person/quantity rows below.
    quantity_history_by_date = []

    grouped = {}
    for quantity, item in quantity_records:
        day = item.date
        if day not in grouped:
            grouped[day] = {
                "date": day,
                "records": [],
            }

        grouped[day]["records"].append(
            {
                "food_name": item.food_name,
                "person_name": quantity.person_name,
                "quantity": float(quantity.quantity),
            }
        )

    quantity_history_by_date = sorted(
        grouped.values(),
        key=lambda group: group["date"],
        reverse=True,
    )

    return render_template(
        "history.html",
        active="history",
        rows=rows,
        total_paid=total_paid(),
        total_food=total_food(),
        quantity_history=quantity_records,
        quantity_history_by_date=quantity_history_by_date,
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