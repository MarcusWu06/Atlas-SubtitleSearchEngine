const params = new URLSearchParams(window.location.search);
const query = params.get("q") || "";
const exact = params.get("exact") === "1";
const currentPage = Number(params.get("page") || "1");
const perPage = 12;

const form = document.getElementById("results-search-form");
const input = document.getElementById("results-search-input");
const exactToggle = document.getElementById("exact-search-toggle");
const resultsTitle = document.getElementById("results-title");
const resultsMeta = document.getElementById("results-meta");
const resultsGrid = document.getElementById("results-grid");
const paginationTop = document.getElementById("pagination-top");
const pagination = document.getElementById("pagination");
const messageBox = document.getElementById("message-box");

if (input) input.value = query;
if (exactToggle) exactToggle.checked = exact;

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  const next = input?.value.trim();
  if (!next) return;

  const nextParams = new URLSearchParams();
  nextParams.set("q", next);
  nextParams.set("page", "1");

  if (exactToggle?.checked) {
    nextParams.set("exact", "1");
  }

  window.location.href = `/results?${nextParams.toString()}`;
});

function showMessage(message) {
  if (!messageBox) return;

  const text = String(message || "").trim();
  if (!text) {
    hideMessage();
    return;
  }

  messageBox.textContent = text;
  messageBox.classList.remove("hidden");
}

function hideMessage() {
  if (!messageBox) return;
  messageBox.textContent = "";
  messageBox.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function highlightText(text, q) {
  const safeText = escapeHtml(text);
  const tokens = q
    .trim()
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token, index, arr) => arr.indexOf(token) === index)
    .sort((a, b) => b.length - a.length);

  if (!tokens.length) return safeText;

  const escapedTokens = tokens.map((token) =>
    token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );

  const regex = new RegExp(`(${escapedTokens.join("|")})`, "gi");
  return safeText.replace(regex, '<mark class="hit-highlight">$1</mark>');
}

const summaryCache = new Map();
const savedMoments = new Set();
const savedVideos = new Set();

function buildMomentKey(videoId, startSeconds, q) {
  return `${videoId}__${Math.floor(startSeconds || 0)}__${(q || "").trim()}`;
}

async function loadSavedState() {
  const response = await fetch("/api/archive");
  const text = await response.text();

  let data = [];
  try {
    data = text ? JSON.parse(text) : [];
  } catch (_) {
    return;
  }

  if (!Array.isArray(data)) return;

  savedMoments.clear();
  savedVideos.clear();

  for (const item of data) {
    const itemType = item?.item_type || "moment";

    if (itemType === "video") {
      if (item.video_id) {
        savedVideos.add(item.video_id);
      }
      continue;
    }

    savedMoments.add(
      buildMomentKey(item.video_id, item.start_seconds, item.query || "")
    );
  }
}

function isMomentSaved(videoId, startSeconds, q) {
  return savedMoments.has(buildMomentKey(videoId, startSeconds, q));
}

function isVideoSaved(videoId) {
  return savedVideos.has(videoId);
}

async function fetchSummary(videoId, startSeconds) {
  const cacheKey = `${videoId}:${startSeconds}:${query}`;
  if (summaryCache.has(cacheKey)) {
    return summaryCache.get(cacheKey);
  }

  const response = await fetch("/api/summarize-context", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      video_id: videoId,
      start_seconds: startSeconds,
      query,
      window_before: 30,
      window_after: 30
    })
  });

  const text = await response.text();
  let data = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    throw new Error("Invalid summarize response.");
  }

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Failed to summarize context.");
  }

  summaryCache.set(cacheKey, data);
  return data;
}

async function saveMoment(payload) {
  const response = await fetch("/api/archive/moments", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const text = await response.text();
  let data = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    throw new Error("Invalid archive response.");
  }

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Failed to save moment.");
  }

  return data;
}

async function saveVideo(payload) {
  const response = await fetch("/api/archive/videos", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const text = await response.text();
  let data = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    throw new Error("Invalid archive response.");
  }

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Failed to save video.");
  }

  return data;
}

function formatTime(seconds) {
  const s = Math.floor(seconds || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;

  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function goToPage(page) {
  const next = Math.max(1, page);
  const nextParams = new URLSearchParams();
  nextParams.set("q", query);
  nextParams.set("page", String(next));

  if (exact) {
    nextParams.set("exact", "1");
  }

  window.location.href = `/results?${nextParams.toString()}`;
}

function buildPageItems(page, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const items = new Set([1, totalPages]);

  for (let i = page - 2; i <= page + 2; i++) {
    if (i >= 1 && i <= totalPages) items.add(i);
  }

  if (page <= 4) {
    [2, 3, 4, 5].forEach((n) => items.add(n));
  }

  if (page >= totalPages - 3) {
    [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1].forEach((n) => {
      if (n >= 1) items.add(n);
    });
  }

  const sorted = [...items].sort((a, b) => a - b);
  const result = [];

  for (let i = 0; i < sorted.length; i++) {
    result.push(sorted[i]);
    if (i < sorted.length - 1 && sorted[i + 1] - sorted[i] > 1) {
      result.push("...");
    }
  }

  return result;
}

function renderPagination(targetEl, page, totalPages) {
  if (!targetEl) return;

  targetEl.innerHTML = "";

  if (!totalPages || totalPages <= 1) return;

  const prev = document.createElement("button");
  prev.className = "page-btn";
  prev.textContent = "Prev";
  prev.disabled = page <= 1;
  prev.addEventListener("click", () => goToPage(page - 1));
  targetEl.appendChild(prev);

  const items = buildPageItems(page, totalPages);

  items.forEach((item) => {
    if (item === "...") {
      const ellipsis = document.createElement("span");
      ellipsis.className = "page-ellipsis";
      ellipsis.textContent = "...";
      targetEl.appendChild(ellipsis);
      return;
    }

    const btn = document.createElement("button");
    btn.className = "page-btn";
    if (item === page) btn.classList.add("active");
    btn.textContent = String(item);
    btn.addEventListener("click", () => goToPage(item));
    targetEl.appendChild(btn);
  });

  const next = document.createElement("button");
  next.className = "page-btn";
  next.textContent = "Next";
  next.disabled = page >= totalPages;
  next.addEventListener("click", () => goToPage(page + 1));
  targetEl.appendChild(next);
}

function buildThumbnail(videoId) {
  return `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
}

const ytPlayers = new Map();
let ytReady = false;
const pendingInitialisers = [];
let activeCardId = null;

window.onYouTubeIframeAPIReady = function () {
  ytReady = true;
  while (pendingInitialisers.length) {
    const fn = pendingInitialisers.shift();
    fn();
  }
};

function whenYouTubeReady(fn) {
  if (ytReady && window.YT && window.YT.Player) {
    fn();
  } else {
    pendingInitialisers.push(fn);
  }
}

function getEntry(cardId) {
  return ytPlayers.get(cardId);
}

function setState(cardId, text) {
  const entry = getEntry(cardId);
  if (entry?.stateEl) entry.stateEl.textContent = text;
}

function showPlayer(cardId) {
  const entry = getEntry(cardId);
  if (!entry) return;
  entry.playerShell.classList.add("active");
  entry.thumb.style.opacity = "0";
}

function showCover(cardId) {
  const entry = getEntry(cardId);
  if (!entry) return;
  entry.playerShell.classList.remove("active");
  entry.thumb.style.opacity = "1";
}

function setCardActive(cardId, active) {
  const entry = getEntry(cardId);
  if (!entry?.articleEl) return;
  entry.articleEl.classList.toggle("is-active", active);
}

function deactivateCard(cardId) {
  const entry = getEntry(cardId);
  if (!entry) return;

  try {
    entry.player?.pauseVideo();
  } catch (_) {}

  showCover(cardId);
  entry.isPlaying = false;
  setState(cardId, "Hover to play");
  setCardActive(cardId, false);

  if (activeCardId === cardId) {
    activeCardId = null;
  }
}

function stopAndHideOthers(exceptCardId) {
  for (const [cardId] of ytPlayers.entries()) {
    if (cardId === exceptCardId) continue;
    deactivateCard(cardId);
  }
}

function ensurePlayer(cardId, mountId, videoId, startSeconds, stateEl, playerShell, thumb, articleEl) {
  return new Promise((resolve) => {
    const existing = getEntry(cardId);
    if (existing?.player) {
      resolve(existing.player);
      return;
    }

    whenYouTubeReady(() => {
      const entry = {
        player: null,
        stateEl,
        playerShell,
        thumb,
        articleEl,
        startSeconds,
        currentClusterStart: startSeconds,
        lastSeekStart: startSeconds,
        hasStarted: false,
        isPlaying: false
      };

      const player = new YT.Player(mountId, {
        videoId,
        playerVars: {
          autoplay: 0,
          controls: 1,
          rel: 0,
          playsinline: 1,
          modestbranding: 1,
          enablejsapi: 1
        },
        events: {
          onReady: (event) => {
            entry.player = event.target;
            ytPlayers.set(cardId, entry);
            resolve(event.target);
          },
          onStateChange: (event) => {
            const YTState = window.YT.PlayerState;
            if (event.data === YTState.PLAYING) {
              entry.isPlaying = true;
              stateEl.textContent = "Playing";
              setCardActive(cardId, true);
            } else if (event.data === YTState.PAUSED) {
              entry.isPlaying = false;
              stateEl.textContent = "Paused";
            } else if (event.data === YTState.ENDED) {
              entry.isPlaying = false;
              stateEl.textContent = "Ended";
            } else if (event.data === YTState.BUFFERING) {
              stateEl.textContent = "Loading";
            }
          }
        }
      });

      entry.player = player;
      ytPlayers.set(cardId, entry);
    });
  });
}

function createClusterChip(group, cluster, onActivate) {
  const chip = document.createElement("div");
  chip.className = "cluster-chip";

  const row = document.createElement("div");
  row.className = "cluster-row";

  const time = document.createElement("div");
  time.className = "cluster-time";
  time.textContent = formatTime(cluster.start_seconds);

  const main = document.createElement("div");
  main.className = "cluster-main";

  const text = document.createElement("div");
  text.className = "cluster-text";
  text.innerHTML = highlightText(cluster.preview_text, query);

  const subhits = document.createElement("div");
  subhits.className = "cluster-subhits";
  subhits.textContent = `${cluster.hits.length} matched line${cluster.hits.length > 1 ? "s" : ""}`;

  const actions = document.createElement("div");
  actions.className = "cluster-actions";

  const summarizeBtn = document.createElement("button");
  summarizeBtn.type = "button";
  summarizeBtn.className = "cluster-action-btn";
  summarizeBtn.textContent = "Summarize";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "cluster-action-btn";
  saveBtn.textContent = isMomentSaved(cluster.video_id, cluster.start_seconds, query) ? "Saved" : "Save";
  if (isMomentSaved(cluster.video_id, cluster.start_seconds, query)) {
    saveBtn.disabled = true;
  }

  const summaryBox = document.createElement("div");
  summaryBox.className = "cluster-summary";

  main.append(text, subhits, actions, summaryBox);
  actions.append(summarizeBtn, saveBtn);
  row.append(time, main);
  chip.appendChild(row);

  chip.addEventListener("click", () => onActivate(cluster, chip, true));

  let summaryOpen = false;

  summarizeBtn.addEventListener("click", async (event) => {
    event.stopPropagation();

    if (summaryOpen) {
      summaryOpen = false;
      summaryBox.classList.remove("active");
      summarizeBtn.textContent = "Summarize";
      return;
    }

    summarizeBtn.disabled = true;
    summarizeBtn.classList.add("is-loading");
    summarizeBtn.textContent = "Loading...";

    try {
      const data = await fetchSummary(cluster.video_id, cluster.start_seconds);
      summaryBox.textContent = data.summary || "No summary is available for this context.";
      summaryBox.classList.add("active");
      summaryOpen = true;
      summarizeBtn.textContent = "Hide summary";
    } catch (error) {
      summaryBox.textContent = error.message || "Failed to summarize context.";
      summaryBox.classList.add("active");
      summaryOpen = true;
      summarizeBtn.textContent = "Hide summary";
      console.error(error);
    } finally {
      summarizeBtn.disabled = false;
      summarizeBtn.classList.remove("is-loading");
    }
  });

  saveBtn.addEventListener("click", async (event) => {
    event.stopPropagation();

    if (isMomentSaved(cluster.video_id, cluster.start_seconds, query)) return;

    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";

    try {
      await saveMoment({
        video_id: cluster.video_id,
        title: group.title,
        channel: group.channel || "",
        query,
        start_seconds: Math.floor(cluster.start_seconds || 0),
        end_seconds: Math.floor(cluster.end || cluster.start_seconds || 0),
        display_text: cluster.display_text || cluster.long_preview_text || cluster.preview_text || "",
        watch_url: cluster.watch_url || group.webpage_url || `https://www.youtube.com/watch?v=${cluster.video_id}&t=${Math.floor(cluster.start_seconds || 0)}s`
      });

      savedMoments.add(buildMomentKey(cluster.video_id, cluster.start_seconds, query));
      saveBtn.textContent = "Saved";
      saveBtn.disabled = true;
    } catch (error) {
      console.error(error);
      saveBtn.disabled = false;
      saveBtn.textContent = "Save";
      showMessage(error.message || "Failed to save moment.");
    }
  });

  return chip;
}

function createVideoCard(group, index) {
  const firstCluster = group.clusters[0];
  const cardId = `video-card-${index}-${group.video_id}`;
  const mountId = `player-${index}-${group.video_id}`;

  const article = document.createElement("article");
  article.className = "video-card";

  const preview = document.createElement("div");
  preview.className = "video-preview";

  const thumb = document.createElement("img");
  thumb.className = "video-thumb";
  thumb.src = buildThumbnail(group.video_id);
  thumb.alt = group.title;

  const playerShell = document.createElement("div");
  playerShell.className = "player-shell";

  const playerMount = document.createElement("div");
  playerMount.id = mountId;
  playerMount.className = "player-frame";

  playerShell.appendChild(playerMount);

  const overlay = document.createElement("div");
  overlay.className = "preview-overlay";

  const previewLeft = document.createElement("div");
  previewLeft.className = "preview-left";

  const timeBadge = document.createElement("div");
  timeBadge.className = "preview-time";
  timeBadge.textContent = formatTime(firstCluster.start_seconds);

  const clusterBadge = document.createElement("div");
  clusterBadge.className = "preview-pill";
  clusterBadge.textContent = `${group.cluster_count} clusters`;

  previewLeft.append(timeBadge, clusterBadge);

  const stateBadge = document.createElement("div");
  stateBadge.className = "preview-state";
  stateBadge.textContent = "Hover to play";

  overlay.append(previewLeft, stateBadge);
  preview.append(thumb, playerShell, overlay);

  let currentCluster = firstCluster;

  function markActiveChip(activeChip) {
    article.querySelectorAll(".cluster-chip").forEach((el) => el.classList.remove("active"));
    if (activeChip) activeChip.classList.add("active");
  }

  async function playCluster(cluster, activeChip = null, forceSeek = false) {
    currentCluster = cluster;
    timeBadge.textContent = formatTime(cluster.start_seconds);
    markActiveChip(activeChip);

    stopAndHideOthers(cardId);

    const player = await ensurePlayer(
      cardId,
      mountId,
      cluster.video_id,
      cluster.start_seconds,
      stateBadge,
      playerShell,
      thumb,
      article
    );

    const entry = getEntry(cardId);
    if (!entry) return;

    showPlayer(cardId);
    activeCardId = cardId;
    setCardActive(cardId, true);

    const firstTime = !entry.hasStarted;
    const clusterChanged = entry.currentClusterStart !== cluster.start_seconds;
    const shouldSeek = forceSeek || firstTime || clusterChanged;

    try {
      if (shouldSeek) {
        player.seekTo(cluster.start_seconds, true);
        entry.currentClusterStart = cluster.start_seconds;
        entry.lastSeekStart = cluster.start_seconds;
      }

      try {
        player.unMute();
      } catch (_) {}

      player.playVideo();
      entry.hasStarted = true;
      entry.isPlaying = true;
      stateBadge.textContent = "Playing";
    } catch (_) {}
  }

  preview.addEventListener("mouseenter", async () => {
    const entry = getEntry(cardId);

    if (activeCardId === cardId && entry?.player) {
      showPlayer(cardId);
      return;
    }

    await playCluster(
      currentCluster,
      article.querySelector(".cluster-chip.active") || article.querySelector(".cluster-chip"),
      false
    );
  });

  preview.addEventListener("click", async () => {
    const entry = getEntry(cardId);

    if (!entry?.player) {
      await playCluster(
        currentCluster,
        article.querySelector(".cluster-chip.active") || article.querySelector(".cluster-chip"),
        false
      );
      return;
    }

    try {
      const state = entry.player.getPlayerState();
      if (state === window.YT.PlayerState.PLAYING) {
        entry.player.pauseVideo();
        entry.isPlaying = false;
        stateBadge.textContent = "Paused";
      } else {
        stopAndHideOthers(cardId);
        showPlayer(cardId);
        entry.player.unMute();
        entry.player.playVideo();
        entry.isPlaying = true;
        activeCardId = cardId;
        stateBadge.textContent = "Playing";
      }
    } catch (_) {}
  });

  const body = document.createElement("div");
  body.className = "video-body";

  const title = document.createElement("h2");
  title.className = "video-title";

  const titleLink = document.createElement("a");
  const detailParams = new URLSearchParams();
  detailParams.set("q", query);
  detailParams.set("sort", "timeline");
  detailParams.set("page", String(currentPage));

  if (exact) {
    detailParams.set("exact", "1");
  }

  titleLink.href = `/video/${group.video_id}?${detailParams.toString()}`;
  titleLink.target = "_self";
  titleLink.innerHTML = highlightText(group.title, query);
  title.appendChild(titleLink);

  const metaRow = document.createElement("div");
  metaRow.className = "video-meta-row";

  const channel = document.createElement("div");
  channel.className = "video-channel";
  channel.textContent = group.channel || "Unknown channel";

  const stats = document.createElement("div");
  stats.className = "video-stats";

  const hitsPill = document.createElement("div");
  hitsPill.className = "video-pill";
  hitsPill.textContent = `${group.hit_count} hits`;

  const saveVideoBtn = document.createElement("button");
  saveVideoBtn.type = "button";
  saveVideoBtn.className = "results-save-video-btn";
  saveVideoBtn.textContent = isVideoSaved(group.video_id) ? "Saved" : "Save video";
  if (isVideoSaved(group.video_id)) {
    saveVideoBtn.disabled = true;
  }

  stats.append(hitsPill, saveVideoBtn);
  metaRow.append(channel, stats);

  const clusterList = document.createElement("div");
  clusterList.className = "cluster-list";

  group.clusters.slice(0, 3).forEach((cluster, idx) => {
    const chip = createClusterChip(group, cluster, playCluster);
    if (idx === 0) chip.classList.add("active");
    clusterList.appendChild(chip);
  });

  saveVideoBtn.addEventListener("click", async (event) => {
    event.stopPropagation();

    if (isVideoSaved(group.video_id)) return;

    saveVideoBtn.disabled = true;
    saveVideoBtn.textContent = "Saving...";

    try {
      await saveVideo({
        video_id: group.video_id,
        title: group.title || "",
        channel: group.channel || "",
        query,
        display_text: group.title || "",
        watch_url: group.webpage_url || `https://www.youtube.com/watch?v=${group.video_id}`
      });

      savedVideos.add(group.video_id);
      saveVideoBtn.textContent = "Saved";
      saveVideoBtn.disabled = true;
    } catch (error) {
      console.error(error);
      saveVideoBtn.disabled = false;
      saveVideoBtn.textContent = "Save video";
      showMessage(error.message || "Failed to save video.");
    }
  });

  body.append(title, metaRow, clusterList);
  article.append(preview, body);

  return article;
}

async function loadResults() {
  try {
    if (!resultsTitle || !resultsMeta || !resultsGrid || !messageBox) {
      console.error("Results page DOM elements are missing.");
      return;
    }

    if (!query.trim()) {
      resultsTitle.textContent = "No query";
      showMessage("Please enter a search query.");
      return;
    }

    resultsTitle.textContent = `Results for “${query}”`;
    resultsMeta.textContent = "Loading...";
    hideMessage();
    resultsGrid.innerHTML = "";
    if (paginationTop) paginationTop.innerHTML = "";
    if (pagination) pagination.innerHTML = "";

    await loadSavedState();

    const searchParams = new URLSearchParams();
    searchParams.set("q", query);
    searchParams.set("page", String(currentPage));
    searchParams.set("per_page", String(perPage));

    if (exact) {
      searchParams.set("exact", "1");
    }

    const response = await fetch(`/api/search?${searchParams.toString()}`);

    const text = await response.text();
    let data = null;

    try {
      data = text ? JSON.parse(text) : null;
    } catch (error) {
      console.error("Failed to parse /api/search response:", text);
      throw new Error("Invalid search response.");
    }

    if (!response.ok) {
      throw new Error(data?.detail || data?.message || "Search request failed.");
    }

    resultsMeta.textContent =
      `${data.total_hits} raw hits • ${data.total_videos} videos • Page ${data.page} of ${data.total_pages || 1}`;

    const responseMessage = String(data.message || "").trim();
    if (responseMessage && responseMessage.toLowerCase() !== "ok") {
      showMessage(responseMessage);
    } else {
      hideMessage();
    }

    if (!data.groups.length) {
      const empty = document.createElement("div");
      empty.className = "empty-card";
      empty.innerHTML = `
        <h2 style="margin:0 0 10px; font-size:24px;">No matching subtitle moments found</h2>
        <div style="color: var(--muted);">Try a longer phrase or a more specific query.</div>
      `;
      resultsGrid.appendChild(empty);
      return;
    }

    data.groups.forEach((group, index) => {
      resultsGrid.appendChild(createVideoCard(group, index));
    });

    renderPagination(paginationTop, data.page, data.total_pages);
    renderPagination(pagination, data.page, data.total_pages);
  } catch (error) {
    console.error("loadResults failed:", error);
    if (resultsTitle) resultsTitle.textContent = "Search error";
    if (resultsMeta) resultsMeta.textContent = "";
    if (messageBox) showMessage(error.message || "Something went wrong while loading results.");
  }
}

loadResults();