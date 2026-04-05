const form = document.getElementById("library-form");
const sourceTypeInput = document.getElementById("source-type");
const sourceUrlInput = document.getElementById("source-url");
const sourceTitleInput = document.getElementById("source-title");
const messageBox = document.getElementById("library-message");
const libraryList = document.getElementById("library-list");
const libraryCount = document.getElementById("library-count");

function showMessage(message, type = "success") {
  messageBox.textContent = message;
  messageBox.className = `library-message ${type}`;
}

function hideMessage() {
  messageBox.textContent = "";
  messageBox.className = "library-message hidden";
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDate(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusClass(status) {
  const allowed = ["success", "failed", "pending", "no_subtitles"];
  return allowed.includes(status) ? status : "pending";
}

function renderEmpty(
  message = "No sources yet. Add a YouTube playlist or video URL to start building your Atlas library."
) {
  libraryList.innerHTML = `
    <div class="empty-library">
      ${escapeHtml(message)}
    </div>
  `;
}

function createStatusBadge(status) {
  const safe = status || "pending";
  return `<span class="library-status ${statusClass(safe)}">${escapeHtml(safe)}</span>`;
}

function formatSourceTypeLabel(sourceType) {
  if (sourceType === "video") return "video";
  if (sourceType === "playlist") return "playlist";
  if (sourceType === "channel") return "channel";
  return sourceType || "source";
}

function updateSourceInputHint() {
  if (!sourceTypeInput || !sourceUrlInput) return;

  const sourceType = sourceTypeInput.value;

  if (sourceType === "video") {
    sourceUrlInput.placeholder = "Paste a YouTube video URL";
    return;
  }

  if (sourceType === "channel") {
    sourceUrlInput.placeholder = "Paste a YouTube channel URL";
    return;
  }

  sourceUrlInput.placeholder = "Paste a YouTube playlist URL";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }

  return data;
}

async function loadRuns(sourceId, target) {
  target.innerHTML = `<div class="library-inline-message">Loading sync runs...</div>`;

  try {
    const runs = await fetchJson(`/api/sources/${sourceId}/sync-runs`);

    if (!runs.length) {
      target.innerHTML = `<div class="library-inline-message">No sync runs yet.</div>`;
      return;
    }

    target.innerHTML = `
      <div class="library-subsection">
        <h4 class="library-subsection-title">Sync runs</h4>
        <div class="library-grid">
          ${runs.map((run) => `
            <div class="library-mini-card">
              <div class="library-mini-top">
                <div class="library-mini-title">Run #${run.id}</div>
                ${createStatusBadge(run.status)}
              </div>

              <div class="library-mini-meta">
                Started: ${escapeHtml(formatDate(run.started_at))}<br>
                Finished: ${escapeHtml(formatDate(run.finished_at))}
              </div>

              <div class="library-mini-meta">
                Discovered: ${run.total_discovered}<br>
                New: ${run.new_videos}<br>
                Processed: ${run.processed}
              </div>

              <div class="library-mini-meta">
                Succeeded: ${run.succeeded}<br>
                Failed: ${run.failed}
              </div>

              ${run.error_summary ? `
                <div class="library-mini-error">
                  Error: ${escapeHtml(run.error_summary)}
                </div>
              ` : ""}
            </div>
          `).join("")}
        </div>
      </div>
    `;
  } catch (error) {
    target.innerHTML = `<div class="library-inline-message">Failed to load sync runs.</div>`;
    console.error(error);
  }
}

async function loadVideos(sourceId, target) {
  target.innerHTML = `<div class="library-inline-message">Loading videos...</div>`;

  try {
    const videos = await fetchJson(`/api/sources/${sourceId}/videos`);

    if (!videos.length) {
      target.innerHTML = `<div class="library-inline-message">No videos discovered yet.</div>`;
      return;
    }

    target.innerHTML = `
      <div class="library-subsection">
        <h4 class="library-subsection-title">Videos</h4>
        <div class="library-grid">
          ${videos.slice(0, 24).map((video) => `
            <div class="library-mini-card">
              <div class="library-mini-top">
                <div class="library-mini-title">${escapeHtml(video.video_id)}</div>
                ${createStatusBadge(video.sync_status)}
              </div>

              <div class="library-mini-meta">
                Position: ${video.position ?? "-"}<br>
                Available: ${video.is_available ? "yes" : "no"}
              </div>

              <div class="library-mini-meta">
                Discovered: ${escapeHtml(formatDate(video.discovered_at))}<br>
                Last seen: ${escapeHtml(formatDate(video.last_seen_at))}
              </div>

              ${video.last_error ? `
                <div class="library-mini-error">
                  Error: ${escapeHtml(video.last_error)}
                </div>
              ` : ""}
            </div>
          `).join("")}
        </div>

        ${videos.length > 24 ? `
          <div class="library-inline-message">
            Showing first 24 of ${videos.length} videos.
          </div>
        ` : ""}
      </div>
    `;
  } catch (error) {
    target.innerHTML = `<div class="library-inline-message">Failed to load videos.</div>`;
    console.error(error);
  }
}

function createSourceCard(source) {
  const card = document.createElement("article");
  card.className = "library-card";

  const title = source.title || source.source_key;

  const body = document.createElement("div");
  body.className = "library-card-body";

  const actions = document.createElement("div");
  actions.className = "library-card-actions";

  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "library-action-btn";
  renameBtn.textContent = "Rename";

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "library-action-btn";
  toggleBtn.textContent = source.is_active ? "Disable" : "Enable";

  const syncBtn = document.createElement("button");
  syncBtn.type = "button";
  syncBtn.className = "library-action-btn primary";
  syncBtn.textContent = "Sync now";

  const runsBtn = document.createElement("button");
  runsBtn.type = "button";
  runsBtn.className = "library-action-btn";
  runsBtn.textContent = "Show runs";

  const videosBtn = document.createElement("button");
  videosBtn.type = "button";
  videosBtn.className = "library-action-btn";
  videosBtn.textContent = "Show videos";

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "library-action-btn";
  deleteBtn.textContent = "Delete";

  actions.append(renameBtn, toggleBtn, syncBtn, runsBtn, videosBtn, deleteBtn);

  card.innerHTML = `
    <div class="library-card-top">
      <div>
        <h3 class="library-card-title">${escapeHtml(title)}</h3>
        <div class="library-card-subtitle">${escapeHtml(source.source_url)}</div>
      </div>

      <div class="library-card-top-pills">
        <div class="library-state-pill ${source.is_active ? "enabled" : "disabled"}">
          ${source.is_active ? "Enable" : "Disable"}
        </div>
        <div class="library-pill">${escapeHtml(formatSourceTypeLabel(source.source_type))}</div>
      </div>
    </div>

    <div class="library-card-meta">
      <div class="library-pill">Videos: ${source.video_count ?? 0}</div>
      <div class="library-pill">Available: ${source.available_video_count ?? 0}</div>
      <div class="library-pill">Runs: ${source.sync_run_count ?? 0}</div>
      <div class="library-pill">Created: ${escapeHtml(formatDate(source.created_at))}</div>
      <div class="library-pill">Last sync: ${escapeHtml(formatDate(source.last_synced_at))}</div>
    </div>
  `;

  card.append(actions, body);

  renameBtn.addEventListener("click", async () => {
    const nextTitle = window.prompt("Rename this source:", source.title || source.source_key || "");
    if (nextTitle === null) return;

    const trimmed = nextTitle.trim();
    hideMessage();
    renameBtn.disabled = true;
    renameBtn.textContent = "Saving...";

    try {
      await fetchJson(`/api/sources/${source.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed || null })
      });

      showMessage("Source title updated.");
      await loadSources();
    } catch (error) {
      showMessage(error.message || "Failed to rename source.", "error");
      console.error(error);
    } finally {
      renameBtn.disabled = false;
      renameBtn.textContent = "Rename";
    }
  });

  toggleBtn.addEventListener("click", async () => {
    hideMessage();
    toggleBtn.disabled = true;
    toggleBtn.textContent = source.is_active ? "Disabling..." : "Enabling...";

    try {
      await fetchJson(`/api/sources/${source.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !source.is_active })
      });

      showMessage(source.is_active ? "Source disabled." : "Source enabled.");
      await loadSources();
    } catch (error) {
      showMessage(error.message || "Failed to update source status.", "error");
      console.error(error);
    } finally {
      toggleBtn.disabled = false;
      toggleBtn.textContent = source.is_active ? "Disable" : "Enable";
    }
  });

  syncBtn.addEventListener("click", async () => {
    if (!source.is_active) {
      showMessage("This source is inactive. Enable it before syncing.", "error");
      return;
    }

    syncBtn.disabled = true;
    syncBtn.textContent = "Syncing...";
    hideMessage();

    try {
      const result = await fetchJson(`/api/sources/${source.id}/sync`, { method: "POST" });
      showMessage(
        `Sync completed. Discovered ${result.sync_run.total_discovered} videos, ${result.sync_run.new_videos} new.`,
        "success"
      );
      await loadSources();
    } catch (error) {
      showMessage(error.message || "Failed to sync source.", "error");
      console.error(error);
    } finally {
      syncBtn.disabled = false;
      syncBtn.textContent = "Sync now";
    }
  });

  let runsOpen = false;
  let videosOpen = false;

  runsBtn.addEventListener("click", async () => {
    runsOpen = !runsOpen;
    videosOpen = false;

    runsBtn.textContent = runsOpen ? "Hide runs" : "Show runs";
    videosBtn.textContent = "Show videos";
    body.classList.toggle("active", runsOpen);

    if (!runsOpen) return;
    await loadRuns(source.id, body);
  });

  videosBtn.addEventListener("click", async () => {
    videosOpen = !videosOpen;
    runsOpen = false;

    videosBtn.textContent = videosOpen ? "Hide videos" : "Show videos";
    runsBtn.textContent = "Show runs";
    body.classList.toggle("active", videosOpen);

    if (!videosOpen) return;
    await loadVideos(source.id, body);
  });

  deleteBtn.addEventListener("click", async () => {
    const confirmed = window.confirm(
      "Delete this source from Library?\n\nThis will also remove related saved moments and videos from Archive."
    );
    if (!confirmed) return;

    deleteBtn.disabled = true;
    deleteBtn.textContent = "Deleting...";
    hideMessage();

    try {
      await fetchJson(`/api/sources/${source.id}`, { method: "DELETE" });
      showMessage("Source deleted from Library.");
      await loadSources();
    } catch (error) {
      showMessage(error.message || "Failed to delete source.", "error");
      console.error(error);
    } finally {
      deleteBtn.disabled = false;
      deleteBtn.textContent = "Delete";
    }
  });

  return card;
}

async function loadSources() {
  libraryCount.textContent = "Loading...";
  libraryList.innerHTML = "";

  try {
    const sources = await fetchJson("/api/sources");
    libraryCount.textContent = `${sources.length} source${sources.length === 1 ? "" : "s"}`;

    if (!sources.length) {
      renderEmpty();
      return;
    }

    const detailedSources = await Promise.all(
      sources.map((source) => fetchJson(`/api/sources/${source.id}`))
    );

    detailedSources.forEach((source) => {
      libraryList.appendChild(createSourceCard(source));
    });
  } catch (error) {
    libraryCount.textContent = "Load failed";
    showMessage("Failed to load library sources.", "error");
    console.error(error);
  }
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage();

  const payload = {
    source_type: sourceTypeInput.value,
    source_url: sourceUrlInput.value.trim(),
    title: sourceTitleInput.value.trim() || null
  };

  if (!payload.source_url) {
    showMessage("Please enter a YouTube URL.", "error");
    return;
  }

  try {
    const data = await fetchJson("/api/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    showMessage(`Source added: ${data.title || data.source_key}`);
    sourceUrlInput.value = "";
    sourceTitleInput.value = "";
    updateSourceInputHint();
    await loadSources();
  } catch (error) {
    showMessage(error.message || "Failed to add source.", "error");
    console.error(error);
  }
});

sourceTypeInput?.addEventListener("change", updateSourceInputHint);

updateSourceInputHint();
loadSources();