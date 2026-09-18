const PLATFORM_TYPES = ["pararius", "kamernet", "funda", "huurwoningen", "housinganywhere"];

const state = {
  view: "dashboard",
  listings: { offset: 0, limit: 30, total: 0, search: "", source: "" },
  sources: [],
  search: { city: "Amsterdam", radius_km: 10 },
  jobPollTimer: null,
};

const viewMeta = {
  dashboard: ["Dashboard", "Overview of your rental search"],
  search: ["Search area", "Choose city and radius from center"],
  listings: ["Listings", "Within your search radius only"],
  sources: ["Platforms", "Enable rental sites to scrape"],
  settings: ["Settings", "Notifications and server info"],
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return data;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 3200);
}

function formatPrice(value) {
  if (value == null) return "?";
  return `€${Number(value).toLocaleString("en-NL")}`;
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value.replace(" ", "T")).toLocaleString();
}

function switchView(view) {
  state.view = view;
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("active", section.id === `view-${view}`);
  });
  const [title, subtitle] = viewMeta[view];
  document.getElementById("view-title").textContent = title;
  document.getElementById("view-subtitle").textContent = subtitle;
  if (view === "dashboard") loadDashboard();
  if (view === "search") loadSearchForm();
  if (view === "listings") loadListings();
  if (view === "sources") loadSources();
  if (view === "settings") loadSettings();
}

function renderSearchSummary(search) {
  const el = document.getElementById("search-summary");
  if (!search) return;
  const center =
    search.center_lat != null
      ? `Center: ${search.center_lat.toFixed(4)}, ${search.center_lon.toFixed(4)}`
      : "Center not geocoded yet";
  el.innerHTML = `
    <div>
      <strong>${search.city}</strong>
      <span class="muted"> · ${search.radius_km} km radius</span>
      <div class="muted">${center}</div>
    </div>
    <button class="ghost-btn" onclick="switchView('search')">Edit search</button>
  `;
}

function renderBarList(containerId, rows, valueKey = "count") {
  const container = document.getElementById(containerId);
  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">No data yet</div>';
    return;
  }
  const max = Math.max(...rows.map((row) => row[valueKey]));
  container.innerHTML = rows
    .map((row) => {
      const label = row.source || row.city || "Unknown";
      const width = max ? Math.round((row[valueKey] / max) * 100) : 0;
      return `
        <div class="bar-row">
          <span>${label}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          <strong>${row[valueKey]}</strong>
        </div>`;
    })
    .join("");
}

async function loadDashboard() {
  const stats = await api("/api/stats");
  state.search = stats.search;
  renderSearchSummary(stats.search);
  document.getElementById("stats-grid").innerHTML = `
    <article class="stat-card"><span>Unique listings</span><strong>${stats.canonical_count}</strong></article>
    <article class="stat-card"><span>Platform entries</span><strong>${stats.source_rows}</strong></article>
    <article class="stat-card"><span>New (24h)</span><strong>${stats.new_24h}</strong></article>
    <article class="stat-card"><span>Sources tracked</span><strong>${stats.by_source.length}</strong></article>
  `;
  renderBarList("source-chart", stats.by_source);
  renderBarList("city-chart", stats.by_city);
}

async function loadListings() {
  const { offset, limit, search, source } = state.listings;
  const params = new URLSearchParams({ limit, offset });
  if (search) params.set("search", search);
  if (source) params.set("source", source);

  const data = await api(`/api/listings?${params}`);
  state.listings.total = data.total;
  if (data.search) {
    state.search = data.search;
    renderSearchSummary(data.search);
  }

  const wrap = document.getElementById("listings-table-wrap");
  if (!data.listings.length) {
    wrap.innerHTML = '<div class="empty-state">No listings found. Run a scrape to populate the database.</div>';
  } else {
    wrap.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Listing</th>
            <th>Price</th>
            <th>Distance</th>
            <th>City</th>
            <th>Sources</th>
            <th>First seen</th>
          </tr>
        </thead>
        <tbody>
          ${data.listings
            .map(
              (listing) => `
            <tr>
              <td><a class="listing-link" href="${listing.best_url}" target="_blank" rel="noopener">${listing.title}</a></td>
              <td class="price">${formatPrice(listing.price_eur)}</td>
              <td>${listing.distance_km != null ? `${listing.distance_km} km` : "—"}</td>
              <td>${listing.city || "—"}</td>
              <td>${(listing.sources || []).map((s) => `<span class="source-pill">${s}</span>`).join("")}</td>
              <td>${formatDate(listing.first_seen_at)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(data.total / limit));
  document.getElementById("page-info").textContent = `Page ${page} of ${totalPages} (${data.total} total)`;
  document.getElementById("prev-page").disabled = offset <= 0;
  document.getElementById("next-page").disabled = offset + limit >= data.total;
}

async function loadSourceFilterOptions() {
  const data = await api("/api/sources");
  const select = document.getElementById("listing-source-filter");
  const current = select.value;
  select.innerHTML = '<option value="">All sources</option>';
  data.sources.forEach((source) => {
    const option = document.createElement("option");
    option.value = source.id;
    option.textContent = source.name;
    select.appendChild(option);
  });
  select.value = current;
}

async function loadSearchForm() {
  const search = await api("/api/search");
  state.search = search;
  document.getElementById("search-city").value = search.city;
  document.getElementById("search-radius").value = search.radius_km;
  document.getElementById("radius-value").textContent = search.radius_km;
  document.getElementById("search-center-info").textContent =
    search.center_lat != null
      ? `Geocoded center: ${search.center_lat.toFixed(4)}, ${search.center_lon.toFixed(4)}`
      : "Save to geocode the city center.";
}

async function saveSearchArea() {
  const city = document.getElementById("search-city").value.trim();
  const radius_km = Number(document.getElementById("search-radius").value);
  const search = await api("/api/search", {
    method: "PUT",
    body: JSON.stringify({ city, radius_km }),
  });
  state.search = search;
  renderSearchSummary(search);
  showToast(`Search area updated: ${search.city}, ${search.radius_km} km`);
  await loadSourceFilterOptions();
}

async function loadSources() {
  const data = await api("/api/sources");
  state.sources = data.sources;
  if (data.search) renderSearchSummary(data.search);
  const container = document.getElementById("sources-list");
  container.innerHTML = state.sources
    .map(
      (source, index) => `
      <div class="source-card" data-index="${index}">
        <label>Name<input type="text" value="${source.name}" data-field="name" /></label>
        <label>Type
          <select data-field="type">
            ${PLATFORM_TYPES.map(
              (type) => `<option value="${type}" ${source.type === type ? "selected" : ""}>${type}</option>`
            ).join("")}
          </select>
        </label>
        <label class="toggle">
          <input type="checkbox" ${source.enabled ? "checked" : ""} data-field="enabled" />
          Enabled
        </label>
        <button class="danger-btn" data-action="remove">Remove</button>
        <small class="muted">${source.url}</small>
      </div>`
    )
    .join("");
}

function readSourcesFromDom() {
  return [...document.querySelectorAll(".source-card")].map((card) => ({
    name: card.querySelector('[data-field="name"]').value.trim(),
    type: card.querySelector('[data-field="type"]').value,
    enabled: card.querySelector('[data-field="enabled"]').checked,
  }));
}

async function saveSources() {
  const sources = readSourcesFromDom();
  await api("/api/sources", { method: "PUT", body: JSON.stringify({ sources }) });
  showToast("Platforms saved");
  await loadSources();
  await loadSourceFilterOptions();
}

function addSourceRow() {
  state.sources.push({ name: "New platform", type: "pararius", enabled: true, url: "", id: "new" });
  loadSources();
}

async function loadSettings() {
  const data = await api("/api/notifications");
  document.getElementById("notification-cards").innerHTML = `
    <div class="notif-card ${data.email.configured ? "on" : ""}">
      <strong>Email</strong>
      <span>${data.email.configured ? data.email.to : "Not configured"}</span>
    </div>
    <div class="notif-card ${data.telegram.configured ? "on" : ""}">
      <strong>Telegram</strong>
      <span>${data.telegram.configured ? "Configured" : "Not configured"}</span>
    </div>
    <div class="notif-card ${data.webhook.configured ? "on" : ""}">
      <strong>Webhook</strong>
      <span>${data.webhook.configured ? "Configured" : "Not configured"}</span>
    </div>`;
}

function setJobStatus(job) {
  const el = document.getElementById("job-status");
  if (!job) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden", "running", "completed", "failed");
  el.classList.add(job.status);
  if (job.status === "running") {
    el.textContent = "Scrape running…";
    return;
  }
  if (job.status === "failed") {
    el.textContent = `Scrape failed: ${job.error || "unknown error"}`;
    return;
  }
  const totalNew = (job.results || []).reduce((sum, row) => sum + (row.new_count || 0), 0);
  el.textContent = `Scrape done — ${totalNew} new listing(s)`;
}

async function pollJob(jobId) {
  clearInterval(state.jobPollTimer);
  state.jobPollTimer = setInterval(async () => {
    const job = await api(`/api/jobs/${jobId}`);
    setJobStatus(job);
    if (job.status === "completed" || job.status === "failed") {
      clearInterval(state.jobPollTimer);
      if (job.status === "completed") {
        showToast("Scrape completed");
        if (state.view === "dashboard") loadDashboard();
        if (state.view === "listings") loadListings();
      } else {
        showToast(job.error || "Scrape failed");
      }
    }
  }, 1200);
}

async function startScrape({ fullSync = false } = {}) {
  const payload = { full_sync: fullSync, max_pages: fullSync ? null : 1 };
  const job = await api("/api/scrape", { method: "POST", body: JSON.stringify(payload) });
  setJobStatus(job);
  showToast(fullSync ? "Full sync started" : "Scrape started");
  pollJob(job.id);
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  document.getElementById("scrape-btn").addEventListener("click", () => startScrape({ fullSync: false }));
  document.getElementById("full-sync-btn").addEventListener("click", () => startScrape({ fullSync: true }));
  document.getElementById("save-sources-btn").addEventListener("click", () => saveSources().catch((err) => showToast(err.message)));
  document.getElementById("add-source-btn").addEventListener("click", addSourceRow);
  document.getElementById("save-search-btn").addEventListener("click", () => saveSearchArea().catch((err) => showToast(err.message)));
  document.getElementById("search-radius").addEventListener("input", (event) => {
    document.getElementById("radius-value").textContent = event.target.value;
  });

  document.getElementById("listing-search").addEventListener("input", (event) => {
    state.listings.search = event.target.value.trim();
    state.listings.offset = 0;
    loadListings();
  });

  document.getElementById("listing-source-filter").addEventListener("change", (event) => {
    state.listings.source = event.target.value;
    state.listings.offset = 0;
    loadListings();
  });

  document.getElementById("prev-page").addEventListener("click", () => {
    state.listings.offset = Math.max(0, state.listings.offset - state.listings.limit);
    loadListings();
  });

  document.getElementById("next-page").addEventListener("click", () => {
    if (state.listings.offset + state.listings.limit < state.listings.total) {
      state.listings.offset += state.listings.limit;
      loadListings();
    }
  });

  document.getElementById("sources-list").addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="remove"]');
    if (!button) return;
    const card = button.closest(".source-card");
    card.remove();
  });
}

async function init() {
  bindEvents();
  await loadSourceFilterOptions();
  switchView("dashboard");
  const latest = await api("/api/jobs/latest");
  if (latest.job && latest.job.status === "running") {
    setJobStatus(latest.job);
    pollJob(latest.job.id);
  }
}

init().catch((err) => showToast(err.message));
