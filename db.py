import sqlite3
import time
import random
import threading
import os
import datetime

DB_PATH = os.path.join(os.environ.get("DATA_DIR", "."), "cancel_game.db")
_lock = threading.Lock()

MAX_ENERGY = 100
FULL_REFILL_SECONDS = 3600  # الطاقة بترجع كاملة كل ساعة
MAX_LEVEL = 100

REFERRAL_REWARD = 500
REFERRAL_SIGNUP_BONUS = 100

# ---------- الإعلانات ----------
AD_REFILL_SECONDS = 3600  # كل نوع إعلان بيرجع يتجدد كل ساعة (زي الطاقة)
AD_MIN_GAP_SECONDS = 8    # أقل فاصل بين ضغطتين على أي زرار إعلان (حماية من double-click)
AD_CONFIG = {
    "interstitial": {"min_reward": 15, "max_reward": 20, "hourly_limit": 50},
    "popup": {"min_reward": 5, "max_reward": 10, "hourly_limit": 50},
}

# ---------- اللعبة البسيطة (صندوق الحظ) ----------
MINIGAME_HOURLY_LIMIT = 10
MINIGAME_MIN_REWARD = 10
MINIGAME_MAX_REWARD = 30

# ---------- تسجيل الدخول اليومي ----------
DAILY_REWARDS = [10, 15, 20, 25, 30, 40, 50]  # دورة 7 أيام، بترجع تلف تاني

# ---------- الإيردروب ----------
AIRDROP_DATE = "2026-09-25"
AIRDROP_PRIZE_EGP = 20000
AIRDROP_COIN_REQUIREMENT = 20000
AIRDROP_REFERRAL_REQUIREMENT = 10
AIRDROP_ENGAGEMENT_TAPS_REQUIREMENT = 3000  # مقياس "التفاعل" المقترح

# 10 معالم، كل واحد بيغطي 10 مستويات = 100 مستوى بالظبط
BUILDINGS = [
    {"name": "خيمة", "icon": "⛺"},
    {"name": "بيت طيني", "icon": "🏠"},
    {"name": "فيلا", "icon": "🏡"},
    {"name": "برج مكاتب", "icon": "🏢"},
    {"name": "مول تجاري", "icon": "🏬"},
    {"name": "معلم أثري", "icon": "🕌"},
    {"name": "مدينة ملاهي", "icon": "🎡"},
    {"name": "برج شهير", "icon": "🗼"},
    {"name": "استاد عالمي", "icon": "🏟️"},
    {"name": "مدينة المستقبل", "icon": "🌆"},
]


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock, _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                photo_url TEXT,
                coins INTEGER NOT NULL DEFAULT 0,
                energy INTEGER NOT NULL DEFAULT 100,
                max_energy INTEGER NOT NULL DEFAULT 100,
                last_full_refill REAL NOT NULL,
                total_taps INTEGER NOT NULL DEFAULT 0,
                ads_watched INTEGER NOT NULL DEFAULT 0,
                last_ad_time REAL NOT NULL DEFAULT 0,
                claimed_tasks TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                last_active REAL NOT NULL,
                referred_by INTEGER,
                referral_count INTEGER NOT NULL DEFAULT 0,
                referral_coins INTEGER NOT NULL DEFAULT 0,
                ad_interstitial_remaining INTEGER NOT NULL DEFAULT 20,
                ad_interstitial_refill REAL NOT NULL DEFAULT 0,
                ad_popup_remaining INTEGER NOT NULL DEFAULT 20,
                ad_popup_refill REAL NOT NULL DEFAULT 0,
                minigame_remaining INTEGER NOT NULL DEFAULT 10,
                minigame_refill REAL NOT NULL DEFAULT 0,
                checkin_streak INTEGER NOT NULL DEFAULT 0,
                last_checkin_date TEXT NOT NULL DEFAULT ''
            )
            """
        )
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        migrations = {
            "referred_by": "INTEGER",
            "referral_count": "INTEGER NOT NULL DEFAULT 0",
            "referral_coins": "INTEGER NOT NULL DEFAULT 0",
            "ad_interstitial_remaining": "INTEGER NOT NULL DEFAULT 20",
            "ad_interstitial_refill": "REAL NOT NULL DEFAULT 0",
            "ad_popup_remaining": "INTEGER NOT NULL DEFAULT 20",
            "ad_popup_refill": "REAL NOT NULL DEFAULT 0",
            "minigame_remaining": "INTEGER NOT NULL DEFAULT 10",
            "minigame_refill": "REAL NOT NULL DEFAULT 0",
            "checkin_streak": "INTEGER NOT NULL DEFAULT 0",
            "last_checkin_date": "TEXT NOT NULL DEFAULT ''",
        }
        for col, coltype in migrations.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,        -- 'task' (اجتماعي) أو 'achievement' (إنجاز تدريجي)
                task_type TEXT NOT NULL,       -- telegram/youtube/instagram/twitter/other/taps/ads/level/referrals
                title_ar TEXT NOT NULL,
                title_en TEXT NOT NULL,
                reward INTEGER NOT NULL,
                target INTEGER NOT NULL DEFAULT 0,
                url TEXT NOT NULL DEFAULT '',
                channel_username TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        # حماية: لو جدول tasks كان موجود قبل كده بمخطط قديم (من نسخة سابقة)
        # وناقصه أعمدة أساسية، امسحه واعمله من جديد. آمن تماماً لأن الجدول ده
        # بيحتوي على تعريفات المهام بس (تقدر تتضاف تاني من الأدمن)، مش بيانات اللاعبين.
        tasks_cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        required_cols = {"category", "task_type", "title_ar", "title_en", "reward"}
        if tasks_cols and not required_cols.issubset(tasks_cols):
            conn.execute("DROP TABLE IF EXISTS tasks")
            conn.execute("DROP TABLE IF EXISTS user_task_claims")
            conn.execute(
                """
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    title_ar TEXT NOT NULL,
                    title_en TEXT NOT NULL,
                    reward INTEGER NOT NULL,
                    target INTEGER NOT NULL DEFAULT 0,
                    url TEXT NOT NULL DEFAULT '',
                    channel_username TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                )
                """
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_task_claims (
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                claimed_at REAL NOT NULL,
                PRIMARY KEY (user_id, task_id)
            )
            """
        )
        conn.commit()

        _seed_default_tasks(conn)


def _seed_default_tasks(conn):
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if count > 0:
        return
    now = time.time()
    telegram_channel = os.environ.get("TELEGRAM_CHANNEL", "")
    defaults = [
        # (category, task_type, title_ar, title_en, reward, target, url, channel_username, sort_order)
        ("task", "telegram", "اشترك في قناة CanCel على تيليجرام", "Subscribe to CanCel Telegram channel",
         50, 0, f"https://t.me/{telegram_channel}" if telegram_channel else "", telegram_channel, 1),
        ("task", "youtube", "تابعنا على يوتيوب", "Follow us on YouTube",
         30, 0, "https://youtube.com/", "", 2),
        ("task", "instagram", "تابعنا على إنستجرام", "Follow us on Instagram",
         30, 0, "https://instagram.com/", "", 3),
        ("task", "twitter", "تابعنا على تويتر / X", "Follow us on Twitter / X",
         30, 0, "https://x.com/", "", 4),
        ("achievement", "taps", "اضغط على العملة 100 مرة", "Tap the coin 100 times", 50, 100, "", "", 1),
        ("achievement", "taps", "اضغط على العملة 1,000 مرة", "Tap the coin 1,000 times", 250, 1000, "", "", 2),
        ("achievement", "taps", "اضغط على العملة 10,000 مرة", "Tap the coin 10,000 times", 1500, 10000, "", "", 3),
        ("achievement", "ads", "شاهد 20 إعلان", "Watch 20 ads", 150, 20, "", "", 4),
        ("achievement", "ads", "شاهد 100 إعلان", "Watch 100 ads", 700, 100, "", "", 5),
        ("achievement", "level", "وصّل مستواك لـ 5", "Reach level 5", 200, 5, "", "", 6),
        ("achievement", "level", "وصّل مستواك لـ 10", "Reach level 10", 500, 10, "", "", 7),
        ("achievement", "level", "وصّل مستواك لـ 25", "Reach level 25", 1500, 25, "", "", 8),
        ("achievement", "level", "وصّل مستواك لـ 50", "Reach level 50", 4000, 50, "", "", 9),
        ("achievement", "level", "وصّل مستواك لأقصى مستوى 100", "Reach max level 100", 15000, 100, "", "", 10),
        ("achievement", "referrals", "ادعُ صديق واحد", "Invite 1 friend", 200, 1, "", "", 11),
        ("achievement", "referrals", "ادعُ 5 أصدقاء", "Invite 5 friends", 750, 5, "", "", 12),
        ("achievement", "referrals", "ادعُ 20 صديق", "Invite 20 friends", 3000, 20, "", "", 13),
    ]
    for d in defaults:
        conn.execute(
            "INSERT INTO tasks (category, task_type, title_ar, title_en, reward, target, url, "
            "channel_username, active, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (*d, now),
        )
    conn.commit()


# ---------- منطق المستويات ----------

def level_threshold(level: int) -> int:
    return 100 * level * (level - 1)


def compute_level(coins: int) -> int:
    level = 1
    for L in range(2, MAX_LEVEL + 1):
        if coins >= level_threshold(L):
            level = L
        else:
            break
    return level


def coins_per_tap(level: int) -> int:
    return (level // 10) + 1


def level_progress(coins: int, level: int):
    if level >= MAX_LEVEL:
        return 1.0, None
    prev_th = level_threshold(level)
    next_th = level_threshold(level + 1)
    span = next_th - prev_th
    progress = (coins - prev_th) / span if span else 1.0
    return max(0.0, min(1.0, progress)), next_th


def continuous_level(coins: int, level: int) -> float:
    progress, _ = level_progress(coins, level)
    return min(MAX_LEVEL, level + progress)


def city_state(coins: int, level: int):
    cont = continuous_level(coins, level)
    squares = []
    for i in range(1, 11):
        band_start = (i - 1) * 10
        band_end = i * 10
        if cont >= band_end:
            status, progress = "built", 1.0
        elif cont >= band_start:
            status, progress = "building", (cont - band_start) / 10
        else:
            status, progress = "locked", 0.0
        squares.append({
            "index": i, "status": status, "progress": progress,
            "name": BUILDINGS[i - 1]["name"], "icon": BUILDINGS[i - 1]["icon"],
            "level_range": f"{band_start + 1}-{band_end}",
        })
    return squares


# ---------- الطاقة ----------

def _apply_energy_regen(row, now):
    last_refill = row["last_full_refill"]
    max_e = row["max_energy"]
    energy = row["energy"]
    if now - last_refill >= FULL_REFILL_SECONDS:
        energy = max_e
        last_refill = now
    seconds_to_refill = max(0, int(FULL_REFILL_SECONDS - (now - last_refill)))
    return energy, last_refill, seconds_to_refill


def _apply_ad_regen(remaining, refill_ts, hourly_limit, now):
    if now - refill_ts >= AD_REFILL_SECONDS:
        remaining = hourly_limit
        refill_ts = now
    seconds_to_refill = max(0, int(AD_REFILL_SECONDS - (now - refill_ts)))
    return remaining, refill_ts, seconds_to_refill


# ---------- المستخدمين ----------

def get_or_create_user(user_id: int, first_name: str = "", photo_url: str = ""):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        now = time.time()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, first_name, photo_url, coins, energy, max_energy, "
                "last_full_refill, total_taps, ads_watched, last_ad_time, claimed_tasks, "
                "created_at, last_active, ad_interstitial_remaining, ad_interstitial_refill, "
                "ad_popup_remaining, ad_popup_refill, minigame_remaining, minigame_refill) "
                "VALUES (?, ?, ?, 0, ?, ?, ?, 0, 0, 0, '', ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, first_name, photo_url, MAX_ENERGY, MAX_ENERGY, now, now, now,
                 AD_CONFIG["interstitial"]["hourly_limit"], now,
                 AD_CONFIG["popup"]["hourly_limit"], now,
                 MINIGAME_HOURLY_LIMIT, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        else:
            updates = {}
            if first_name and first_name != row["first_name"]:
                updates["first_name"] = first_name
            if photo_url and photo_url != row["photo_url"]:
                updates["photo_url"] = photo_url
            updates["last_active"] = now
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE users SET {set_clause} WHERE user_id=?",
                         (*updates.values(), user_id))
            conn.commit()

        energy, last_refill, _ = _apply_energy_regen(row, now)
        if energy != row["energy"] or last_refill != row["last_full_refill"]:
            conn.execute("UPDATE users SET energy=?, last_full_refill=? WHERE user_id=?",
                         (energy, last_refill, user_id))
            conn.commit()

        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row)


def tap_batch(user_id: int, count: int):
    count = max(1, min(count, 60))
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        now = time.time()
        energy, last_refill, _ = _apply_energy_regen(row, now)
        coins = row["coins"]
        total_taps = row["total_taps"]

        level_before = compute_level(coins)
        applied = min(count, energy)
        for _ in range(applied):
            lvl = compute_level(coins)
            coins += coins_per_tap(lvl)
        energy -= applied
        total_taps += applied
        level_after = compute_level(coins)

        conn.execute(
            "UPDATE users SET coins=?, energy=?, last_full_refill=?, total_taps=?, "
            "last_active=? WHERE user_id=?",
            (coins, energy, last_refill, total_taps, now, user_id),
        )
        conn.commit()

        return {
            "applied": applied,
            "leveled_up": level_after > level_before,
            "building_completed": (level_before // 10) != (level_after // 10),
        }


# ---------- الإعلانات ----------

def watch_ad(user_id: int, ad_type: str):
    cfg = AD_CONFIG.get(ad_type)
    if cfg is None:
        return {"error": "invalid_ad_type"}

    remaining_col = f"ad_{ad_type}_remaining"
    refill_col = f"ad_{ad_type}_refill"

    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        now = time.time()

        if now - row["last_ad_time"] < AD_MIN_GAP_SECONDS:
            return {"error": "cooldown", "seconds_left": int(AD_MIN_GAP_SECONDS - (now - row["last_ad_time"])) + 1}

        remaining, refill_ts, seconds_to_refill = _apply_ad_regen(
            row[remaining_col], row[refill_col], cfg["hourly_limit"], now
        )
        if remaining <= 0:
            conn.execute(f"UPDATE users SET {refill_col}=? WHERE user_id=?", (refill_ts, user_id))
            conn.commit()
            return {"error": "limit_reached", "seconds_left": seconds_to_refill}

        reward = random.randint(cfg["min_reward"], cfg["max_reward"])
        coins = row["coins"] + reward
        ads_watched = row["ads_watched"] + 1
        remaining -= 1

        conn.execute(
            f"UPDATE users SET coins=?, ads_watched=?, last_ad_time=?, last_active=?, "
            f"{remaining_col}=?, {refill_col}=? WHERE user_id=?",
            (coins, ads_watched, now, now, remaining, refill_ts, user_id),
        )
        conn.commit()
        return {"reward": reward, "ad_type": ad_type, "remaining": remaining}


def get_ad_status(user_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return {}
        now = time.time()
        result = {}
        for ad_type, cfg in AD_CONFIG.items():
            remaining, _, seconds_to_refill = _apply_ad_regen(
                row[f"ad_{ad_type}_remaining"], row[f"ad_{ad_type}_refill"], cfg["hourly_limit"], now
            )
            result[ad_type] = {
                "remaining": remaining, "limit": cfg["hourly_limit"],
                "seconds_to_refill": seconds_to_refill,
                "min_reward": cfg["min_reward"], "max_reward": cfg["max_reward"],
            }
        return result


# ---------- اللعبة البسيطة ----------

def play_minigame(user_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        now = time.time()
        remaining, refill_ts, seconds_to_refill = _apply_ad_regen(
            row["minigame_remaining"], row["minigame_refill"], MINIGAME_HOURLY_LIMIT, now
        )
        if remaining <= 0:
            conn.execute("UPDATE users SET minigame_refill=? WHERE user_id=?", (refill_ts, user_id))
            conn.commit()
            return {"error": "limit_reached", "seconds_left": seconds_to_refill}

        reward = random.randint(MINIGAME_MIN_REWARD, MINIGAME_MAX_REWARD)
        coins = row["coins"] + reward
        remaining -= 1
        conn.execute(
            "UPDATE users SET coins=?, minigame_remaining=?, minigame_refill=?, last_active=? "
            "WHERE user_id=?",
            (coins, remaining, refill_ts, now, user_id),
        )
        conn.commit()
        return {"reward": reward, "remaining": remaining}


def get_minigame_status(user_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return {"remaining": 0, "limit": MINIGAME_HOURLY_LIMIT, "seconds_to_refill": 0}
        now = time.time()
        remaining, _, seconds_to_refill = _apply_ad_regen(
            row["minigame_remaining"], row["minigame_refill"], MINIGAME_HOURLY_LIMIT, now
        )
        return {"remaining": remaining, "limit": MINIGAME_HOURLY_LIMIT, "seconds_to_refill": seconds_to_refill,
                "min_reward": MINIGAME_MIN_REWARD, "max_reward": MINIGAME_MAX_REWARD}


# ---------- تسجيل الدخول اليومي ----------

def _today_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _yesterday_str():
    return (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def get_checkin_status(user_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return {"claimed_today": False, "streak": 0, "next_reward": DAILY_REWARDS[0]}
        today = _today_str()
        claimed_today = row["last_checkin_date"] == today
        streak = row["checkin_streak"]
        next_index = streak % 7 if claimed_today else streak % 7
        return {
            "claimed_today": claimed_today,
            "streak": streak,
            "next_reward": DAILY_REWARDS[next_index],
        }


def claim_checkin(user_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return {"error": "user_not_found"}
        today = _today_str()
        if row["last_checkin_date"] == today:
            return {"error": "already_claimed"}

        streak = row["checkin_streak"] + 1 if row["last_checkin_date"] == _yesterday_str() else 1
        reward = DAILY_REWARDS[(streak - 1) % 7]
        coins = row["coins"] + reward
        conn.execute(
            "UPDATE users SET coins=?, checkin_streak=?, last_checkin_date=?, last_active=? "
            "WHERE user_id=?",
            (coins, streak, today, time.time(), user_id),
        )
        conn.commit()
        return {"reward": reward, "streak": streak}


# ---------- الدعوات ----------

def user_exists(user_id: int) -> bool:
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row is not None


def apply_referral(user_id: int, referrer_id: int) -> bool:
    with _lock, _get_conn() as conn:
        referrer = conn.execute("SELECT user_id FROM users WHERE user_id=?", (referrer_id,)).fetchone()
        if referrer is None:
            return False
        conn.execute(
            "UPDATE users SET coins=coins+?, referred_by=? WHERE user_id=?",
            (REFERRAL_SIGNUP_BONUS, referrer_id, user_id),
        )
        conn.execute(
            "UPDATE users SET coins=coins+?, referral_count=referral_count+1, "
            "referral_coins=referral_coins+? WHERE user_id=?",
            (REFERRAL_REWARD, REFERRAL_REWARD, referrer_id),
        )
        conn.commit()
        return True


def get_referral_info(user_id: int, limit: int = 50):
    with _lock, _get_conn() as conn:
        row = conn.execute(
            "SELECT referral_count, referral_coins FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            return {"referral_count": 0, "referral_coins": 0, "friends": []}
        friends = conn.execute(
            "SELECT first_name, created_at FROM users WHERE referred_by=? "
            "ORDER BY created_at DESC LIMIT ?", (user_id, limit)
        ).fetchall()
        return {
            "referral_count": row["referral_count"],
            "referral_coins": row["referral_coins"],
            "friends": [{"first_name": f["first_name"] or "صديق", "joined_at": f["created_at"]} for f in friends],
        }


# ---------- المهام والإنجازات (Tasks / Achievements) ----------

def _task_progress_value(task_type: str, user_row) -> int:
    return {
        "taps": user_row["total_taps"],
        "ads": user_row["ads_watched"],
        "level": compute_level(user_row["coins"]),
        "referrals": user_row["referral_count"],
    }.get(task_type, 0)


def list_tasks(user_id: int, category: str, lang: str = "ar"):
    with _lock, _get_conn() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if user_row is None:
            return []
        task_rows = conn.execute(
            "SELECT * FROM tasks WHERE category=? AND active=1 ORDER BY sort_order", (category,)
        ).fetchall()
        claimed_ids = {
            r["task_id"] for r in conn.execute(
                "SELECT task_id FROM user_task_claims WHERE user_id=?", (user_id,)
            ).fetchall()
        }

        result = []
        for t in task_rows:
            claimed = t["id"] in claimed_ids
            if category == "achievement":
                progress_value = _task_progress_value(t["task_type"], user_row)
                available = progress_value >= t["target"] and not claimed
                item = {
                    "id": t["id"], "title": t["title_ar"] if lang == "ar" else t["title_en"],
                    "reward": t["reward"], "target": t["target"], "progress": min(progress_value, t["target"]),
                    "status": "claimed" if claimed else ("available" if available else "locked"),
                }
            else:
                item = {
                    "id": t["id"], "title": t["title_ar"] if lang == "ar" else t["title_en"],
                    "reward": t["reward"], "url": t["url"], "task_type": t["task_type"],
                    "status": "claimed" if claimed else "available",
                }
            result.append(item)
        return result


def claim_task(user_id: int, task_id: int, telegram_verified: bool = False):
    with _lock, _get_conn() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if user_row is None:
            return {"error": "user_not_found"}
        task = conn.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)).fetchone()
        if task is None:
            return {"error": "unknown_task"}
        already = conn.execute(
            "SELECT 1 FROM user_task_claims WHERE user_id=? AND task_id=?", (user_id, task_id)
        ).fetchone()
        if already:
            return {"error": "already_claimed"}

        if task["category"] == "achievement":
            progress_value = _task_progress_value(task["task_type"], user_row)
            if progress_value < task["target"]:
                return {"error": "not_eligible"}
        elif task["task_type"] == "telegram":
            if not telegram_verified:
                return {"error": "not_subscribed"}
        # لباقي أنواع المهام الاجتماعية (يوتيوب/إنستجرام/تويتر) بنعتمد على نظام الثقة
        # لعدم توفر API عام للتحقق التلقائي من المتابعة

        conn.execute(
            "INSERT INTO user_task_claims (user_id, task_id, claimed_at) VALUES (?, ?, ?)",
            (user_id, task_id, time.time()),
        )
        coins = user_row["coins"] + task["reward"]
        conn.execute("UPDATE users SET coins=?, last_active=? WHERE user_id=?",
                     (coins, time.time(), user_id))
        conn.commit()
        return {"reward": task["reward"]}


def admin_list_tasks():
    with _lock, _get_conn() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY category, sort_order").fetchall()
        return [dict(r) for r in rows]


def admin_add_task(data: dict):
    with _lock, _get_conn() as conn:
        conn.execute(
            "INSERT INTO tasks (category, task_type, title_ar, title_en, reward, target, url, "
            "channel_username, active, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (data["category"], data["task_type"], data["title_ar"], data["title_en"],
             data["reward"], data.get("target", 0), data.get("url", ""),
             data.get("channel_username", ""), 1, data.get("sort_order", 0), time.time()),
        )
        conn.commit()


def admin_update_task(task_id: int, data: dict):
    with _lock, _get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET title_ar=?, title_en=?, reward=?, target=?, url=?, "
            "channel_username=?, sort_order=? WHERE id=?",
            (data["title_ar"], data["title_en"], data["reward"], data.get("target", 0),
             data.get("url", ""), data.get("channel_username", ""), data.get("sort_order", 0), task_id),
        )
        conn.commit()


def admin_toggle_task(task_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT active FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return
        conn.execute("UPDATE tasks SET active=? WHERE id=?", (0 if row["active"] else 1, task_id))
        conn.commit()


def admin_delete_task(task_id: int):
    with _lock, _get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.execute("DELETE FROM user_task_claims WHERE task_id=?", (task_id,))
        conn.commit()


# ---------- الإيردروب ----------

def get_airdrop_status(user_id: int, telegram_subscribed: bool):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        conditions = [
            {"key": "coins", "met": row["coins"] >= AIRDROP_COIN_REQUIREMENT,
             "current": row["coins"], "target": AIRDROP_COIN_REQUIREMENT},
            {"key": "referrals", "met": row["referral_count"] >= AIRDROP_REFERRAL_REQUIREMENT,
             "current": row["referral_count"], "target": AIRDROP_REFERRAL_REQUIREMENT},
            {"key": "telegram", "met": telegram_subscribed, "current": int(telegram_subscribed), "target": 1},
            {"key": "engagement", "met": row["total_taps"] >= AIRDROP_ENGAGEMENT_TAPS_REQUIREMENT,
             "current": row["total_taps"], "target": AIRDROP_ENGAGEMENT_TAPS_REQUIREMENT},
        ]
        return {
            "date": AIRDROP_DATE, "prize_egp": AIRDROP_PRIZE_EGP,
            "conditions": conditions, "eligible": all(c["met"] for c in conditions),
        }


# ---------- الليدر بورد ----------

def get_leaderboard(limit=20):
    with _lock, _get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, first_name, photo_url, coins FROM users ORDER BY coins DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"rank": i, "user_id": r["user_id"], "first_name": r["first_name"] or "لاعب",
             "photo_url": r["photo_url"], "coins": r["coins"], "level": compute_level(r["coins"])}
            for i, r in enumerate(rows, start=1)
        ]


def get_user_rank(user_id: int):
    with _lock, _get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users ORDER BY coins DESC").fetchall()
        for i, r in enumerate(rows, start=1):
            if r["user_id"] == user_id:
                return i
        return None


# ---------- أدمن ----------

def get_all_users():
    with _lock, _get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY coins DESC").fetchall()
        return [dict(r) for r in rows]


def get_stats():
    with _lock, _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as total_users, COALESCE(SUM(coins),0) as total_coins, "
            "COALESCE(SUM(total_taps),0) as total_taps, "
            "COALESCE(SUM(ads_watched),0) as total_ads, "
            "COALESCE(SUM(referral_count),0) as total_referrals FROM users"
        ).fetchone()
        return dict(row)


def admin_set_user_coins(user_id: int, new_coins: int):
    with _lock, _get_conn() as conn:
        conn.execute("UPDATE users SET coins=? WHERE user_id=?", (max(0, new_coins), user_id))
        conn.commit()
