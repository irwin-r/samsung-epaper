/**
 * Samsung ePaper Display — Custom Lovelace Card v3
 * Baroque-framed preview with controls below.
 */
const CARD_VERSION = "4.0.0";

function timeAgo(dateStr) {
  if (!dateStr) return "Never";
  // Server returns UTC datetimes without Z suffix — append it
  const d = dateStr.endsWith("Z") ? dateStr : dateStr + "Z";
  const diff = (Date.now() - new Date(d).getTime()) / 1000;
  if (diff < 0) return "Just now";
  if (diff < 60) return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

class SamsungEpaperCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._assets = [];
    this._activeTab = "create";
    this._createMode = "upload";  // upload, ai, newspaper
    this._genTypes = null;
    this._selectedArtType = "tabloid";
    this._selectedNewspaper = "smh";
    this._generatingJob = null;
    this._aiFiles = [];
    this._cropImage = null;
    this._cropScale = 1;
    this._cropX = 0;
    this._cropY = 0;
    this._dragging = false;
    this._dragStartX = 0;
    this._dragStartY = 0;
    this._cropFile = null;
    this._favourites = [];
    this._collections = [];
    this._schedules = [];
    this._currentCollectionId = null; // null = "All" / root
    this._currentName = null;
    this._currentAssetId = null;
    this._lastDisplayedAt = null;
  }

  setConfig(config) {
    if (!config.addon_url) throw new Error("Please set addon_url");
    this._config = {
      addon_url: config.addon_url.replace(/\/$/, ""),
      title: config.title || "Samsung ePaper",
      display_width: config.display_width || 1440,
      display_height: config.display_height || 2560,
      ...config,
    };
    this._config.auth_token = config.auth_token || "";
    this._render();
    this._loadHistory();
    this._loadCurrentAsset();
    this._loadGenTypes();
  }

  async _loadCurrentAsset() {
    try {
      const r = await fetch(this._url("/api/status"));
      if (r.ok) {
        const s = await r.json();
        if (s.current_asset_id) {
          this._currentAssetId = s.current_asset_id;
          this._lastDisplayedAt = s.last_update;
          const ar = await fetch(this._url(`/api/assets/${s.current_asset_id}`));
          if (ar.ok) {
            const a = await ar.json();
            this._currentName = a.title || a.filename_original;
          }
          this._updateDynamic();
        }
      }
    } catch (e) { console.error("Load current:", e); }
  }

  set hass(hass) {
    const changed = !this._hass ||
      this._hass.states?.["sensor.samsung_epaper_status"]?.state !== hass.states?.["sensor.samsung_epaper_status"]?.state ||
      this._hass.states?.["camera.samsung_epaper_display_preview"]?.attributes?.access_token !== hass.states?.["camera.samsung_epaper_display_preview"]?.attributes?.access_token;
    this._hass = hass;
    if (changed) this._render();
  }

  static getStubConfig() { return { addon_url: "http://192.168.50.84:8000" }; }
  _url(p) { return `${this._config.addon_url}${p}`; }

  async _loadHistory() {
    try {
      // Fetch history (ordered by displayed_at) and assets for thumbnails
      const [hRes, aRes] = await Promise.all([
        fetch(this._url("/api/history?limit=30")),
        fetch(this._url("/api/assets?limit=100")),
      ]);
      if (hRes.ok && aRes.ok) {
        const history = await hRes.json();
        const assets = await aRes.json();
        const assetMap = {};
        for (const a of assets) assetMap[a.id] = a;
        // Deduplicate by asset_id, keep most recent display
        const seen = new Set();
        this._assets = [];
        for (const h of history) {
          if (!seen.has(h.asset_id) && assetMap[h.asset_id]?.filename_thumbnail) {
            seen.add(h.asset_id);
            this._assets.push(assetMap[h.asset_id]);
          }
        }
        this._render();
      }
    } catch (e) { console.error("History:", e); }
  }

  async _loadGenTypes() {
    if (this._genTypes) return;
    try {
      const r = await fetch(this._url("/api/generate/types"));
      if (r.ok) this._genTypes = await r.json();
    } catch (e) { console.error("Gen types:", e); }
  }

  _authHeaders() {
    const h = {};
    if (this._config.auth_token) h["Authorization"] = `Bearer ${this._config.auth_token}`;
    return h;
  }

  async _generateArt() {
    if (!this._aiFiles.length) { this._toast("Select photos first"); return; }
    const count = this._aiFiles.length;
    this._toast(`Generating ${count} artwork${count > 1 ? "s" : ""}...`);
    this._generatingJob = true;
    this._updateDynamic();

    let lastJobId = null;
    for (const file of this._aiFiles) {
      const fd = new FormData();
      fd.append("photo", file);
      fd.append("art_type", this._selectedArtType);
      try {
        const r = await fetch(this._url("/api/generate/art"), { method: "POST", body: fd, headers: this._authHeaders() });
        const d = await r.json();
        if (d.job_id) lastJobId = d.job_id;
        else this._toast(d.detail || `Failed for ${file.name}`);
      } catch (e) { this._toast("Error: " + e.message); }
    }

    this._aiFiles = [];
    if (lastJobId) {
      this._toast(`${count} job${count > 1 ? "s" : ""} submitted — generating...`);
      this._pollJob(lastJobId);
    } else {
      this._generatingJob = null;
      this._updateDynamic();
    }
  }

  async _generateNewspaper() {
    this._toast("Fetching newspaper...");
    try {
      const r = await fetch(this._url(`/api/generate/frontpage`), {
        method: "POST",
        headers: { ...this._authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ newspaper: this._selectedNewspaper }),
      });
      const d = await r.json();
      if (d.job_id) {
        this._generatingJob = d.job_id;
        this._toast("Fetching — please wait...");
        this._pollJob(d.job_id);
      } else {
        this._toast(d.detail || "Failed");
      }
    } catch (e) { this._toast("Error: " + e.message); }
  }

  async _pollJob(jobId) {
    const poll = async () => {
      try {
        const r = await fetch(this._url(`/api/generate/jobs/${jobId}`));
        if (!r.ok) return;
        const d = await r.json();
        if (d.status === "completed") {
          this._generatingJob = null;
          this._toast("Done! Sent to display.");
          this._loadHistory();
          // Update preview
          if (d.asset_id) {
            this._currentAssetId = d.asset_id;
            this._currentName = d.title || "Generated";
            this._lastDisplayedAt = new Date().toISOString();
            this._updateDynamic();
            const img = this.shadowRoot.getElementById("preview-img");
            if (img) img.src = this._url(`/api/assets/${d.asset_id}/image`) + `?t=${Date.now()}`;
          }
          return;
        } else if (d.status === "failed") {
          this._generatingJob = null;
          this._toast("Generation failed: " + (d.error || "unknown error"));
          return;
        }
        setTimeout(poll, 3000);
      } catch (e) { setTimeout(poll, 5000); }
    };
    setTimeout(poll, 2000);
  }

  async _loadFavourites() {
    try {
      const [fRes, cRes, aRes] = await Promise.all([
        fetch(this._url("/api/favourites")),
        fetch(this._url("/api/collections")),
        fetch(this._url("/api/assets?limit=200")),
      ]);
      if (fRes.ok) this._favourites = await fRes.json();
      if (cRes.ok) this._collections = await cRes.json();
      if (aRes.ok) {
        const assets = await aRes.json();
        this._assetMap = {};
        for (const a of assets) this._assetMap[a.id] = a;
      }
      this._render();
    } catch (e) { console.error("Favourites:", e); }
  }

  async _loadSchedules() {
    try {
      const r = await fetch(this._url("/api/schedules"));
      if (r.ok) { this._schedules = await r.json(); this._render(); }
    } catch (e) { console.error("Schedules:", e); }
  }

  async _toggleFavourite(assetId) {
    const existing = this._favourites.find(f => f.asset_id === assetId);
    if (existing) {
      if (!confirm("Remove from favourites?")) return;
      await fetch(this._url(`/api/favourites/${existing.id}`), { method: "DELETE" });
      this._toast("Removed from favourites");
    } else {
      await fetch(this._url("/api/favourites"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_id: assetId }),
      });
      this._toast("Added to favourites");
    }
    await this._loadFavourites();
  }

  async _createCollection() {
    const name = prompt("Folder name:");
    if (!name) return;
    await fetch(this._url("/api/collections"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent_id: this._currentCollectionId }),
    });
    this._toast("Folder created");
    await this._loadFavourites();
  }

  async _deleteCollection(id) {
    if (!confirm("Delete this folder? Favourites inside will be moved to All.")) return;
    // Move favourites out first
    const favsInFolder = this._favourites.filter(f => f.collection_id === id);
    for (const f of favsInFolder) {
      await fetch(this._url(`/api/favourites/${f.id}`), { method: "DELETE" });
      await fetch(this._url("/api/favourites"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_id: f.asset_id, name: f.name }),
      });
    }
    await fetch(this._url(`/api/collections/${id}`), { method: "DELETE" });
    this._currentCollectionId = null;
    this._toast("Folder deleted");
    await this._loadFavourites();
  }

  async _renameCollection(id) {
    const col = this._collections.find(c => c.id === id);
    const name = prompt("Rename folder:", col?.name || "");
    if (!name) return;
    await fetch(this._url(`/api/collections/${id}?name=${encodeURIComponent(name)}`), { method: "PUT" });
    await this._loadFavourites();
  }

  _showMovePopover(favId, anchorEl) {
    // Remove any existing popover
    this._closeMovePopover();

    const fav = this._favourites.find(f => f.id === favId);
    if (!fav) return;

    const rect = anchorEl.getBoundingClientRect();
    const shadowRect = this.shadowRoot.host.getBoundingClientRect();

    const backdrop = document.createElement("div");
    backdrop.className = "move-popover-backdrop";
    backdrop.addEventListener("click", () => this._closeMovePopover());

    const popover = document.createElement("div");
    popover.className = "move-popover";
    popover.style.top = `${rect.bottom - shadowRect.top + 4}px`;
    popover.style.left = `${rect.left - shadowRect.left}px`;

    const options = [{ id: null, name: "All (no folder)" }, ...this._collections];
    for (const opt of options) {
      const btn = document.createElement("button");
      btn.className = `move-popover-item${opt.id === fav.collection_id ? " current" : ""}`;
      btn.innerHTML = `${opt.id ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>' : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'} ${opt.name}`;
      btn.addEventListener("click", async () => {
        this._closeMovePopover();
        await fetch(this._url(`/api/favourites/${favId}`), { method: "DELETE" });
        await fetch(this._url("/api/favourites"), {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ asset_id: fav.asset_id, collection_id: opt.id, name: fav.name }),
        });
        this._toast("Moved");
        await this._loadFavourites();
      });
      popover.appendChild(btn);
    }

    this.shadowRoot.appendChild(backdrop);
    this.shadowRoot.appendChild(popover);
    this._movePopoverEls = [backdrop, popover];
  }

  _closeMovePopover() {
    if (this._movePopoverEls) {
      this._movePopoverEls.forEach(el => el.remove());
      this._movePopoverEls = null;
    }
  }

  async _renameFavourite(favId) {
    const fav = this._favourites.find(f => f.id === favId);
    const name = prompt("Name this favourite:", fav?.name || "");
    if (name === null) return;
    await fetch(this._url(`/api/favourites/${favId}?name=${encodeURIComponent(name)}`), { method: "PUT" });
    this._toast("Renamed");
    await this._loadFavourites();
  }

  async _deleteAsset(assetId) {
    if (!confirm("Delete this image from history?")) return;
    await fetch(this._url(`/api/assets/${assetId}`), { method: "DELETE" });
    this._toast("Deleted");
    await this._loadHistory();
    await this._loadFavourites();
  }

  async _deleteSchedule(id) {
    await fetch(this._url(`/api/schedules/${id}`), { method: "DELETE" });
    this._toast("Schedule deleted");
    await this._loadSchedules();
  }

  async _toggleSchedule(id, enabled) {
    await fetch(this._url(`/api/schedules/${id}`), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_enabled: !enabled }),
    });
    await this._loadSchedules();
  }

  async _runSchedule(id) {
    this._toast("Running schedule...");
    await fetch(this._url(`/api/schedules/${id}/run`), { method: "POST" });
    setTimeout(() => this._loadHistory(), 3000);
  }

  async _svc(s, d = {}) {
    if (!this._hass) return;
    await this._hass.callService("samsung_epaper", s, d);
    setTimeout(() => this._loadHistory(), 3000);
  }

  _toast(m) {
    const t = this.shadowRoot.getElementById("toast");
    if (t) { t.textContent = m; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 3000); }
  }

  _getPreviewUrl() {
    // Serve the full processed image (not thumbnail) so aspect ratio matches the real display
    const assetId = this._currentAssetId;
    if (assetId) return this._url(`/api/assets/${assetId}/image`);
    return "";
  }

  _updateStatusBar() {
    const status = this._hass?.states?.["sensor.samsung_epaper_status"];
    const metaEl = this.shadowRoot.getElementById("status-meta");
    if (metaEl) {
      const name = this._currentName || this._hass?.states?.["select.samsung_epaper_active_preset"]?.state || "No preset";
      const t = this._lastDisplayedAt || status?.attributes?.last_update;
      metaEl.innerHTML = `
        <span class="meta-label">${name}</span>
        <span class="meta-sep">&middot;</span>
        <span class="meta-time">${status?.state === "updating" ? "Updating..." : timeAgo(t)}</span>
      `;
    }
  }

  async _refresh() {
    this._toast("Refreshing...");
    this._currentName = null;
    this._currentAssetId = null;
    await this._svc("refresh");
  }
  async _displayAsset(id, displayName) {
    this._toast("Sending...");
    const asset = this._assets?.find(a => a.id === id) || this._assetMap?.[id];
    this._currentAssetId = id;
    this._currentName = displayName || asset?.title || asset?.filename_original || "Image";
    this._lastDisplayedAt = new Date().toISOString();
    this._updateStatusBar();
    // Update preview immediately from addon thumbnail
    const img = this.shadowRoot.getElementById("preview-img");
    if (img) img.src = this._url(`/api/assets/${id}/thumbnail`) + `?t=${Date.now()}`;
    await this._svc("display_asset", { asset_id: id });
  }
  async _displayUrl() {
    const v = this.shadowRoot.getElementById("url-input")?.value?.trim();
    if (!v) return;
    this._toast("Fetching..."); await this._svc("display_url", { url: v, title: "URL Image" });
  }

  // --- Crop ---
  _onFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    this._cropFile = file;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        this._cropImage = img;
        const ar = this._config.display_width / this._config.display_height;
        const iar = img.width / img.height;
        this._cropScale = iar > ar ? 1 : ar / iar;
        this._cropX = 0; this._cropY = 0;
        this._render();
        requestAnimationFrame(() => this._drawCrop());
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  }

  _drawCrop() {
    const c = this.shadowRoot.getElementById("crop-canvas");
    if (!c || !this._cropImage) return;
    const ctx = c.getContext("2d");
    const dw = this._config.display_width, dh = this._config.display_height;
    const ch = c.parentElement?.clientHeight || 350;
    const cw = ch * (dw / dh);
    c.width = cw; c.height = ch;
    ctx.fillStyle = "#111"; ctx.fillRect(0, 0, cw, ch);
    const img = this._cropImage, s = this._cropScale, ds = ch / dh;
    ctx.drawImage(img, 0, 0, img.width, img.height,
      this._cropX * ds, this._cropY * ds, img.width * s * ds, img.height * s * ds);
    ctx.strokeStyle = "rgba(255,255,255,0.15)"; ctx.lineWidth = 1;
    for (let i = 1; i < 3; i++) {
      ctx.beginPath(); ctx.moveTo(cw/3*i, 0); ctx.lineTo(cw/3*i, ch); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, ch/3*i); ctx.lineTo(cw, ch/3*i); ctx.stroke();
    }
  }

  _onCropDown(e) {
    this._dragging = true;
    const p = e.touches ? e.touches[0] : e;
    this._dragStartX = p.clientX - this._cropX;
    this._dragStartY = p.clientY - this._cropY;
    e.preventDefault();
  }
  _onCropMove(e) {
    if (!this._dragging) return;
    const p = e.touches ? e.touches[0] : e;
    this._cropX = p.clientX - this._dragStartX;
    this._cropY = p.clientY - this._dragStartY;
    this._drawCrop(); e.preventDefault();
  }
  _onCropUp() { this._dragging = false; }
  _onCropWheel(e) {
    e.preventDefault();
    this._cropScale = Math.max(0.1, Math.min(5, this._cropScale + (e.deltaY > 0 ? -0.05 : 0.05)));
    this._drawCrop();
  }

  async _uploadCropped() {
    if (!this._cropFile || !this._cropImage) return;
    this._toast("Uploading...");
    const s = this._cropScale, img = this._cropImage;
    const dw = this._config.display_width, dh = this._config.display_height;
    const cx = Math.max(0, -this._cropX / s), cy = Math.max(0, -this._cropY / s);
    const cw = Math.min(img.width - cx, dw / s), ch = Math.min(img.height - cy, dh / s);
    const fd = new FormData(); fd.append("file", this._cropFile);
    const p = new URLSearchParams({
      title: this._cropFile.name,
      crop_x: Math.round(cx), crop_y: Math.round(cy),
      crop_width: Math.round(cw), crop_height: Math.round(ch),
    });
    try {
      const r = await fetch(this._url(`/api/upload?${p}`), { method: "POST", body: fd });
      const d = await r.json();
      this._toast(d.status === "sent" ? "Sent!" : "Failed");
      if (d.status === "sent") {
        this._cropImage = null; this._cropFile = null;
        setTimeout(() => this._loadHistory(), 2000);
      }
    } catch (e) { this._toast("Error: " + e.message); }
    this._render();
  }

  // --- Render ---
  _render() {
    // If the shell is already built, just update dynamic parts
    if (this.shadowRoot.getElementById("tab-body")) {
      this._updateDynamic();
      return;
    }
    this._renderFull();
  }

  _updateDynamic() {
    const status = this._hass?.states?.["sensor.samsung_epaper_status"];
    const preset = this._hass?.states?.["select.samsung_epaper_active_preset"];
    const reachable = this._hass?.states?.["binary_sensor.samsung_epaper_reachable"];

    // Update status bar — prefer locally tracked name over HA entity
    const metaEl = this.shadowRoot.getElementById("status-meta");
    if (metaEl) {
      const name = this._currentName || preset?.state || "No preset";
      const t = this._lastDisplayedAt || status?.attributes?.last_update;
      metaEl.innerHTML = `
        <span class="meta-label">${name}</span>
        <span class="meta-sep">&middot;</span>
        <span class="meta-time">${status?.state === "updating" ? "Updating..." : timeAgo(t)}</span>
      `;
    }

    // Update refresh button state
    const refreshBtn = this.shadowRoot.getElementById("btn-refresh");
    if (refreshBtn) {
      const online = reachable?.state === "on";
      refreshBtn.className = `btn-status ${online ? "" : "offline"}`;
      refreshBtn.innerHTML = `
        <span class="dot ${online ? "on" : "off"}"></span>
        ${status?.state === "updating" ? "Updating..." : (online ? "Online" : "Offline")}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M23 4v6h-6M1 20v-6h6"/>
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>
      `;
    }

    // Update tab highlights
    this.shadowRoot.querySelectorAll(".tab").forEach(t => {
      t.classList.toggle("active", t.dataset.tab === this._activeTab);
    });

    // Update tab body content
    const tabBody = this.shadowRoot.getElementById("tab-body");
    if (tabBody) {
      tabBody.innerHTML = this._renderTab();
      this._bindTabContent();
    }

    // Update preview image
    const previewImg = this.shadowRoot.getElementById("preview-img");
    const placeholder = this.shadowRoot.getElementById("preview-placeholder");
    const previewUrl = this._getPreviewUrl();
    if (previewImg && previewUrl) {
      if (previewImg.getAttribute("src") !== previewUrl) previewImg.src = previewUrl;
      previewImg.style.display = "";
      if (placeholder) placeholder.style.display = "none";
    }
  }

  _renderFull() {
    const status = this._hass?.states?.["sensor.samsung_epaper_status"];
    const preset = this._hass?.states?.["select.samsung_epaper_active_preset"];
    const camera = this._hass?.states?.["camera.samsung_epaper_display_preview"];
    const reachable = this._hass?.states?.["binary_sensor.samsung_epaper_reachable"];
    const camUrl = camera
      ? `/api/camera_proxy/${camera.entity_id}?token=${camera.attributes.access_token}`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; font-family:var(--primary-font-family,sans-serif); }

        /* --- Layout --- */
        .outer {
          padding:24px;
          min-height:calc(100vh - 112px);
          display:flex; align-items:center; justify-content:center;
        }
        .layout {
          display:flex; gap:24px; align-items:stretch;
          width:100%; max-width:900px;
        }
        .left-col {
          flex:0 0 auto; display:flex; flex-direction:column; align-items:center;
        }

        /* --- Photo Frame Overlay --- */
        .frame-wrap {
          position:relative;
          width:220px;
          aspect-ratio:437/679;
        }
        .frame-overlay {
          position:absolute; top:0; left:0; width:100%; height:100%;
          background:url('/local/epaper-frame.png') center/contain no-repeat;
          z-index:2; pointer-events:none;
        }
        .frame-inner {
          position:absolute;
          top:10%; bottom:10%; left:16.5%; right:16%;
          overflow:hidden; background:#000;
          z-index:1;
        }
        .frame-inner img {
          width:100%; height:100%;
          display:block;
        }
        .frame-placeholder {
          width:100%; height:100%;
          display:flex; align-items:center; justify-content:center;
          color:#555; font-size:12px; text-align:center; padding:16px;
        }
        .status-bar {
          display:flex; align-items:center; gap:8px;
          padding:0 0 12px; margin-bottom:10px; font-size:12px;
          color:var(--primary-text-color);
          border-bottom:1px solid var(--divider-color, #e8e8e8);
        }
        .status-bar .meta { flex:1; min-width:0; display:flex; align-items:center; gap:6px; }
        .status-bar .meta-label { font-weight:500; }
        .status-bar .meta-sep { opacity:0.3; }
        .status-bar .meta-time { opacity:0.5; font-size:11px; }

        /* --- Card (right side) --- */
        .right-col { flex:1; min-width:0; display:flex; flex-direction:column; }
        .card {
          flex:1; display:flex; flex-direction:column;
          background:var(--ha-card-background,var(--card-background-color,#fff));
          border-radius:var(--ha-card-border-radius,12px);
          box-shadow:var(--ha-card-box-shadow,0 2px 6px rgba(0,0,0,.15));
          padding:16px; color:var(--primary-text-color);
          margin-top:12px;
        }
        .dot { width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px; }
        .btn-status {
          display:flex; align-items:center; gap:5px;
          padding:5px 12px 5px 10px; border-radius:20px; border:none; cursor:pointer;
          font-size:11px; font-family:inherit; font-weight:500; letter-spacing:0.3px;
          background:rgba(76,175,80,0.08); color:#4caf50;
          transition:all .2s;
        }
        .btn-status.offline { background:rgba(244,67,54,0.08); color:#f44336; }
        .btn-status:hover { background:rgba(76,175,80,0.18); }
        .btn-status.offline:hover { background:rgba(244,67,54,0.18); }
        .btn-status svg {
          opacity:0.6; transition:opacity .2s, transform .3s;
        }
        .btn-status:hover svg { opacity:1; transform:rotate(45deg); }
        .dot.on { background:#4caf50; } .dot.off { background:#f44336; }
        .tabs { display:flex; gap:4px; margin-bottom:12px; }
        .tab {
          padding:5px 12px; border-radius:6px; cursor:pointer; font-size:12px;
          background:transparent; border:none; color:var(--secondary-text-color); font-family:inherit;
        }
        .tab.active { background:var(--primary-color,#03a9f4); color:#fff; }
        .tab:hover:not(.active) { background:var(--secondary-background-color,#f5f5f5); }
        .tab-body { flex:1; min-height:120px; display:flex; flex-direction:column; }
        .btn {
          padding:7px 14px; border-radius:6px; border:none; cursor:pointer;
          font-size:12px; font-family:inherit; background:var(--primary-color,#03a9f4); color:#fff;
        }
        .btn:hover { opacity:.85; }
        .btn.sm { padding:5px 10px; font-size:11px; }
        .btn.secondary { background:var(--secondary-background-color,#e0e0e0); color:var(--primary-text-color); }
        .btn-row { display:flex; gap:6px; margin-top:10px; flex-wrap:wrap; align-items:center; }
        .url-row { display:flex; gap:6px; margin-top:8px; }
        .url-row input {
          flex:1; padding:7px 10px; border:1px solid var(--divider-color,#ccc);
          border-radius:6px; font-size:12px; background:var(--card-background-color,#fff);
          color:var(--primary-text-color); font-family:inherit;
        }
        .upload-area {
          border:2px dashed var(--divider-color,#ccc); border-radius:8px;
          padding:28px; text-align:center; cursor:pointer;
          flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
        }
        .upload-area:hover { border-color:var(--primary-color,#03a9f4); background:rgba(3,169,244,0.02); }
        .upload-area.drag-over {
          border-color:var(--primary-color,#03a9f4);
          background:rgba(3,169,244,0.06);
          transform:scale(1.01);
        }
        .upload-area input[type=file] { display:none; }
        .drop-icon { margin-bottom:8px; }
        .spinner {
          width:24px; height:24px; border:3px solid var(--divider-color,#ddd);
          border-top-color:var(--primary-color,#03a9f4); border-radius:50%;
          animation:spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform:rotate(360deg); } }
        .crop-wrap { height:320px; display:flex; align-items:center; justify-content:center; background:#111; border-radius:8px; overflow:hidden; }
        #crop-canvas { cursor:grab; display:block; height:100%; }
        #crop-canvas:active { cursor:grabbing; }
        .crop-bar { display:flex; justify-content:center; gap:6px; margin-top:6px; align-items:center; font-size:11px; }
        .gallery {
          display:grid; grid-template-columns:repeat(auto-fill,minmax(65px,1fr));
          gap:6px; align-content:start; flex:1;
        }
        .gallery-item {
          aspect-ratio:9/16; border-radius:5px; overflow:hidden; cursor:pointer;
          background:#111; transition:transform .15s,box-shadow .15s; position:relative;
        }
        .gallery-item:hover { transform:scale(1.05); box-shadow:0 2px 8px rgba(0,0,0,.3); }
        .gallery-item img { width:100%; height:100%; object-fit:cover; }
        .gallery-item .lbl {
          position:absolute; bottom:0; left:0; right:0; background:rgba(0,0,0,.7);
          color:#fff; font-size:8px; padding:2px 3px; white-space:nowrap;
          overflow:hidden; text-overflow:ellipsis;
        }
        .empty { text-align:center; padding:20px; color:var(--secondary-text-color); font-size:12px; flex:1; display:flex; align-items:center; justify-content:center; }
        .fav-layout { display:flex; gap:12px; flex:1; min-height:0; }
        .folder-sidebar {
          width:140px; flex-shrink:0; display:flex; flex-direction:column; gap:4px;
          overflow-y:auto;
        }
        .folder-item {
          display:flex; align-items:center; gap:6px; padding:8px 10px;
          border-radius:8px; cursor:pointer; font-size:12px;
          background:transparent; border:none; font-family:inherit;
          color:var(--primary-text-color); transition:all .15s;
          text-align:left; position:relative;
        }
        .folder-item:hover { background:var(--secondary-background-color,#f5f5f5); }
        .folder-item.active {
          background:var(--primary-color,#03a9f4); color:#fff;
        }
        .folder-item .folder-icon { flex-shrink:0; opacity:0.5; }
        .folder-item.active .folder-icon { opacity:1; }
        .folder-item .folder-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .folder-item .folder-count {
          font-size:10px; opacity:0.5; background:rgba(0,0,0,0.06);
          padding:1px 5px; border-radius:8px; flex-shrink:0;
        }
        .folder-item.active .folder-count { background:rgba(255,255,255,0.2); opacity:1; }
        .folder-item .folder-actions {
          display:none; gap:1px; margin-left:auto; flex-shrink:0;
        }
        .folder-item:hover .folder-actions { display:flex; }
        .folder-item:hover .folder-count { display:none; }
        .folder-action-btn {
          width:20px; height:20px; border:none; border-radius:4px; cursor:pointer;
          display:flex; align-items:center; justify-content:center;
          background:transparent; color:inherit; font-size:10px; padding:0;
          opacity:0.5; transition:all .15s;
        }
        .folder-action-btn:hover { opacity:1; background:rgba(0,0,0,0.1); }
        .folder-item.active .folder-action-btn { color:#fff; }
        .folder-item.active .folder-action-btn:hover { background:rgba(255,255,255,0.2); }
        /* Move-to popover */
        .move-popover {
          position:absolute; z-index:100; background:var(--card-background-color,#fff);
          border-radius:8px; box-shadow:0 4px 20px rgba(0,0,0,.2); padding:4px;
          min-width:160px; max-height:200px; overflow-y:auto;
        }
        .move-popover-item {
          display:flex; align-items:center; gap:6px; padding:7px 10px;
          border-radius:6px; cursor:pointer; font-size:12px;
          border:none; background:transparent; width:100%; text-align:left;
          font-family:inherit; color:var(--primary-text-color); transition:background .1s;
        }
        .move-popover-item:hover { background:var(--secondary-background-color,#f0f0f0); }
        .move-popover-item.current { opacity:0.4; pointer-events:none; }
        .move-popover-backdrop { position:fixed; top:0; left:0; right:0; bottom:0; z-index:99; }
        .folder-add {
          display:flex; align-items:center; gap:6px; padding:8px 10px;
          border-radius:8px; cursor:pointer; font-size:11px;
          border:1px dashed var(--divider-color,#ddd); background:transparent;
          color:var(--secondary-text-color); font-family:inherit;
          transition:all .15s; margin-top:4px;
        }
        .folder-add:hover { border-color:var(--primary-color,#03a9f4); background:rgba(3,169,244,0.04); }
        .folder-divider { height:1px; background:var(--divider-color,#e8e8e8); margin:4px 0; }
        .fav-gallery-area { flex:1; min-width:0; overflow-y:auto; }
        .sub-tabs {
          display:flex; gap:0; margin-bottom:14px;
          border:1px solid var(--divider-color,#e0e0e0);
          border-radius:10px; overflow:hidden;
        }
        .sub-tab {
          flex:1; padding:9px 8px; border:none; cursor:pointer;
          font-size:12px; font-family:inherit; text-align:center;
          background:transparent; color:var(--secondary-text-color);
          transition:all .2s; position:relative;
          border-right:1px solid var(--divider-color,#e0e0e0);
        }
        .sub-tab:last-child { border-right:none; }
        .sub-tab:hover:not(.active) { background:var(--secondary-background-color,#f8f8f8); }
        .sub-tab.active {
          background:var(--primary-color,#03a9f4); color:#fff;
          font-weight:600; letter-spacing:0.3px;
          border-right-color:var(--primary-color,#03a9f4);
        }
        .sub-tab .sub-icon { display:block; font-size:16px; margin-bottom:2px; }
        .sub-tab.active .sub-icon { filter:brightness(10); }
        .mode-select {
          width:100%; padding:8px 10px; border:1px solid var(--divider-color,#ccc);
          border-radius:6px; font-size:12px; font-family:inherit;
          background:var(--card-background-color,#fff); color:var(--primary-text-color);
          margin-bottom:10px;
        }
        .mode-desc { font-size:11px; color:var(--secondary-text-color); margin-bottom:12px; line-height:1.4; }
        .ai-file-row { display:flex; gap:8px; align-items:center; margin-bottom:10px; }
        .ai-file-row label {
          padding:7px 14px; border-radius:6px; cursor:pointer; font-size:12px;
          background:var(--secondary-background-color,#e0e0e0); color:var(--primary-text-color);
        }
        .ai-file-row label:hover { opacity:.8; }
        .ai-file-row .filename { flex:1; font-size:11px; color:var(--secondary-text-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .generating { text-align:center; padding:30px; color:var(--secondary-text-color); }
        .generating .spinner { display:inline-block; width:24px; height:24px; border:3px solid var(--divider-color,#ccc); border-top-color:var(--primary-color,#03a9f4); border-radius:50%; animation:spin 1s linear infinite; margin-bottom:8px; }
        @keyframes spin { to { transform:rotate(360deg); } }
        .schedule-item, .fav-item {
          display:flex; align-items:center; gap:8px; padding:8px 10px;
          border-radius:6px; font-size:12px;
          background:var(--secondary-background-color,#f5f5f5);
          margin-bottom:6px;
        }
        .schedule-item .name, .fav-item .name { flex:1; font-weight:500; }
        .schedule-item .cron { opacity:0.5; font-size:11px; font-family:monospace; }
        .schedule-item .actions, .fav-item .actions { display:flex; gap:4px; }
        .icon-btn {
          width:28px; height:28px; border-radius:6px; border:none; cursor:pointer;
          display:flex; align-items:center; justify-content:center;
          background:transparent; color:var(--secondary-text-color);
          transition:background .15s;
        }
        .icon-btn:hover { background:var(--divider-color,#e0e0e0); }
        .icon-btn.active { color:#f44336; }
        .fav-thumb { width:28px; height:50px; border-radius:4px; overflow:hidden; background:#111; flex-shrink:0; }
        .fav-thumb img { width:100%; height:100%; object-fit:cover; }
        .item-actions {
          position:absolute; top:3px; right:3px;
          display:flex; gap:2px; opacity:0; transition:opacity .15s;
        }
        .gallery-item:hover .item-actions { opacity:1; }
        .overlay-btn {
          width:20px; height:20px; border-radius:4px; border:none; cursor:pointer;
          display:flex; align-items:center; justify-content:center;
          background:rgba(0,0,0,.6); color:#fff; font-size:12px;
          transition:background .15s;
        }
        .overlay-btn:hover { background:rgba(0,0,0,.8); }
        .overlay-btn.active { color:#f44336; }
        #toast {
          position:fixed; bottom:20px; left:50%; transform:translateX(-50%) translateY(80px);
          background:var(--primary-color,#03a9f4); color:#fff; padding:8px 18px;
          border-radius:8px; font-size:13px; transition:transform .3s; z-index:9999; pointer-events:none;
        }
        #toast.show { transform:translateX(-50%) translateY(0); }
      </style>

      <div class="outer">
      <div class="layout">
        <!-- Left: Framed Preview -->
        <div class="left-col">
          <div class="frame-wrap">
            <div class="frame-overlay"></div>
            <div class="frame-inner">
              <img id="preview-img" src="${this._getPreviewUrl()}" alt="Display"
                style="${this._getPreviewUrl() ? "" : "display:none"}" />
              ${this._getPreviewUrl() ? "" : `<div class="frame-placeholder" id="preview-placeholder">No image displayed</div>`}
            </div>
          </div>
        </div>

        <!-- Right: Controls -->
        <div class="right-col">
          <div class="card">
            <div class="status-bar">
              <div class="meta" id="status-meta">
                <span class="meta-label">${preset?.state || "No preset"}</span>
                <span class="meta-sep">&middot;</span>
                <span class="meta-time">${status?.state === "updating" ? "Updating..." : timeAgo(status?.attributes?.last_update)}</span>
              </div>
              <button class="btn-status ${reachable?.state === "on" ? "" : "offline"}" id="btn-refresh" title="Refresh display">
                <span class="dot ${reachable?.state === "on" ? "on" : "off"}"></span>
                ${status?.state === "updating" ? "Updating..." : (reachable?.state === "on" ? "Online" : "Offline")}
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M23 4v6h-6M1 20v-6h6"/>
                  <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </svg>
              </button>
            </div>
            <div class="tabs">
              <button class="tab ${this._activeTab === "create" ? "active" : ""}" data-tab="create">Create</button>
              <button class="tab ${this._activeTab === "history" ? "active" : ""}" data-tab="history">History</button>
              <button class="tab ${this._activeTab === "favourites" ? "active" : ""}" data-tab="favourites">Favourites</button>
              <button class="tab ${this._activeTab === "schedules" ? "active" : ""}" data-tab="schedules">Schedules</button>
            </div>
            <div class="tab-body" id="tab-body">${this._renderTab()}</div>
          </div>
        </div>
      </div>
      </div>
      <div id="toast"></div>
    `;
    this._bind();
  }

  _renderTab() {
    switch (this._activeTab) {
      case "create":
        const subTabs = `
          <div class="sub-tabs">
            <button class="sub-tab ${this._createMode === "upload" ? "active" : ""}" data-mode="upload">
              <span class="sub-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              </span>Upload
            </button>
            <button class="sub-tab ${this._createMode === "ai" ? "active" : ""}" data-mode="ai">
              <span class="sub-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
              </span>AI Art
            </button>
            <button class="sub-tab ${this._createMode === "newspaper" ? "active" : ""}" data-mode="newspaper">
              <span class="sub-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 22h16a2 2 0 002-2V4a2 2 0 00-2-2H8a2 2 0 00-2 2v16a2 2 0 01-2 2zm0 0a2 2 0 01-2-2v-9c0-1.1.9-2 2-2h2"/><line x1="10" y1="6" x2="18" y2="6"/><line x1="10" y1="10" x2="18" y2="10"/><line x1="10" y1="14" x2="14" y2="14"/></svg>
              </span>Newspaper
            </button>
          </div>`;

        if (this._createMode === "upload") {
          if (this._cropImage) return subTabs + `
            <div class="crop-wrap"><canvas id="crop-canvas"></canvas></div>
            <div class="crop-bar">
              <button class="btn sm secondary" id="btn-zout">-</button>
              <span>${Math.round(this._cropScale * 100)}%</span>
              <button class="btn sm secondary" id="btn-zin">+</button>
              <span style="flex:1"></span>
              <button class="btn sm secondary" id="btn-cancel">Cancel</button>
              <button class="btn sm" id="btn-upload">Send to Display</button>
            </div>`;
          return subTabs + `
            <div class="upload-area" id="upload-area">
              <input type="file" id="file-input" accept="image/*" />
              <div class="drop-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                  <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
                </svg>
              </div>
              <div style="font-size:13px">Drop an image here or click to browse</div>
              <div style="font-size:11px;color:var(--secondary-text-color);margin-top:4px">
                Then crop &amp; position for the display
              </div>
            </div>`;
        }

        if (this._createMode === "ai") {
          if (this._generatingJob) return subTabs + `
            <div class="generating">
              <div class="spinner"></div>
              <div>Generating artwork...</div>
              <div style="font-size:11px;margin-top:4px">This may take up to a minute</div>
            </div>`;
          const types = this._genTypes?.ai_art || [];
          const sel = types.find(t => t.key === this._selectedArtType);
          const fileCount = this._aiFiles?.length || 0;
          return subTabs + `
            <select class="mode-select" id="ai-type-select">
              ${types.map(t => `<option value="${t.key}" ${t.key === this._selectedArtType ? "selected" : ""}>${t.name}</option>`).join("")}
            </select>
            <div class="upload-area" id="ai-drop-area" style="min-height:100px">
              <input type="file" id="ai-file-input" accept="image/*" multiple />
              <div class="drop-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                  <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
                </svg>
              </div>
              ${fileCount > 0
                ? `<div style="font-size:13px;font-weight:500">${fileCount} photo${fileCount > 1 ? "s" : ""} selected</div>
                   <div style="font-size:11px;color:var(--secondary-text-color);margin-top:2px">${this._aiFiles.map(f => f.name).join(", ")}</div>`
                : `<div style="font-size:13px">Drop photos here or click to browse</div>
                   <div style="font-size:11px;color:var(--secondary-text-color);margin-top:4px">
                     Select one or more photos to transform
                   </div>`}
            </div>
            <button class="btn" id="btn-generate-art" style="width:100%;margin-top:10px" ${fileCount === 0 ? "disabled" : ""}>
              Generate${fileCount > 1 ? ` ${fileCount} Artworks` : ""} & Display
            </button>`;
        }

        if (this._createMode === "newspaper") {
          if (this._generatingJob) return subTabs + `
            <div class="generating">
              <div class="spinner"></div>
              <div>Fetching front page...</div>
            </div>`;
          const papers = this._genTypes?.frontpage || [];
          return subTabs + `
            <select class="mode-select" id="newspaper-select">
              ${papers.map(p => `<option value="${p.key}" ${p.key === this._selectedNewspaper ? "selected" : ""}>${p.name}</option>`).join("")}
            </select>
            <button class="btn" id="btn-generate-newspaper">Fetch & Display</button>`;
        }
        return subTabs;
      case "history":
        if (!this._assets.length) return `<div class="empty">No history yet</div>`;
        return `<div class="gallery">${this._assets
          .filter(a => a.filename_thumbnail)
          .map(a => {
            const isFav = this._favourites.some(f => f.asset_id === a.id);
            return `<div class="gallery-item" data-id="${a.id}">
              <img src="${this._url(`/api/assets/${a.id}/thumbnail`)}" loading="lazy" />
              <div class="lbl">${a.title || a.source_type}</div>
              <div class="item-actions">
                <button class="overlay-btn fav-btn ${isFav ? "active" : ""}" data-fav-asset="${a.id}"
                  title="${isFav ? "Unfavourite" : "Favourite"}">
                  ${isFav ? "&#9829;" : "&#9825;"}
                </button>
                <button class="overlay-btn del-btn" data-del-asset="${a.id}" title="Delete">
                  &times;
                </button>
              </div>
            </div>`;
          }).join("")}</div>`;

      case "favourites":
        const fSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>';
        const fSvgSm = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>';
        const pencilSvg = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';

        // Count favourites per folder
        const favCounts = {};
        let totalFavs = 0;
        for (const f of this._favourites) {
          totalFavs++;
          const cid = f.collection_id || "__all__";
          favCounts[cid] = (favCounts[cid] || 0) + 1;
        }

        const sidebar = `<div class="folder-sidebar">
          <button class="folder-item ${this._currentCollectionId === null ? "active" : ""}" data-folder-id="all">
            <span class="folder-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            </span>
            <span class="folder-name">All</span>
            <span class="folder-count">${totalFavs}</span>
          </button>
          <div class="folder-divider"></div>
          ${this._collections.map(c => {
            const count = favCounts[c.id] || 0;
            const isActive = this._currentCollectionId === c.id;
            return `<button class="folder-item ${isActive ? "active" : ""}" data-folder-id="${c.id}">
              <span class="folder-icon">${fSvg}</span>
              <span class="folder-name">${c.name}</span>
              <span class="folder-count">${count}</span>
              <span class="folder-actions">
                <button class="folder-action-btn" data-rename-col="${c.id}" title="Rename">${pencilSvg}</button>
                <button class="folder-action-btn" data-del-col="${c.id}" title="Delete">&times;</button>
              </span>
            </button>`;
          }).join("")}
          <button class="folder-add" id="btn-add-folder">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New Folder
          </button>
        </div>`;

        const filtered = this._currentCollectionId
          ? this._favourites.filter(f => f.collection_id === this._currentCollectionId)
          : this._favourites;

        const activeFolder = this._collections.find(c => c.id === this._currentCollectionId);
        const galleryTitle = activeFolder ? activeFolder.name : "All Favourites";

        let galleryContent;
        if (!this._favourites.length) {
          galleryContent = `<div class="empty">No favourites yet.<br/>Click the heart on any image in History.</div>`;
        } else if (!filtered.length) {
          galleryContent = `<div class="empty">This folder is empty.<br/>Drag images here or use the move button.</div>`;
        } else {
          galleryContent = `<div class="gallery">${filtered.map(f => {
            const asset = this._assetMap?.[f.asset_id];
            const label = f.name || asset?.title || asset?.filename_original || "Untitled";
            return `<div class="gallery-item" data-id="${f.asset_id}">
              <img src="${this._url(`/api/assets/${f.asset_id}/thumbnail`)}" loading="lazy" />
              <div class="lbl">${label}</div>
              <div class="item-actions">
                <button class="overlay-btn" data-move-fav="${f.id}" title="Move to folder">${fSvgSm}</button>
                <button class="overlay-btn" data-rename-fav="${f.id}" title="Rename">${pencilSvg}</button>
                <button class="overlay-btn fav-btn active" data-fav-asset="${f.asset_id}" title="Unfavourite">&#9829;</button>
              </div>
            </div>`;
          }).join("")}</div>`;
        }

        return `<div class="fav-layout">
          ${sidebar}
          <div class="fav-gallery-area">${galleryContent}</div>
        </div>`;

      case "schedules":
        const items = this._schedules.map(s => `
          <div class="schedule-item">
            <div style="width:8px;height:8px;border-radius:50;background:${s.is_enabled ? "#4caf50" : "#999"}"></div>
            <div class="name">${s.name}</div>
            <div class="cron">${s.cron_expression}</div>
            <div class="actions">
              <button class="icon-btn" data-run-schedule="${s.id}" title="Run now">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
              </button>
              <button class="icon-btn" data-toggle-schedule="${s.id}" data-enabled="${s.is_enabled}" title="${s.is_enabled ? "Disable" : "Enable"}">
                ${s.is_enabled
                  ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="10" y1="15" x2="10" y2="9"/><line x1="14" y1="15" x2="14" y2="9"/></svg>'
                  : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10,8 16,12 10,16" fill="currentColor"/></svg>'}
              </button>
              <button class="icon-btn" data-del-schedule="${s.id}" title="Delete">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>`).join("");
        return items || `<div class="empty">No schedules. Use HA services to create one.</div>`;

      default: return "";
    }
  }

  _bind() {
    // One-time shell bindings
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._activeTab = t.dataset.tab;
        this._updateDynamic();
        if (t.dataset.tab === "history") this._loadHistory();
        if (t.dataset.tab === "favourites") this._loadFavourites();
        if (t.dataset.tab === "schedules") this._loadSchedules();
        if (t.dataset.tab === "create") this._loadGenTypes();
        if (t.dataset.tab === "create" && this._createMode === "upload" && this._cropImage)
          requestAnimationFrame(() => this._drawCrop());
      })
    );
    this.shadowRoot.getElementById("btn-refresh")?.addEventListener("click", () => this._refresh());
    this._bindTabContent();
  }

  _bindTabContent() {
    // Sub-tab switching within Create
    this.shadowRoot.querySelectorAll(".sub-tab").forEach(st =>
      st.addEventListener("click", () => {
        this._createMode = st.dataset.mode;
        this._updateDynamic();
      })
    );

    if (this._activeTab === "create" && this._createMode === "ai") {
      this.shadowRoot.getElementById("ai-type-select")?.addEventListener("change", (e) => {
        this._selectedArtType = e.target.value;
        this._updateDynamic();
      });
      const aiArea = this.shadowRoot.getElementById("ai-drop-area");
      const aiFi = this.shadowRoot.getElementById("ai-file-input");
      aiArea?.addEventListener("click", () => aiFi?.click());
      aiFi?.addEventListener("change", () => {
        this._aiFiles = Array.from(aiFi.files || []);
        this._updateDynamic();
      });
      aiArea?.addEventListener("dragover", e => { e.preventDefault(); aiArea.classList.add("drag-over"); });
      aiArea?.addEventListener("dragleave", () => aiArea.classList.remove("drag-over"));
      aiArea?.addEventListener("drop", e => {
        e.preventDefault();
        aiArea.classList.remove("drag-over");
        const files = Array.from(e.dataTransfer?.files || []).filter(f => f.type.startsWith("image/"));
        if (files.length) {
          this._aiFiles = [...this._aiFiles, ...files];
          this._updateDynamic();
        }
      });
      this.shadowRoot.getElementById("btn-generate-art")?.addEventListener("click", () => this._generateArt());
    }

    if (this._activeTab === "create" && this._createMode === "newspaper") {
      this.shadowRoot.getElementById("newspaper-select")?.addEventListener("change", (e) => {
        this._selectedNewspaper = e.target.value;
      });
      this.shadowRoot.getElementById("btn-generate-newspaper")?.addEventListener("click", () => this._generateNewspaper());
    }

    if (this._activeTab === "create" && this._createMode === "upload") {
      const area = this.shadowRoot.getElementById("upload-area");
      const fi = this.shadowRoot.getElementById("file-input");
      area?.addEventListener("click", () => fi?.click());
      fi?.addEventListener("change", e => this._onFileSelect(e));
      // Drag and drop
      area?.addEventListener("dragover", e => { e.preventDefault(); area.classList.add("drag-over"); });
      area?.addEventListener("dragleave", () => area.classList.remove("drag-over"));
      area?.addEventListener("drop", e => {
        e.preventDefault();
        area.classList.remove("drag-over");
        const file = e.dataTransfer?.files?.[0];
        if (file && file.type.startsWith("image/")) {
          // Reuse the same handler by setting the file input
          const dt = new DataTransfer();
          dt.items.add(file);
          fi.files = dt.files;
          fi.dispatchEvent(new Event("change"));
        }
      });
      const cv = this.shadowRoot.getElementById("crop-canvas");
      if (cv && this._cropImage) {
        cv.addEventListener("mousedown", e => this._onCropDown(e));
        cv.addEventListener("mousemove", e => this._onCropMove(e));
        cv.addEventListener("mouseup", () => this._onCropUp());
        cv.addEventListener("mouseleave", () => this._onCropUp());
        cv.addEventListener("wheel", e => this._onCropWheel(e), { passive: false });
        cv.addEventListener("touchstart", e => this._onCropDown(e), { passive: false });
        cv.addEventListener("touchmove", e => this._onCropMove(e), { passive: false });
        cv.addEventListener("touchend", () => this._onCropUp());
        this.shadowRoot.getElementById("btn-upload")?.addEventListener("click", () => this._uploadCropped());
        this.shadowRoot.getElementById("btn-cancel")?.addEventListener("click", () => {
          this._cropImage = null; this._cropFile = null; this._render();
        });
        this.shadowRoot.getElementById("btn-zin")?.addEventListener("click", () => {
          this._cropScale = Math.min(5, this._cropScale + 0.1); this._drawCrop();
        });
        this.shadowRoot.getElementById("btn-zout")?.addEventListener("click", () => {
          this._cropScale = Math.max(0.1, this._cropScale - 0.1); this._drawCrop();
        });
        requestAnimationFrame(() => this._drawCrop());
      }
    }
    if (this._activeTab === "url") {
      this.shadowRoot.getElementById("btn-url")?.addEventListener("click", () => this._displayUrl());
      this.shadowRoot.getElementById("url-input")?.addEventListener("keydown", e => { if (e.key === "Enter") this._displayUrl(); });
    }
    if (this._activeTab === "history" || this._activeTab === "favourites") {
      this.shadowRoot.querySelectorAll(".gallery-item").forEach(i =>
        i.addEventListener("click", (e) => {
          if (e.target.closest(".overlay-btn")) return;
          // Use favourite name if on favourites tab
          let name = null;
          if (this._activeTab === "favourites") {
            const fav = this._favourites.find(f => f.asset_id === i.dataset.id);
            if (fav?.name) name = fav.name;
          }
          this._displayAsset(i.dataset.id, name);
        })
      );
      this.shadowRoot.querySelectorAll(".fav-btn").forEach(b =>
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          this._toggleFavourite(b.dataset.favAsset);
        })
      );
      // Folder navigation
      this.shadowRoot.querySelectorAll("[data-folder-id]").forEach(b =>
        b.addEventListener("click", (e) => {
          if (e.target.closest(".folder-action-btn")) return;
          this._currentCollectionId = b.dataset.folderId === "all" ? null : b.dataset.folderId;
          this._updateDynamic();
        })
      );
      this.shadowRoot.getElementById("btn-add-folder")?.addEventListener("click", () => this._createCollection());
      this.shadowRoot.querySelectorAll("[data-rename-col]").forEach(b =>
        b.addEventListener("click", (e) => { e.stopPropagation(); this._renameCollection(b.dataset.renameCol); })
      );
      this.shadowRoot.querySelectorAll("[data-del-col]").forEach(b =>
        b.addEventListener("click", (e) => { e.stopPropagation(); this._deleteCollection(b.dataset.delCol); })
      );

      this.shadowRoot.querySelectorAll("[data-move-fav]").forEach(b =>
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          this._showMovePopover(b.dataset.moveFav, b);
        })
      );
      this.shadowRoot.querySelectorAll("[data-del-asset]").forEach(b =>
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          this._deleteAsset(b.dataset.delAsset);
        })
      );
      this.shadowRoot.querySelectorAll("[data-rename-fav]").forEach(b =>
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          this._renameFavourite(b.dataset.renameFav);
        })
      );
    }
    if (this._activeTab === "schedules") {
      this.shadowRoot.querySelectorAll("[data-run-schedule]").forEach(b =>
        b.addEventListener("click", () => this._runSchedule(b.dataset.runSchedule))
      );
      this.shadowRoot.querySelectorAll("[data-toggle-schedule]").forEach(b =>
        b.addEventListener("click", () => this._toggleSchedule(b.dataset.toggleSchedule, b.dataset.enabled === "true"))
      );
      this.shadowRoot.querySelectorAll("[data-del-schedule]").forEach(b =>
        b.addEventListener("click", () => this._deleteSchedule(b.dataset.delSchedule))
      );
    }
  }

  getCardSize() { return 8; }
}

customElements.define("samsung-epaper-card", SamsungEpaperCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "samsung-epaper-card", name: "Samsung ePaper Display",
  description: "Control your Samsung ePaper display with baroque frame preview", preview: true,
});
console.info(`%c SAMSUNG-EPAPER %c v${CARD_VERSION} `, "color:#fff;background:#8B6914;font-weight:bold;padding:2px 6px;border-radius:4px 0 0 4px", "color:#8B6914;background:#FFF8E7;font-weight:bold;padding:2px 6px;border-radius:0 4px 4px 0");
