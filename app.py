from datetime import datetime, timedelta
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

UTILS_DIR = ROOT_DIR / "utils"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from flask import Flask, redirect, render_template, request, session, url_for

from services.admin_service import AdminConfigService
from services.data_service import DataService
from services.prediction_engine import PredictionEngine
from services.subscription import SubscriptionService
import models
from werkzeug.security import generate_password_hash
import re
try:
    import stripe
except Exception:
    stripe = None
from utils.email_utils import send_email
import secrets

app = Flask(__name__)
app.secret_key = "crystal-sports-dev-secret"

app.config["DATA_SERVICE"] = DataService()
app.config["PREDICTION_ENGINE"] = PredictionEngine()
app.config["SUBSCRIPTION_SERVICE"] = SubscriptionService()
app.config["ADMIN_SERVICE"] = AdminConfigService()
models.init_db()


def current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return models.get_user_by_id(uid)


def is_admin_user(user: dict | None) -> bool:
    return bool(user and user.get("is_admin"))


@app.route("/")
def index():
    data_service = app.config["DATA_SERVICE"]
    admin_service = app.config["ADMIN_SERVICE"]
    return render_template(
        "index.html",
        leagues=data_service.get_configured_leagues(),
        sports=admin_service.get_available_sports(),
    )


@app.route("/pricing")
def pricing():
    admin_service = app.config["ADMIN_SERVICE"]
    return render_template(
        "pricing.html",
        plans=admin_service.get_plans(),
    )


@app.route("/predictions", methods=["GET", "POST"])
def predictions():
    user = current_user()

    plan_name = user.get("plan", "free") if user else "free"
    expires_at = user.get("expires_at") if user else None
    admin_service = app.config["ADMIN_SERVICE"]
    subscription = admin_service.get_plan(plan_name)

    active = app.config["SUBSCRIPTION_SERVICE"].is_active(plan_name, expires_at)
    if not active:
        # downgrade to free
        plan_name = "free"
        subscription = admin_service.get_plan("free")

    matches = app.config["DATA_SERVICE"].get_live_matches()
    if is_admin_user(user):
        picks = app.config["PREDICTION_ENGINE"].build_slips(matches, subscription, admin_service.get_config())
        if subscription.get("name", "").lower() == "vip":
            combo_slips = app.config["PREDICTION_ENGINE"].build_magic_combinations(matches, subscription, admin_service.get_config())
        else:
            combo_slips = []
    else:
        picks = app.config["PREDICTION_ENGINE"].build_slips(matches, subscription, admin_service.get_config())
        combo_slips = []

    return render_template(
        "predictions.html",
        picks=picks,
        combo_slips=combo_slips,
        subscription=subscription,
        leagues=app.config["DATA_SERVICE"].get_configured_leagues(),
        admin_config=admin_service.get_config(),
        is_admin=is_admin_user(user),
    )


@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    user = current_user()
    if not is_admin_user(user):
        return redirect(url_for("predictions"))

    admin_service = app.config["ADMIN_SERVICE"]
    if request.method == "POST":
        target_username = request.form.get("target_username")
        target_plan = request.form.get("target_plan")
        if target_username and target_plan:
            target_user = models.get_user_by_username(target_username)
            if target_user:
                models.update_subscription(target_user["id"], target_plan)
        admin_service.update_from_form(request)
    return render_template("admin.html", admin_config=admin_service.get_config(), sports=admin_service.get_available_sports())


@app.route("/admin/create-user", methods=["GET", "POST"])
def admin_create_user():
    user = current_user()
    if not is_admin_user(user):
        return redirect(url_for("predictions"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        plan = request.form.get("plan", "free")
        if not username or not email:
            return render_template("admin.html", admin_config=app.config["ADMIN_SERVICE"].get_config(), sports=app.config["ADMIN_SERVICE"].get_available_sports(), error="Username and email are required")
        if models.get_user_by_username(username):
            return render_template("admin.html", admin_config=app.config["ADMIN_SERVICE"].get_config(), sports=app.config["ADMIN_SERVICE"].get_available_sports(), error="Username already exists")
        models.create_user(username, email, password or models.DEFAULT_ADMIN_PASSWORD, plan)
        return redirect(url_for("admin_panel"))
    return redirect(url_for("admin_panel"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        plan = request.form.get("plan", "free")
        if not username or not email or not password:
            return render_template("register.html", error="Missing fields")
        # basic email validation
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return render_template("register.html", error="Invalid email address")
        existing = models.get_user_by_username(username)
        if existing:
            return render_template("register.html", error="Username already exists")
        try:
            user = models.create_user(username, email, password, plan)
            # send confirmation email
            token = secrets.token_urlsafe(24)
            models.set_confirm_token(user['id'], token)
            confirm_link = url_for('confirm_email', token=token, _external=True)
            send_email(email, 'Confirm your Crystal Sports account', f'Click to confirm: {confirm_link}')
        except Exception as e:
            return render_template("register.html", error="Could not create account: %s" % str(e))
        session["user_id"] = user["id"]
        return redirect(url_for("predictions"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = models.verify_user(username, password)
        if not user:
            return render_template("login.html", error="Invalid credentials")
        session["user_id"] = user["id"]
        return redirect(request.args.get("next") or url_for("predictions"))
    return render_template("login.html")


@app.route('/confirm-email')
def confirm_email():
    token = request.args.get('token')
    if not token:
        return redirect(url_for('index'))
    user = models.confirm_email_by_token(token)
    if not user:
        return render_template('index.html', message='Invalid or expired confirmation token')
    return render_template('index.html', message='Email confirmed. Thank you!')


@app.route('/reset-request', methods=['GET', 'POST'])
def reset_request():
    if request.method == 'POST':
        email = request.form.get('email')
        user = None
        if email:
            # find user
            conn_user = models.get_user_by_username(email) if '@' not in email else None
            # allow lookup by email
            if not conn_user:
                # search by email
                # quick query
                def find_by_email(e):
                    all_users = []
                    # lightweight query
                    db = models.get_conn()
                    cur = db.cursor()
                    cur.execute("SELECT * FROM users WHERE email = ?", (e,))
                    r = cur.fetchone()
                    db.close()
                    return dict(r) if r else None
                conn_user = find_by_email(email)
            user = conn_user
        if user:
            token = secrets.token_urlsafe(24)
            models.set_reset_token(user['id'], token)
            link = url_for('reset_password', token=token, _external=True)
            send_email(user['email'], 'Reset your password', f'Reset link: {link}')
            return render_template('reset_request.html', message='Reset link sent if the email exists')
        return render_template('reset_request.html', message='Reset link sent if the email exists')
    return render_template('reset_request.html')


@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    valid = models.verify_reset_token(token)
    if not valid:
        return render_template('reset_password.html', error='Invalid or expired token')
    if request.method == 'POST':
        password = request.form.get('password')
        if not password or len(password) < 6:
            return render_template('reset_password.html', error='Password too short')
        ok = models.reset_password(token, password)
        if ok:
            return render_template('login.html', message='Password updated; please sign in')
        return render_template('reset_password.html', error='Could not update password')
    return render_template('reset_password.html')


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/account", methods=["GET", "POST"])
def account():
    user = current_user()
    if not user:
        return redirect(url_for("login", next="/account"))
    message = None
    if request.method == "POST":
        plan = request.form.get("plan", "free")
        models.update_subscription(user["id"], plan)
        user = models.get_user_by_id(user["id"])
        message = f"Plan updated to {plan}"
    purchases = models.get_purchases_for_user(user['id'])
    return render_template("account.html", user=user, message=message, purchases=purchases)


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    user = current_user()
    if not user:
        return redirect(url_for('login', next='/account'))
    if not stripe:
        return ("Stripe SDK not installed", 500)
    plan = request.form.get('plan') or 'pro'
    # simple pricing map (in cents)
    price_map = {'pro': 500, 'elite': 1500, 'vip': 3000}
    amount = price_map.get(plan, 500)
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
    if not stripe.api_key:
        return ("Missing STRIPE_SECRET_KEY environment variable", 500)
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='payment',
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': f'Crystal Sports {plan} plan'},
                    'unit_amount': amount,
                },
                'quantity': 1,
            }],
            metadata={'user_id': str(user['id']), 'plan': plan},
            success_url=url_for('checkout_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}&plan=' + plan,
            cancel_url=url_for('account', _external=True),
        )
        return {'checkout_url': session.url}
    except Exception as e:
        return (str(e), 500)


@app.route('/checkout-success')
def checkout_success():
    user = current_user()
    if not user:
        return redirect(url_for('login', next='/account'))
    session_id = request.args.get('session_id')
    plan = request.args.get('plan') or 'pro'
    if not stripe:
        return render_template('account.html', user=user, message='Payment processed (SDK missing).')
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
        if sess.payment_status == 'paid':
            # record purchase
            amt = 0
            cur = None
            try:
                if hasattr(sess, 'amount_total') and sess.amount_total:
                    amt = int(sess.amount_total)
                else:
                    # try to expand line_items
                    sess_exp = stripe.checkout.Session.retrieve(session_id, expand=['line_items'])
                    if sess_exp and getattr(sess_exp, 'line_items', None):
                        items = sess_exp.line_items.data
                        if items:
                            amt = int(items[0].amount_total or 0)
            except Exception:
                amt = 0
            models.create_purchase(user['id'], plan, amt, 'usd', session_id)
            models.update_subscription(user['id'], plan)
            user = models.get_user_by_id(user['id'])
            return render_template('account.html', user=user, message='Payment successful. Plan updated.')
    except Exception:
        pass
    return render_template('account.html', user=user, message='Payment processed — pending verification.')


@app.route("/reset")
def reset_subscription():
    session.pop("subscription_plan", None)
    session.pop("subscription_expires", None)
    return redirect(url_for("pricing"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)


@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = os.getenv('STRIPE_ENDPOINT_SECRET')
    if not stripe:
        return ('Stripe SDK missing', 500)
    if endpoint_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except Exception as e:
            return (f'Webhook error: {str(e)}', 400)
    else:
        # best-effort parse
        try:
            event = stripe.Event.construct_from(request.get_json(), stripe.api_key)
        except Exception as e:
            return (f'Event parse error: {e}', 400)

    # Handle the event
    if event.type == 'checkout.session.completed':
        sess = event.data.object
        # retrieve full session with line items
        try:
            stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
            sess_full = stripe.checkout.Session.retrieve(sess.id, expand=['line_items'])
            metadata = getattr(sess_full, 'metadata', {}) or {}
            user_id = int(metadata.get('user_id')) if metadata.get('user_id') else None
            plan = metadata.get('plan') or None
            amount = 0
            try:
                if hasattr(sess_full, 'amount_total') and sess_full.amount_total:
                    amount = int(sess_full.amount_total)
                elif sess_full.line_items and sess_full.line_items.data:
                    amount = int(sess_full.line_items.data[0].amount_total or 0)
            except Exception:
                amount = 0
            if user_id and plan:
                models.create_purchase(user_id, plan, amount, 'usd', sess_full.id)
                models.update_subscription(user_id, plan)
        except Exception as e:
            print('webhook processing error', e)

    return ('', 200)
