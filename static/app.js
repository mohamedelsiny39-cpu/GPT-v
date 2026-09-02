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
  ads: {}, minigame: {},
};
let prevSquares = null;

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
  minigameBtn: document.getElementById("minigameBtn"),
  adVideoReward: document.getElementById("adVideoReward"),
  adExternalReward: document.getElementById("adExternalReward"),
  minigameReward: document.getElementById("minigameReward"),
  adVideoRemaining: document.getElementById("adVideoRemaining"),
  adExternalRemaining: document.getElementById("adExternalRemaining"),
  minigameRemaining: document.getElementById("minigameRemaining"),
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
  if (S.minigame.min_reward !== undefined) {
    els.minigameReward.textContent = `+${S.minigame.min_reward}-${S.minigame.max_reward}`;
    els.minigameRemaining.textContent = `${S.minigame.remaining}/${S.minigame.limit}`;
  }
}

const PLOT_ICONS = ["⛺", "🏠", "🏡", "🏢", "🏬", "🕌", "🎡", "🗼", "🏟️", "🌆"];

function renderCity() {
  if (!S.squares || S.squares.length === 0) return;

  els.skyline.innerHTML = "";
  S.squares.forEach((sq) => {
    const div = document.createElement("div");
    const heightPct = sq.status === "locked" ? 6 : Math.max(10, sq.progress * 100);
    const wasNotBuilt = prevSquares && prevSquares[sq.index - 1] && prevSquares[sq.index - 1].status !== "built";
    div.className = `sky-building ${sq.status}` + (sq.status === "built" && wasNotBuilt ? " just-built" : "");
    div.style.height = `${heightPct}%`;
    div.textContent = sq.status === "locked" ? "" : sq.icon;
    els.skyline.appendChild(div);
    if (sq.status === "built" && wasNotBuilt) {
      showToast(`${t("buildingCompleted")} ${sq.name}`);
    }
  });

  els.cityList.innerHTML = "";
  S.squares.forEach((sq) => {
    const row = document.createElement("div");
    row.className = `city-row ${sq.status}`;
    const statusIcon = sq.status === "built" ? "✅" : sq.status === "building" ? "🚧" : "🔒";
    row.innerHTML = `
      <span class="city-row-icon">${sq.icon}</span>
      <div class="city-row-info">
        <div class="city-row-name">${sq.name} <span style="color:var(--text-muted);font-weight:400;">(${sq.level_range})</span></div>
        ${sq.status !== "locked" ? `<div class="city-row-bar"><div class="city-row-bar-fill" style="width:${Math.round(sq.progress * 100)}%"></div></div>` : ""}
      </div>
      <span class="city-row-status">${statusIcon}</span>
    `;
    els.cityList.appendChild(row);
  });

  prevSquares = S.squares.map((s) => ({ status: s.status }));
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
    ads: state.ads || {}, minigame: state.minigame || {},
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

// ===== صندوق الحظ (Minigame) =====
els.minigameBtn.addEventListener("click", async () => {
  const now = Date.now();
  if (now - lastAdClientTime < AD_MIN_GAP_MS) return;
  if (els.minigameBtn.disabled) return;

  if (S.minigame.remaining <= 0) {
    showToast(`${t("dailyLimitReached")} ${Math.ceil(S.minigame.seconds_to_refill / 60)}m`);
    return;
  }

  els.minigameBtn.disabled = true;
  els.adOverlay.classList.remove("hidden");
  els.adProgressFill.style.width = "30%";

  const ready = await waitForAdSdk();
  if (!ready) {
    els.adOverlay.classList.add("hidden");
    els.minigameBtn.disabled = false;
    showToast(t("noAdsAvailable"));
    return;
  }
  lastAdClientTime = now;
  els.adProgressFill.style.width = "70%";

  window[AD_ZONE_FN]()
    .then(async () => {
      els.adOverlay.classList.add("hidden");
      showToast(t("minigameOpening"));
      try {
        const res = await fetch("/api/minigame/play", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: user.id, first_name: user.first_name, photo_url: user.photo_url }),
        });
        const state = await res.json();
        if (res.ok) {
          applyServerState(state);
          showToast(`🎁 +${state.minigame_reward} CCL`);
          if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
        }
      } catch (e) { /* تجاهل */ }
      startButtonCooldown(els.minigameBtn, 8);
    })
    .catch(() => {
      els.adOverlay.classList.add("hidden");
      els.minigameBtn.disabled = false;
      lastAdClientTime = 0;
    });
});

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

function handleSocialTaskClick(btn) {
  const stage = btn.dataset.stage;
  const url = btn.dataset.url;

  if (stage === "start") {
    if (url) {
      if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
    }
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
      if (url) {
        if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
      }
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
  els.boardList.innerHTML = "";
  data.leaderboard.forEach((p) => {
    const row = document.createElement("div");
    const topClass = p.rank <= 3 ? `top${p.rank}` : "";
    row.className = `board-row ${topClass}`;
    const medal = p.rank === 1 ? "🥇" : p.rank === 2 ? "🥈" : p.rank === 3 ? "🥉" : p.rank;
    const avatarContent = p.photo_url ? `<img src="${p.photo_url}">` : (p.first_name || "?").charAt(0);
    row.innerHTML = `
      <span class="board-rank">${medal}</span>
      <span class="board-avatar">${avatarContent}</span>
      <span class="board-name">${p.first_name}</span>
      <span class="board-coins">${formatNum(p.coins)} CCL</span>
    `;
    els.boardList.appendChild(row);
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
    telegram: t("conditionTelegram"),
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
    if (btn.dataset.tab === "referrals") loadReferrals();
    if (btn.dataset.tab === "leaderboard") loadLeaderboard();
    if (btn.dataset.tab === "wallet") loadAirdrop();
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
