const videoId = window.__VIDEO_ID__;
const params = new URLSearchParams(window.location.search);
const query = params.get("q") || "";
const sortMode = params.get("sort") || "timeline";
const page = params.get("page") || "1";
const exact = params.get("exact") === "1";

const titleEl = document.getElementById("video-detail-title");
const metaEl = document.getElementById("video-detail-meta");
const infoEl = document.getElementById("video-info");
const clustersEl = document.getElementById("video-clusters");
const clusterCountLabel = document.getElementById("cluster-count-label");
const playerTimeLabel = document.getElementById("player-time-label");
const playerCardEl = document.getElementById("detail-player-card");
const playerShellEl = document.getElementById("player-shell");
const backToResultsEl = document.getElementById("back-to-results-sticky");
const resultsReturnTextEl = document.getElementById("results-return-text");
const sortTimelineBtn = document.getElementById("sort-timeline");
const sortBestBtn = document.getElementById("sort-best");

const summaryCache = new Map();

let ytPlayer = null;
let ytApiPromise = null;
let miniPlayerEnabled = false;
let playerPlaceholderEl = null;
let scrollStopTimer = null;

function escapeHtml(value) {
  return String(value ?? "")
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

function normalizePreviewLine(text) {
  return String(text ?? "")
    .replace(/\s+/g, " ")
    .replace(/\s+\|+\s*/g, " ")
    .trim();
}

function buildDetailPreview(cluster, maxLines = 5) {
  const hits = Array.isArray(cluster?.hits) ? cluster.hits : [];
  const lines = [];
  const seen = new Set();

  for (const hit of hits) {
    const text = normalizePreviewLine(hit?.text);
    if (!text) continue;
    if (seen.has(text)) continue;

    seen.add(text);
    lines.push(text);

    if (lines.length >= maxLines) break;
  }

  if (lines.length > 0) {
    return lines.join(" ");
  }

  return normalizePreviewLine(cluster?.preview_text || "");
}

function buildResultsUrl() {
  const nextParams = new URLSearchParams();
  nextParams.set("q", query);
  nextParams.set("page", page);

  if (exact) {
    nextParams.set("exact", "1");
  }

  return `/results?${nextParams.toString()}`;
}

function ensurePlayerPlaceholder() {
  if (!playerCardEl) return;

  if (!playerPlaceholderEl) {
    playerPlaceholderEl = document.createElement("div");
    playerPlaceholderEl.className = "detail-player-placeholder";
    playerCardEl.parentNode.insertBefore(playerPlaceholderEl, playerCardEl.nextSibling);
  }

  const rect = playerCardEl.getBoundingClientRect();
  const computed = window.getComputedStyle(playerCardEl);
  const height = playerCardEl.offsetHeight;

  playerPlaceholderEl.style.height = `${height}px`;
  playerPlaceholderEl.style.margin = computed.margin;
}

function setMiniPlayer(enabled) {
  if (!playerCardEl) return;
  if (miniPlayerEnabled === enabled) return;

  miniPlayerEnabled = enabled;

  if (enabled) {
    ensurePlayerPlaceholder();
    playerPlaceholderEl?.classList.add("active");
    playerCardEl.classList.add("is-mini-player");
  } else {
    playerCardEl.classList.remove("is-mini-player");
    playerPlaceholderEl?.classList.remove("active");
  }
}

function updateMiniPlayerState() {
  if (!playerCardEl) return;

  const rect = playerCardEl.getBoundingClientRect();

  const shouldMini =
    rect.top < -180 &&
    window.innerWidth > 640;

  setMiniPlayer(shouldMini);
}

function bindMiniPlayerEvents() {
  window.addEventListener("scroll", updateMiniPlayerState, { passive: true });
  window.addEventListener("resize", () => {
    if (miniPlayerEnabled) {
      ensurePlayerPlaceholder();
    }
    updateMiniPlayerState();
  });

  updateMiniPlayerState();
}

function goToSort(sort) {
  const nextParams = new URLSearchParams();
  nextParams.set("q", query);
  nextParams.set("sort", sort);
  nextParams.set("page", page);

  if (exact) {
    nextParams.set("exact", "1");
  }

  window.location.href = `/video/${videoId}?${nextParams.toString()}`;
}

function createBadge(label, neutral = false) {
  return `<div class="cluster-badge${neutral ? " neutral" : ""}">${escapeHtml(label)}</div>`;
}

function ensureYouTubeApi() {
  if (window.YT && window.YT.Player) {
    return Promise.resolve();
  }

  if (ytApiPromise) {
    return ytApiPromise;
  }

  ytApiPromise = new Promise((resolve) => {
    const prevReady = window.onYouTubeIframeAPIReady;

    window.onYouTubeIframeAPIReady = () => {
      if (typeof prevReady === "function") {
        prevReady();
      }
      resolve();
    };

    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);
  });

  return ytApiPromise;
}

async function initPlayer(startSeconds) {
  await ensureYouTubeApi();

  ytPlayer = new window.YT.Player("detail-player", {
    videoId,
    playerVars: {
      autoplay: 1,
      controls: 1,
      rel: 0,
      playsinline: 1,
      start: Math.max(0, Math.floor(startSeconds || 0))
    }
  });
}

function activateCluster(index, cluster) {
  document.querySelectorAll(".cluster-card").forEach((card, i) => {
    card.classList.toggle("is-active", i === index);
  });

  if (ytPlayer && typeof ytPlayer.seekTo === "function") {
    try {
      ytPlayer.seekTo(cluster.start_seconds, true);
      if (typeof ytPlayer.playVideo === "function") {
        ytPlayer.playVideo();
      }
    } catch (error) {
      console.error(error);
    }
  }

  if (playerTimeLabel) {
    playerTimeLabel.textContent = `Jumped to ${formatTime(cluster.start_seconds)}`;
  }
}

async function fetchSummary(startSeconds) {
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

function createClusterCard(cluster, index) {
  const article = document.createElement("article");
  article.className = "cluster-card";
  if (index === 0) article.classList.add("is-active");

  const badges = [];

  if (cluster.phrase_match) {
    badges.push(createBadge("Exact phrase"));
  }
  if ((cluster.proximity_boost || 0) > 0) {
    badges.push(createBadge("Near match"));
  }

  badges.push(createBadge(`${cluster.hits.length} hits`, true));

  article.innerHTML = `
    <div class="cluster-top">
      <div class="cluster-time-range">
        ${formatTime(cluster.start)} → ${formatTime(cluster.end)}
      </div>
      <div class="cluster-badges">
        ${badges.join("")}
      </div>
    </div>

    <div class="cluster-body">
      <div class="cluster-row">
        <button type="button" class="cluster-time-link">
          ${formatTime(cluster.start_seconds)}
        </button>

        <div class="cluster-main">
          <div class="cluster-preview">${highlightText(cluster.long_preview_text || cluster.preview_text, query)}</div>
          <div class="cluster-subtext">
            ${cluster.hits.length} matched line${cluster.hits.length > 1 ? "s" : ""}
          </div>
          <div class="cluster-actions">
            <button type="button" class="cluster-action-btn summarize-btn">Summarize</button>
          </div>
          <div class="cluster-summary"></div>
        </div>
      </div>
    </div>
  `;

  const jumpBtn = article.querySelector(".cluster-time-link");
  const summarizeBtn = article.querySelector(".summarize-btn");
  const summaryBox = article.querySelector(".cluster-summary");

  jumpBtn?.addEventListener("click", () => activateCluster(index, cluster));

  let summaryOpen = false;

  summarizeBtn?.addEventListener("click", async () => {
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
      const data = await fetchSummary(cluster.start_seconds);
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

  return article;
}

async function loadVideoDetail() {
  if (!query) {
    titleEl.textContent = "Missing query";
    metaEl.textContent = "";
    return;
  }

  if (backToResultsEl) {
  backToResultsEl.href = buildResultsUrl();
}

if (resultsReturnTextEl) {
  resultsReturnTextEl.textContent = query
    ? `Return to results for “${query}”`
    : "Return to search results";
}

  sortTimelineBtn?.classList.toggle("active", sortMode === "timeline");
  sortBestBtn?.classList.toggle("active", sortMode === "best");

  sortTimelineBtn?.addEventListener("click", () => goToSort("timeline"));
  sortBestBtn?.addEventListener("click", () => goToSort("best"));

  const apiParams = new URLSearchParams();
  apiParams.set("q", query);
  apiParams.set("sort", sortMode);

  const response = await fetch(`/api/videos/${videoId}?${apiParams.toString()}`);
  const data = await response.json();

  titleEl.textContent = data.title || "Video detail";
  metaEl.textContent = `${data.hit_count} hits • ${sortMode === "timeline" ? "Timeline order" : "Best match order"} • Query: "${data.query}"`;

  clusterCountLabel.textContent = `${data.clusters.length} clusters`;
  playerTimeLabel.textContent = data.clusters.length
    ? `Starts at ${formatTime(data.clusters[0].start_seconds)}`
    : "No matching moments";

  infoEl.innerHTML = `
    <h2 class="video-info-title">${escapeHtml(data.title || "")}</h2>
    <div class="video-info-sub">
      Channel: ${escapeHtml(data.channel || "Unknown")} ·
      Uploader: ${escapeHtml(data.uploader || "Unknown")}
    </div>

    <div class="video-stat-list">
      <div class="video-stat-pill">Duration: ${formatTime(data.duration || 0)}</div>
      <div class="video-stat-pill">Subtitle type: ${escapeHtml(data.selected_subtitle_type || "unknown")}</div>
      <div class="video-stat-pill">Subtitle lang: ${escapeHtml(data.selected_subtitle_lang || "unknown")}</div>
      <div class="video-stat-pill">Query: ${escapeHtml(data.query || "")}</div>
    </div>

    <a class="video-link-btn" href="${data.webpage_url}" target="_blank" rel="noreferrer">
      Open on YouTube
    </a>
  `;

  clustersEl.innerHTML = "";

  if (!data.clusters.length) {
    clustersEl.innerHTML = `<div class="empty-card">No hits found for this video and query.</div>`;
    return;
  }

  await initPlayer(data.clusters[0].start_seconds);
  bindMiniPlayerEvents();

  data.clusters.forEach((cluster, index) => {
    clustersEl.appendChild(createClusterCard(cluster, index));
  });
}

loadVideoDetail().catch((error) => {
  console.error(error);
  titleEl.textContent = "Failed to load video detail";
  metaEl.textContent = "";
  if (clustersEl) {
    clustersEl.innerHTML = `<div class="empty-card">Something went wrong while loading this page.</div>`;
  }
});