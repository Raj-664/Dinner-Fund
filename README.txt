Dinner Fund — Final UI + Working Theme
========================================
Replace ONLY these UI files:
templates/base.html
templates/dashboard.html
templates/dinner.html
templates/history.html
templates/people.html
static/css/style.css
static/js/app.js
static/images/dinner-bowl.svg
static/images/crew-food.svg
static/images/food-party.svg

Do NOT replace app.py, models.py, instance/dinner.db, or requirements.txt.

Theme:
- Top-right Light/Dark button works.
- Mobile has the same theme button in the sidebar.
- Theme is saved in localStorage as dinner-fund-theme.

After copying:
1. Stop Flask with Ctrl+C.
2. Start: python -m flask --app app run --debug
3. Open http://127.0.0.1:5000
4. Press Ctrl+F5 once.
