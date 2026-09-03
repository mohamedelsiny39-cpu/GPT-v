import os
import time
import json
import urllib.request
import urllib.parse
from functools import wraps

from flask import Flask, jsonify, request, render_template, session, redirect, url_for

import db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
db.init_db()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "")


import logging

logger = logging.getLogger(__name__)


def check_telegram_membership(user_id: int, channel_username: str = None) -> bool:
    """بيتحقق حقيقي من اشتراك المستخدم في قناة تليجرام عن طريق Bot API"""
    channel = (channel_username or TELEGRAM_CHANNEL or "").strip().lstrip("@")
    if not channel or not BOT_TOKEN:
        logger.warning(
            "check_telegram_membership: TELEGRAM_CHANNEL أو BOT_TOKEN مش متظبطين "
            "(channel=%r, bot_token_set=%s)", channel, bool(BOT_TOKEN)
        )
        return False
    try:
        params = urllib.parse.urlencode({"chat_id": f"@{channel}", "user_id": user_id})
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?{params}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            logger.warning("check_telegram_membership: Telegram API رفض الطلب: %s", data)
            return False
        status = data["result"]["status"]
        return status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning("check_telegram_membership: exception %s", e)
        return False


def build_state(row):
    coins = row["coins"]
    energy = row["energy"]
    now = time.time()
    _, _, seconds_to_refill = db._apply_energy_regen(row, now)
    level = db.compute_level(coins)
    progress, next_th = db.level_progress(coins, level)

    return {
        "first_name": row["first_name"],
        "photo_url": row.get("photo_url", ""),
        "coins": coins,
        "energy": energy,
        "max_energy": row["max_energy"],
        "seconds_to_refill": seconds_to_refill,
        "level": level,
        "max_level": db.MAX_LEVEL,
        "coins_per_tap": db.coins_per_tap(level),
        "next_level_at": next_th,
        "level_progress": progress,
        "squares": db.city_state(coins, level),
        "total_taps": row["total_taps"],
        "ads_watched": row["ads_watched"],
        "ads": db.get_ad_status(row["user_id"]),
    }


# ---------- صفحات ----------

@app.route("/")
def index():
    return render_template("index.html", bot_username=BOT_USERNAME)


# ---------- API اللعبة ----------

@app.route("/api/state")
def api_state():
    user_id = request.args.get("user_id", type=int)
    first_name = request.args.get("first_name", default="", type=str)
    photo_url = request.args.get("photo_url", default="", type=str)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    row = db.get_or_create_user(user_id, first_name, photo_url)
    return jsonify(build_state(row))


@app.route("/api/tap_batch", methods=["POST"])
def api_tap_batch():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    count = data.get("count", 1)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    db.get_or_create_user(user_id, data.get("first_name", ""), data.get("photo_url", ""))
    result = db.tap_batch(user_id, int(count))
    if result is None:
        return jsonify({"error": "user not found"}), 404

    row = db.get_or_create_user(user_id)
    state = build_state(row)
    state["leveled_up"] = result["leveled_up"]
    state["building_completed"] = result["building_completed"]
    state["applied"] = result["applied"]
    return jsonify(state)


@app.route("/api/watch_ad", methods=["POST"])
def api_watch_ad():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    ad_type = data.get("ad_type", "interstitial")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    db.get_or_create_user(user_id, data.get("first_name", ""), data.get("photo_url", ""))
    result = db.watch_ad(user_id, ad_type)
    if result is None:
        return jsonify({"error": "user not found"}), 404
    if "error" in result:
        status = 429 if result["error"] in ("cooldown", "limit_reached") else 400
        return jsonify(result), status

    row = db.get_or_create_user(user_id)
    state = build_state(row)
    state["ad_reward"] = result["reward"]
    return jsonify(state)


@app.route("/api/checkin")
def api_checkin_status():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    db.get_or_create_user(user_id)
    return jsonify(db.get_checkin_status(user_id))


@app.route("/api/checkin/claim", methods=["POST"])
def api_checkin_claim():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    db.get_or_create_user(user_id, data.get("first_name", ""), data.get("photo_url", ""))
    result = db.claim_checkin(user_id)
    if "error" in result:
        return jsonify(result), 400
    row = db.get_or_create_user(user_id)
    state = build_state(row)
    state["checkin_reward"] = result["reward"]
    state["checkin_streak"] = result["streak"]
    return jsonify(state)


@app.route("/api/tasks")
def api_tasks():
    user_id = request.args.get("user_id", type=int)
    category = request.args.get("category", default="task", type=str)
    lang = request.args.get("lang", default="ar", type=str)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    db.get_or_create_user(user_id)
    return jsonify(db.list_tasks(user_id, category, lang))


@app.route("/api/tasks/claim", methods=["POST"])
def api_tasks_claim():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    task_id = data.get("task_id")
    if not user_id or not task_id:
        return jsonify({"error": "user_id and task_id required"}), 400

    # التحقق الحقيقي لو المهمة من نوع تليجرام
    all_tasks = db.admin_list_tasks()
    task_row = next((t for t in all_tasks if t["id"] == int(task_id)), None)
    telegram_verified = False
    if task_row and task_row["task_type"] == "telegram":
        telegram_verified = check_telegram_membership(user_id, task_row["channel_username"])

    result = db.claim_task(user_id, int(task_id), telegram_verified=telegram_verified)
    if "error" in result:
        return jsonify(result), 400

    row = db.get_or_create_user(user_id)
    state = build_state(row)
    state["claimed_reward"] = result["reward"]
    return jsonify(state)


@app.route("/api/referrals")
def api_referrals():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    db.get_or_create_user(user_id)
    info = db.get_referral_info(user_id)
    info["reward_per_invite"] = db.REFERRAL_REWARD
    info["signup_bonus"] = db.REFERRAL_SIGNUP_BONUS
    info["bot_username"] = BOT_USERNAME
    return jsonify(info)


@app.route("/api/leaderboard")
def api_leaderboard():
    user_id = request.args.get("user_id", type=int)
    board = db.get_leaderboard(100)
    my_rank = db.get_user_rank(user_id) if user_id else None
    return jsonify({"leaderboard": board, "my_rank": my_rank})


@app.route("/api/airdrop")
def api_airdrop():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    db.get_or_create_user(user_id)
    status = db.get_airdrop_status(user_id)
    return jsonify(status)


# ---------- الأدمن ----------

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "كلمة السر غلط"
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = db.get_stats()
    users = db.get_all_users()
    for u in users:
        u["level"] = db.compute_level(u["coins"])
    return render_template("admin.html", stats=stats, users=users, now=time.time())


@app.route("/admin/user/<int:user_id>/set_coins", methods=["POST"])
@admin_required
def admin_set_coins(user_id):
    new_coins = request.form.get("new_coins", type=int)
    if new_coins is not None:
        db.admin_set_user_coins(user_id, new_coins)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/tasks")
@admin_required
def admin_tasks():
    tasks = db.admin_list_tasks()
    return render_template("admin_tasks.html", tasks=tasks)


@app.route("/admin/tasks/add", methods=["POST"])
@admin_required
def admin_tasks_add():
    data = {
        "category": request.form.get("category"),
        "task_type": request.form.get("task_type"),
        "title_ar": request.form.get("title_ar"),
        "title_en": request.form.get("title_en"),
        "reward": int(request.form.get("reward", 0)),
        "target": int(request.form.get("target", 0) or 0),
        "url": request.form.get("url", ""),
        "channel_username": request.form.get("channel_username", ""),
        "sort_order": int(request.form.get("sort_order", 0) or 0),
    }
    db.admin_add_task(data)
    return redirect(url_for("admin_tasks"))


@app.route("/admin/tasks/<int:task_id>/edit", methods=["POST"])
@admin_required
def admin_tasks_edit(task_id):
    data = {
        "title_ar": request.form.get("title_ar"),
        "title_en": request.form.get("title_en"),
        "reward": int(request.form.get("reward", 0)),
        "target": int(request.form.get("target", 0) or 0),
        "url": request.form.get("url", ""),
        "channel_username": request.form.get("channel_username", ""),
        "sort_order": int(request.form.get("sort_order", 0) or 0),
    }
    db.admin_update_task(task_id, data)
    return redirect(url_for("admin_tasks"))


@app.route("/admin/tasks/<int:task_id>/toggle", methods=["POST"])
@admin_required
def admin_tasks_toggle(task_id):
    db.admin_toggle_task(task_id)
    return redirect(url_for("admin_tasks"))


@app.route("/admin/tasks/<int:task_id>/delete", methods=["POST"])
@admin_required
def admin_tasks_delete(task_id):
    db.admin_delete_task(task_id)
    return redirect(url_for("admin_tasks"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
