const archiveGrid = document.getElementById("archive-grid");
const archiveCount = document.getElementById("archive-count");
const tabMoments = document.getElementById("archive-tab-moments");
const tabVideos = document.getElementById("archive-tab-videos");

let allItems = [];
let activeType = "moment";

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTime(seconds) {
  const s = Math.floor(Number(seconds) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;

  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();

  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    throw new Error("Invalid server response.");
  }

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Request failed.");
  }

  return data;
}

function buildDetailUrl(item) {
  const params = new URLSearchParams();
  if (item.query) {
    params.set("q", item.query);
  }
  params.set("sort", "timeline");
  params.set("page", "1");
  return `/video/${item.video_id}?${params.toString()}`;
}

function buildFallbackWatchUrl(item) {
  if (item.watch_url) return item.watch_url;
  return buildDetailUrl(item);
}

function setActiveTab(type) {
  activeType = type;
  tabMoments?.classList.toggle("active", type === "moment");
  tabVideos?.classList.toggle("active", type === "video");
  renderArchive();
}

function getFilteredItems() {
  return allItems.filter((item) => (item.item_type || "moment") === activeType);
}

function renderEmpty(type = "moment") {
  const title = type === "video" ? "No saved videos yet." : "No saved moments yet.";
  const text =
    type === "video"
      ? "Save a whole video later to build your video archive."
      : "Save a moment from search results or video detail to build your archive.";

  archiveGrid.innerHTML = `
    <div class="archive-empty">
      <h2 class="archive-empty-title">${escapeHtml(title)}</h2>
      <p class="archive-empty-text">${escapeHtml(text)}</p>
    </div>
  `;
}

function renderLoadError(message = "Please try refreshing the page.") {
  archiveGrid.innerHTML = `
    <div class="archive-empty">
      <h2 class="archive-empty-title">Failed to load archive.</h2>
      <p class="archive-empty-text">${escapeHtml(message)}</p>
    </div>
  `;
}

function createMomentCard(item) {
  const article = document.createElement("article");
  article.className = "archive-card archive-card-moment";

  const detailUrl = buildDetailUrl(item);
  const watchUrl = buildFallbackWatchUrl(item);

  article.innerHTML = `
    <div class="archive-card-top">
      <span class="archive-time-pill">${formatTime(item.start_seconds)}</span>
      <span class="archive-type-pill">Moment</span>
    </div>

    <h2 class="archive-card-title">${escapeHtml(item.title || "Untitled video")}</h2>

    <p class="archive-card-text">
      ${escapeHtml(item.display_text || "No saved text available.")}
    </p>

    <div class="archive-card-meta">
      ${item.channel ? `<span class="archive-meta-pill">${escapeHtml(item.channel)}</span>` : ""}
      ${item.query ? `<span class="archive-meta-pill">${escapeHtml(item.query)}</span>` : ""}
      <span class="archive-meta-pill">${escapeHtml(formatDate(item.created_at))}</span>
    </div>

    <div class="archive-card-actions">
      <a class="archive-action-btn primary" href="${detailUrl}">Open detail</a>
      <a class="archive-action-btn" href="${watchUrl}">Open Youtube link</a>
      <button type="button" class="archive-action-btn danger remove-btn">Remove</button>
    </div>
  `;

  bindRemove(article, item.id);
  return article;
}

function createVideoCard(item) {
  const article = document.createElement("article");
  article.className = "archive-card archive-card-video";

  const detailUrl = buildDetailUrl(item);
  const watchUrl = buildFallbackWatchUrl(item);

  article.innerHTML = `
    <div class="archive-card-top">
      <span class="archive-video-label">Saved video</span>
      <span class="archive-type-pill neutral">Video</span>
    </div>

    <h2 class="archive-card-title">${escapeHtml(item.title || "Untitled video")}</h2>

    <p class="archive-card-text">
      ${escapeHtml(item.display_text || "Saved video item.")}
    </p>

    <div class="archive-card-meta">
      ${item.channel ? `<span class="archive-meta-pill">${escapeHtml(item.channel)}</span>` : ""}
      ${item.query ? `<span class="archive-meta-pill">${escapeHtml(item.query)}</span>` : ""}
      <span class="archive-meta-pill">${escapeHtml(formatDate(item.created_at))}</span>
    </div>

    <div class="archive-card-actions">
      <a class="archive-action-btn primary" href="${detailUrl}">Open detail</a>
      <a class="archive-action-btn" href="${watchUrl}">Open Youtube link</a>
      <button type="button" class="archive-action-btn danger remove-btn">Remove</button>
    </div>
  `;

  bindRemove(article, item.id);
  return article;
}

function bindRemove(article, itemId) {
  const removeBtn = article.querySelector(".remove-btn");

  removeBtn?.addEventListener("click", async () => {
    const confirmed = window.confirm("Remove this item from Archive?");
    if (!confirmed) return;

    removeBtn.disabled = true;
    removeBtn.textContent = "Removing...";

    try {
      await fetchJson(`/api/archive/${itemId}`, { method: "DELETE" });
      await loadArchive();
    } catch (error) {
      console.error(error);
      removeBtn.disabled = false;
      removeBtn.textContent = "Remove";
    }
  });
}

function renderArchive() {
  if (!archiveGrid || !archiveCount) return;

  archiveGrid.innerHTML = "";

  const items = getFilteredItems();
  const label = activeType === "video" ? "video" : "moment";
  archiveCount.textContent = `${items.length} saved ${label}${items.length === 1 ? "" : "s"}`;

  if (!items.length) {
    renderEmpty(activeType);
    return;
  }

  items.forEach((item) => {
    const type = item.item_type || "moment";
    if (type === "video") {
      archiveGrid.appendChild(createVideoCard(item));
    } else {
      archiveGrid.appendChild(createMomentCard(item));
    }
  });
}

async function loadArchive() {
  if (!archiveGrid || !archiveCount) return;

  archiveCount.textContent = "Loading...";
  archiveGrid.innerHTML = "";

  try {
    allItems = await fetchJson("/api/archive");
    renderArchive();
  } catch (error) {
    console.error(error);
    archiveCount.textContent = "Load failed";
    renderLoadError(error.message || "Please try refreshing the page.");
  }
}

tabMoments?.addEventListener("click", () => setActiveTab("moment"));
tabVideos?.addEventListener("click", () => setActiveTab("video"));

loadArchive();