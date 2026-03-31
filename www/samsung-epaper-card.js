/**
 * Samsung ePaper Display — Custom Lovelace Card v2
 * Side-by-side layout optimised for portrait displays.
 */
const CARD_VERSION = "2.0.0";

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
    this._hass = hass;
    this._render();
  }

  static getStubConfig() {
    return { addon_url: "http://192.168.50.84:8000" };
  }

  _url(path) { return `${this._config.addon_url}${path}`; }

  async _loadHistory() {
    try {
      const r = await fetch(this._url("/api/assets?limit=30"));
      if (r.ok) { this._assets = await r.json(); this._render(); }
    } catch (e) { console.error("History load failed:", e); }
  }

  async _svc(service, data = {}) {
    if (!this._hass) return;
    await this._hass.callService("samsung_epaper", service, data);
    setTimeout(() => this._loadHistory(), 3000);
  }

  _toast(msg) {
    const t = this.shadowRoot.getElementById("toast");
    if (t) { t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 3000); }
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
    const ch = c.parentElement?.clientHeight || 400;
    const cw = ch * (dw / dh);
    c.width = cw; c.height = ch;
    const ds = ch / dh;
    ctx.fillStyle = "#111"; ctx.fillRect(0, 0, cw, ch);
    const img = this._cropImage, s = this._cropScale;
    ctx.drawImage(img, 0, 0, img.width, img.height,
      this._cropX * ds, this._cropY * ds, img.width * s * ds, img.height * s * ds);
    ctx.strokeStyle = "rgba(255,255,255,0.15)"; ctx.lineWidth = 1;
    for (let i = 1; i < 3; i++) {
      ctx.beginPath(); ctx.moveTo(cw / 3 * i, 0); ctx.lineTo(cw / 3 * i, ch); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, ch / 3 * i); ctx.lineTo(cw, ch / 3 * i); ctx.stroke();
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
    const dw = this._config.display_width, dh = this._config.display_height;
    const img = this._cropImage, s = this._cropScale;
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
      if (d.status === "sent") {
        this._toast("Sent!");
        this._cropImage = null; this._cropFile = null;
        setTimeout(() => this._loadHistory(), 2000);
      } else { this._toast("Failed"); }
    } catch (e) { this._toast("Error: " + e.message); }
    this._render();
  }

  // --- Render ---
  _render() {
    const status = this._hass?.states?.["sensor.samsung_epaper_status"];
    const preset = this._hass?.states?.["select.samsung_epaper_active_preset"];
    const camera = this._hass?.states?.["camera.samsung_epaper_display_preview"];
    const reachable = this._hass?.states?.["binary_sensor.samsung_epaper_reachable"];
    const camUrl = camera ? `/api/camera_proxy/${camera.entity_id}?token=${camera.attributes.access_token}&t=${Date.now()}` : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; font-family:var(--primary-font-family,sans-serif); }
        .card {
          background:var(--ha-card-background,var(--card-background-color,#fff));
          border-radius:var(--ha-card-border-radius,12px);
          box-shadow:var(--ha-card-box-shadow,0 2px 6px rgba(0,0,0,.15));
          padding:16px; color:var(--primary-text-color);
        }
        .header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
        .header h2 { margin:0; font-size:18px; font-weight:500; }
        .dot { width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px; }
        .dot.on { background:#4caf50; } .dot.off { background:#f44336; }
        .layout { display:flex; gap:16px; min-height:420px; }
        .preview-col { flex:0 0 auto; display:flex; flex-direction:column; align-items:center; }
        .preview-frame {
          width:180px; height:320px; border-radius:8px; overflow:hidden; background:#111;
          display:flex; align-items:center; justify-content:center;
        }
        .preview-frame img { width:100%; height:100%; object-fit:cover; }
        .preview-placeholder { color:#666; font-size:13px; text-align:center; padding:20px; }
        .preview-info { margin-top:8px; font-size:11px; color:var(--secondary-text-color); text-align:center; }
        .right-col { flex:1; min-width:0; display:flex; flex-direction:column; }
        .tabs { display:flex; gap:4px; margin-bottom:12px; }
        .tab {
          padding:6px 14px; border-radius:6px; cursor:pointer; font-size:13px;
          background:transparent; border:none; color:var(--secondary-text-color); font-family:inherit;
        }
        .tab.active { background:var(--primary-color,#03a9f4); color:#fff; }
        .tab:hover:not(.active) { background:var(--secondary-background-color,#f5f5f5); }
        .tab-body { flex:1; overflow-y:auto; }
        .btn {
          padding:8px 16px; border-radius:6px; border:none; cursor:pointer;
          font-size:13px; font-family:inherit; background:var(--primary-color,#03a9f4); color:#fff;
        }
        .btn:hover { opacity:.85; }
        .btn.sm { padding:6px 10px; font-size:12px; }
        .btn.secondary { background:var(--secondary-background-color,#e0e0e0); color:var(--primary-text-color); }
        .btn-row { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
        .url-row { display:flex; gap:8px; margin-top:8px; }
        .url-row input {
          flex:1; padding:8px 12px; border:1px solid var(--divider-color,#ccc);
          border-radius:6px; font-size:13px; background:var(--card-background-color,#fff);
          color:var(--primary-text-color); font-family:inherit;
        }
        .upload-area {
          border:2px dashed var(--divider-color,#ccc); border-radius:8px;
          padding:32px; text-align:center; cursor:pointer;
        }
        .upload-area:hover { border-color:var(--primary-color,#03a9f4); }
        .upload-area input[type=file] { display:none; }
        .crop-wrap { height:380px; display:flex; align-items:center; justify-content:center; background:#111; border-radius:8px; overflow:hidden; }
        #crop-canvas { cursor:grab; display:block; height:100%; }
        #crop-canvas:active { cursor:grabbing; }
        .crop-bar { display:flex; justify-content:center; gap:8px; margin-top:8px; align-items:center; font-size:12px; }
        .gallery {
          display:grid; grid-template-columns:repeat(auto-fill,minmax(70px,1fr));
          gap:8px;
        }
        .gallery-item {
          aspect-ratio:9/16; border-radius:6px; overflow:hidden; cursor:pointer;
          background:#111; transition:transform .15s,box-shadow .15s; position:relative;
        }
        .gallery-item:hover { transform:scale(1.05); box-shadow:0 2px 8px rgba(0,0,0,.3); }
        .gallery-item img { width:100%; height:100%; object-fit:cover; }
        .gallery-item .lbl {
          position:absolute; bottom:0; left:0; right:0; background:rgba(0,0,0,.7);
          color:#fff; font-size:9px; padding:2px 4px; white-space:nowrap;
          overflow:hidden; text-overflow:ellipsis;
        }
        .empty { text-align:center; padding:24px; color:var(--secondary-text-color); font-size:13px; }
        #toast {
          position:fixed; bottom:20px; left:50%; transform:translateX(-50%) translateY(80px);
          background:var(--primary-color,#03a9f4); color:#fff; padding:10px 20px;
          border-radius:8px; font-size:14px; transition:transform .3s; z-index:9999; pointer-events:none;
        }
        #toast.show { transform:translateX(-50%) translateY(0); }
      </style>
      <div class="card">
        <div class="header">
          <h2>${this._config.title}</h2>
          <span style="font-size:12px;color:var(--secondary-text-color)">
            <span class="dot ${reachable?.state === "on" ? "on" : "off"}"></span>
            ${status?.state === "updating" ? "Updating..." : (reachable?.state === "on" ? "Online" : "Offline")}
          </span>
        </div>
        <div class="layout">
          <div class="preview-col">
            <div class="preview-frame">
              ${camUrl
                ? `<img src="${camUrl}" alt="Preview" />`
                : `<div class="preview-placeholder">No image yet</div>`}
            </div>
            <div class="preview-info">
              ${preset?.state || "No preset"}<br/>
              ${status?.attributes?.last_update ? new Date(status.attributes.last_update).toLocaleString() : "Never updated"}
            </div>
            <div class="btn-row" style="margin-top:8px">
              <button class="btn sm" id="btn-refresh">Refresh</button>
            </div>
          </div>
          <div class="right-col">
            <div class="tabs">
              <button class="tab ${this._activeTab === "upload" ? "active" : ""}" data-tab="upload">Upload</button>
              <button class="tab ${this._activeTab === "url" ? "active" : ""}" data-tab="url">URL</button>
              <button class="tab ${this._activeTab === "history" ? "active" : ""}" data-tab="history">History</button>
            </div>
            <div class="tab-body">${this._renderTab()}</div>
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
            <div style="font-size:28px;margin-bottom:6px">+</div>
            <div>Select an image</div>
            <div style="font-size:11px;color:var(--secondary-text-color);margin-top:4px">
              Crop to ${this._config.display_width} x ${this._config.display_height}
            </div>
          </div>`;
      case "url":
        return `
          <p style="font-size:13px;color:var(--secondary-text-color);margin:0 0 8px">
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
          .map(a => `<div class="gallery-item" data-id="${a.id}">
            <img src="${this._url(`/api/assets/${a.id}/thumbnail`)}" loading="lazy" />
            <div class="lbl">${a.title || a.source_type}</div>
          </div>`).join("")}</div>`;
      default: return "";
    }
  }

  _bind() {
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._activeTab = t.dataset.tab;
        this._render();
        if (t.dataset.tab === "history") this._loadHistory();
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
    if (this._activeTab === "history") {
      this.shadowRoot.querySelectorAll(".gallery-item").forEach(i =>
        i.addEventListener("click", () => this._displayAsset(i.dataset.id))
      );
    }
  }

  getCardSize() { return 6; }
}

customElements.define("samsung-epaper-card", SamsungEpaperCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "samsung-epaper-card",
  name: "Samsung ePaper Display",
  description: "Control your Samsung ePaper display",
  preview: true,
});
console.info(`%c SAMSUNG-EPAPER %c v${CARD_VERSION} `, "color:#fff;background:#03a9f4;font-weight:bold;padding:2px 6px;border-radius:4px 0 0 4px", "color:#03a9f4;background:#e3f2fd;font-weight:bold;padding:2px 6px;border-radius:0 4px 4px 0");
