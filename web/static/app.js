const PLATFORM_TYPES = ["pararius", "kamernet", "funda", "huurwoningen", "housinganywhere"];

const state = {
  view: "dashboard",
  listings: { offset: 0, limit: 30, total: 0, search: "", source: "" },
  sources: [],
  cities: [],
  search: { city: "Amsterdam", radius_km: 10 },
  map: { instance: null, circle: null, marker: null, center: null },
  geocodeTimer: null,
  geocodeRequestId: 0,
  jobPollTimer: null,
  jobPollId: null,
};

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed", "cancelled"]);

const viewMeta = {
  dashboard: ["Dashboard", "Overview of your rental search"],
  search: ["Search area", "Pick a city, neighborhood, and radius on the map"],
  listings: ["Listings", "Within your search radius only"],
  sources: ["Platforms", "Enable rental sites to scrape"],
  settings: ["Settings", "Notifications and data"],
};

const SESSION_KEY = "easyhouse_session";

function getSessionToken() {
  return localStorage.getItem(SESSION_KEY);
}

function setSessionToken(token) {
  if (token) localStorage.setItem(SESSION_KEY, token);
  else localStorage.removeItem(SESSION_KEY);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getSessionToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(path, {
    headers,
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
  if (view === "search") loadSearchMap();
  if (view === "listings") loadListings();
  if (view === "sources") loadSources();
  if (view === "settings") loadSettings().catch((err) => showToast(err.message));
}

function renderSearchSummary(search) {
  const el = document.getElementById("search-summary");
  if (!search) return;
  const label = search.label || search.city;
  el.innerHTML = `
    <div>
      <strong>${label}</strong>
      <span class="muted"> · ${search.radius_km} km radius</span>
    </div>
    <button class="ghost-btn" id="edit-search-summary-btn" type="button">Edit search</button>
  `;
  document.getElementById("edit-search-summary-btn")?.addEventListener("click", () => switchView("search"));
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

async function loadCitiesCatalog() {
  if (state.cities.length) return state.cities;
  const data = await api("/api/cities");
  state.cities = data.cities || [];
  return state.cities;
}

function populateCitySelect(selectedCity) {
  const select = document.getElementById("search-city");
  select.innerHTML = state.cities
    .map((city) => `<option value="${city.name}">${city.name}</option>`)
    .join("");
  if (selectedCity) select.value = selectedCity;
}

function populateNeighborhoodSelect(cityName, selectedNeighborhood) {
  const select = document.getElementById("search-neighborhood");
  const city = state.cities.find((entry) => entry.name === cityName);
  const neighborhoods = city?.neighborhoods || [];
  select.innerHTML =
    '<option value="">Whole city</option>' +
    neighborhoods.map((name) => `<option value="${name}">${name}</option>`).join("");
  select.value = selectedNeighborhood || "";
}

function initSearchMap() {
  if (state.map.instance) return;
  const mapEl = document.getElementById("search-map");
  state.map.instance = L.map(mapEl, { zoomControl: true }).setView([52.37, 4.89], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(state.map.instance);
}

function updateMapCircle(center, radiusKm) {
  if (!state.map.instance || !center) return;
  const latLng = [center.lat, center.lng];
  if (!state.map.marker) {
    state.map.marker = L.marker(latLng).addTo(state.map.instance);
  } else {
    state.map.marker.setLatLng(latLng);
  }
  if (!state.map.circle) {
    state.map.circle = L.circle(latLng, {
      radius: radiusKm * 1000,
      color: "#e07a4a",
      fillColor: "#e07a4a",
      fillOpacity: 0.15,
      weight: 2,
    }).addTo(state.map.instance);
  } else {
    state.map.circle.setLatLng(latLng);
    state.map.circle.setRadius(radiusKm * 1000);
  }
  state.map.instance.fitBounds(state.map.circle.getBounds(), { padding: [24, 24] });
}

function scheduleGeocodePreview() {
  clearTimeout(state.geocodeTimer);
  state.geocodeTimer = setTimeout(() => previewSearchCenter().catch((err) => showToast(err.message)), 350);
}

async function previewSearchCenter() {
  const city = document.getElementById("search-city").value;
  const neighborhood = document.getElementById("search-neighborhood").value;
  const radius_km = Number(document.getElementById("search-radius").value);
  const info = document.getElementById("search-center-info");
  const requestId = ++state.geocodeRequestId;
  info.textContent = "Locating on map…";

  const result = await api("/api/search/geocode", {
    method: "POST",
    body: JSON.stringify({ city, neighborhood: neighborhood || null }),
  });

  if (requestId !== state.geocodeRequestId) return;

  state.map.center = { lat: result.center_lat, lng: result.center_lon };
  updateMapCircle(state.map.center, radius_km);
  info.textContent = `Center: ${result.label}`;
  setTimeout(() => state.map.instance?.invalidateSize(), 50);
}

async function loadSearchMap() {
  await loadCitiesCatalog();
  const search = await api("/api/search");
  state.search = search;

  populateCitySelect(search.city);
  populateNeighborhoodSelect(search.city, search.neighborhood || "");
  document.getElementById("search-radius").value = search.radius_km;
  document.getElementById("radius-value").textContent = search.radius_km;

  initSearchMap();

  if (search.center_lat != null && search.center_lon != null) {
    state.map.center = { lat: search.center_lat, lng: search.center_lon };
    updateMapCircle(state.map.center, search.radius_km);
    document.getElementById("search-center-info").textContent =
      `Center: ${search.label || search.city}`;
  } else {
    await previewSearchCenter();
  }

  setTimeout(() => state.map.instance?.invalidateSize(), 100);
}

async function saveSearchArea() {
  const city = document.getElementById("search-city").value;
  const neighborhood = document.getElementById("search-neighborhood").value;
  const radius_km = Number(document.getElementById("search-radius").value);
  const payload = { city, radius_km, neighborhood: neighborhood || null };

  const search = await api("/api/search", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  state.search = search;
  renderSearchSummary(search);
  await loadSourceFilterOptions();
  switchView("dashboard");

  if (search.scrape_job) {
    setJobStatus(search.scrape_job);
    pollJob(search.scrape_job.id);
    showToast(`City changed — scraping ${search.city}…`);
    return;
  }
  showToast(`Search area saved: ${search.label || search.city}, ${search.radius_km} km`);
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

function openAuthModal(tab = "signup") {
  document.getElementById("auth-modal").classList.remove("hidden");
  switchAuthTab(tab);
  document.body.style.overflow = "hidden";
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.add("hidden");
  if (document.getElementById("verify-modal").classList.contains("hidden")) {
    document.body.style.overflow = "";
  }
}

function openVerifyModal(email, emailSent = true) {
  document.getElementById("verify-modal-email").textContent = email;
  document.getElementById("verify-code-input").value = "";
  document.getElementById("verify-email-notice").classList.toggle("hidden", emailSent !== false);
  document.getElementById("verify-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.getElementById("verify-code-input").focus();
}

function closeVerifyModal() {
  document.getElementById("verify-modal").classList.add("hidden");
  if (document.getElementById("auth-modal").classList.contains("hidden")) {
    document.body.style.overflow = "";
  }
}

function setAuthActiveVisible(visible) {
  document.getElementById("auth-active").classList.toggle("hidden", !visible);
}

function renderAuthState(notifications) {
  const toggle = document.getElementById("notifications-enabled");
  const statusEl = document.getElementById("auth-status");
  const account = notifications.account;

  if (!notifications.signed_in || !account) {
    setAuthActiveVisible(false);
    toggle.checked = false;
    if (notifications.remote_auth) {
      statusEl.textContent = notifications.can_send_mail
        ? ""
        : "Cloud email delivery is not configured on the auth service yet.";
    } else {
      statusEl.textContent = notifications.can_send_mail
        ? ""
        : "Configure email delivery below to send verification codes.";
    }
    return;
  }

  setAuthActiveVisible(true);
  document.getElementById("auth-email").textContent = account.email;

  const verified = account.verified;
  const verificationEl = document.getElementById("auth-verification-status");
  const resendBtn = document.getElementById("resend-verification-btn");

  toggle.checked = verified ? account.alerts_enabled !== false : true;

  if (verified) {
    verificationEl.textContent = "Your email is verified. You'll receive alerts for new listings in your search area.";
    resendBtn.classList.add("hidden");
  } else {
    verificationEl.textContent = "Enter the 6-digit code we sent to your email to start receiving alerts.";
    resendBtn.classList.remove("hidden");
    resendBtn.textContent = "Enter verification code";
  }

  statusEl.textContent = "";
}

function switchAuthTab(tab) {
  document.querySelectorAll(".auth-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.authTab === tab);
  });
  document.getElementById("signup-form").classList.toggle("hidden", tab !== "signup");
  document.getElementById("login-form").classList.toggle("hidden", tab !== "login");
}

function renderEmailService(settings) {
  document.getElementById("smtp-host").value = settings.host || "smtp.gmail.com";
  document.getElementById("smtp-port").value = settings.port || 587;
  document.getElementById("smtp-from").value = settings.from_address || "";
  document.getElementById("smtp-username").value = settings.username || "";
  document.getElementById("smtp-use-tls").checked = settings.use_tls !== false;
  document.getElementById("smtp-password").value = "";
  const statusEl = document.getElementById("email-service-status");
  if (settings.configured) {
    statusEl.textContent = `Email delivery is configured${settings.source === "environment" ? " (via environment variables)" : ""}.`;
  } else {
    statusEl.textContent = "Email delivery is not configured — verification codes cannot be emailed yet.";
  }
}

async function loadSettings() {
  let authConfig = { remote_auth: false };
  try {
    authConfig = await api("/api/auth/config");
  } catch (err) {
    authConfig = { remote_auth: false };
  }

  document.getElementById("email-service-panel").classList.toggle("hidden", authConfig.remote_auth === true);

  try {
    const health = await api("/api/health");
    const authLine = health.remote_auth === "true" && health.auth_url
      ? `\nAuth service: ${health.auth_url}`
      : "";
    document.getElementById("data-paths").textContent =
      `Data directory: ${health.data_dir}\nDatabase: ${health.database}\nSources: ${health.sources}${authLine}`;
  } catch (err) {
    document.getElementById("data-paths").textContent = `Could not load data paths: ${err.message}`;
  }

  if (!authConfig.remote_auth) {
    try {
      renderEmailService(await api("/api/email-service"));
    } catch (err) {
      document.getElementById("email-service-status").textContent = `Could not load email settings: ${err.message}`;
    }
  }

  try {
    renderAuthState(await api("/api/notifications"));
  } catch (err) {
    renderAuthState({ signed_in: false, account: null, can_send_mail: false, remote_auth: authConfig.remote_auth });
  }
}

async function saveEmailService(event) {
  event.preventDefault();
  const payload = {
    host: document.getElementById("smtp-host").value.trim(),
    port: Number(document.getElementById("smtp-port").value),
    from_address: document.getElementById("smtp-from").value.trim(),
    username: document.getElementById("smtp-username").value.trim(),
    use_tls: document.getElementById("smtp-use-tls").checked,
  };
  const password = document.getElementById("smtp-password").value;
  if (password) payload.password = password;

  const settings = await api("/api/email-service", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  renderEmailService(settings);
  showToast("Email delivery saved");
}

async function testEmailService() {
  const result = await api("/api/email-service/test", { method: "POST" });
  showToast(result.to ? `Test email sent to ${result.to}` : "Test email sent");
}

function applyGmailPreset() {
  document.getElementById("smtp-host").value = "smtp.gmail.com";
  document.getElementById("smtp-port").value = 587;
  document.getElementById("smtp-use-tls").checked = true;
  const username = document.getElementById("smtp-username").value.trim();
  if (username && !document.getElementById("smtp-from").value.trim()) {
    document.getElementById("smtp-from").value = `easyHouse <${username}>`;
  }
  showToast("Gmail preset applied — add your Gmail address, app password, then Save");
}

async function signupAccount(event) {
  event.preventDefault();
  const result = await api("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify({
      email: document.getElementById("signup-email").value.trim(),
      password: document.getElementById("signup-password").value,
    }),
  });
  setSessionToken(result.session_token);
  closeAuthModal();
  openVerifyModal(result.account.email, result.email_sent);
}

async function loginAccount(event) {
  event.preventDefault();
  const result = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: document.getElementById("login-email").value.trim(),
      password: document.getElementById("login-password").value,
    }),
  });
  setSessionToken(result.session_token);
  closeAuthModal();
  if (!result.account.verified) {
    openVerifyModal(result.account.email, true);
    return;
  }
  showToast("Signed in");
  await loadSettings();
}

async function logoutAccount() {
  await api("/api/auth/logout", { method: "POST" });
  setSessionToken(null);
  document.getElementById("notifications-enabled").checked = false;
  showToast("Signed out");
  await loadSettings();
}

async function resendVerificationCode() {
  const result = await api("/api/auth/resend-verification", { method: "POST" });
  document.getElementById("verify-email-notice").classList.toggle("hidden", result.email_sent !== false);
  if (result.email_sent === false) {
    showToast("New code generated — configure Email delivery in Settings, or check the agent terminal.");
    return;
  }
  showToast("Verification code sent");
}

async function submitVerificationCode(event) {
  event.preventDefault();
  const code = document.getElementById("verify-code-input").value.trim();
  await api("/api/auth/verify", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  closeVerifyModal();
  document.getElementById("notifications-enabled").checked = true;
  showToast("Email verified — notifications are on");
  await loadSettings();
}

async function fetchNotificationStatus() {
  if (!getSessionToken()) {
    return { signed_in: false, account: null, can_send_mail: false };
  }
  try {
    return await api("/api/notifications");
  } catch (err) {
    setSessionToken(null);
    return { signed_in: false, account: null, can_send_mail: false };
  }
}

async function handleNotificationsToggle(event) {
  const toggle = event.target;
  const enabled = toggle.checked;

  if (!enabled) {
    closeAuthModal();
    const notifications = await fetchNotificationStatus();
    const account = notifications.account;
    if (notifications.signed_in && account?.verified) {
      try {
        await api("/api/auth/alerts", {
          method: "PUT",
          body: JSON.stringify({ enabled: false }),
        });
        showToast("Email notifications paused");
        await loadSettings();
      } catch (err) {
        toggle.checked = true;
        showToast(err.message);
      }
    }
    return;
  }

  const notifications = await fetchNotificationStatus();
  const account = notifications.account;

  if (notifications.signed_in && account?.verified) {
    try {
      await api("/api/auth/alerts", {
        method: "PUT",
        body: JSON.stringify({ enabled: true }),
      });
      showToast("Email notifications enabled");
      await loadSettings();
    } catch (err) {
      toggle.checked = false;
      showToast(err.message);
    }
    return;
  }

  toggle.checked = true;

  if (notifications.signed_in && account && !account.verified) {
    renderAuthState(notifications);
    openVerifyModal(account.email, notifications.can_send_mail);
    return;
  }

  openAuthModal("signup");
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
  if (job.status === "cancelled") {
    el.textContent = "Scrape cancelled";
    return;
  }
  const totalNew = (job.results || []).reduce((sum, row) => sum + (row.new_count || 0), 0);
  el.textContent = `Scrape done — ${totalNew} new listing(s)`;
}

function stopJobPolling() {
  if (state.jobPollTimer) {
    clearInterval(state.jobPollTimer);
    state.jobPollTimer = null;
  }
  state.jobPollId = null;
}

async function pollJob(jobId) {
  stopJobPolling();
  state.jobPollId = jobId;

  const tick = async () => {
    if (state.jobPollId !== jobId) return;
    try {
      const job = await api(`/api/jobs/${jobId}`);
      if (state.jobPollId !== jobId) return;
      setJobStatus(job);
      if (!TERMINAL_JOB_STATUSES.has(job.status)) return;

      stopJobPolling();
      if (job.status === "completed") {
        showToast("Scrape completed");
        if (state.view === "dashboard") loadDashboard();
        if (state.view === "listings") loadListings();
      } else if (job.status === "failed") {
        showToast(job.error || "Scrape failed");
      }
    } catch (err) {
      if (state.jobPollId !== jobId) return;
      stopJobPolling();
      setJobStatus(null);
    }
  };

  await tick();
  if (state.jobPollId === jobId) {
    state.jobPollTimer = setInterval(tick, 1200);
  }
}

async function startScrape({ fullSync = false } = {}) {
  const payload = { full_sync: fullSync, max_pages: fullSync ? null : 1 };
  const job = await api("/api/scrape", { method: "POST", body: JSON.stringify(payload) });
  setJobStatus(job);
  showToast(fullSync ? "Full sync started" : "Scrape started");
  pollJob(job.id);
}

function bindEvents() {
  document.querySelectorAll(".sidebar .nav-btn[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  document.querySelectorAll(".auth-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchAuthTab(btn.dataset.authTab));
  });

  document.getElementById("scrape-btn").addEventListener("click", () => startScrape({ fullSync: false }));
  document.getElementById("full-sync-btn").addEventListener("click", () => startScrape({ fullSync: true }));
  document.getElementById("save-sources-btn").addEventListener("click", () => saveSources().catch((err) => showToast(err.message)));
  document.getElementById("add-source-btn").addEventListener("click", addSourceRow);
  document.getElementById("open-search-map-btn").addEventListener("click", () => switchView("search"));
  document.getElementById("save-search-btn").addEventListener("click", () => saveSearchArea().catch((err) => showToast(err.message)));
  document.getElementById("search-city").addEventListener("change", (event) => {
    populateNeighborhoodSelect(event.target.value, "");
    scheduleGeocodePreview();
  });
  document.getElementById("search-neighborhood").addEventListener("change", () => scheduleGeocodePreview());
  document.getElementById("search-radius").addEventListener("input", (event) => {
    const radius = Number(event.target.value);
    document.getElementById("radius-value").textContent = radius;
    if (state.map.center) updateMapCircle(state.map.center, radius);
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

  document.getElementById("signup-form").addEventListener("submit", (event) => {
    signupAccount(event).catch((err) => showToast(err.message));
  });
  document.getElementById("login-form").addEventListener("submit", (event) => {
    loginAccount(event).catch((err) => showToast(err.message));
  });
  document.getElementById("logout-btn").addEventListener("click", () => {
    logoutAccount().catch((err) => showToast(err.message));
  });
  document.getElementById("resend-verification-btn").addEventListener("click", () => {
    const email = document.getElementById("auth-email").textContent.trim();
    if (email) openVerifyModal(email);
  });
  document.getElementById("verify-code-form").addEventListener("submit", (event) => {
    submitVerificationCode(event).catch((err) => showToast(err.message));
  });
  document.getElementById("verify-resend-btn").addEventListener("click", () => {
    resendVerificationCode().catch((err) => showToast(err.message));
  });
  document.getElementById("email-service-form").addEventListener("submit", (event) => {
    saveEmailService(event).catch((err) => showToast(err.message));
  });
  document.getElementById("smtp-test-btn").addEventListener("click", () => {
    testEmailService().catch((err) => showToast(err.message));
  });
  document.getElementById("smtp-gmail-preset-btn").addEventListener("click", applyGmailPreset);
  document.getElementById("verify-modal-close").addEventListener("click", closeVerifyModal);
  document.getElementById("verify-modal-backdrop").addEventListener("click", closeVerifyModal);
  document.getElementById("notifications-enabled").addEventListener("change", (event) => {
    handleNotificationsToggle(event).catch((err) => {
      event.target.checked = false;
      showToast(err.message);
    });
  });
  document.getElementById("auth-modal-close").addEventListener("click", () => {
    document.getElementById("notifications-enabled").checked = false;
    closeAuthModal();
  });
  document.getElementById("auth-modal-backdrop").addEventListener("click", () => {
    document.getElementById("notifications-enabled").checked = false;
    closeAuthModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!document.getElementById("verify-modal").classList.contains("hidden")) {
      closeVerifyModal();
      return;
    }
    if (!document.getElementById("auth-modal").classList.contains("hidden")) {
      document.getElementById("notifications-enabled").checked = false;
      closeAuthModal();
    }
  });
}

function initialView() {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  if (view && viewMeta[view]) return view;
  return "dashboard";
}

async function init() {
  bindEvents();
  await loadSourceFilterOptions();
  switchView(initialView());
  const latest = await api("/api/jobs/latest");
  if (latest.job && latest.job.status === "running") {
    setJobStatus(latest.job);
    pollJob(latest.job.id);
  }
}

init().catch((err) => showToast(err.message));
