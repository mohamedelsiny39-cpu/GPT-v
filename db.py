import sqlite3
import time
import threading

DB_PATH = "cancel_game.db"
_lock = threading.Lock()

MAX_ENERGY = 100
FULL_REFILL_SECONDS = 3600  # الطاقة بترجع كاملة كل ساعة
AD_REWARDS = {
    "interstitial": 15,  # فيديو كامل الشاشة (أعلى قيمة)
    "popup": 10,          # عرض خارجي (أسرع، قيمة أقل)
}
AD_COOLDOWN_SECONDS = 10
MAX_LEVEL = 100
REFERRAL_REWARD = 500          # بيدّيها اللي بيدعي، لكل صديق جديد
REFERRAL_SIGNUP_BONUS = 100    # هدية ترحيب لللي جه عن طريق دعوة

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

TASKS = [
    {"id": "first_login", "title": "ابدأ اللعب لأول مرة", "reward": 20,
     "check": lambda s: True},
    {"id": "taps_100", "title": "اضغط على العملة 100 مرة", "reward": 50,
     "check": lambda s: s["total_taps"] >= 100},
    {"id": "taps_1000", "title": "اضغط على العملة 1000 مرة", "reward": 250,
     "check": lambda s: s["total_taps"] >= 1000},
    {"id": "taps_10000", "title": "اضغط على العملة 10,000 مرة", "reward": 1500,
     "check": lambda s: s["total_taps"] >= 10000},
    {"id": "ads_5", "title": "شاهد 5 إعلانات", "reward": 100,
     "check": lambda s: s["ads_watched"] >= 5},
    {"id": "ads_20", "title": "شاهد 20 إعلان", "reward": 500,
     "check": lambda s: s["ads_watched"] >= 20},
    {"id": "ads_50", "title": "شاهد 50 إعلان", "reward": 1500,
     "check": lambda s: s["ads_watched"] >= 50},
    {"id": "level_5", "title": "وصّل مستواك لـ 5", "reward": 200,
     "check": lambda s: s["level"] >= 5},
    {"id": "level_10", "title": "وصّل مستواك لـ 10", "reward": 500,
     "check": lambda s: s["level"] >= 10},
    {"id": "level_25", "title": "وصّل مستواك لـ 25", "reward": 1500,
     "check": lambda s: s["level"] >= 25},
    {"id": "level_50", "title": "وصّل مستواك لـ 50", "reward": 4000,
     "check": lambda s: s["level"] >= 50},
    {"id": "level_100", "title": "وصّل مستواك لأقصى مستوى 100", "reward": 15000,
     "check": lambda s: s["level"] >= 100},
    {"id": "invite_1", "title": "ادعُ صديق واحد", "reward": 200,
     "check": lambda s: s["referral_count"] >= 1},
    {"id": "invite_5", "title": "ادعُ 5 أصدقاء", "reward": 750,
     "check": lambda s: s["referral_count"] >= 5},
    {"id": "invite_20", "title": "ادعُ 20 صديق", "reward": 3000,
     "check": lambda s: s["referral_count"] >= 20},
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
                referral_coins INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # migration آمنة لو الجدول كان موجود قبل إضافة أعمدة الدعوات
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        migrations = {
            "referred_by": "INTEGER",
            "referral_count": "INTEGER NOT NULL DEFAULT 0",
            "referral_coins": "INTEGER NOT NULL DEFAULT 0",
        }
        for col, coltype in migrations.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
        conn.commit()


# ---------- منطق المستويات ----------

def level_threshold(level: int) -> int:
    """إجمالي العملات المطلوبة عشان توصل للمستوى ده"""
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
    """يرجع (نسبة التقدم للمستوى الجاي 0-1, عدد العملات المطلوب)"""
    if level >= MAX_LEVEL:
        return 1.0, None
    prev_th = level_threshold(level)
    next_th = level_threshold(level + 1)
    span = next_th - prev_th
    progress = (coins - prev_th) / span if span else 1.0
    return max(0.0, min(1.0, progress)), next_th


def continuous_level(coins: int, level: int) -> float:
    """مستوى بالكسور عشان المباني تكبر بسلاسة"""
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
            "index": i,
            "status": status,
            "progress": progress,
            "name": BUILDINGS[i - 1]["name"],
            "icon": BUILDINGS[i - 1]["icon"],
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


# ---------- المستخدمين ----------

def get_or_create_user(user_id: int, first_name: str = "", photo_url: str = ""):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        now = time.time()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, first_name, photo_url, coins, energy, "
                "max_energy, last_full_refill, total_taps, ads_watched, last_ad_time, "
                "claimed_tasks, created_at, last_active) "
                "VALUES (?, ?, ?, 0, ?, ?, ?, 0, 0, 0, '', ?, ?)",
                (user_id, first_name, photo_url, MAX_ENERGY, MAX_ENERGY, now, now, now),
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
            conn.execute(
                "UPDATE users SET energy=?, last_full_refill=? WHERE user_id=?",
                (energy, last_refill, user_id),
            )
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
        }


def watch_ad(user_id: int, ad_type: str = "interstitial"):
    reward = AD_REWARDS.get(ad_type)
    if reward is None:
        return {"error": "invalid_ad_type"}

    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return None
        now = time.time()
        remaining = AD_COOLDOWN_SECONDS - (now - row["last_ad_time"])
        if remaining > 0:
            return {"error": "cooldown", "seconds_left": int(remaining) + 1}

        coins = row["coins"] + reward
        ads_watched = row["ads_watched"] + 1
        conn.execute(
            "UPDATE users SET coins=?, ads_watched=?, last_ad_time=?, last_active=? "
            "WHERE user_id=?",
            (coins, ads_watched, now, now, user_id),
        )
        conn.commit()
        return {"reward": reward, "ad_type": ad_type}



def get_tasks_status(user_id: int):
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return []
        claimed = set(filter(None, row["claimed_tasks"].split(",")))
        level = compute_level(row["coins"])
        state = {
            "total_taps": row["total_taps"],
            "ads_watched": row["ads_watched"],
            "level": level,
            "referral_count": row["referral_count"],
        }
        result = []
        for t in TASKS:
            if t["id"] in claimed:
                status = "claimed"
            elif t["check"](state):
                status = "available"
            else:
                status = "locked"
            result.append({
                "id": t["id"], "title": t["title"], "reward": t["reward"], "status": status,
            })
        return result


def claim_task(user_id: int, task_id: str):
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if task is None:
        return {"error": "unknown_task"}

    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            return {"error": "user_not_found"}
        claimed = set(filter(None, row["claimed_tasks"].split(",")))
        if task_id in claimed:
            return {"error": "already_claimed"}

        level = compute_level(row["coins"])
        state = {
            "total_taps": row["total_taps"],
            "ads_watched": row["ads_watched"],
            "level": level,
            "referral_count": row["referral_count"],
        }
        if not task["check"](state):
            return {"error": "not_eligible"}

        claimed.add(task_id)
        coins = row["coins"] + task["reward"]
        conn.execute(
            "UPDATE users SET coins=?, claimed_tasks=?, last_active=? WHERE user_id=?",
            (coins, ",".join(claimed), time.time(), user_id),
        )
        conn.commit()
        return {"reward": task["reward"]}


def get_leaderboard(limit=20):
    with _lock, _get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, first_name, photo_url, coins FROM users "
            "ORDER BY coins DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for i, r in enumerate(rows, start=1):
            result.append({
                "rank": i,
                "user_id": r["user_id"],
                "first_name": r["first_name"] or "لاعب",
                "photo_url": r["photo_url"],
                "coins": r["coins"],
                "level": compute_level(r["coins"]),
            })
        return result


def get_user_rank(user_id: int):
    with _lock, _get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users ORDER BY coins DESC"
        ).fetchall()
        for i, r in enumerate(rows, start=1):
            if r["user_id"] == user_id:
                return i
        return None


# ---------- الدعوات ----------

def user_exists(user_id: int) -> bool:
    with _lock, _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row is not None


def apply_referral(user_id: int, referrer_id: int) -> bool:
    """يتنادى مرة واحدة بس، لحظة إنشاء المستخدم الجديد لو جه بدعوة"""
    with _lock, _get_conn() as conn:
        referrer = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?", (referrer_id,)
        ).fetchone()
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
            "friends": [
                {"first_name": f["first_name"] or "صديق", "joined_at": f["created_at"]}
                for f in friends
            ],
        }


# ---------- أدمن ----------

def get_all_users():
    with _lock, _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY coins DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats():
    with _lock, _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as total_users, COALESCE(SUM(coins),0) as total_coins, "
            "COALESCE(SUM(total_taps),0) as total_taps, "
            "COALESCE(SUM(ads_watched),0) as total_ads, "
            "COALESCE(SUM(referral_count),0) as total_referrals "
            "FROM users"
        ).fetchone()
        return dict(row)
