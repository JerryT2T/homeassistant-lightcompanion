/* Light Companion sidebar panel — hosts one lightcompanion-card full height. */

const PANEL_TAG = "lightcompanion-panel";

class LightCompanionPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._narrow = false;
    this._card = null;
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    if (this._card) return;
    // The card is normally loaded via extra_js_url; import it as a safety net (define is guarded).
    if (!customElements.get("lightcompanion-card")) {
      import("./lightcompanion-card.js").catch(() => {});
    }

    const style = document.createElement("style");
    style.textContent = `
      :host { display: flex; flex-direction: column; height: 100%; background: var(--primary-background-color); color: var(--primary-text-color); }
      header { flex: none; display: flex; align-items: center; gap: 4px; min-height: var(--header-height, 56px); padding: 0 12px;
        background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, var(--text-primary-color, #fff)); }
      h1 { font-size: 20px; font-weight: 400; margin: 0; }
      main { flex: 1; min-height: 0; padding: 16px; display: flex; flex-direction: column; align-items: center; }
      lightcompanion-card { width: 100%; max-width: 760px; flex: 1; min-height: 0; }
      :host([narrow]) main { padding: 8px; }
    `;

    this._menu = document.createElement("ha-menu-button");
    this._title = document.createElement("h1");
    this._title.textContent = "Light Companion";
    const header = document.createElement("header");
    header.append(this._menu, this._title);

    this._card = document.createElement("lightcompanion-card");
    this._card.setConfig({ type: "custom:lightcompanion-card", area: null });
    const main = document.createElement("main");
    main.append(this._card);

    this.shadowRoot.append(style, header, main);
    this._sync();
  }

  set hass(hass) { this._hass = hass; this._sync(); }
  get hass() { return this._hass; }

  set narrow(value) { this._narrow = !!value; this._sync(); }
  get narrow() { return this._narrow; }

  // Provided by HA, unused here.
  set route(_v) {}
  set panel(_v) {}

  _sync() {
    if (!this._card) return;
    this.toggleAttribute("narrow", this._narrow);
    this._menu.hass = this._hass;
    this._menu.narrow = this._narrow;
    this._menu.hidden = !this._narrow;
    this._card.narrow = this._narrow;
    if (this._hass) this._card.hass = this._hass;
  }
}

if (!customElements.get(PANEL_TAG)) customElements.define(PANEL_TAG, LightCompanionPanel);
