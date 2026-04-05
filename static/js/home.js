const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const exactToggle = document.getElementById("exact-search-toggle");
const chips = document.querySelectorAll(".hint-chip");

const sourceModeSelect = document.getElementById("home-source-mode");
const sourcePickerBtn = document.getElementById("home-source-picker-btn");

const sourceModal = document.getElementById("home-source-modal");
const sourceModalBackdrop = document.getElementById("home-source-modal-backdrop");
const sourceModalClose = document.getElementById("home-source-modal-close");
const sourceModalBody = document.getElementById("home-source-modal-body");
const sourceModalCount = document.getElementById("home-source-modal-count");
const sourceClearBtn = document.getElementById("home-source-clear-btn");
const sourceDoneBtn = document.getElementById("home-source-done-btn");

let allSources = [];
let selectedSourceIds = [];

function buildResultsUrl(query) {
  const q = String(query || "").trim();
  if (!q) return null;

  const params = new URLSearchParams();
  params.set("q", q);

  if (exactToggle?.checked) {
    params.set("exact", "1");
  }

  if (getSourceMode() === "selected") {
    params.set("source_mode", "selected");
    const joined = buildSourceIdsParam(selectedSourceIds);
    if (joined) {
      params.set("source_ids", joined);
    }
  }

  return `/results?${params.toString()}`;
}

function parseSourceIds(raw) {
  if (!raw) return [];
  const result = [];

  String(raw)
    .split(",")
    .map((item) => item.trim())
    .forEach((item) => {
      if (!/^\d+$/.test(item)) return;
      const value = Number(item);
      if (!result.includes(value)) result.push(value);
    });

  return result;
}

function buildSourceIdsParam(ids) {
  return ids
    .filter((value) => Number.isInteger(value) && value > 0)
    .join(",");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getSourceMode() {
  return sourceModeSelect?.value === "selected" ? "selected" : "all";
}

function getSelectedSourceLabel() {
  if (getSourceMode() !== "selected") return "Choose sources";
  if (!selectedSourceIds.length) return "Choose sources";

  const selected = allSources.filter((source) => selectedSourceIds.includes(Number(source.id)));
  if (selected.length === 0) return "Choose sources";
  if (selected.length === 1) return selected[0].title || selected[0].source_key || "1 source";
  return `${selected.length} sources selected`;
}

function getSelectedCountText() {
  const count = selectedSourceIds.length;
  return `${count} selected${count === 1 ? "" : ""}`;
}

function syncSourceFilterUi() {
  if (!sourcePickerBtn) return;

  const selectedMode = getSourceMode() === "selected";
  sourcePickerBtn.style.display = selectedMode ? "inline-flex" : "none";
  sourcePickerBtn.textContent = getSelectedSourceLabel();

  if (sourceModalCount) {
    sourceModalCount.textContent = getSelectedCountText();
  }

  if (!selectedMode) {
    closeSourceModal();
  }
}

function openSourceModal() {
  if (!sourceModal || getSourceMode() !== "selected") return;
  sourceModal.classList.remove("hidden");
  sourceModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("home-modal-open");
}

function closeSourceModal() {
  if (!sourceModal) return;
  sourceModal.classList.add("hidden");
  sourceModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("home-modal-open");
}

function renderSourceModalOptions() {
  if (!sourceModalBody) return;

  if (!allSources.length) {
    sourceModalBody.innerHTML = `
      <div class="home-source-empty-state">
        <div class="home-source-empty-title">No library sources yet</div>
        <div class="home-source-empty-text">
          Add a playlist or video in Library first, then come back to filter your homepage search.
        </div>
      </div>
    `;
    if (sourceModalCount) {
      sourceModalCount.textContent = "0 selected";
    }
    return;
  }

  sourceModalBody.innerHTML = `
    <div class="home-source-grid">
      ${allSources.map((source) => {
        const sourceId = Number(source.id);
        const checked = selectedSourceIds.includes(sourceId) ? "checked" : "";
        const sourceTitle = source.title || source.source_key || `Source ${source.id}`;
        const sourceType = (source.source_type || "source").toUpperCase();

        return `
          <label class="home-source-card ${checked ? "is-selected" : ""}" data-source-id="${sourceId}">
            <span class="home-source-card-check">
              <input type="checkbox" value="${sourceId}" ${checked} />
              <span class="home-source-check-ui"></span>
            </span>

            <span class="home-source-card-main">
              <span class="home-source-card-title">${escapeHtml(sourceTitle)}</span>
              <span class="home-source-card-meta">${escapeHtml(sourceType)}</span>
            </span>
          </label>
        `;
      }).join("")}
    </div>
  `;

  sourceModalBody.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const checkedIds = [];
      sourceModalBody.querySelectorAll('input[type="checkbox"]:checked').forEach((item) => {
        checkedIds.push(Number(item.value));
      });

      selectedSourceIds = checkedIds;

      sourceModalBody.querySelectorAll(".home-source-card").forEach((card) => {
        const id = Number(card.dataset.sourceId);
        card.classList.toggle("is-selected", selectedSourceIds.includes(id));
      });

      syncSourceFilterUi();
    });
  });

  if (sourceModalCount) {
    sourceModalCount.textContent = getSelectedCountText();
  }
}

async function loadSourcesForFilter() {
  try {
    const response = await fetch("/api/sources");
    const text = await response.text();

    let data = [];
    try {
      data = text ? JSON.parse(text) : [];
    } catch (_) {
      data = [];
    }

    if (!Array.isArray(data)) {
      allSources = [];
    } else {
      allSources = data
        .filter((source) => source && source.id != null)
        .sort((a, b) => {
          const left = String(a.title || a.source_key || "").toLowerCase();
          const right = String(b.title || b.source_key || "").toLowerCase();
          return left.localeCompare(right);
        });
    }
  } catch (error) {
    console.error("Failed to load sources for home filter:", error);
    allSources = [];
  }

  renderSourceModalOptions();
  syncSourceFilterUi();
}

function goToResults(query) {
  const nextUrl = buildResultsUrl(query);
  if (!nextUrl) return;
  window.location.href = nextUrl;
}

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  goToResults(input?.value || "");
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const query = chip.dataset.query || "";
    if (input) input.value = query;
    goToResults(query);
  });
});

sourceModeSelect?.addEventListener("change", () => {
  syncSourceFilterUi();
});

sourcePickerBtn?.addEventListener("click", () => {
  if (getSourceMode() !== "selected") return;
  renderSourceModalOptions();
  openSourceModal();
});

sourceModalBackdrop?.addEventListener("click", closeSourceModal);
sourceModalClose?.addEventListener("click", closeSourceModal);
sourceDoneBtn?.addEventListener("click", closeSourceModal);

sourceClearBtn?.addEventListener("click", () => {
  selectedSourceIds = [];
  renderSourceModalOptions();
  syncSourceFilterUi();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && sourceModal && !sourceModal.classList.contains("hidden")) {
    closeSourceModal();
  }
});

loadSourcesForFilter();