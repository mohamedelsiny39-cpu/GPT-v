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
    return { id: tgUser.id, first_name: tgUser.first_name || "Player", photo_url: tgUser.photo_url || "" };
  }
  let guestId = localStorage.getItem("cc_guest_id");
  if (!guestId) {
    guestId = String(Math.floor(Math.random() * 1e9));
    localStorage.setItem("cc_guest_id", guestId);
  }
  return { id: Number(guestId), first_name: "Guest", photo_url: "" };
}

const user = getUser();

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add("hidden"), 2200);
}

// ===== الحالة المحلية =====
let S = {
  coins: 0, energy: 100, max_energy: 100, seconds_to_refill: 0,
  level: 1, coins_per_tap: 1, squares: [], total_taps: 0, ads_watched: 0,
  ads: {},
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
  miningCounter: document.getElementById("miningCounter"),
  miningTimer: document.getElementById("miningTimer"),
  miningBtn: document.getElementById("miningBtn"),
  upgrade1Card: document.getElementById("upgrade1Card"),
  upgrade1Detail: document.getElementById("upgrade1Detail"),
  upgrade1Btn: document.getElementById("upgrade1Btn"),
  levelBarNum: document.getElementById("levelBarNum"),
  levelBarNext: document.getElementById("levelBarNext"),
  levelBarFill: document.getElementById("levelBarFill"),
  adBtnVideo: document.getElementById("adBtnVideo"),
  adBtnExternal: document.getElementById("adBtnExternal"),
  adVideoReward: document.getElementById("adVideoReward"),
  adExternalReward: document.getElementById("adExternalReward"),
  adVideoRemaining: document.getElementById("adVideoRemaining"),
  adExternalRemaining: document.getElementById("adExternalRemaining"),
  adOverlay: document.getElementById("adOverlay"),
  adProgressFill: document.getElementById("adProgressFill"),
  checkinStreakText: document.getElementById("checkinStreakText"),
  checkinBtn: document.getElementById("checkinBtn"),
  tasksList: document.getElementById("tasksList"),
  achievementsList: document.getElementById("achievementsList"),
  refRewardText: document.getElementById("refRewardText"),
  refCount: document.getElementById("refCount"),
  refCoins: document.getElementById("refCoins"),
  refLinkText: document.getElementById("refLinkText"),
  refCopyBtn: document.getElementById("refCopyBtn"),
  refShareBtn: document.getElementById("refShareBtn"),
  refFriendsList: document.getElementById("refFriendsList"),
  podium: document.getElementById("podium"),
  boardList: document.getElementById("boardList"),
  myRank: document.getElementById("myRank"),
  airdropConditions: document.getElementById("airdropConditions"),
};

function formatNum(n) { return Math.floor(n).toLocaleString("en-US"); }

function renderProfile() {
  els.userName.textContent = user.first_name;
  if (user.photo_url) {
    els.avatar.innerHTML = `<img src="${user.photo_url}" alt="">`;
  } else {
    els.avatar.textContent = (user.first_name || "?").trim().charAt(0);
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
    ? t("maxLevelReached")
    : `${formatNum(nextTh - S.coins)} ${t("ccyNextLevel")}`;

  renderAdButtons();
}

function renderRefillCountdown() {
  if (S.energy >= S.max_energy) {
    els.energyRefill.textContent = t("energyFull");
  } else {
    const m = Math.floor(S.seconds_to_refill / 60);
    const s = S.seconds_to_refill % 60;
    els.energyRefill.textContent = `${t("energyRefillIn")} ${m}:${String(s).padStart(2, "0")}`;
  }
}

function renderAdButtons() {
  if (S.ads.interstitial) {
    const a = S.ads.interstitial;
    els.adVideoReward.textContent = `+${a.min_reward}-${a.max_reward}`;
    els.adVideoRemaining.textContent = `${a.remaining}/${a.limit}`;
  }
  if (S.ads.popup) {
    const a = S.ads.popup;
    els.adExternalReward.textContent = `+${a.min_reward}-${a.max_reward}`;
    els.adExternalRemaining.textContent = `${a.remaining}/${a.limit}`;
  }
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

  spawnSparks();
}

function spawnSparks() {
  const count = 8;
  const startRadius = 88; // قريب من حافة العملة
  const endRadius = 165;  // لحد ما يتلاشى برا
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
    const sx = Math.cos(angle) * startRadius;
    const sy = Math.sin(angle) * startRadius;
    const ex = Math.cos(angle) * endRadius;
    const ey = Math.sin(angle) * endRadius;

    const s = document.createElement("span");
    s.className = "spark";
    s.style.setProperty("--sx", `${sx}px`);
    s.style.setProperty("--sy", `${sy}px`);
    s.style.setProperty("--ex", `${ex}px`);
    s.style.setProperty("--ey", `${ey}px`);
    els.particles.appendChild(s);
    setTimeout(() => s.remove(), 700);
  }
}

// ===== مزامنة مع السيرفر =====
function applyServerState(state) {
  S = {
    coins: state.coins, energy: state.energy, max_energy: state.max_energy,
    seconds_to_refill: state.seconds_to_refill, level: state.level,
    coins_per_tap: state.coins_per_tap,
    total_taps: state.total_taps, ads_watched: state.ads_watched,
    ads: state.ads || {},
  };
  renderCore();
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
    pendingTaps += count;
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
const AD_ZONE_FN = "show_11673059";
const AD_MIN_GAP_MS = 8000;

function waitForAdSdk(timeoutMs = 4000, intervalMs = 200) {
  return new Promise((resolve) => {
    if (typeof window[AD_ZONE_FN] === "function") { resolve(true); return; }
    const start = Date.now();
    const check = setInterval(() => {
      if (typeof window[AD_ZONE_FN] === "function") {
        clearInterval(check); resolve(true);
      } else if (Date.now() - start > timeoutMs) {
        clearInterval(check); resolve(false);
      }
    }, intervalMs);
  });
}

function startButtonCooldown(btnEl, seconds) {
  const labelEl = btnEl.querySelector(".ad-mini-label");
  const originalLabel = labelEl.dataset.original || labelEl.textContent;
  labelEl.dataset.original = originalLabel;
  btnEl.disabled = true;
  let secondsLeft = seconds;
  labelEl.textContent = `${t("waitSeconds")} ${secondsLeft}s`;
  const interval = setInterval(() => {
    secondsLeft -= 1;
    if (secondsLeft <= 0) {
      clearInterval(interval);
      labelEl.textContent = originalLabel;
      btnEl.disabled = false;
    } else {
      labelEl.textContent = `${t("waitSeconds")} ${secondsLeft}s`;
    }
  }, 1000);
}

function setupAdButton(btnEl, adType, sdkArg) {
  btnEl.addEventListener("click", async () => {
    const now = Date.now();
    if (now - lastAdClientTime < AD_MIN_GAP_MS) return;
    if (btnEl.disabled) return;

    const adInfo = S.ads[adType];
    if (adInfo && adInfo.remaining <= 0) {
      showToast(`${t("dailyLimitReached")} ${Math.ceil(adInfo.seconds_to_refill / 60)}m`);
      return;
    }

    btnEl.disabled = true;
    els.adOverlay.classList.remove("hidden");
    els.adProgressFill.style.width = "30%";

    const ready = await waitForAdSdk();
    if (!ready) {
      els.adOverlay.classList.add("hidden");
      btnEl.disabled = false;
      showToast(t("noAdsAvailable"));
      return;
    }

    lastAdClientTime = now;
    els.adProgressFill.style.width = "70%";

    const call = sdkArg === undefined ? window[AD_ZONE_FN]() : window[AD_ZONE_FN](sdkArg);
    call
      .then(() => finishAdWatch(adType, btnEl))
      .catch(() => {
        els.adOverlay.classList.add("hidden");
        btnEl.disabled = false;
        lastAdClientTime = 0;
      });
  });
}

async function finishAdWatch(adType, btnEl) {
  els.adOverlay.classList.add("hidden");
  try {
    const res = await fetch("/api/watch_ad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id, first_name: user.first_name, photo_url: user.photo_url, ad_type: adType }),
    });
    const state = await res.json();
    if (res.ok) {
      applyServerState(state);
      showToast(`+${state.ad_reward} CCL`);
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    } else if (state.error === "limit_reached") {
      showToast(`${t("dailyLimitReached")} ${Math.ceil(state.seconds_left / 60)}m`);
    }
  } catch (e) { /* تجاهل */ }
  startButtonCooldown(btnEl, 8);
}

setupAdButton(els.adBtnVideo, "interstitial", undefined);
setupAdButton(els.adBtnExternal, "popup", "pop");

// ===== In-App Interstitial (تلقائي في الخلفية، من غير مكافأة) =====
function initInAppAds() {
  waitForAdSdk().then((ready) => {
    if (!ready || typeof window[AD_ZONE_FN] !== "function") return;
    window[AD_ZONE_FN]({
      type: "inApp",
      inAppSettings: { frequency: 2, capping: 0.1, interval: 30, timeout: 5, everyPage: false },
    });
  });
}
initInAppAds();

// ===== التسجيل اليومي =====
async function loadCheckin() {
  const res = await fetch(`/api/checkin?user_id=${user.id}`);
  const data = await res.json();
  els.checkinStreakText.innerHTML = `${data.streak} <span data-i18n="days">${t("days")}</span>`;
  if (data.claimed_today) {
    els.checkinBtn.textContent = t("claimed");
    els.checkinBtn.disabled = true;
  } else {
    els.checkinBtn.textContent = `${t("claim")} (+${data.next_reward})`;
    els.checkinBtn.disabled = false;
  }
}

els.checkinBtn.addEventListener("click", async () => {
  els.checkinBtn.disabled = true;
  try {
    const res = await fetch("/api/checkin/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id, first_name: user.first_name, photo_url: user.photo_url }),
    });
    const state = await res.json();
    if (res.ok) {
      applyServerState(state);
      showToast(`${t("checkinToast")} +${state.checkin_reward} CCL 🔥`);
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      loadCheckin();
    } else {
      loadCheckin();
    }
  } catch (e) {
    els.checkinBtn.disabled = false;
  }
});

// ===== المهام والإنجازات =====
async function loadTasks() {
  const lang = getLang() || "ar";
  const res = await fetch(`/api/tasks?user_id=${user.id}&category=task&lang=${lang}`);
  const tasks = await res.json();
  els.tasksList.innerHTML = "";
  tasks.forEach((tItem) => {
    const card = document.createElement("div");
    card.className = "task-card";
    const btnLabel = tItem.status === "claimed" ? t("claimed") : t("start");
    card.innerHTML = `
      <div class="task-info">
        <div class="task-title">${tItem.title}</div>
        <div class="task-reward">+${tItem.reward} CCL</div>
      </div>
      <button class="task-btn ${tItem.status === "claimed" ? "claimed" : "available"}"
              ${tItem.status === "claimed" ? "disabled" : ""}
              data-id="${tItem.id}" data-url="${tItem.url || ""}" data-type="${tItem.task_type}"
              data-stage="start">${btnLabel}</button>
    `;
    els.tasksList.appendChild(card);
  });
  attachSocialTaskHandlers();
}

function attachSocialTaskHandlers() {
  els.tasksList.querySelectorAll(".task-btn.available").forEach((btn) => {
    btn.addEventListener("click", () => handleSocialTaskClick(btn));
  });
}

// بيفتح اللينك بالطريقة الصح حسب نوعه: لينكات تليجرام (t.me) لازم تتفتح
// بدالة openTelegramLink عشان تنقل المستخدم للقناة جوه التطبيق مباشرة،
// مش بمتصفح داخلي زي باقي الروابط الخارجية
function openTaskUrl(url, taskType) {
  if (!url) return;
  if (taskType === "telegram" && tg && tg.openTelegramLink) {
    tg.openTelegramLink(url);
  } else if (tg && tg.openLink) {
    tg.openLink(url);
  } else {
    window.open(url, "_blank");
  }
}

function handleSocialTaskClick(btn) {
  const stage = btn.dataset.stage;
  const url = btn.dataset.url;
  const taskType = btn.dataset.type;

  if (stage === "start") {
    openTaskUrl(url, taskType);
    btn.disabled = true;
    let secondsLeft = 5;
    btn.textContent = `${t("waitSeconds")} ${secondsLeft}s`;
    const interval = setInterval(() => {
      secondsLeft -= 1;
      if (secondsLeft <= 0) {
        clearInterval(interval);
        btn.textContent = t("claim");
        btn.dataset.stage = "claim";
        btn.disabled = false;
      } else {
        btn.textContent = `${t("waitSeconds")} ${secondsLeft}s`;
      }
    }, 1000);
    return;
  }

  if (stage === "claim") {
    claimSocialTask(btn);
  }
}

async function claimSocialTask(btn) {
  btn.disabled = true;
  const taskId = btn.dataset.id;
  const taskType = btn.dataset.type;
  const url = btn.dataset.url;
  try {
    const res = await fetch("/api/tasks/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id, task_id: taskId }),
    });
    const state = await res.json();

    if (res.ok) {
      applyServerState(state);
      showToast(`+${state.claimed_reward} CCL`);
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      btn.textContent = t("claimed");
      btn.className = "task-btn claimed";
      return;
    }

    if (state.error === "not_subscribed") {
      showToast(t("notSubscribedRetry"));
      openTaskUrl(url, taskType);
      btn.disabled = false; // يقدر يدوس استلام تاني بعد ما يشترك فعلاً
    } else {
      btn.disabled = false;
    }
  } catch (e) {
    btn.disabled = false;
  }
}

async function loadAchievements() {
  const lang = getLang() || "ar";
  const res = await fetch(`/api/tasks?user_id=${user.id}&category=achievement&lang=${lang}`);
  const items = await res.json();
  els.achievementsList.innerHTML = "";
  items.forEach((a) => {
    const card = document.createElement("div");
    card.className = "task-card";
    const btnLabel = a.status === "claimed" ? t("claimed") : a.status === "available" ? t("claim") : t("locked");
    const pct = a.target ? Math.round((a.progress / a.target) * 100) : 0;
    card.innerHTML = `
      <div class="task-info">
        <div class="task-title">${a.title}</div>
        <div class="task-reward">+${a.reward} CCL</div>
        <div class="task-progress-bar"><div class="task-progress-fill" style="width:${pct}%"></div></div>
        <div class="task-progress-label">${formatNum(a.progress)} / ${formatNum(a.target)}</div>
      </div>
      <button class="task-btn ${a.status}" ${a.status !== "available" ? "disabled" : ""} data-id="${a.id}">${btnLabel}</button>
    `;
    els.achievementsList.appendChild(card);
  });
  attachTaskClaimHandlers(els.achievementsList, loadAchievements);
}

function attachTaskClaimHandlers(container, reloadFn) {
  container.querySelectorAll(".task-btn.available").forEach((btn) => {
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
        showToast(`+${state.claimed_reward} CCL`);
        if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
        reloadFn();
      } else {
        btn.disabled = false;
      }
    });
  });
}

document.querySelectorAll(".sub-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sub-tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("subscreen-tasks").classList.toggle("hidden", btn.dataset.subtab !== "tasks");
    document.getElementById("subscreen-achievements").classList.toggle("hidden", btn.dataset.subtab !== "achievements");
    if (btn.dataset.subtab === "tasks") loadTasks(); else loadAchievements();
  });
});

// ===== الدعوات =====
let referralLink = "";

async function loadReferrals() {
  const res = await fetch(`/api/referrals?user_id=${user.id}`);
  const data = await res.json();
  els.refRewardText.textContent = data.reward_per_invite;
  els.refCount.textContent = data.referral_count;
  els.refCoins.textContent = formatNum(data.referral_coins);

  const botUsername = data.bot_username || window.BOT_USERNAME || "";
  referralLink = botUsername ? `https://t.me/${botUsername}?start=ref_${user.id}` : "";
  els.refLinkText.textContent = referralLink || t("setBotUsername");

  els.refFriendsList.innerHTML = "";
  if (data.friends.length === 0) {
    els.refFriendsList.innerHTML = `<div class="ref-empty">${t("noFriendsYet")}</div>`;
  } else {
    data.friends.forEach((f) => {
      const row = document.createElement("div");
      row.className = "ref-friend-row";
      row.innerHTML = `
        <span class="ref-friend-avatar">${(f.first_name || "?").charAt(0)}</span>
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
  els.refCopyBtn.textContent = t("copied");
  els.refCopyBtn.classList.add("copied");
  setTimeout(() => {
    els.refCopyBtn.textContent = t("copy");
    els.refCopyBtn.classList.remove("copied");
  }, 1500);
});

els.refShareBtn.addEventListener("click", () => {
  if (!referralLink) return;
  const text = `Join me on CanCel World and earn CCL coins! 🪙`;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(referralLink)}&text=${encodeURIComponent(text)}`;
  if (tg && tg.openTelegramLink) tg.openTelegramLink(shareUrl); else window.open(shareUrl, "_blank");
});

// ===== الصدارة =====
async function loadLeaderboard() {
  const res = await fetch(`/api/leaderboard?user_id=${user.id}`);
  const data = await res.json();
  els.myRank.innerHTML = data.my_rank ? `${t("yourRankNow")}: <b>#${data.my_rank}</b>` : "";

  const top3 = data.leaderboard.filter((p) => p.rank <= 3);
  const rest = data.leaderboard.filter((p) => p.rank > 3);

  // البوديوم
  els.podium.innerHTML = "";
  top3.forEach((p) => {
    const card = document.createElement("div");
    card.className = `podium-card place-${p.rank}`;
    const avatarContent = p.photo_url ? `<img src="${p.photo_url}">` : (p.first_name || "?").charAt(0);
    card.innerHTML = `
      ${p.rank === 1 ? `<span class="podium-crown">👑</span>` : ""}
      <span class="podium-avatar">${avatarContent}</span>
      <span class="podium-rank-badge">${p.rank === 1 ? "#1" : p.rank === 2 ? "#2" : "#3"}</span>
      <span class="podium-name">${p.first_name}</span>
      <span class="podium-coins">${formatNum(p.coins)}</span>
    `;
    els.podium.appendChild(card);
  });

  // باقي القايمة (من 4 لحد 100)
  els.boardList.innerHTML = "";
  rest.forEach((p) => {
    const row = document.createElement("div");
    row.className = "board-row";
    const avatarContent = p.photo_url ? `<img src="${p.photo_url}">` : (p.first_name || "?").charAt(0);
    row.innerHTML = `
      <span class="board-rank">${p.rank}</span>
      <span class="board-avatar">${avatarContent}</span>
      <span class="board-name">${p.first_name}</span>
      <span class="board-coins">${formatNum(p.coins)} CCL</span>
    `;
    els.boardList.appendChild(row);
  });
}

// ===== التعدين المجاني والمحفظة الحقيقية =====
let currentCurrency = localStorage.getItem("cc_currency") || (getLang() === "en" ? "usd" : "egp");
let mining = {
  started: false, ready: false, secondsLeft: 0, accrued: 0,
  rate: 0.01, upgrade1Purchased: false, upgrade1Cost: 5000, upgrade1Rate: 0.02,
  walletBalance: 0, egpPerUsd: 50,
};
let selectedWithdrawMethod = null;

function formatCurrency(amountUsd, decimals = 2) {
  if (currentCurrency === "egp") {
    return `${(amountUsd * mining.egpPerUsd).toFixed(decimals)} ${t("egpShort")}`;
  }
  return `$${amountUsd.toFixed(decimals)}`;
}

function formatCountdown(totalSeconds) {
  const d = Math.floor(totalSeconds / 86400);
  const h = Math.floor((totalSeconds % 86400) / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${d}${t("dayShort")} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatCountdown(totalSeconds) {
  const d = Math.floor(totalSeconds / 86400);
  const h = Math.floor((totalSeconds % 86400) / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${d}${t("dayShort")} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

let currentRateUnit = "sec";
const RATE_UNIT_SECONDS = { sec: 1, min: 60, hour: 3600, day: 86400 };
const RATE_UNIT_DECIMALS = { sec: 8, min: 6, hour: 4, day: 2 };

function safeNum(n, fallback = 0) {
  return typeof n === "number" && !isNaN(n) ? n : fallback;
}

async function loadMining() {
  try {
    const res = await fetch(`/api/mining?user_id=${user.id}`);
    const data = await res.json();
    applyMiningData(data);
  } catch (e) { /* هيتزامن تاني في المحاولة الجاية */ }
}

function applyMiningData(data) {
  mining = {
    started: !!data.started, ready: !!data.ready_to_collect,
    secondsLeft: safeNum(data.seconds_left), accrued: safeNum(data.accrued_usd),
    rate: safeNum(data.rate_usd_per_day, 0.01), upgrade1Purchased: !!data.upgrade1_purchased,
    upgrade1Cost: safeNum(data.upgrade1_cost, 5000), upgrade1Rate: safeNum(data.upgrade1_rate_usd, 0.02),
    walletBalance: safeNum(data.wallet_balance_usd), egpPerUsd: safeNum(data.egp_per_usd, 50),
    lifetimeMined: safeNum(data.lifetime_mined_usd), harvestCount: safeNum(data.harvest_count),
  };
  renderMining();
}

function renderMining() {
  els.miningCounter.textContent = formatCurrency(mining.accrued, 8);

  const perUnit = (mining.rate / 86400) * RATE_UNIT_SECONDS[currentRateUnit];
  const rateLine = document.getElementById("miningRateLine");
  if (rateLine) rateLine.textContent = `${formatCurrency(perUnit, RATE_UNIT_DECIMALS[currentRateUnit])} /${currentRateUnit}`;

  const lifetimeEl = document.getElementById("lifetimeMined");
  if (lifetimeEl) lifetimeEl.textContent = formatCurrency(mining.lifetimeMined);

  if (!mining.started) {
    els.miningTimer.textContent = "--:--:--";
    els.miningBtn.textContent = t("startFreeMining");
    els.miningBtn.disabled = false;
  } else if (mining.ready) {
    els.miningTimer.textContent = t("readyToCollect");
    els.miningBtn.textContent = t("collectAndRestart");
    els.miningBtn.disabled = false;
  } else {
    els.miningTimer.textContent = formatCountdown(mining.secondsLeft);
    els.miningBtn.textContent = t("miningRunning");
    els.miningBtn.disabled = true;
  }

  // حلقة التقدم حوالين البيت الرئيسي
  const ring = document.getElementById("villageRing");
  if (ring) {
    let pct = 0;
    if (mining.ready) pct = 100;
    else if (mining.started) pct = Math.max(0, Math.min(100, ((86400 - mining.secondsLeft) / 86400) * 100));
    ring.style.setProperty("--progress", pct.toFixed(2));
  }

  // البيوت الصغيرة بتنور حسب التطويرات
  const n1 = document.getElementById("villageNode1");
  const n2 = document.getElementById("villageNode2");
  if (n1) n1.classList.toggle("lit", mining.harvestCount > 0);
  if (n2) n2.classList.toggle("lit", mining.upgrade1Purchased);

  els.upgrade1Detail.textContent = formatCurrency(mining.upgrade1Rate) + ` / ${t("day")}`;
  if (mining.upgrade1Purchased) {
    els.upgrade1Btn.textContent = t("purchased");
    els.upgrade1Btn.disabled = true;
    els.upgrade1Btn.classList.add("purchased");
  } else {
    els.upgrade1Btn.textContent = `${t("buyFor")} ${formatNum(mining.upgrade1Cost)}`;
    els.upgrade1Btn.disabled = S.coins < mining.upgrade1Cost;
    els.upgrade1Btn.classList.remove("purchased");
  }
}

document.querySelectorAll(".rate-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".rate-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentRateUnit = btn.dataset.unit;
    renderMining();
  });
});

els.miningBtn.addEventListener("click", async () => {
  els.miningBtn.disabled = true;
  try {
    const res = await fetch("/api/mining/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id, first_name: user.first_name, photo_url: user.photo_url }),
    });
    const data = await res.json();
    if (res.ok) {
      if (data.action === "collected") {
        showToast(`+${formatCurrency(data.collected_usd, 4)} 💰`);
        spawnHarvestSparks();
        if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      }
      applyMiningData(data);
    } else {
      els.miningBtn.disabled = false;
    }
  } catch (e) {
    els.miningBtn.disabled = false;
  }
});

// شرر احتفالي حوالين البيت لحظة تجميع الأرباح
function spawnHarvestSparks() {
  const ring = document.getElementById("villageRing");
  if (!ring) return;
  for (let i = 0; i < 10; i++) {
    const angle = (Math.PI * 2 * i) / 10 + Math.random() * 0.3;
    const s = document.createElement("span");
    s.className = "spark";
    s.style.position = "absolute";
    s.style.left = "50%";
    s.style.top = "50%";
    s.style.setProperty("--sx", `${Math.cos(angle) * 20}px`);
    s.style.setProperty("--sy", `${Math.sin(angle) * 20}px`);
    s.style.setProperty("--ex", `${Math.cos(angle) * 90}px`);
    s.style.setProperty("--ey", `${Math.sin(angle) * 90}px`);
    ring.appendChild(s);
    setTimeout(() => s.remove(), 700);
  }
}

els.upgrade1Btn.addEventListener("click", async () => {
  if (mining.upgrade1Purchased) return;
  els.upgrade1Btn.disabled = true;
  try {
    const res = await fetch("/api/mining/upgrade1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id }),
    });
    const data = await res.json();
    if (res.ok) {
      S.coins = data.coins;
      renderCore();
      applyMiningData(data);
      showToast(`⚡ ${t("upgradePurchased")}`);
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    } else {
      els.upgrade1Btn.disabled = false;
      if (data.error === "not_enough_coins") showToast(t("notEnoughCoins"));
    }
  } catch (e) {
    els.upgrade1Btn.disabled = false;
  }
});

// عداد التعدين الحي محلياً كل ثانية
setInterval(() => {
  const screen = document.getElementById("screen-earnings");
  if (!screen || screen.classList.contains("hidden")) return;
  if (mining.started && !mining.ready) {
    mining.secondsLeft = Math.max(0, mining.secondsLeft - 1);
    mining.accrued += mining.rate / 86400;
    mining.lifetimeMined = safeNum(mining.lifetimeMined) + mining.rate / 86400;
    if (mining.secondsLeft <= 0) mining.ready = true;
    renderMining();
  }
}, 1000);

// مزامنة دورية مع السيرفر كل 20 ثانية لضمان الاستقرار ومنع أي انحراف في الأرقام
setInterval(() => {
  const screen = document.getElementById("screen-earnings");
  if (screen && !screen.classList.contains("hidden")) loadMining();
}, 20000);

// ===== المحفظة الحقيقية =====
function renderWalletBalance() {
  document.getElementById("walletBalanceBig").innerHTML =
    currentCurrency === "egp"
      ? `${(mining.walletBalance * mining.egpPerUsd).toFixed(2)} <span id="walletCurrencySymbol">${t("egpShort")}</span>`
      : `${mining.walletBalance.toFixed(2)} <span id="walletCurrencySymbol">USD</span>`;
}

async function loadWallet() {
  if (mining.egpPerUsd === undefined || mining.walletBalance === undefined) {
    await loadMining();
  }
  renderWalletBalance();
  loadWithdrawHistory();
}

document.querySelectorAll(".currency-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".currency-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentCurrency = btn.dataset.currency;
    localStorage.setItem("cc_currency", currentCurrency);
    renderWalletBalance();
    renderMining();
    updateWithdrawFormLabels();
  });
});

const WITHDRAW_METHOD_LABELS = { vodafone_cash: "vodafoneCash", faucetpay: "FaucetPay" };

function updateWithdrawFormLabels() {
  if (!selectedWithdrawMethod) return;
  const minNote = currentCurrency === "egp" ? "5.00 " + t("egpShort") : "$0.10";
  document.getElementById("withdrawMinNote").textContent = `${t("minWithdraw")}: ${minNote}`;
  document.getElementById("withdrawTarget").placeholder =
    selectedWithdrawMethod === "vodafone_cash" ? t("phoneNumberPlaceholder") : t("faucetpayPlaceholder");
  document.getElementById("withdrawAmount").placeholder =
    currentCurrency === "egp" ? t("amountInEgp") : t("amountInUsd");
}

document.querySelectorAll(".withdraw-method-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".withdraw-method-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    selectedWithdrawMethod = btn.dataset.method;
    const label = btn.dataset.method === "vodafone_cash" ? t("vodafoneCash") : "FaucetPay";
    document.getElementById("withdrawFormTitle").textContent = label;
    document.getElementById("withdrawForm").classList.remove("hidden");
    updateWithdrawFormLabels();
  });
});

document.getElementById("withdrawSubmitBtn").addEventListener("click", async () => {
  const target = document.getElementById("withdrawTarget").value.trim();
  const amountRaw = parseFloat(document.getElementById("withdrawAmount").value);
  if (!selectedWithdrawMethod || !target || !amountRaw || amountRaw <= 0) {
    showToast(t("fillAllFields"));
    return;
  }
  const amountUsd = currentCurrency === "egp" ? amountRaw / mining.egpPerUsd : amountRaw;

  const btn = document.getElementById("withdrawSubmitBtn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/withdraw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: user.id, method: selectedWithdrawMethod, target, amount_usd: amountUsd }),
    });
    const data = await res.json();
    if (res.ok) {
      mining.walletBalance = data.wallet_balance_usd;
      renderWalletBalance();
      renderMining();
      document.getElementById("withdrawTarget").value = "";
      document.getElementById("withdrawAmount").value = "";
      showToast(t("withdrawRequested"));
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      loadWithdrawHistory();
    } else {
      if (data.error === "below_minimum") showToast(t("belowMinimum"));
      else if (data.error === "insufficient_balance") showToast(t("insufficientBalance"));
      else showToast(t("withdrawFailed"));
    }
  } catch (e) {
    showToast(t("withdrawFailed"));
  } finally {
    btn.disabled = false;
  }
});

async function loadWithdrawHistory() {
  const res = await fetch(`/api/withdrawals?user_id=${user.id}`);
  const list = await res.json();
  const container = document.getElementById("withdrawHistory");
  container.innerHTML = "";
  list.forEach((w) => {
    const row = document.createElement("div");
    row.className = "withdraw-history-row";
    const statusClass = `wh-status-${w.status}`;
    const statusLabel = w.status === "paid" ? t("statusPaid") : w.status === "rejected" ? t("statusRejected") : t("statusPending");
    const label = w.method === "vodafone_cash" ? t("vodafoneCash") : "FaucetPay";
    row.innerHTML = `
      <span>${label} · ${formatCurrency(w.amount_usd)}</span>
      <span class="${statusClass}">${statusLabel}</span>
    `;
    container.appendChild(row);
  });
}

// ===== الإيردروب =====
async function loadAirdrop() {
  const res = await fetch(`/api/airdrop?user_id=${user.id}`);
  const data = await res.json();
  els.airdropConditions.innerHTML = "";

  const condLabels = {
    coins: `${t("conditionCoins")} ${formatNum(data.conditions.find(c => c.key === "coins").target)} CCL`,
    referrals: `${t("conditionReferrals")} ${data.conditions.find(c => c.key === "referrals").target} ${t("friends")}`,
    engagement: `${t("conditionEngagement")} ${formatNum(data.conditions.find(c => c.key === "engagement").target)} ${t("taps")}`,
  };

  data.conditions.forEach((c) => {
    const row = document.createElement("div");
    row.className = `airdrop-cond ${c.met ? "met" : ""}`;
    row.innerHTML = `
      <span>${condLabels[c.key]}</span>
      <span class="airdrop-cond-status">${c.met ? t("met") : `${formatNum(c.current)}/${formatNum(c.target)}`}</span>
    `;
    els.airdropConditions.appendChild(row);
  });

  const eligibleEl = document.createElement("div");
  eligibleEl.className = "airdrop-eligible";
  eligibleEl.textContent = data.eligible ? t("eligibleYes") : t("eligibleNo");
  els.airdropConditions.appendChild(eligibleEl);
}

// ===== تبديل التابات =====
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".screen").forEach((s) => s.classList.add("hidden"));
    document.getElementById(`screen-${btn.dataset.tab}`).classList.remove("hidden");

    if (btn.dataset.tab === "tasks") loadTasks();
    if (btn.dataset.tab === "earnings") loadMining();
    if (btn.dataset.tab === "referrals") loadReferrals();
    if (btn.dataset.tab === "leaderboard") loadLeaderboard();
    if (btn.dataset.tab === "wallet") { loadAirdrop(); loadWallet(); }
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

// ===== اختيار اللغة =====
function initLanguage() {
  const saved = getLang();
  const overlay = document.getElementById("langOverlay");
  if (saved) {
    applyLang(saved);
    overlay.classList.add("hidden");
    startApp();
  } else {
    overlay.classList.remove("hidden");
    document.querySelectorAll(".lang-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        setLang(btn.dataset.lang);
        overlay.classList.add("hidden");
        startApp();
      });
    });
  }
}

let appStarted = false;
function startApp() {
  if (appStarted) return;
  appStarted = true;
  renderProfile();
  fetchState();
  loadCheckin();
  setInterval(fetchState, 10000);
}

initLanguage();
