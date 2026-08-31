const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }

const MAX_LEVEL = 100;
function levelThreshold(level) { return 100 * level * (level - 1); }
function computeLevel(coins) {
  let level = 1;
  for (let L = 2; L <= MAX_LEVEL; L++) {
    if (coins >= levelThreshold(L)) level = L; else break;
  }
  return level;
}
function coinsPerTap(level) { return Math.floor(level / 10) + 1; }
function levelProgress(coins, level) {
  if (level >= MAX_LEVEL) return { progress: 1, nextTh: null };
  const prev = levelThreshold(level);
  const next = levelThreshold(level + 1);
  const span = next - prev;
  const progress = span ? (coins - prev) / span : 1;
  return { progress: Math.max(0, Math.min(1, progress)), nextTh: next };
}

function getUser() {
  const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  if (tgUser) {
    return { id: tgUser.id, first_name: tgUser.first_name || "لاعب", photo_url: tgUser.photo_url || "" };
  }
  let guestId = localStorage.getItem("cc_guest_id");
  if (!guestId) {
    guestId = String(Math.floor(Math.random() * 1e9));
    localStorage.setItem("cc_guest_id", guestId);
  }
  return { id: Number(guestId), first_name: "ضيف", photo_url: "" };
}

const user = getUser();

// ===== الحالة المحلية (للتحديث اللحظي) =====
let S = {
  coins: 0, energy: 100, max_energy: 100, seconds_to_refill: 0,
  level: 1, coins_per_tap: 1, squares: [], total_taps: 0, ads_watched: 0,
};

let pendingTaps = 0;
let sendTimer = null;
let sendInFlight = false;
let lastAdClientTime = 0;

const els = {
  avatar: document.getElementById("avatar"),
  userName: document.getElementById("userName"),
  levelNum: document.getElementById("levelNum"),
  topCoins: document.getElementById("topCoins"),
  coinCount: document.getElementById("coinCount"),
  energyNum: document.getElementById("energyNum"),
  energyMax: document.getElementById("energyMax"),
  energyFill: document.getElementById("energyFill"),
  energyRefill: document.getElementById("energyRefill"),
  perTap: document.getElementById("perTap"),
  coinBtn: document.getElementById("coinBtn"),
  particles: document.getElementById("particles"),
  skyline: document.getElementById("skyline"),
  cityList: document.getElementById("cityList"),
  levelBarNum: document.getElementById("levelBarNum"),
  levelBarNext: document.getElementById("levelBarNext"),
  levelBarFill: document.getElementById("levelBarFill"),
  adBtnVideo: document.getElementById("adBtnVideo"),
  adBtnExternal: document.getElementById("adBtnExternal"),
  adOverlay: document.getElementById("adOverlay"),
  adProgressFill: document.getElementById("adProgressFill"),
  tasksList: document.getElementById("tasksList"),
  refRewardText: document.getElementById("refRewardText"),
  refCount: document.getElementById("refCount"),
  refCoins: document.getElementById("refCoins"),
  refLinkText: document.getElementById("refLinkText"),
  refCopyBtn: document.getElementById("refCopyBtn"),
  refShareBtn: document.getElementById("refShareBtn"),
  refFriendsList: document.getElementById("refFriendsList"),
  boardList: document.getElementById("boardList"),
  myRank: document.getElementById("myRank"),
};

function formatNum(n) { return Math.floor(n).toLocaleString("en-US"); }

function renderProfile() {
  els.userName.textContent = user.first_name;
  if (user.photo_url) {
    els.avatar.innerHTML = `<img src="${user.photo_url}" alt="">`;
  } else {
    els.avatar.textContent = (user.first_name || "؟").trim().charAt(0);
  }
}

function renderCore() {
  els.levelNum.textContent = S.level;
  els.topCoins.textContent = formatNum(S.coins);
  els.coinCount.textContent = formatNum(S.coins);
  els.energyNum.textContent = S.energy;
  els.energyMax.textContent = S.max_energy;
  els.energyFill.style.width = `${(S.energy / S.max_energy) * 100}%`;
  els.perTap.textContent = S.coins_per_tap;
  renderRefillCountdown();

  const { progress, nextTh } = levelProgress(S.coins, S.level);
  els.levelBarNum.textContent = S.level;
  els.levelBarFill.style.width = `${progress * 100}%`;
  els.levelBarNext.textContent = S.level >= MAX_LEVEL
    ? "وصلت لأقصى مستوى! 🎉"
    : `${formatNum(nextTh - S.coins)} CCL للمستوى الجاي`;
}

function renderRefillCountdown() {
  if (S.energy >= S.max_energy) {
    els.energyRefill.textContent = "طاقة كاملة";
  } else {
    const m = Math.floor(S.seconds_to_refill / 60);
    const s = S.seconds_to_refill % 60;
    els.energyRefill.textContent = `تجديد كامل بعد ${m}:${String(s).padStart(2, "0")}`;
  }
}

const PLOT_ICONS = ["⛺", "🏠", "🏡", "🏢", "🏬", "🕌", "🎡", "🗼", "🏟️", "🌆"];

function renderCity() {
  if (!S.squares || S.squares.length === 0) return;

  els.skyline.innerHTML = "";
  S.squares.forEach((sq) => {
    const div = document.createElement("div");
    const heightPct = sq.status === "locked" ? 6 : Math.max(10, sq.progress * 100);
    div.className = `sky-building ${sq.status}`;
    div.style.height = `${heightPct}%`;
    div.textContent = sq.status === "locked" ? "" : sq.icon;
    els.skyline.appendChild(div);
  });

  els.cityList.innerHTML = "";
  S.squares.forEach((sq) => {
    const row = document.createElement("div");
    row.className = `city-row ${sq.status}`;
    const statusIcon = sq.status === "built" ? "✅" : sq.status === "building" ? "🚧" : "🔒";
    row.innerHTML = `
      <span class="city-row-icon">${sq.icon}</span>
      <div class="city-row-info">
        <div class="city-row-name">${sq.name} <span style="color:var(--text-muted);font-weight:400;">(مستوى ${sq.level_range})</span></div>
        ${sq.status !== "locked" ? `<div class="city-row-bar"><div class="city-row-bar-fill" style="width:${Math.round(sq.progress * 100)}%"></div></div>` : ""}
      </div>
      <span class="city-row-status">${statusIcon}</span>
    `;
    els.cityList.appendChild(row);
  });
}

function spawnParticle() {
  const p = document.createElement("span");
  p.className = "particle";
  p.textContent = `+${S.coins_per_tap}`;
  const offsetX = (Math.random() - 0.5) * 60;
  p.style.left = `calc(50% + ${offsetX}px)`;
  p.style.top = "40%";
  els.particles.appendChild(p);
  setTimeout(() => p.remove(), 800);
}

// ===== مزامنة مع السيرفر =====
function applyServerState(state) {
  S = {
    coins: state.coins, energy: state.energy, max_energy: state.max_energy,
    seconds_to_refill: state.seconds_to_refill, level: state.level,
    coins_per_tap: state.coins_per_tap, squares: state.squares,
    total_taps: state.total_taps, ads_watched: state.ads_watched,
  };
  renderCore();
  renderCity();
}

async function fetchState() {
  const params = new URLSearchParams({ user_id: user.id, first_name: user.first_name, photo_url: user.photo_url });
  const res = await fetch(`/api/state?${params.toString()}`);
  const state = await res.json();
  applyServerState(state);
}

async function sendPendingTaps() {
  if (pendingTaps === 0 || sendInFlight) return;
  const count = pendingTaps;
  pendingTaps = 0;
  sendInFlight = true;
  try {
    const res = await fetch("/api/tap_batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id, first_name: user.first_name, photo_url: user.photo_url, count }),
    });
    const state = await res.json();
    applyServerState(state);
    if (state.leveled_up && tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
  } catch (e) {
    pendingTaps += count; // رجّع العدّاد لو الاتصال فشل
  } finally {
    sendInFlight = false;
    if (pendingTaps > 0) sendTimer = setTimeout(sendPendingTaps, 300);
  }
}

// ===== الضغط اللحظي =====
els.coinBtn.addEventListener("click", () => {
  if (S.energy <= 0) {
    els.coinBtn.style.transform = "scale(0.96)";
    setTimeout(() => (els.coinBtn.style.transform = ""), 100);
    return;
  }
  // تحديث فوري على الشاشة
  S.energy -= 1;
  S.coins += S.coins_per_tap;
  S.total_taps += 1;
  const newLevel = computeLevel(S.coins);
  if (newLevel > S.level) {
    S.level = newLevel;
    S.coins_per_tap = coinsPerTap(newLevel);
  }
  renderCore();
  spawnParticle();
  if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");

  pendingTaps += 1;
  clearTimeout(sendTimer);
  sendTimer = setTimeout(sendPendingTaps, 250);
});

// ===== الإعلانات الحقيقية (Monetag) =====
const AD_ZONE_FN = "show_11673059"; // نفس الدالة لكل الفورمات، بنفرّق بينها بالباراميتر
const AD_COOLDOWN_MS = 10000; // نفس قيمة AD_COOLDOWN_SECONDS في db.py - خليهم متطابقين دايماً

function waitForAdSdk(timeoutMs = 4000, intervalMs = 200) {
  return new Promise((resolve) => {
    if (typeof window[AD_ZONE_FN] === "function") {
      resolve(true);
      return;
    }
    const start = Date.now();
    const check = setInterval(() => {
      if (typeof window[AD_ZONE_FN] === "function") {
        clearInterval(check);
        resolve(true);
      } else if (Date.now() - start > timeoutMs) {
        clearInterval(check);
        resolve(false);
      }
    }, intervalMs);
  });
}

// بيبدأ عدّاد تنازلي على الزرار بعد المشاهدة، لحد ما يشتغل تاني
function startCooldownDisplay(btnEl, labelEl, originalLabel) {
  let secondsLeft = Math.ceil(AD_COOLDOWN_MS / 1000);
  btnEl.disabled = true;
  labelEl.textContent = `استنى ${secondsLeft}ث`;
  const interval = setInterval(() => {
    secondsLeft -= 1;
    if (secondsLeft <= 0) {
      clearInterval(interval);
      labelEl.textContent = originalLabel;
      btnEl.disabled = false;
    } else {
      labelEl.textContent = `استنى ${secondsLeft}ث`;
    }
  }, 1000);
}

function setupAdButton(btnEl, adType, sdkArg) {
  const labelEl = btnEl.querySelector(".ad-mini-label");
  const originalLabel = labelEl.textContent;

  btnEl.addEventListener("click", async () => {
    const now = Date.now();
    if (now - lastAdClientTime < AD_COOLDOWN_MS) return;

    btnEl.disabled = true;
    els.adOverlay.classList.remove("hidden");
    els.adProgressFill.style.width = "30%";

    const ready = await waitForAdSdk();
    if (!ready) {
      els.adOverlay.classList.add("hidden");
      btnEl.disabled = false;
      alert("مفيش إعلانات متاحة دلوقتي، جرب تاني بعد شوية 🙏");
      return;
    }

    lastAdClientTime = now;
    els.adProgressFill.style.width = "70%";

    const call = sdkArg === undefined
      ? window[AD_ZONE_FN]()
      : window[AD_ZONE_FN](sdkArg);

    call
      .then(() => finishAdWatch(adType, btnEl, labelEl, originalLabel))
      .catch(() => {
        els.adOverlay.classList.add("hidden");
        btnEl.disabled = false;
        lastAdClientTime = 0; // اسمحله يجرب تاني على طول لو فشل
      });
  });
}

async function finishAdWatch(adType, btnEl, labelEl, originalLabel) {
  els.adOverlay.classList.add("hidden");
  try {
    const res = await fetch("/api/watch_ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: user.id, first_name: user.first_name, photo_url: user.photo_url, ad_type: adType,
      }),
    });
    const state = await res.json();
    if (res.ok) {
      applyServerState(state);
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    }
  } catch (e) { /* تجاهل */ }
  startCooldownDisplay(btnEl, labelEl, originalLabel);
}

setupAdButton(els.adBtnVideo, "interstitial", undefined); // show_11673059()
setupAdButton(els.adBtnExternal, "popup", "pop");          // show_11673059('pop')

// ===== In-App Interstitial: فورمات تلقائي في الخلفية، من غير زرار ومن غير مكافأة =====
function initInAppAds() {
  waitForAdSdk().then((ready) => {
    if (!ready || typeof window[AD_ZONE_FN] !== "function") return;
    window[AD_ZONE_FN]({
      type: "inApp",
      inAppSettings: {
        frequency: 2,
        capping: 0.1,
        interval: 30,
        timeout: 5,
        everyPage: false,
      },
    });
  });
}
initInAppAds();

// ===== المهام =====
async function loadTasks() {
  const res = await fetch(`/api/tasks?user_id=${user.id}`);
  const tasks = await res.json();
  els.tasksList.innerHTML = "";
  tasks.forEach((t) => {
    const card = document.createElement("div");
    card.className = "task-card";
    const btnLabel = t.status === "claimed" ? "تم ✓" : t.status === "available" ? "استلم" : "مقفول";
    card.innerHTML = `
      <div class="task-info">
        <div class="task-title">${t.title}</div>
        <div class="task-reward">+${t.reward} CCL</div>
      </div>
      <button class="task-btn ${t.status}" ${t.status !== "available" ? "disabled" : ""} data-id="${t.id}">${btnLabel}</button>
    `;
    els.tasksList.appendChild(card);
  });

  els.tasksList.querySelectorAll(".task-btn.available").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const res = await fetch("/api/tasks/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.id, task_id: btn.dataset.id }),
      });
      const state = await res.json();
      if (res.ok) {
        applyServerState(state);
        if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
        loadTasks();
      } else {
        btn.disabled = false;
      }
    });
  });
}

// ===== الدعوات =====
let referralLink = "";

async function loadReferrals() {
  const res = await fetch(`/api/referrals?user_id=${user.id}`);
  const data = await res.json();

  els.refRewardText.textContent = data.reward_per_invite;
  els.refCount.textContent = data.referral_count;
  els.refCoins.textContent = formatNum(data.referral_coins);

  const botUsername = data.bot_username || window.BOT_USERNAME || "";
  referralLink = botUsername
    ? `https://t.me/${botUsername}?start=ref_${user.id}`
    : "";
  els.refLinkText.textContent = referralLink || "لازم تظبط اسم البوت في إعدادات السيرفر (BOT_USERNAME)";

  els.refFriendsList.innerHTML = "";
  if (data.friends.length === 0) {
    els.refFriendsList.innerHTML = `<div class="ref-empty">لسه محدش انضم بلينكك، ابدأ تشارك! 🚀</div>`;
  } else {
    data.friends.forEach((f) => {
      const row = document.createElement("div");
      row.className = "ref-friend-row";
      row.innerHTML = `
        <span class="ref-friend-avatar">${(f.first_name || "؟").charAt(0)}</span>
        <span class="ref-friend-name">${f.first_name}</span>
        <span class="ref-friend-reward">+${data.reward_per_invite} CCL</span>
      `;
      els.refFriendsList.appendChild(row);
    });
  }
}

els.refCopyBtn.addEventListener("click", async () => {
  if (!referralLink) return;
  try {
    await navigator.clipboard.writeText(referralLink);
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = referralLink;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  els.refCopyBtn.textContent = "اتنسخ ✓";
  els.refCopyBtn.classList.add("copied");
  setTimeout(() => {
    els.refCopyBtn.textContent = "نسخ";
    els.refCopyBtn.classList.remove("copied");
  }, 1500);
});

els.refShareBtn.addEventListener("click", () => {
  if (!referralLink) return;
  const text = `تعالى العب معايا CanCel Coin واكسب عملات CCL! 🪙`;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(referralLink)}&text=${encodeURIComponent(text)}`;
  if (tg && tg.openTelegramLink) {
    tg.openTelegramLink(shareUrl);
  } else {
    window.open(shareUrl, "_blank");
  }
});

// ===== الصدارة =====
async function loadLeaderboard() {
  const res = await fetch(`/api/leaderboard?user_id=${user.id}`);
  const data = await res.json();
  els.myRank.innerHTML = data.my_rank ? `ترتيبك الحالي: <b>#${data.my_rank}</b>` : "";
  els.boardList.innerHTML = "";
  data.leaderboard.forEach((p) => {
    const row = document.createElement("div");
    const topClass = p.rank <= 3 ? `top${p.rank}` : "";
    row.className = `board-row ${topClass}`;
    const medal = p.rank === 1 ? "🥇" : p.rank === 2 ? "🥈" : p.rank === 3 ? "🥉" : p.rank;
    const avatarContent = p.photo_url ? `<img src="${p.photo_url}">` : (p.first_name || "؟").charAt(0);
    row.innerHTML = `
      <span class="board-rank">${medal}</span>
      <span class="board-avatar">${avatarContent}</span>
      <span class="board-name">${p.first_name}</span>
      <span class="board-coins">${formatNum(p.coins)} CCL</span>
    `;
    els.boardList.appendChild(row);
  });
}

// ===== تبديل التابات =====
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
    document.getElementById(`screen-${btn.dataset.tab}`).classList.remove("hidden");

    if (btn.dataset.tab === "tasks") loadTasks();
    if (btn.dataset.tab === "referrals") loadReferrals();
    if (btn.dataset.tab === "leaderboard") loadLeaderboard();
  });
});

// ===== عداد الطاقة كل ثانية =====
setInterval(() => {
  if (S.seconds_to_refill > 0) {
    S.seconds_to_refill -= 1;
    renderRefillCountdown();
    if (S.seconds_to_refill <= 0) fetchState();
  }
}, 1000);

renderProfile();
fetchState();
setInterval(fetchState, 10000); // مزامنة كاملة كل 10 ثواني احتياطي
