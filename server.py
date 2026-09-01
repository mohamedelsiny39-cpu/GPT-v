import os
import time
from functools import wraps

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    session,
    redirect,
    url_for,
    flash,
)

import db


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-secret-change-me",
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

db.init_db()


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "",
)

BOT_USERNAME = os.environ.get(
    "BOT_USERNAME",
    "",
)


# =========================================================
# USER STATE
# =========================================================

def build_state(row):

    coins = row["coins"]

    energy = row["energy"]

    now = time.time()

    _, _, seconds_to_refill = (
        db._apply_energy_regen(
            row,
            now,
        )
    )

    level = db.compute_level(
        coins
    )

    progress, next_th = (
        db.level_progress(
            coins,
            level,
        )
    )

    return {

        "user_id":
            row["user_id"],

        "first_name":
            row["first_name"],

        "photo_url":
            row.get(
                "photo_url",
                "",
            ),

        # اللغة
        "language":
            row.get(
                "language",
                "",
            ),

        # العملات
        "coins":
            coins,

        # الطاقة
        "energy":
            energy,

        "max_energy":
            row["max_energy"],

        "seconds_to_refill":
            seconds_to_refill,

        # المستوى
        "level":
            level,

        "max_level":
            db.MAX_LEVEL,

        "coins_per_tap":
            db.coins_per_tap(
                level
            ),

        "next_level_at":
            next_th,

        "level_progress":
            progress,

        # المدينة
        "squares":
            db.city_state(
                coins,
                level,
            ),

        # الإحصائيات
        "total_taps":
            row["total_taps"],

        "ads_watched":
            row["ads_watched"],

        "referral_count":
            row.get(
                "referral_count",
                0,
            ),

        "daily_streak":
            row.get(
                "daily_streak",
                0,
            ),

        "total_game_plays":
            row.get(
                "total_game_plays",
                0,
            ),

        "game_coins":
            row.get(
                "game_coins",
                0,
            ),
    }


# =========================================================
# MAIN PAGE
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html",
        bot_username=BOT_USERNAME,
    )


# =========================================================
# API - USER STATE
# =========================================================

@app.route("/api/state")
def api_state():

    user_id = request.args.get(
        "user_id",
        type=int,
    )

    first_name = request.args.get(
        "first_name",
        default="",
        type=str,
    )

    photo_url = request.args.get(
        "photo_url",
        default="",
        type=str,
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    row = db.get_or_create_user(
        user_id,
        first_name,
        photo_url,
    )

    return jsonify(
        build_state(row)
    )


# =========================================================
# API - LANGUAGE
# =========================================================

@app.route(
    "/api/language",
    methods=["GET"],
)
def api_get_language():

    user_id = request.args.get(
        "user_id",
        type=int,
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    row = db.get_or_create_user(
        user_id
    )

    return jsonify(
        {
            "language":
                row.get(
                    "language",
                    "",
                )
        }
    )


@app.route(
    "/api/language",
    methods=["POST"],
)
def api_set_language():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    user_id = data.get(
        "user_id"
    )

    language = data.get(
        "language",
        ""
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    if language not in (
        "ar",
        "en",
    ):

        return jsonify(
            {
                "error":
                    "invalid_language"
            }
        ), 400

    db.get_or_create_user(
        user_id,
        data.get(
            "first_name",
            "",
        ),
        data.get(
            "photo_url",
            "",
        ),
    )

    success = (
        db.set_user_language(
            user_id,
            language,
        )
    )

    if not success:

        return jsonify(
            {
                "error":
                    "could_not_save_language"
            }
        ), 400

    row = db.get_or_create_user(
        user_id
    )

    state = build_state(
        row
    )

    return jsonify(
        state
    )


# =========================================================
# API - TAPPING
# =========================================================

@app.route(
    "/api/tap_batch",
    methods=["POST"],
)
def api_tap_batch():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    user_id = data.get(
        "user_id"
    )

    count = data.get(
        "count",
        1,
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    db.get_or_create_user(
        user_id,
        data.get(
            "first_name",
            "",
        ),
        data.get(
            "photo_url",
            "",
        ),
    )

    try:

        count = int(
            count
        )

    except (
        ValueError,
        TypeError,
    ):

        count = 1

    result = db.tap_batch(
        user_id,
        count,
    )

    if result is None:

        return jsonify(
            {
                "error":
                    "user not found"
            }
        ), 404

    row = db.get_or_create_user(
        user_id
    )

    state = build_state(
        row
    )

    state["leveled_up"] = (
        result["leveled_up"]
    )

    state["applied"] = (
        result["applied"]
    )

    return jsonify(
        state
    )


# =========================================================
# API - ADS
# =========================================================

@app.route(
    "/api/watch_ad",
    methods=["POST"],
)
def api_watch_ad():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    user_id = data.get(
        "user_id"
    )

    ad_type = data.get(
        "ad_type",
        "interstitial",
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    db.get_or_create_user(
        user_id,
        data.get(
            "first_name",
            "",
        ),
        data.get(
            "photo_url",
            "",
        ),
    )

    result = db.watch_ad(
        user_id,
        ad_type,
    )

    if result is None:

        return jsonify(
            {
                "error":
                    "user not found"
            }
        ), 404

    if "error" in result:

        status = 400

        if result["error"] == "cooldown":

            status = 429

        elif result["error"] == "hourly_limit":

            status = 429

        return jsonify(
            result
        ), status

    row = db.get_or_create_user(
        user_id
    )

    state = build_state(
        row
    )

    state["ad_reward"] = (
        result["reward"]
    )

    state["ad_type"] = (
        result["ad_type"]
    )

    return jsonify(
        state
    )


# =========================================================
# API - TASKS
# =========================================================

@app.route("/api/tasks")
def api_tasks():

    user_id = request.args.get(
        "user_id",
        type=int,
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    db.get_or_create_user(
        user_id
    )

    return jsonify(
        db.get_tasks_status(
            user_id
        )
    )


@app.route(
    "/api/tasks/claim",
    methods=["POST"],
)
def api_tasks_claim():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    user_id = data.get(
        "user_id"
    )

    task_id = data.get(
        "task_id"
    )

    if (
        not user_id
        or not task_id
    ):

        return jsonify(
            {
                "error":
                    "user_id and task_id required"
            }
        ), 400

    result = db.claim_task(
        user_id,
        task_id,
    )

    if "error" in result:

        return jsonify(
            result
        ), 400

    row = db.get_or_create_user(
        user_id
    )

    state = build_state(
        row
    )

    state["claimed_reward"] = (
        result["reward"]
    )

    return jsonify(
        state
    )


# =========================================================
# API - REFERRALS
# =========================================================

@app.route("/api/referrals")
def api_referrals():

    user_id = request.args.get(
        "user_id",
        type=int,
    )

    if not user_id:

        return jsonify(
            {
                "error":
                    "user_id required"
            }
        ), 400

    db.get_or_create_user(
        user_id
    )

    info = db.get_referral_info(
        user_id
    )

    info["reward_per_invite"] = (
        db.REFERRAL_REWARD
    )

    info["signup_bonus"] = (
        db.REFERRAL_SIGNUP_BONUS
    )

    info["bot_username"] = (
        BOT_USERNAME
    )

    return jsonify(
        info
    )


# =========================================================
# API - LEADERBOARD
# =========================================================

@app.route("/api/leaderboard")
def api_leaderboard():

    user_id = request.args.get(
        "user_id",
        type=int,
    )

    board = db.get_leaderboard(
        20
    )

    my_rank = (
        db.get_user_rank(user_id)
        if user_id
        else None
    )

    return jsonify(
        {
            "leaderboard":
                board,

            "my_rank":
                my_rank,
        }
    )


# =========================================================
# ADMIN AUTH
# =========================================================

def admin_required(f):

    @wraps(f)

    def wrapper(
        *args,
        **kwargs,
    ):

        if not session.get(
            "is_admin"
        ):

            return redirect(
                url_for(
                    "admin_login"
                )
            )

        return f(
            *args,
            **kwargs,
        )

    return wrapper


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=[
        "GET",
        "POST",
    ],
)
def admin_login():

    error = None

    if request.method == "POST":

        password = request.form.get(
            "password",
            "",
        )

        if (
            ADMIN_PASSWORD
            and password
            == ADMIN_PASSWORD
        ):

            session["is_admin"] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        error = (
            "كلمة السر غلط"
        )

    return render_template(
        "admin_login.html",
        error=error,
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "is_admin",
        None,
    )

    return redirect(
        url_for(
            "admin_login"
        )
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    stats = db.get_stats()

    users = db.get_all_users()

    for user in users:

        user["level"] = (
            db.compute_level(
                user["coins"]
            )
        )

    return render_template(
        "admin.html",
        stats=stats,
        users=users,
        now=time.time(),
    )


# =========================================================
# ADMIN - UPDATE USER
# =========================================================

@app.route(
    "/admin/users/<int:user_id>/update",
    methods=["POST"],
)
@admin_required
def admin_update_user(
    user_id
):

    fields = [

        "first_name",

        "coins",

        "energy",

        "max_energy",

        "total_taps",

        "ads_watched",

        "referral_count",

        "referral_coins",

        "language",

        "daily_streak",
    ]

    updates = {

        field:
            request.form.get(
                field
            )

        for field in fields

        if field
        in request.form
    }

    try:

        updated = (
            db.update_user_by_admin(
                user_id,
                updates,
            )
        )

        if updated is None:

            flash(
                "اللاعب غير موجود.",
                "error",
            )

        else:

            player_name = (
                updated[
                    "first_name"
                ]
                or user_id
            )

            flash(
                f"تم تحديث بيانات اللاعب "
                f"{player_name} بنجاح.",
                "success",
            )

    except ValueError as exc:

        flash(
            str(exc),
            "error",
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# =========================================================
# ADMIN - RESET TASKS
# =========================================================

@app.route(
    "/admin/users/<int:user_id>/reset-tasks",
    methods=["POST"],
)
@admin_required
def admin_reset_user_tasks(
    user_id
):

    if db.reset_user_tasks_by_admin(
        user_id
    ):

        flash(
            "تم إعادة ضبط مكافآت "
            "المهام والإنجازات لهذا اللاعب.",
            "success",
        )

    else:

        flash(
            "اللاعب غير موجود.",
            "error",
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8080,
            )
        ),
    )
