from datetime import datetime, timedelta

from flask import Flask, redirect, render_template, request, session, url_for

from services.admin_service import AdminConfigService
from services.data_service import DataService
from services.prediction_engine import PredictionEngine
from services.subscription import SubscriptionService

app = Flask(__name__)
app.secret_key = "crystal-sports-dev-secret"

app.config["DATA_SERVICE"] = DataService()
app.config["PREDICTION_ENGINE"] = PredictionEngine()
app.config["SUBSCRIPTION_SERVICE"] = SubscriptionService()
app.config["ADMIN_SERVICE"] = AdminConfigService()


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
    plan_name = request.form.get("plan", session.get("subscription_plan", "free")) or "free"
    admin_service = app.config["ADMIN_SERVICE"]
    subscription = admin_service.get_plan(plan_name)

    if request.method == "POST":
        session["subscription_plan"] = plan_name
        session["subscription_expires"] = (
            datetime.now() + timedelta(days=30)
        ).strftime("%Y-%m-%d %H:%M:%S")

    active = app.config["SUBSCRIPTION_SERVICE"].is_active(
        session.get("subscription_plan"), session.get("subscription_expires")
    )

    if not active:
        session["subscription_plan"] = "free"
        subscription = admin_service.get_plan("free")

    matches = app.config["DATA_SERVICE"].get_live_matches()
    picks = app.config["PREDICTION_ENGINE"].build_slips(matches, subscription, admin_service.get_config())

    if subscription.get("name", "").lower() == "vip":
        combo_slips = app.config["PREDICTION_ENGINE"].build_magic_combinations(matches, subscription, admin_service.get_config())
    else:
        combo_slips = []

    return render_template(
        "predictions.html",
        picks=picks,
        combo_slips=combo_slips,
        subscription=subscription,
        leagues=app.config["DATA_SERVICE"].get_configured_leagues(),
        admin_config=admin_service.get_config(),
    )


@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    admin_service = app.config["ADMIN_SERVICE"]
    if request.method == "POST":
        admin_service.update_from_form(request)
    return render_template("admin.html", admin_config=admin_service.get_config(), sports=admin_service.get_available_sports())


@app.route("/reset")
def reset_subscription():
    session.pop("subscription_plan", None)
    session.pop("subscription_expires", None)
    return redirect(url_for("pricing"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
