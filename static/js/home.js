const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const exactToggle = document.getElementById("exact-search-toggle");
const chips = document.querySelectorAll(".hint-chip");

function goToResults(query) {
  const q = query.trim();
  if (!q) return;

  const params = new URLSearchParams();
  params.set("q", q);

  if (exactToggle?.checked) {
    params.set("exact", "1");
  }

  window.location.href = `/results?${params.toString()}`;
}

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = input?.value.trim();
  if (!query) return;
  goToResults(query);
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const query = chip.dataset.query || "";
    if (input) input.value = query;
    goToResults(query);
  });
});