import os
import sqlite3
import time
import threading
import json
import random


# =========================================================
# DATABASE
# =========================================================

# محليًا: قاعدة البيانات في مجلد المشروع
# Railway: ضع DATA_DIR=/app/data
DATA_DIR = os.environ.get("DATA_DIR", ".")

# إنشاء المجلد تلقائيًا لو مش موجود
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "cancel_game.db")

_lock = threading.RLock()


def _get_conn():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# GAME SETTINGS
# =========================================================

MAX_ENERGY = 100
FULL_REFILL_SECONDS = 3600

MAX_LEVEL = 100

REFERRAL_REWARD = 500
REFERRAL_SIGNUP_BONUS = 100

# الإعدادات القديمة للحفاظ على توافق المشروع الحالي
AD_REWARDS = {
    "interstitial": 15,
    "popup": 10,
}

AD_COOLDOWN_SECONDS = 10


# =========================================================
# BUILDINGS
# =========================================================

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


# =========================================================
# DEFAULT ACHIEVEMENTS
# =========================================================

DEFAULT_ACHIEVEMENTS = [
    {
        "achievement_id": "taps_100",
        "title": "100 ضغطة",
        "description": "اضغط على العملة 100 مرة",
        "target_type": "taps",
        "target_value": 100,
        "reward": 50,
    },
    {
        "achievement_id": "taps_1000",
        "title": "1000 ضغطة",
        "description": "اضغط على العملة 1000 مرة",
        "target_type": "taps",
        "target_value": 1000,
        "reward": 250,
    },
    {
        "achievement_id": "taps_10000",
        "title": "10000 ضغطة",
        "description": "اضغط على العملة 10000 مرة",
        "target_type": "taps",
        "target_value": 10000,
        "reward": 1500,
    },
    {
        "achievement_id": "ads_10",
        "title": "مشاهد الإعلانات",
        "description": "شاهد 10 إعلانات",
        "target_type": "ads",
        "target_value": 10,
        "reward": 150,
    },
    {
        "achievement_id": "ads_100",
        "title": "خبير الإعلانات",
        "description": "شاهد 100 إعلان",
        "target_type": "ads",
        "target_value": 100,
        "reward": 1000,
    },
    {
        "achievement_id": "invite_1",
        "title": "أول دعوة",
        "description": "ادعُ صديق واحد",
        "target_type": "referrals",
        "target_value": 1,
        "reward": 200,
    },
    {
        "achievement_id": "invite_10",
        "title": "صانع المجتمع",
        "description": "ادعُ 10 أصدقاء",
        "target_type": "referrals",
        "target_value": 10,
        "reward": 2000,
    },
]


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def _add_column_if_missing(conn, table, column, definition):
    existing_cols = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})")
    }

    if column not in existing_cols:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def init_db():

    with _lock, _get_conn() as conn:

        # -------------------------------------------------
        # USERS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (

                user_id INTEGER PRIMARY KEY,

                first_name TEXT DEFAULT '',
                photo_url TEXT DEFAULT '',

                language TEXT DEFAULT '',

                coins INTEGER NOT NULL DEFAULT 0,

                energy INTEGER NOT NULL DEFAULT 100,
                max_energy INTEGER NOT NULL DEFAULT 100,

                last_full_refill REAL NOT NULL DEFAULT 0,

                total_taps INTEGER NOT NULL DEFAULT 0,

                ads_watched INTEGER NOT NULL DEFAULT 0,
                last_ad_time REAL NOT NULL DEFAULT 0,

                claimed_tasks TEXT NOT NULL DEFAULT '',

                created_at REAL NOT NULL DEFAULT 0,
                last_active REAL NOT NULL DEFAULT 0,

                referred_by INTEGER,

                referral_count INTEGER NOT NULL DEFAULT 0,
                referral_coins INTEGER NOT NULL DEFAULT 0,

                last_daily_claim REAL NOT NULL DEFAULT 0,
                daily_streak INTEGER NOT NULL DEFAULT 0,

                total_game_plays INTEGER NOT NULL DEFAULT 0,
                game_coins INTEGER NOT NULL DEFAULT 0

            )
            """
        )

        # -------------------------------------------------
        # MIGRATIONS
        # -------------------------------------------------

        migrations = {

            "referred_by":
                "INTEGER",

            "referral_count":
                "INTEGER NOT NULL DEFAULT 0",

            "referral_coins":
                "INTEGER NOT NULL DEFAULT 0",

            "language":
                "TEXT DEFAULT ''",

            "last_daily_claim":
                "REAL NOT NULL DEFAULT 0",

            "daily_streak":
                "INTEGER NOT NULL DEFAULT 0",

            "total_game_plays":
                "INTEGER NOT NULL DEFAULT 0",

            "game_coins":
                "INTEGER NOT NULL DEFAULT 0",
        }

        for column, definition in migrations.items():

            _add_column_if_missing(
                conn,
                "users",
                column,
                definition,
            )

        # -------------------------------------------------
        # TASKS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                task_key TEXT UNIQUE NOT NULL,

                title_ar TEXT NOT NULL,
                title_en TEXT NOT NULL,

                description_ar TEXT DEFAULT '',
                description_en TEXT DEFAULT '',

                task_type TEXT NOT NULL DEFAULT 'social',

                target_url TEXT DEFAULT '',

                platform TEXT DEFAULT '',

                reward INTEGER NOT NULL DEFAULT 0,

                active INTEGER NOT NULL DEFAULT 1,

                created_at REAL NOT NULL

            )
            """
        )

        # -------------------------------------------------
        # USER TASKS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tasks (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                task_key TEXT NOT NULL,

                completed INTEGER NOT NULL DEFAULT 0,

                claimed INTEGER NOT NULL DEFAULT 0,

                completed_at REAL,

                claimed_at REAL,

                UNIQUE(user_id, task_key)

            )
            """
        )

        # -------------------------------------------------
        # ACHIEVEMENTS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS achievements (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                achievement_key TEXT UNIQUE NOT NULL,

                title_ar TEXT NOT NULL,
                title_en TEXT NOT NULL,

                description_ar TEXT DEFAULT '',
                description_en TEXT DEFAULT '',

                target_type TEXT NOT NULL,

                target_value INTEGER NOT NULL,

                reward INTEGER NOT NULL DEFAULT 0,

                active INTEGER NOT NULL DEFAULT 1,

                created_at REAL NOT NULL

            )
            """
        )

        # -------------------------------------------------
        # USER ACHIEVEMENTS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_achievements (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                achievement_key TEXT NOT NULL,

                claimed INTEGER NOT NULL DEFAULT 0,

                claimed_at REAL,

                UNIQUE(user_id, achievement_key)

            )
            """
        )

        # -------------------------------------------------
        # AD SETTINGS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_settings (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                ad_type TEXT UNIQUE NOT NULL,

                title_ar TEXT NOT NULL,
                title_en TEXT NOT NULL,

                min_reward INTEGER NOT NULL DEFAULT 5,

                max_reward INTEGER NOT NULL DEFAULT 20,

                cooldown_seconds INTEGER NOT NULL DEFAULT 60,

                max_per_hour INTEGER NOT NULL DEFAULT 20,

                active INTEGER NOT NULL DEFAULT 1

            )
            """
        )

        # -------------------------------------------------
        # USER ADS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_ads (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                ad_type TEXT NOT NULL,

                watched_at REAL NOT NULL,

                reward INTEGER NOT NULL DEFAULT 0

            )
            """
        )

        # -------------------------------------------------
        # DAILY REWARDS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_rewards (

                day INTEGER PRIMARY KEY,

                reward INTEGER NOT NULL

            )
            """
        )

        # -------------------------------------------------
        # AIRDROP SETTINGS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS airdrop_settings (

                id INTEGER PRIMARY KEY CHECK(id = 1),

                enabled INTEGER NOT NULL DEFAULT 1,

                title TEXT NOT NULL,

                prize_amount TEXT NOT NULL,

                airdrop_date TEXT NOT NULL,

                required_coins INTEGER NOT NULL DEFAULT 20000,

                required_referrals INTEGER NOT NULL DEFAULT 10,

                require_telegram INTEGER NOT NULL DEFAULT 1,

                require_activity INTEGER NOT NULL DEFAULT 1

            )
            """
        )

        # -------------------------------------------------
        # AIRDROP USERS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS airdrop_users (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER UNIQUE NOT NULL,

                telegram_verified INTEGER NOT NULL DEFAULT 0,

                activity_verified INTEGER NOT NULL DEFAULT 0,

                joined INTEGER NOT NULL DEFAULT 0,

                joined_at REAL

            )
            """
        )

        # -------------------------------------------------
        # BUILDINGS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buildings (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                building_key TEXT UNIQUE NOT NULL,

                name_ar TEXT NOT NULL,

                name_en TEXT NOT NULL,

                icon TEXT NOT NULL,

                required_level INTEGER NOT NULL,

                active INTEGER NOT NULL DEFAULT 1

            )
            """
        )

        # -------------------------------------------------
        # GAME SETTINGS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_settings (

                setting_key TEXT PRIMARY KEY,

                setting_value TEXT NOT NULL

            )
            """
        )

        # -------------------------------------------------
        # GAME PLAYS
        # -------------------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_plays (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id INTEGER NOT NULL,

                played_at REAL NOT NULL,

                reward INTEGER NOT NULL DEFAULT 0

            )
            """
        )

        # -------------------------------------------------
        # DEFAULT ADS
        # -------------------------------------------------

        default_ads = [

            (
                "interstitial",
                "إعلان فيديو",
                "Video Ad",
                5,
                20,
                60,
                20,
            ),

            (
                "rewarded",
                "إعلان مكافأة",
                "Rewarded Ad",
                5,
                20,
                60,
                20,
            ),

            (
                "popup",
                "إعلان سريع",
                "Quick Ad",
                5,
                15,
                60,
                20,
            ),
        ]

        for ad in default_ads:

            conn.execute(
                """
                INSERT OR IGNORE INTO ad_settings
                (
                    ad_type,
                    title_ar,
                    title_en,
                    min_reward,
                    max_reward,
                    cooldown_seconds,
                    max_per_hour
                )

                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ad,
            )

        # -------------------------------------------------
        # DEFAULT DAILY REWARDS
        # -------------------------------------------------

        daily_rewards = [

            (1, 10),
            (2, 15),
            (3, 20),
            (4, 25),
            (5, 30),
            (6, 40),
            (7, 75),
        ]

        for day, reward in daily_rewards:

            conn.execute(
                """
                INSERT OR IGNORE INTO daily_rewards
                (day, reward)

                VALUES (?, ?)
                """,
                (day, reward),
            )

        # -------------------------------------------------
        # DEFAULT AIRDROP
        # -------------------------------------------------

        conn.execute(
            """
            INSERT OR IGNORE INTO airdrop_settings
            (
                id,
                enabled,
                title,
                prize_amount,
                airdrop_date,
                required_coins,
                required_referrals,
                require_telegram,
                require_activity
            )

            VALUES
            (
                1,
                1,
                'CanCel First Airdrop',
                '20000 EGP',
                '2026-09-25',
                20000,
                10,
                1,
                1
            )
            """
        )

        # -------------------------------------------------
        # DEFAULT BUILDINGS
        # -------------------------------------------------

        for index, building in enumerate(BUILDINGS):

            conn.execute(
                """
                INSERT OR IGNORE INTO buildings
                (
                    building_key,
                    name_ar,
                    name_en,
                    icon,
                    required_level
                )

                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"building_{index + 1}",
                    building["name"],
                    building["name"],
                    building["icon"],
                    index * 10 + 1,
                ),
            )

        # -------------------------------------------------
        # DEFAULT ACHIEVEMENTS
        # -------------------------------------------------

        for achievement in DEFAULT_ACHIEVEMENTS:

            conn.execute(
                """
                INSERT OR IGNORE INTO achievements
                (
                    achievement_key,
                    title_ar,
                    title_en,
                    description_ar,
                    description_en,
                    target_type,
                    target_value,
                    reward
                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    achievement["achievement_id"],
                    achievement["title"],
                    achievement["title"],
                    achievement["description"],
                    achievement["description"],
                    achievement["target_type"],
                    achievement["target_value"],
                    achievement["reward"],
                ),
            )

        conn.commit()


# =========================================================
# LEVEL SYSTEM
# =========================================================

def level_threshold(level: int) -> int:

    return 100 * level * (level - 1)


def compute_level(coins: int) -> int:

    level = 1

    for current_level in range(2, MAX_LEVEL + 1):

        if coins >= level_threshold(current_level):

            level = current_level

        else:

            break

    return level


def coins_per_tap(level: int) -> int:

    return (level // 10) + 1


def level_progress(coins: int, level: int):

    if level >= MAX_LEVEL:

        return 1.0, None

    previous_threshold = level_threshold(level)

    next_threshold = level_threshold(level + 1)

    span = next_threshold - previous_threshold

    progress = (
        (coins - previous_threshold) / span
        if span
        else 1.0
    )

    return max(0.0, min(1.0, progress)), next_threshold


def continuous_level(coins: int, level: int):

    progress, _ = level_progress(coins, level)

    return min(
        MAX_LEVEL,
        level + progress,
    )


def city_state(coins: int, level: int):

    continuous = continuous_level(coins, level)

    squares = []

    for index in range(1, 11):

        band_start = (index - 1) * 10

        band_end = index * 10

        if continuous >= band_end:

            status = "built"

            progress = 1.0

        elif continuous >= band_start:

            status = "building"

            progress = (
                continuous - band_start
            ) / 10

        else:

            status = "locked"

            progress = 0.0

        squares.append(
            {
                "index": index,

                "status": status,

                "progress": progress,

                "name": BUILDINGS[index - 1]["name"],

                "icon": BUILDINGS[index - 1]["icon"],

                "level_range":
                    f"{band_start + 1}-{band_end}",
            }
        )

    return squares


# =========================================================
# ENERGY
# =========================================================

def _apply_energy_regen(row, now):

    last_refill = row["last_full_refill"]

    max_energy = row["max_energy"]

    energy = row["energy"]

    if now - last_refill >= FULL_REFILL_SECONDS:

        energy = max_energy

        last_refill = now

    seconds_to_refill = max(
        0,
        int(
            FULL_REFILL_SECONDS
            - (now - last_refill)
        ),
    )

    return (
        energy,
        last_refill,
        seconds_to_refill,
    )


# =========================================================
# USERS
# =========================================================

def get_or_create_user(
    user_id: int,
    first_name: str = "",
    photo_url: str = "",
):

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        now = time.time()

        if row is None:

            conn.execute(
                """
                INSERT INTO users
                (
                    user_id,
                    first_name,
                    photo_url,
                    coins,
                    energy,
                    max_energy,
                    last_full_refill,
                    total_taps,
                    ads_watched,
                    last_ad_time,
                    claimed_tasks,
                    created_at,
                    last_active
                )

                VALUES
                (?, ?, ?, 0, ?, ?, ?, 0, 0, 0, '', ?, ?)
                """,
                (
                    user_id,

                    first_name,

                    photo_url,

                    MAX_ENERGY,

                    MAX_ENERGY,

                    now,

                    now,

                    now,
                ),
            )

            conn.commit()

        else:

            updates = {}

            if (
                first_name
                and first_name != row["first_name"]
            ):

                updates["first_name"] = first_name

            if (
                photo_url
                and photo_url != row["photo_url"]
            ):

                updates["photo_url"] = photo_url

            updates["last_active"] = now

            set_clause = ", ".join(
                f"{key}=?"
                for key in updates
            )

            conn.execute(
                f"""
                UPDATE users
                SET {set_clause}
                WHERE user_id=?
                """,
                (
                    *updates.values(),
                    user_id,
                ),
            )

            conn.commit()

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        energy, last_refill, _ = _apply_energy_regen(
            row,
            now,
        )

        if (
            energy != row["energy"]
            or last_refill != row["last_full_refill"]
        ):

            conn.execute(
                """
                UPDATE users
                SET
                    energy=?,
                    last_full_refill=?
                WHERE user_id=?
                """,
                (
                    energy,
                    last_refill,
                    user_id,
                ),
            )

            conn.commit()

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        return dict(row)


def user_exists(user_id: int) -> bool:

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        return row is not None


def set_user_language(user_id, language):

    if language not in ("ar", "en"):

        return False

    with _lock, _get_conn() as conn:

        conn.execute(
            """
            UPDATE users
            SET language=?
            WHERE user_id=?
            """,
            (
                language,
                user_id,
            ),
        )

        conn.commit()

    return True


# =========================================================
# TAPPING
# =========================================================

def tap_batch(
    user_id: int,
    count: int,
):

    count = max(
        1,
        min(count, 60),
    )

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if row is None:

            return None

        now = time.time()

        energy, last_refill, _ = (
            _apply_energy_regen(
                row,
                now,
            )
        )

        coins = row["coins"]

        total_taps = row["total_taps"]

        level_before = compute_level(coins)

        applied = min(
            count,
            energy,
        )

        for _ in range(applied):

            level = compute_level(coins)

            coins += coins_per_tap(level)

        energy -= applied

        total_taps += applied

        level_after = compute_level(coins)

        conn.execute(
            """
            UPDATE users
            SET
                coins=?,
                energy=?,
                last_full_refill=?,
                total_taps=?,
                last_active=?
            WHERE user_id=?
            """,
            (
                coins,

                energy,

                last_refill,

                total_taps,

                now,

                user_id,
            ),
        )

        conn.commit()

        return {
            "applied": applied,

            "leveled_up":
                level_after > level_before,
        }


# =========================================================
# ADS
# =========================================================

def watch_ad(
    user_id: int,
    ad_type: str = "interstitial",
):

    with _lock, _get_conn() as conn:

        setting = conn.execute(
            """
            SELECT *
            FROM ad_settings
            WHERE
                ad_type=?
                AND active=1
            """,
            (ad_type,),
        ).fetchone()

        # توافق مع النظام القديم
        if setting is None:

            return {
                "error":
                    "invalid_ad_type"
            }

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if row is None:

            return None

        now = time.time()

        # آخر إعلان من نفس النوع
        last_ad = conn.execute(
            """
            SELECT watched_at
            FROM user_ads
            WHERE
                user_id=?
                AND ad_type=?
            ORDER BY watched_at DESC
            LIMIT 1
            """,
            (
                user_id,
                ad_type,
            ),
        ).fetchone()

        if last_ad:

            elapsed = (
                now - last_ad["watched_at"]
            )

            remaining = (
                setting["cooldown_seconds"]
                - elapsed
            )

            if remaining > 0:

                return {
                    "error":
                        "cooldown",

                    "seconds_left":
                        int(remaining) + 1,
                }

        # عدد الإعلانات خلال آخر ساعة
        hour_ago = now - 3600

        hour_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM user_ads
            WHERE
                user_id=?
                AND ad_type=?
                AND watched_at>=?
            """,
            (
                user_id,
                ad_type,
                hour_ago,
            ),
        ).fetchone()[0]

        if hour_count >= setting["max_per_hour"]:

            return {
                "error":
                    "hourly_limit",

                "seconds_left":
                    3600,
            }

        reward = random.randint(
            setting["min_reward"],
            setting["max_reward"],
        )

        conn.execute(
            """
            INSERT INTO user_ads
            (
                user_id,
                ad_type,
                watched_at,
                reward
            )

            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                ad_type,
                now,
                reward,
            ),
        )

        conn.execute(
            """
            UPDATE users
            SET
                coins=coins+?,
                ads_watched=ads_watched+1,
                last_ad_time=?,
                last_active=?
            WHERE user_id=?
            """,
            (
                reward,
                now,
                now,
                user_id,
            ),
        )

        conn.commit()

        return {
            "reward": reward,

            "ad_type": ad_type,
        }


# =========================================================
# OLD TASK COMPATIBILITY
# =========================================================

TASKS = [
    {
        "id": "first_login",

        "title":
            "ابدأ اللعب لأول مرة",

        "reward": 20,

        "check":
            lambda state: True,
    },

    {
        "id": "taps_100",

        "title":
            "اضغط على العملة 100 مرة",

        "reward": 50,

        "check":
            lambda state:
                state["total_taps"] >= 100,
    },

    {
        "id": "taps_1000",

        "title":
            "اضغط على العملة 1000 مرة",

        "reward": 250,

        "check":
            lambda state:
                state["total_taps"] >= 1000,
    },

    {
        "id": "taps_10000",

        "title":
            "اضغط على العملة 10,000 مرة",

        "reward": 1500,

        "check":
            lambda state:
                state["total_taps"] >= 10000,
    },

    {
        "id": "ads_5",

        "title":
            "شاهد 5 إعلانات",

        "reward": 100,

        "check":
            lambda state:
                state["ads_watched"] >= 5,
    },

    {
        "id": "ads_20",

        "title":
            "شاهد 20 إعلان",

        "reward": 500,

        "check":
            lambda state:
                state["ads_watched"] >= 20,
    },

    {
        "id": "invite_1",

        "title":
            "ادعُ صديق واحد",

        "reward": 200,

        "check":
            lambda state:
                state["referral_count"] >= 1,
    },

    {
        "id": "invite_5",

        "title":
            "ادعُ 5 أصدقاء",

        "reward": 750,

        "check":
            lambda state:
                state["referral_count"] >= 5,
    },
]


def get_tasks_status(user_id):

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if row is None:

            return []

        claimed = set(
            filter(
                None,
                row["claimed_tasks"].split(","),
            )
        )

        level = compute_level(
            row["coins"]
        )

        state = {
            "total_taps":
                row["total_taps"],

            "ads_watched":
                row["ads_watched"],

            "level":
                level,

            "referral_count":
                row["referral_count"],
        }

        result = []

        for task in TASKS:

            if task["id"] in claimed:

                status = "claimed"

            elif task["check"](state):

                status = "available"

            else:

                status = "locked"

            result.append(
                {
                    "id":
                        task["id"],

                    "title":
                        task["title"],

                    "reward":
                        task["reward"],

                    "status":
                        status,
                }
            )

        return result


def claim_task(
    user_id,
    task_id,
):

    task = next(
        (
            task
            for task in TASKS
            if task["id"] == task_id
        ),
        None,
    )

    if task is None:

        return {
            "error":
                "unknown_task"
        }

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if row is None:

            return {
                "error":
                    "user_not_found"
            }

        claimed = set(
            filter(
                None,
                row["claimed_tasks"].split(","),
            )
        )

        if task_id in claimed:

            return {
                "error":
                    "already_claimed"
            }

        level = compute_level(
            row["coins"]
        )

        state = {
            "total_taps":
                row["total_taps"],

            "ads_watched":
                row["ads_watched"],

            "level":
                level,

            "referral_count":
                row["referral_count"],
        }

        if not task["check"](state):

            return {
                "error":
                    "not_eligible"
            }

        claimed.add(task_id)

        coins = (
            row["coins"]
            + task["reward"]
        )

        conn.execute(
            """
            UPDATE users
            SET
                coins=?,
                claimed_tasks=?,
                last_active=?
            WHERE user_id=?
            """,
            (
                coins,

                ",".join(claimed),

                time.time(),

                user_id,
            ),
        )

        conn.commit()

        return {
            "reward":
                task["reward"]
        }


# =========================================================
# REFERRALS
# =========================================================

def apply_referral(
    user_id: int,
    referrer_id: int,
) -> bool:

    if user_id == referrer_id:

        return False

    with _lock, _get_conn() as conn:

        user = conn.execute(
            """
            SELECT referred_by
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if user is None:

            return False

        # منع استخدام الدعوة أكثر من مرة
        if user["referred_by"] is not None:

            return False

        referrer = conn.execute(
            """
            SELECT user_id
            FROM users
            WHERE user_id=?
            """,
            (referrer_id,),
        ).fetchone()

        if referrer is None:

            return False

        conn.execute(
            """
            UPDATE users
            SET
                coins=coins+?,
                referred_by=?
            WHERE user_id=?
            """,
            (
                REFERRAL_SIGNUP_BONUS,
                referrer_id,
                user_id,
            ),
        )

        conn.execute(
            """
            UPDATE users
            SET
                coins=coins+?,
                referral_count=referral_count+1,
                referral_coins=referral_coins+?
            WHERE user_id=?
            """,
            (
                REFERRAL_REWARD,
                REFERRAL_REWARD,
                referrer_id,
            ),
        )

        conn.commit()

        return True


def get_referral_info(
    user_id: int,
    limit: int = 50,
):

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT
                referral_count,
                referral_coins
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if row is None:

            return {
                "referral_count": 0,

                "referral_coins": 0,

                "friends": [],
            }

        friends = conn.execute(
            """
            SELECT
                first_name,
                created_at
            FROM users
            WHERE referred_by=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (
                user_id,
                limit,
            ),
        ).fetchall()

        return {
            "referral_count":
                row["referral_count"],

            "referral_coins":
                row["referral_coins"],

            "friends":
                [
                    {
                        "first_name":
                            friend["first_name"]
                            or "صديق",

                        "joined_at":
                            friend["created_at"],
                    }

                    for friend in friends
                ],
        }


# =========================================================
# LEADERBOARD
# =========================================================

def get_leaderboard(limit=20):

    with _lock, _get_conn() as conn:

        rows = conn.execute(
            """
            SELECT
                user_id,
                first_name,
                photo_url,
                coins
            FROM users
            ORDER BY coins DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        result = []

        for index, row in enumerate(
            rows,
            start=1,
        ):

            result.append(
                {
                    "rank":
                        index,

                    "user_id":
                        row["user_id"],

                    "first_name":
                        row["first_name"]
                        or "لاعب",

                    "photo_url":
                        row["photo_url"],

                    "coins":
                        row["coins"],

                    "level":
                        compute_level(
                            row["coins"]
                        ),
                }
            )

        return result


def get_user_rank(user_id):

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT COUNT(*) + 1
            FROM users
            WHERE coins >
            (
                SELECT coins
                FROM users
                WHERE user_id=?
            )
            """,
            (user_id,),
        ).fetchone()

        if row is None:

            return None

        return row[0]


# =========================================================
# ADMIN
# =========================================================

def get_all_users():

    with _lock, _get_conn() as conn:

        rows = conn.execute(
            """
            SELECT *
            FROM users
            ORDER BY coins DESC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def get_stats():

    with _lock, _get_conn() as conn:

        row = conn.execute(
            """
            SELECT

                COUNT(*)
                AS total_users,

                COALESCE(
                    SUM(coins),
                    0
                )
                AS total_coins,

                COALESCE(
                    SUM(total_taps),
                    0
                )
                AS total_taps,

                COALESCE(
                    SUM(ads_watched),
                    0
                )
                AS total_ads,

                COALESCE(
                    SUM(referral_count),
                    0
                )
                AS total_referrals

            FROM users
            """
        ).fetchone()

        return dict(row)


def update_user_by_admin(
    user_id,
    updates,
):

    allowed_fields = {

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
    }

    clean_updates = {}

    integer_fields = {

        "coins",

        "energy",

        "max_energy",

        "total_taps",

        "ads_watched",

        "referral_count",

        "referral_coins",

        "daily_streak",
    }

    for field, value in updates.items():

        if field not in allowed_fields:

            continue

        if value is None:

            continue

        if field in integer_fields:

            try:

                value = int(value)

            except (
                ValueError,
                TypeError,
            ):

                raise ValueError(
                    f"القيمة غير صحيحة: {field}"
                )

            if value < 0:

                raise ValueError(
                    f"لا يمكن أن تكون قيمة {field} سالبة"
                )

        clean_updates[field] = value

    if not clean_updates:

        return None

    with _lock, _get_conn() as conn:

        exists = conn.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if exists is None:

            return None

        set_clause = ", ".join(
            f"{field}=?"
            for field in clean_updates
        )

        conn.execute(
            f"""
            UPDATE users
            SET {set_clause}
            WHERE user_id=?
            """,
            (
                *clean_updates.values(),
                user_id,
            ),
        )

        conn.commit()

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        return dict(row)


def reset_user_tasks_by_admin(user_id):

    with _lock, _get_conn() as conn:

        exists = conn.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()

        if exists is None:

            return False

        conn.execute(
            """
            UPDATE users
            SET claimed_tasks=''
            WHERE user_id=?
            """,
            (user_id,),
        )

        conn.execute(
            """
            DELETE FROM user_tasks
            WHERE user_id=?
            """,
            (user_id,),
        )

        conn.execute(
            """
            DELETE FROM user_achievements
            WHERE user_id=?
            """,
            (user_id,),
        )

        conn.commit()

        return True


# =========================================================
# STARTUP
# =========================================================

init_db()
