/**
 * Samsung ePaper Display — Custom Lovelace Card v3
 * Baroque-framed preview with controls below.
 */
const CARD_VERSION = "3.3.0";

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
    this._activeTab = "upload";
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
    this._render();
    this._loadHistory();
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

  async _refresh() { this._toast("Refreshing..."); await this._svc("refresh"); }
  async _displayAsset(id) { this._toast("Sending..."); await this._svc("display_asset", { asset_id: id }); }
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
    const status = this._hass?.states?.["sensor.samsung_epaper_status"];
    const preset = this._hass?.states?.["select.samsung_epaper_active_preset"];
    const camera = this._hass?.states?.["camera.samsung_epaper_display_preview"];
    const reachable = this._hass?.states?.["binary_sensor.samsung_epaper_reachable"];
    const camUrl = camera
      ? `/api/camera_proxy/${camera.entity_id}?token=${camera.attributes.access_token}&t=${Date.now()}`
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

        /* --- Baroque Frame --- */
        .baroque-frame {
          position:relative; display:inline-block;
          padding:14px;
          background: linear-gradient(135deg, #8B6914 0%, #D4A843 15%, #F5D98A 30%, #D4A843 45%, #8B6914 55%, #D4A843 70%, #F5D98A 85%, #8B6914 100%);
          border-radius:4px;
          box-shadow:
            0 0 0 2px #6B4F0A,
            0 0 0 4px #D4A843,
            0 0 0 6px #6B4F0A,
            inset 0 0 8px rgba(0,0,0,0.5),
            4px 6px 20px rgba(0,0,0,0.4),
            inset 2px 2px 4px rgba(255,235,180,0.3);
        }
        .baroque-frame::before {
          content:'';
          position:absolute; top:5px; left:5px; right:5px; bottom:5px;
          border:2px solid rgba(139,105,20,0.6);
          border-radius:2px;
          pointer-events:none;
        }
        .baroque-frame::after {
          content:'';
          position:absolute; top:9px; left:9px; right:9px; bottom:9px;
          border:1px solid rgba(212,168,67,0.4);
          pointer-events:none;
        }
        .frame-inner {
          position:relative;
          width:180px; height:320px;
          overflow:hidden; background:#111;
          box-shadow: inset 0 0 12px rgba(0,0,0,0.8);
        }
        .frame-inner img {
          width:100%; height:100%; object-fit:cover;
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
        .upload-area:hover { border-color:var(--primary-color,#03a9f4); }
        .upload-area input[type=file] { display:none; }
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
          <div class="baroque-frame">
            <div class="frame-inner">
              ${camUrl
                ? `<img src="${camUrl}" alt="Display" />`
                : `<div class="frame-placeholder">No image displayed</div>`}
            </div>
          </div>
        </div>

        <!-- Right: Controls -->
        <div class="right-col">
          <div class="card">
            <div class="status-bar">
              <div class="meta">
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
              <button class="tab ${this._activeTab === "upload" ? "active" : ""}" data-tab="upload">Upload</button>
              <button class="tab ${this._activeTab === "history" ? "active" : ""}" data-tab="history">History</button>
              <button class="tab ${this._activeTab === "favourites" ? "active" : ""}" data-tab="favourites">Favourites</button>
              <button class="tab ${this._activeTab === "schedules" ? "active" : ""}" data-tab="schedules">Schedules</button>
            </div>
            <div class="tab-body">${this._renderTab()}</div>
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
      case "upload":
        if (this._cropImage) return `
          <div class="crop-wrap"><canvas id="crop-canvas"></canvas></div>
          <div class="crop-bar">
            <button class="btn sm secondary" id="btn-zout">-</button>
            <span>${Math.round(this._cropScale * 100)}%</span>
            <button class="btn sm secondary" id="btn-zin">+</button>
            <span style="flex:1"></span>
            <button class="btn sm secondary" id="btn-cancel">Cancel</button>
            <button class="btn sm" id="btn-upload">Send to Display</button>
          </div>`;
        return `
          <div class="upload-area" id="upload-area">
            <input type="file" id="file-input" accept="image/*" />
            <div style="font-size:24px;margin-bottom:4px">+</div>
            <div style="font-size:13px">Select an image</div>
            <div style="font-size:11px;color:var(--secondary-text-color);margin-top:4px">
              Drag to position, scroll to zoom
            </div>
          </div>`;
      case "url":
        return `
          <p style="font-size:12px;color:var(--secondary-text-color);margin:0 0 6px">
            Paste an image URL to display on the panel.
          </p>
          <div class="url-row">
            <input id="url-input" type="text" placeholder="https://example.com/image.jpg" />
            <button class="btn sm" id="btn-url">Display</button>
          </div>`;
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
        if (!this._favourites.length) return `<div class="empty">No favourites yet. Click the heart on any image in History.</div>`;
        return `<div class="gallery">${this._favourites
          .map(f => {
            const asset = this._assetMap?.[f.asset_id];
            const label = f.name || asset?.title || asset?.filename_original || "Untitled";
            return `<div class="gallery-item" data-id="${f.asset_id}">
              <img src="${this._url(`/api/assets/${f.asset_id}/thumbnail`)}" loading="lazy" />
              <div class="lbl">${label}</div>
              <div class="item-actions">
                <button class="overlay-btn" data-rename-fav="${f.id}" title="Rename">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="overlay-btn fav-btn active" data-fav-asset="${f.asset_id}" title="Unfavourite">&#9829;</button>
              </div>
            </div>`;
          }).join("")}</div>`;

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
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._activeTab = t.dataset.tab; this._render();
        if (t.dataset.tab === "history") this._loadHistory();
        if (t.dataset.tab === "favourites") this._loadFavourites();
        if (t.dataset.tab === "schedules") this._loadSchedules();
        if (t.dataset.tab === "upload" && this._cropImage)
          requestAnimationFrame(() => this._drawCrop());
      })
    );
    this.shadowRoot.getElementById("btn-refresh")?.addEventListener("click", () => this._refresh());
    if (this._activeTab === "upload") {
      const area = this.shadowRoot.getElementById("upload-area");
      const fi = this.shadowRoot.getElementById("file-input");
      area?.addEventListener("click", () => fi?.click());
      fi?.addEventListener("change", e => this._onFileSelect(e));
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
          this._displayAsset(i.dataset.id);
        })
      );
      this.shadowRoot.querySelectorAll(".fav-btn").forEach(b =>
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          this._toggleFavourite(b.dataset.favAsset);
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
