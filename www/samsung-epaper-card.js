/**
 * Samsung ePaper Display — Custom Lovelace Card
 *
 * Features:
 *   - Live preview of current display content
 *   - Upload image with visual crop/zoom to fit display
 *   - Display image from URL
 *   - History gallery with click-to-display
 *   - Preset selector + refresh
 */

const CARD_VERSION = "1.0.0";

class SamsungEpaperCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._assets = [];
    this._activeTab = "preview";
    // Crop state
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

  static getConfigElement() {
    return document.createElement("samsung-epaper-card-editor");
  }

  static getStubConfig() {
    return { addon_url: "http://192.168.50.84:8000" };
  }

  _getAddonUrl(path) {
    return `${this._config.addon_url}${path}`;
  }

  async _loadHistory() {
    try {
      const resp = await fetch(this._getAddonUrl("/api/assets?limit=30"));
      if (resp.ok) {
        this._assets = await resp.json();
        this._render();
      }
    } catch (e) {
      console.error("Failed to load history:", e);
    }
  }

  async _callService(service, data = {}) {
    if (!this._hass) return;
    await this._hass.callService("samsung_epaper", service, data);
    setTimeout(() => this._loadHistory(), 3000);
  }

  async _displayAsset(assetId) {
    await this._callService("display_asset", { asset_id: assetId });
    this._showToast("Sending to display...");
  }

  async _displayUrl() {
    const input = this.shadowRoot.getElementById("url-input");
    const url = input?.value?.trim();
    if (!url) return;
    this._showToast("Fetching and sending...");
    await this._callService("display_url", { url, title: "URL Image" });
    input.value = "";
  }

  async _refresh() {
    this._showToast("Refreshing...");
    await this._callService("refresh");
  }

  // --- Upload with crop ---

  _onFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    this._cropFile = file;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        this._cropImage = img;
        this._cropScale = 1;
        this._cropX = 0;
        this._cropY = 0;
        // Auto-fit: scale so image covers the crop area
        const aspectDisplay =
          this._config.display_width / this._config.display_height;
        const aspectImage = img.width / img.height;
        if (aspectImage > aspectDisplay) {
          this._cropScale = 1;
        } else {
          this._cropScale = aspectDisplay / aspectImage;
        }
        this._activeTab = "upload";
        this._render();
        this._drawCrop();
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  }

  _drawCrop() {
    const canvas = this.shadowRoot.getElementById("crop-canvas");
    if (!canvas || !this._cropImage) return;
    const ctx = canvas.getContext("2d");
    const dw = this._config.display_width;
    const dh = this._config.display_height;

    // Canvas display size (fit in card, max 300px tall)
    const displayScale = 300 / dh;
    canvas.width = dw * displayScale;
    canvas.height = 300;

    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const img = this._cropImage;
    const scale = this._cropScale;

    // Image dimensions scaled to display resolution
    const imgW = img.width * scale;
    const imgH = img.height * scale;

    // Draw position (in display coords, then scaled to canvas)
    const sx = this._cropX;
    const sy = this._cropY;

    ctx.drawImage(
      img,
      0,
      0,
      img.width,
      img.height,
      (sx * displayScale),
      (sy * displayScale),
      imgW * displayScale,
      imgH * displayScale
    );

    // Draw aspect ratio guide lines
    ctx.strokeStyle = "rgba(255,255,255,0.2)";
    ctx.lineWidth = 1;
    const thirdW = canvas.width / 3;
    const thirdH = canvas.height / 3;
    for (let i = 1; i < 3; i++) {
      ctx.beginPath();
      ctx.moveTo(thirdW * i, 0);
      ctx.lineTo(thirdW * i, canvas.height);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, thirdH * i);
      ctx.lineTo(canvas.width, thirdH * i);
      ctx.stroke();
    }
  }

  _onCropMouseDown(e) {
    this._dragging = true;
    this._dragStartX = e.clientX - this._cropX;
    this._dragStartY = e.clientY - this._cropY;
    e.preventDefault();
  }

  _onCropMouseMove(e) {
    if (!this._dragging) return;
    this._cropX = e.clientX - this._dragStartX;
    this._cropY = e.clientY - this._dragStartY;
    this._drawCrop();
    e.preventDefault();
  }

  _onCropMouseUp() {
    this._dragging = false;
  }

  _onCropWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.05 : 0.05;
    this._cropScale = Math.max(0.1, Math.min(5, this._cropScale + delta));
    this._drawCrop();
  }

  async _uploadCropped() {
    if (!this._cropFile || !this._cropImage) return;
    this._showToast("Uploading and sending...");

    const dw = this._config.display_width;
    const dh = this._config.display_height;
    const displayScale = 300 / dh;
    const img = this._cropImage;
    const scale = this._cropScale;

    // Calculate crop region in original image coordinates
    const imgScaledW = img.width * scale;
    const imgScaledH = img.height * scale;

    // The visible area in display coords
    const cropX = Math.max(0, -this._cropX / scale);
    const cropY = Math.max(0, -this._cropY / scale);
    const cropW = Math.min(img.width - cropX, dw / scale);
    const cropH = Math.min(img.height - cropY, dh / scale);

    const formData = new FormData();
    formData.append("file", this._cropFile);

    const params = new URLSearchParams({
      title: this._cropFile.name,
      crop_x: Math.round(cropX),
      crop_y: Math.round(cropY),
      crop_width: Math.round(cropW),
      crop_height: Math.round(cropH),
    });

    try {
      const resp = await fetch(
        this._getAddonUrl(`/api/upload?${params}`),
        { method: "POST", body: formData }
      );
      const data = await resp.json();
      if (data.status === "sent") {
        this._showToast("Sent to display!");
        this._cropImage = null;
        this._cropFile = null;
        this._activeTab = "preview";
        setTimeout(() => this._loadHistory(), 2000);
      } else {
        this._showToast("Upload failed");
      }
    } catch (e) {
      this._showToast("Upload error: " + e.message);
    }
    this._render();
  }

  _showToast(msg) {
    const toast = this.shadowRoot.getElementById("toast");
    if (toast) {
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 3000);
    }
  }

  _render() {
    const status = this._hass?.states?.["sensor.samsung_epaper_status"];
    const preset = this._hass?.states?.["select.samsung_epaper_active_preset"];
    const camera = this._hass?.states?.["camera.samsung_epaper_display_preview"];
    const reachable = this._hass?.states?.["binary_sensor.samsung_epaper_reachable"];

    const cameraUrl = camera
      ? `/api/camera_proxy/${camera.entity_id}?token=${camera.attributes.access_token}&t=${Date.now()}`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--primary-font-family, sans-serif);
        }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
          padding: 16px;
          color: var(--primary-text-color);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .header h2 {
          margin: 0;
          font-size: 18px;
          font-weight: 500;
        }
        .status-dot {
          width: 10px; height: 10px; border-radius: 50%;
          display: inline-block; margin-right: 6px;
        }
        .status-dot.on { background: #4caf50; }
        .status-dot.off { background: #f44336; }

        .tabs {
          display: flex;
          gap: 4px;
          margin-bottom: 12px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          padding-bottom: 8px;
        }
        .tab {
          padding: 6px 14px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 13px;
          background: transparent;
          border: none;
          color: var(--secondary-text-color);
          font-family: inherit;
        }
        .tab.active {
          background: var(--primary-color, #03a9f4);
          color: #fff;
        }
        .tab:hover:not(.active) {
          background: var(--secondary-background-color, #f5f5f5);
        }

        .preview-img {
          width: 100%;
          max-height: 350px;
          object-fit: contain;
          border-radius: 8px;
          background: #000;
        }
        .preview-placeholder {
          width: 100%;
          height: 200px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 8px;
          color: var(--secondary-text-color);
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 0;
          font-size: 13px;
        }
        .info-label { color: var(--secondary-text-color); }

        .btn {
          padding: 8px 16px;
          border-radius: 6px;
          border: none;
          cursor: pointer;
          font-size: 13px;
          font-family: inherit;
          background: var(--primary-color, #03a9f4);
          color: #fff;
        }
        .btn:hover { opacity: 0.85; }
        .btn.secondary {
          background: var(--secondary-background-color, #e0e0e0);
          color: var(--primary-text-color);
        }
        .btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .btn-row {
          display: flex;
          gap: 8px;
          margin-top: 12px;
          flex-wrap: wrap;
        }

        .url-row {
          display: flex;
          gap: 8px;
          margin-top: 12px;
        }
        .url-row input {
          flex: 1;
          padding: 8px 12px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px;
          font-size: 13px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          font-family: inherit;
        }

        .upload-area {
          border: 2px dashed var(--divider-color, #ccc);
          border-radius: 8px;
          padding: 24px;
          text-align: center;
          cursor: pointer;
          transition: border-color 0.2s;
        }
        .upload-area:hover {
          border-color: var(--primary-color, #03a9f4);
        }
        .upload-area input[type=file] { display: none; }

        #crop-canvas {
          cursor: grab;
          border-radius: 8px;
          display: block;
          margin: 0 auto;
          background: #1a1a1a;
        }
        #crop-canvas:active { cursor: grabbing; }
        .crop-controls {
          display: flex;
          justify-content: center;
          gap: 8px;
          margin-top: 12px;
          align-items: center;
          font-size: 13px;
        }
        .crop-hint {
          text-align: center;
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-top: 6px;
        }

        .gallery {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
          gap: 8px;
          margin-top: 8px;
        }
        .gallery-item {
          position: relative;
          aspect-ratio: 9/16;
          border-radius: 6px;
          overflow: hidden;
          cursor: pointer;
          background: #1a1a1a;
          transition: transform 0.15s, box-shadow 0.15s;
        }
        .gallery-item:hover {
          transform: scale(1.03);
          box-shadow: 0 2px 8px rgba(0,0,0,.3);
        }
        .gallery-item img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .gallery-item .label {
          position: absolute;
          bottom: 0;
          left: 0; right: 0;
          background: rgba(0,0,0,.65);
          color: #fff;
          font-size: 10px;
          padding: 3px 5px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .gallery-empty {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
        }

        #toast {
          position: fixed;
          bottom: 20px;
          left: 50%;
          transform: translateX(-50%) translateY(100px);
          background: var(--primary-color, #03a9f4);
          color: #fff;
          padding: 10px 20px;
          border-radius: 8px;
          font-size: 14px;
          transition: transform 0.3s;
          z-index: 9999;
          pointer-events: none;
        }
        #toast.show { transform: translateX(-50%) translateY(0); }
      </style>

      <div class="card">
        <div class="header">
          <h2>${this._config.title}</h2>
          <div>
            <span class="status-dot ${reachable?.state === "on" ? "on" : "off"}"></span>
            <span style="font-size:12px;color:var(--secondary-text-color)">
              ${status?.state === "updating" ? "Updating..." : (reachable?.state === "on" ? "Online" : "Offline")}
            </span>
          </div>
        </div>

        <div class="tabs">
          <button class="tab ${this._activeTab === "preview" ? "active" : ""}" data-tab="preview">Preview</button>
          <button class="tab ${this._activeTab === "upload" ? "active" : ""}" data-tab="upload">Upload</button>
          <button class="tab ${this._activeTab === "url" ? "active" : ""}" data-tab="url">URL</button>
          <button class="tab ${this._activeTab === "history" ? "active" : ""}" data-tab="history">History</button>
        </div>

        ${this._renderTab(cameraUrl, status, preset)}
      </div>
      <div id="toast"></div>
    `;

    // Bind events
    this.shadowRoot.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        this._activeTab = tab.dataset.tab;
        this._render();
        if (tab.dataset.tab === "history") this._loadHistory();
        if (tab.dataset.tab === "upload" && this._cropImage) {
          requestAnimationFrame(() => this._drawCrop());
        }
      });
    });

    // Tab-specific bindings
    if (this._activeTab === "preview") {
      this.shadowRoot.getElementById("btn-refresh")?.addEventListener("click", () => this._refresh());
    }
    if (this._activeTab === "upload") {
      const uploadArea = this.shadowRoot.getElementById("upload-area");
      const fileInput = this.shadowRoot.getElementById("file-input");
      uploadArea?.addEventListener("click", () => fileInput?.click());
      fileInput?.addEventListener("change", (e) => this._onFileSelect(e));

      const canvas = this.shadowRoot.getElementById("crop-canvas");
      if (canvas && this._cropImage) {
        canvas.addEventListener("mousedown", (e) => this._onCropMouseDown(e));
        canvas.addEventListener("mousemove", (e) => this._onCropMouseMove(e));
        canvas.addEventListener("mouseup", () => this._onCropMouseUp());
        canvas.addEventListener("mouseleave", () => this._onCropMouseUp());
        canvas.addEventListener("wheel", (e) => this._onCropWheel(e), { passive: false });
        // Touch support
        canvas.addEventListener("touchstart", (e) => {
          const t = e.touches[0];
          this._onCropMouseDown({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => e.preventDefault() });
        });
        canvas.addEventListener("touchmove", (e) => {
          const t = e.touches[0];
          this._onCropMouseMove({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => e.preventDefault() });
        });
        canvas.addEventListener("touchend", () => this._onCropMouseUp());

        this.shadowRoot.getElementById("btn-upload")?.addEventListener("click", () => this._uploadCropped());
        this.shadowRoot.getElementById("btn-cancel-crop")?.addEventListener("click", () => {
          this._cropImage = null;
          this._cropFile = null;
          this._render();
        });
        this.shadowRoot.getElementById("btn-zoom-in")?.addEventListener("click", () => {
          this._cropScale = Math.min(5, this._cropScale + 0.1);
          this._drawCrop();
        });
        this.shadowRoot.getElementById("btn-zoom-out")?.addEventListener("click", () => {
          this._cropScale = Math.max(0.1, this._cropScale - 0.1);
          this._drawCrop();
        });
        requestAnimationFrame(() => this._drawCrop());
      }
    }
    if (this._activeTab === "url") {
      this.shadowRoot.getElementById("btn-display-url")?.addEventListener("click", () => this._displayUrl());
      this.shadowRoot.getElementById("url-input")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this._displayUrl();
      });
    }
    if (this._activeTab === "history") {
      this.shadowRoot.querySelectorAll(".gallery-item").forEach((item) => {
        item.addEventListener("click", () => this._displayAsset(item.dataset.id));
      });
    }
  }

  _renderTab(cameraUrl, status, preset) {
    switch (this._activeTab) {
      case "preview":
        return `
          ${cameraUrl
            ? `<img class="preview-img" src="${cameraUrl}" alt="Display preview" />`
            : `<div class="preview-placeholder">No image displayed yet</div>`
          }
          <div class="info-row">
            <span class="info-label">Preset</span>
            <span>${preset?.state || "None"}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Last update</span>
            <span>${status?.attributes?.last_update ? new Date(status.attributes.last_update).toLocaleString() : "Never"}</span>
          </div>
          <div class="btn-row">
            <button class="btn" id="btn-refresh">Refresh Display</button>
          </div>
        `;

      case "upload":
        if (this._cropImage) {
          return `
            <canvas id="crop-canvas" width="169" height="300"></canvas>
            <div class="crop-hint">Drag to pan, scroll to zoom</div>
            <div class="crop-controls">
              <button class="btn secondary" id="btn-zoom-out">-</button>
              <span>${Math.round(this._cropScale * 100)}%</span>
              <button class="btn secondary" id="btn-zoom-in">+</button>
            </div>
            <div class="btn-row" style="justify-content:center">
              <button class="btn secondary" id="btn-cancel-crop">Cancel</button>
              <button class="btn" id="btn-upload">Send to Display</button>
            </div>
          `;
        }
        return `
          <div class="upload-area" id="upload-area">
            <input type="file" id="file-input" accept="image/*" />
            <div style="font-size:32px;margin-bottom:8px">+</div>
            <div>Tap to select an image</div>
            <div style="font-size:12px;color:var(--secondary-text-color);margin-top:4px">
              Image will be cropped to ${this._config.display_width}x${this._config.display_height}
            </div>
          </div>
        `;

      case "url":
        return `
          <p style="font-size:13px;color:var(--secondary-text-color);margin-top:0">
            Enter an image URL to display on the panel.
          </p>
          <div class="url-row">
            <input id="url-input" type="text" placeholder="https://example.com/image.jpg" />
            <button class="btn" id="btn-display-url">Display</button>
          </div>
        `;

      case "history":
        if (!this._assets.length) {
          return `<div class="gallery-empty">No images in history yet</div>`;
        }
        return `
          <div class="gallery">
            ${this._assets
              .filter((a) => a.filename_thumbnail)
              .map(
                (a) => `
                <div class="gallery-item" data-id="${a.id}">
                  <img src="${this._getAddonUrl(`/api/assets/${a.id}/thumbnail`)}" loading="lazy" />
                  <div class="label">${a.title || a.source_type}</div>
                </div>
              `
              )
              .join("")}
          </div>
        `;

      default:
        return "";
    }
  }

  getCardSize() {
    return 5;
  }
}

customElements.define("samsung-epaper-card", SamsungEpaperCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "samsung-epaper-card",
  name: "Samsung ePaper Display",
  description: "Control your Samsung ePaper display with upload, crop, history, and presets",
  preview: true,
});

console.info(
  `%c SAMSUNG-EPAPER-CARD %c v${CARD_VERSION} `,
  "color: white; background: #03a9f4; font-weight: bold; padding: 2px 6px; border-radius: 4px 0 0 4px",
  "color: #03a9f4; background: #e3f2fd; font-weight: bold; padding: 2px 6px; border-radius: 0 4px 4px 0"
);
