/* Light Companion card — plain ES module Web Component, no build step, no dependencies. */

const CARD_TAG = "lightcompanion-card";
const EDITOR_TAG = "lightcompanion-card-editor";
const DESKTOP_QUERY = "(min-width: 870px) and (hover: hover) and (pointer: fine)";

/* ------------------------------------------------------------------ i18n */

const STRINGS = {
  en: {
    placeholder: "Describe the light you want…",
    send: "Send",
    mic: "Voice input",
    micStop: "Stop listening",
    stop: "Stop effect",
    settings: "Settings",
    rooms: "Rooms",
    listening: "Listening…",
    noSpeech: "Voice input is not available in this browser.",
    noCatch: "I did not catch that, please try again.",
    idle: "No effect running",
    running: "Running",
    sourceChat: "Chat",
    sourceMusic: "Music",
    aiBudget: "AI calls",
    rateLimitedNote: "AI limit reached — the current effect keeps running",
    notLoaded: "Light Companion is not loaded. Check Settings → Devices & services → Light Companion.",
    noAreas: "No room with lights found.",
    emptyHint: "Tell me what the room should feel like.",
    thinking: "Thinking",
    avg: "Average color",
    off: "off",
    suggestions: ["Cozy warm evening", "Disco like the music, but dark colors", "Slow blue waves", "Lights off"],
    "err.rate_limited": "The AI call limit for this hour is used up. Try again later or raise the limit in the settings.",
    "err.invalid_plan": "I could not turn that into a safe light plan. Nothing was changed — try rephrasing.",
    "err.no_lights": "This room has no controllable lights.",
    "err.timeout": "The AI took too long to answer. Please try again.",
    "err.request_failed": "The AI request failed. Check the provider and API key in the settings.",
    "err.no_answer": "The AI gave no answer. Please try again.",
    "err.invalid_json": "The AI answer was not usable. Nothing was changed.",
    "err.not_configured": "No AI provider is configured yet. Set one up in the Light Companion settings.",
    "err.not_loaded": "Light Companion is not loaded.",
    "err.unknown_area": "That room is unknown.",
    "err.generic": "Something went wrong.",
    "p.static": "Static",
    "p.breathe": "Breathe",
    "p.pulse": "Pulse",
    "p.wave": "Wave",
    "p.color_cycle": "Color cycle",
    "p.sparkle": "Sparkle",
    "p.strobe": "Strobe",
    sTitle: "Light Companion settings",
    sClose: "Close",
    sSave: "Save",
    sCancel: "Cancel",
    sSaving: "Saving…",
    sSaved: "Saved. The integration is reloading.",
    sLoading: "Loading settings…",
    sReadOnly: "Only administrators can change these settings. They are shown read-only.",
    sProvider: "AI provider",
    sModel: "Model",
    sApiKey: "API key",
    sApiKeySaved: "••• saved",
    sApiKeyHelp: "Leave empty to keep the stored key.",
    sAiTask: "AI task entity",
    sConversation: "Conversation agent",
    sDefaultEntity: "Default",
    sCalls: "AI calls per hour",
    sRate: "Light commands per second",
    sStrobe: "Allow strobe effects",
    sStrobeWarn: "Strobe flashing can trigger seizures in people with photosensitive epilepsy. Only enable it if everyone present is safe.",
    sExcluded: "Excluded lights",
    sExcludedHelp: "Checked lights are never touched. Lights matching an exclude keyword are locked.",
    sKeyword: "Matches a keyword",
    sKeywords: "Exclude keywords",
    sKeywordsHelp: "Comma separated. Lights whose name or room contains one are excluded.",
    sPlayers: "Music player per room",
    sAuto: "Automatic",
    sDefaultArea: "Default room",
    sNone: "None (first room)",
    sPanel: "Show sidebar panel",
    sFail: "Saving failed",
    "prov.ai_task": "Home Assistant AI task",
    "prov.conversation": "Conversation agent",
    "prov.openai": "OpenAI",
    "prov.anthropic": "Anthropic",
    "prov.google": "Google Gemini",
    eArea: "Room",
    eAuto: "Automatic (default room)",
  },
  de: {
    placeholder: "Beschreibe das gewünschte Licht…",
    send: "Senden",
    mic: "Spracheingabe",
    micStop: "Aufnahme beenden",
    stop: "Effekt stoppen",
    settings: "Einstellungen",
    rooms: "Räume",
    listening: "Ich höre zu…",
    noSpeech: "Spracheingabe ist in diesem Browser nicht verfügbar.",
    noCatch: "Das habe ich nicht verstanden, bitte noch einmal.",
    idle: "Kein Effekt aktiv",
    running: "Läuft",
    sourceChat: "Chat",
    sourceMusic: "Musik",
    aiBudget: "KI-Aufrufe",
    rateLimitedNote: "KI-Limit erreicht — der aktuelle Effekt läuft weiter",
    notLoaded: "Light Companion ist nicht geladen. Prüfe Einstellungen → Geräte & Dienste → Light Companion.",
    noAreas: "Kein Raum mit Lichtern gefunden.",
    emptyHint: "Sag mir, wie sich der Raum anfühlen soll.",
    thinking: "Denke nach",
    avg: "Durchschnittsfarbe",
    off: "aus",
    suggestions: ["Gemütlicher warmer Abend", "Disco passend zur Musik, aber dunkle Farben", "Langsame blaue Wellen", "Licht aus"],
    "err.rate_limited": "Das KI-Limit für diese Stunde ist aufgebraucht. Versuche es später oder erhöhe das Limit in den Einstellungen.",
    "err.invalid_plan": "Daraus konnte ich keinen sicheren Lichtplan machen. Es wurde nichts geändert — formuliere es anders.",
    "err.no_lights": "Dieser Raum hat keine steuerbaren Lichter.",
    "err.timeout": "Die KI hat zu lange gebraucht. Bitte erneut versuchen.",
    "err.request_failed": "Die KI-Anfrage ist fehlgeschlagen. Prüfe Anbieter und API-Key in den Einstellungen.",
    "err.no_answer": "Die KI hat nicht geantwortet. Bitte erneut versuchen.",
    "err.invalid_json": "Die KI-Antwort war nicht verwendbar. Es wurde nichts geändert.",
    "err.not_configured": "Es ist noch kein KI-Anbieter eingerichtet. Richte ihn in den Light-Companion-Einstellungen ein.",
    "err.not_loaded": "Light Companion ist nicht geladen.",
    "err.unknown_area": "Dieser Raum ist unbekannt.",
    "err.generic": "Etwas ist schiefgelaufen.",
    "p.static": "Statisch",
    "p.breathe": "Atmen",
    "p.pulse": "Pulsieren",
    "p.wave": "Welle",
    "p.color_cycle": "Farbwechsel",
    "p.sparkle": "Funkeln",
    "p.strobe": "Stroboskop",
    sTitle: "Light-Companion-Einstellungen",
    sClose: "Schließen",
    sSave: "Speichern",
    sCancel: "Abbrechen",
    sSaving: "Speichere…",
    sSaved: "Gespeichert. Die Integration lädt neu.",
    sLoading: "Lade Einstellungen…",
    sReadOnly: "Nur Administratoren können diese Einstellungen ändern. Sie werden schreibgeschützt angezeigt.",
    sProvider: "KI-Anbieter",
    sModel: "Modell",
    sApiKey: "API-Key",
    sApiKeySaved: "••• gespeichert",
    sApiKeyHelp: "Leer lassen, um den gespeicherten Key zu behalten.",
    sAiTask: "KI-Task-Entität",
    sConversation: "Konversations-Agent",
    sDefaultEntity: "Standard",
    sCalls: "KI-Aufrufe pro Stunde",
    sRate: "Lichtbefehle pro Sekunde",
    sStrobe: "Stroboskop-Effekte erlauben",
    sStrobeWarn: "Stroboskop-Blitze können bei Menschen mit photosensibler Epilepsie Anfälle auslösen. Nur aktivieren, wenn alle Anwesenden sicher sind.",
    sExcluded: "Ausgeschlossene Lichter",
    sExcludedHelp: "Angehakte Lichter werden nie angefasst. Lichter mit passendem Ausschluss-Stichwort sind gesperrt.",
    sKeyword: "Passt auf ein Stichwort",
    sKeywords: "Ausschluss-Stichwörter",
    sKeywordsHelp: "Kommagetrennt. Lichter, deren Name oder Raum eines enthält, werden ausgeschlossen.",
    sPlayers: "Musik-Player pro Raum",
    sAuto: "Automatisch",
    sDefaultArea: "Standardraum",
    sNone: "Keiner (erster Raum)",
    sPanel: "Seitenleisten-Panel anzeigen",
    sFail: "Speichern fehlgeschlagen",
    "prov.ai_task": "Home-Assistant-KI-Task",
    "prov.conversation": "Konversations-Agent",
    "prov.openai": "OpenAI",
    "prov.anthropic": "Anthropic",
    "prov.google": "Google Gemini",
    eArea: "Raum",
    eAuto: "Automatisch (Standardraum)",
  },
};

function makeT(hass) {
  const lang = String(hass?.locale?.language || hass?.language || "en").toLowerCase();
  const dict = lang.startsWith("de") ? STRINGS.de : STRINGS.en;
  return (key) => dict[key] ?? STRINGS.en[key] ?? key;
}

/* ----------------------------------------------------------------- utils */

/** Tiny DOM builder. Text always goes through textContent / text nodes — never innerHTML. */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected" || k === "hidden") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === undefined || c === null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Color temperature (K) → RGB, Tanner Helland approximation. */
function kelvinToRgb(kelvin) {
  const t = clamp(kelvin, 1000, 40000) / 100;
  const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
  const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  return [r, g, b].map((v) => Math.round(clamp(v, 0, 255)));
}

function hsToRgb(hue, sat) {
  const s = clamp(sat, 0, 100) / 100;
  const hh = ((hue % 360) + 360) % 360 / 60;
  const c = s;
  const x = c * (1 - Math.abs((hh % 2) - 1));
  const [r, g, b] = hh < 1 ? [c, x, 0] : hh < 2 ? [x, c, 0] : hh < 3 ? [0, c, x] : hh < 4 ? [0, x, c] : hh < 5 ? [x, 0, c] : [c, 0, x];
  const m = 1 - c;
  return [r + m, g + m, b + m].map((v) => Math.round(v * 255));
}

const OFF_RGB = [74, 78, 90];

/** Color of one light entity state: {on, rgb, weight}. */
function lightColor(state) {
  if (!state || state.state !== "on") return { on: false, rgb: OFF_RGB, weight: 0 };
  const a = state.attributes || {};
  let rgb;
  if (Array.isArray(a.rgb_color) && a.rgb_color.length >= 3) rgb = a.rgb_color.slice(0, 3);
  else if (Array.isArray(a.hs_color) && a.hs_color.length >= 2) rgb = hsToRgb(a.hs_color[0], a.hs_color[1]);
  else if (a.color_temp_kelvin) rgb = kelvinToRgb(a.color_temp_kelvin);
  else if (a.color_temp) rgb = kelvinToRgb(1000000 / a.color_temp);
  else rgb = [255, 244, 229];
  const weight = typeof a.brightness === "number" ? clamp(a.brightness / 255, 0.02, 1) : 1;
  return { on: true, rgb, weight };
}

/** Brightness-weighted average. Returns {rgb, level 0..1, anyOn}. */
function averageColor(lights) {
  let r = 0, g = 0, b = 0, w = 0, maxW = 0;
  for (const l of lights) {
    if (!l.on) continue;
    r += l.rgb[0] * l.weight; g += l.rgb[1] * l.weight; b += l.rgb[2] * l.weight;
    w += l.weight; maxW = Math.max(maxW, l.weight);
  }
  if (!w) return { rgb: OFF_RGB, level: 0, anyOn: false };
  return { rgb: [Math.round(r / w), Math.round(g / w), Math.round(b / w)], level: maxW, anyOn: true };
}

const css = (rgb) => `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
const hex = (rgb) => "#" + rgb.map((v) => v.toString(16).padStart(2, "0")).join("");

function errorCode(err) {
  if (!err) return "generic";
  return err.code || err.error?.code || "generic";
}

/* ------------------------------------------------------------- AudioWorklet */

const WORKLET_SRC = `
class LcPcm extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0; this.acc = 0; this.n = 0;
    this.out = new Int16Array(1600); this.fill = 0;
  }
  process(inputs) {
    const ch = inputs[0];
    if (!ch || !ch.length) return true;
    const len = ch[0].length;
    for (let i = 0; i < len; i++) {
      let s = 0;
      for (let c = 0; c < ch.length; c++) s += ch[c][i];
      this.acc += s / ch.length; this.n++; this.pos += 1;
      if (this.pos >= this.ratio) {
        let v = this.acc / this.n;
        v = Math.max(-1, Math.min(1, v));
        this.out[this.fill++] = v < 0 ? v * 32768 : v * 32767;
        this.pos -= this.ratio; this.acc = 0; this.n = 0;
        if (this.fill === this.out.length) {
          this.port.postMessage(this.out.slice().buffer);
          this.fill = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("lc-pcm", LcPcm);
`;

/* -------------------------------------------------------------------- CSS */

const STYLE = `
:host { display: block; height: 100%; }
* { box-sizing: border-box; scrollbar-width: thin; scrollbar-color: var(--divider-color, #888) transparent; }
*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-thumb { background: var(--divider-color, #888); border-radius: 8px; }
*::-webkit-scrollbar-track { background: transparent; }
ha-card { display: flex; flex-direction: column; height: 100%; min-height: 440px; overflow: hidden; position: relative; isolation: isolate; }
[hidden] { display: none !important; }
button { font: inherit; color: inherit; cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible, .chip:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

/* tooltips: app-styled, label tier (delayed), hover-capable devices only */
[data-tip] { position: relative; }
@media (hover: hover) {
  [data-tip]::after {
    content: attr(data-tip); position: absolute; z-index: 20; right: 0; top: calc(100% + 6px);
    background: var(--primary-text-color); color: var(--card-background-color);
    font-size: 12px; line-height: 1; padding: 6px 8px; border-radius: 6px; white-space: nowrap;
    opacity: 0; pointer-events: none; transition: opacity .12s ease 0s;
  }
  [data-tip].tip-up::after { top: auto; bottom: calc(100% + 6px); }
  [data-tip].tip-c::after { right: auto; left: 50%; transform: translateX(-50%); }
  [data-tip]:hover::after, [data-tip]:focus-visible::after { opacity: .94; transition-delay: .5s; }
}

.hero { position: relative; padding: 14px 12px 8px; display: flex; flex-direction: column; align-items: center; gap: 10px; overflow: hidden; flex: none; }
.halo { position: absolute; left: 50%; top: 58%; width: 130%; aspect-ratio: 1; transform: translate(-50%, -50%); border-radius: 50%;
  filter: blur(60px); opacity: .0; transition: background-color 1.2s ease, opacity 1.2s ease; z-index: 0; pointer-events: none; }
.hero > *:not(.halo) { position: relative; z-index: 1; }
.chips { display: flex; gap: 8px; overflow-x: auto; width: 100%; padding: 2px 2px 6px; scroll-snap-type: x proximity; -webkit-overflow-scrolling: touch; }
.chips { scrollbar-width: none; }
.chips::-webkit-scrollbar { display: none; }
.chips.has-gear { padding-right: 48px; }
.chip { flex: none; scroll-snap-align: start; border: 1px solid var(--divider-color); background: color-mix(in srgb, var(--card-background-color) 70%, transparent);
  color: var(--primary-text-color); border-radius: 999px; padding: 0 16px; min-height: 44px; font-size: 14px; transition: background .2s, border-color .2s, color .2s; backdrop-filter: blur(6px); }
.chip[aria-selected="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.gear { position: absolute !important; top: 14px; right: 12px; width: 44px; height: 44px; border-radius: 50%; border: 1px solid var(--divider-color);
  background: color-mix(in srgb, var(--card-background-color) 70%, transparent); display: grid; place-items: center; padding: 0; z-index: 3 !important; }
.gear svg, .iconbtn svg { width: 22px; height: 22px; fill: currentColor; }
.orbwrap { width: clamp(120px, 34vw, 168px); aspect-ratio: 1; display: grid; place-items: center; margin: 4px 0 0; }
.orb { width: 100%; height: 100%; border-radius: 50%; position: relative; transition: background-color 1.2s ease, box-shadow 1.2s ease, opacity 1.2s ease, transform 1.2s ease; }
.orb::after { content: ""; position: absolute; inset: 0; border-radius: 50%;
  background: radial-gradient(circle at 32% 26%, rgba(255,255,255,.55), rgba(255,255,255,0) 52%), radial-gradient(circle at 70% 80%, rgba(0,0,0,.22), rgba(0,0,0,0) 60%); }
.orb.running { animation: breathe 4s ease-in-out infinite; }
@keyframes breathe { 50% { transform: scale(1.045); } }
.avg { font-size: 12px; color: var(--primary-text-color); letter-spacing: .04em; display: flex; align-items: center; gap: 6px; min-height: 18px; }
.dots { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; max-width: 100%; min-height: 14px; }
.dot { width: 14px; height: 14px; border-radius: 50%; border: 2px solid transparent; transition: background-color 1s ease, box-shadow 1s ease; cursor: default; }
.dot.off { background: transparent !important; border-color: var(--divider-color); box-shadow: none !important; }

.status { flex: none; display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap; padding: 4px 12px 10px; font-size: 13px; color: var(--secondary-text-color); }
.pill { border: 1px solid var(--divider-color); border-radius: 999px; padding: 4px 10px; display: inline-flex; gap: 6px; align-items: center; background: transparent; }
.pill.warn { color: var(--warning-color, #b26a00); border-color: currentColor; }
.pill.live { color: var(--primary-text-color); }
.pill.live::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--primary-color); animation: breathe 2s ease-in-out infinite; }
.stopbtn { min-height: 44px; padding: 0 16px; border-radius: 999px; border: 1px solid var(--error-color, #db4437); color: var(--error-color, #db4437); background: transparent; font-weight: 500; }
.stopbtn:hover { background: color-mix(in srgb, var(--error-color, #db4437) 12%, transparent); }

.msgs { flex: 1 1 auto; min-height: 90px; overflow-y: auto; padding: 8px 12px; display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--divider-color); }
.bubble { max-width: 86%; padding: 9px 13px; border-radius: 16px; line-height: 1.4; font-size: 14.5px; white-space: pre-wrap; overflow-wrap: anywhere; }
.bubble.user { align-self: flex-end; background: var(--primary-color); color: var(--text-primary-color, #fff); border-bottom-right-radius: 5px; }
.bubble.bot { align-self: flex-start; background: var(--secondary-background-color); color: var(--primary-text-color); border-bottom-left-radius: 5px; }
.bubble.err { background: color-mix(in srgb, var(--error-color, #db4437) 14%, var(--card-background-color)); border: 1px solid color-mix(in srgb, var(--error-color, #db4437) 45%, transparent); }
.bubble.hint { align-self: center; background: transparent; color: var(--secondary-text-color); text-align: center; }
.typing span { display: inline-block; width: 6px; height: 6px; margin: 0 2px; border-radius: 50%; background: var(--secondary-text-color); animation: blink 1.2s infinite both; }
.typing span:nth-child(2) { animation-delay: .2s; } .typing span:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }
.empty { margin: auto; display: flex; flex-direction: column; gap: 10px; align-items: center; color: var(--secondary-text-color); text-align: center; padding: 6px 0; }
.sugs { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.sug { border: 1px dashed var(--divider-color); background: transparent; color: var(--primary-text-color); border-radius: 14px; padding: 8px 12px; min-height: 40px; font-size: 13px; }
.sug:hover { border-style: solid; border-color: var(--primary-color); }

.composer { flex: none; display: flex; gap: 8px; padding: 8px 12px 12px; align-items: center; }
.composer input { flex: 1; min-width: 0; min-height: 46px; padding: 0 16px; border-radius: 23px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font: inherit; font-size: 16px; }
.iconbtn { width: 46px; height: 46px; flex: none; border-radius: 50%; border: 1px solid var(--divider-color); background: transparent; display: grid; place-items: center; padding: 0; transition: background .2s, color .2s; }
.iconbtn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.iconbtn:disabled { opacity: .45; cursor: default; }
.iconbtn.rec { background: var(--error-color, #db4437); border-color: var(--error-color, #db4437); color: #fff; animation: breathe 1.2s ease-in-out infinite; }
.notice { margin: 8px 12px; padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); color: var(--secondary-text-color); font-size: 13px; }

/* modal */
.backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000; display: grid; place-items: center; padding: 16px; }
.dialog { background: var(--card-background-color); color: var(--primary-text-color); width: min(560px, 100%); max-height: min(86vh, 800px); display: flex; flex-direction: column; border-radius: var(--ha-card-border-radius, 12px); box-shadow: 0 12px 40px rgba(0,0,0,.4); overflow: hidden; }
.dialog header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--divider-color); }
.dialog header h2 { margin: 0; font-size: 18px; font-weight: 500; }
.dialog .body { padding: 8px 16px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
.dialog footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--divider-color); }
.field { display: flex; flex-direction: column; gap: 4px; }
.field > label, .field > .lbl { font-size: 13px; color: var(--secondary-text-color); }
.field input[type=text], .field input[type=password], .field input[type=number], .field select { min-height: 40px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font: inherit; width: 100%; }
.field .help { font-size: 12px; color: var(--secondary-text-color); }
.field .warn { font-size: 12px; color: var(--warning-color, #b26a00); }
.row { display: flex; align-items: center; gap: 10px; }
.row input[type=range] { flex: 1; accent-color: var(--primary-color); }
.row output { min-width: 3ch; text-align: right; font-variant-numeric: tabular-nums; }
.check { display: flex; align-items: center; gap: 10px; min-height: 36px; font-size: 14px; }
.check input { width: 18px; height: 18px; accent-color: var(--primary-color); }
.list { max-height: 190px; overflow-y: auto; border: 1px solid var(--divider-color); border-radius: 8px; padding: 4px 10px; }
.list .check small { color: var(--secondary-text-color); }
.btn { min-height: 40px; padding: 0 18px; border-radius: 20px; border: 1px solid var(--divider-color); background: transparent; }
.btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.btn:disabled { opacity: .5; cursor: default; }
.formerr { color: var(--error-color, #db4437); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition-duration: .01s !important; } }
`;

const ICONS = {
  gear: "M12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5m7.43-2.53c.04-.32.07-.64.07-.97s-.03-.66-.07-1l2.11-1.63a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.61-.22l-2.49 1a7.3 7.3 0 0 0-1.69-.98l-.38-2.65A.49.49 0 0 0 14 2h-4a.49.49 0 0 0-.49.42l-.38 2.65a7.3 7.3 0 0 0-1.69.98l-2.49-1a.5.5 0 0 0-.61.22l-2 3.46a.5.5 0 0 0 .12.64L4.57 11c-.04.34-.07.67-.07 1s.03.65.07.97l-2.11 1.66a.5.5 0 0 0-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.05.24.26.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65a7.3 7.3 0 0 0 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46a.5.5 0 0 0-.12-.64z",
  mic: "M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3m5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z",
  send: "M2.01 21 23 12 2.01 3 2 10l15 2-15 2z",
  stop: "M6 6h12v12H6z",
  close: "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
};

function icon(name) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", ICONS[name]);
  svg.append(p);
  return svg;
}

/* ------------------------------------------------------------------- Card */

class LightCompanionCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static async getStubConfig(hass) {
    try {
      const res = await hass.callWS({ type: "lightcompanion/areas" });
      const first = res?.areas?.[0]?.area_id;
      return first ? { area: first } : {};
    } catch (_e) {
      return {};
    }
  }

  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._narrow = false;
    this._areas = [];
    this._areasLoaded = false;
    this._loadError = null;
    this._area = null;
    this._userPicked = false;
    this._defaultArea = null;
    this._threads = new Map();
    this._pending = new Set();
    this._status = { engine: {}, planner: {} };
    this._unsub = null;
    this._subscribing = false;
    this._retryTimer = null;
    this._voice = null;
    this._lastSig = "";
    this._built = false;
    this._connected = false;
    this._desktop = false;
    this._mq = null;
    this._onMq = () => this._updateGear();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    if (!this._userPicked) this._area = null;
    if (this._built) this._resolveArea();
    this._renderAll();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._built) this._build();
    if (first || this._connChanged(hass)) {
      this._conn = hass?.connection;
      if (this._connected) this._init();
    }
    this._updateColors();
  }
  get hass() { return this._hass; }

  set narrow(v) { this._narrow = !!v; this._updateGear(); }
  get narrow() { return this._narrow; }

  getCardSize() { return 8; }

  getGridOptions() {
    return { columns: 12, rows: 8, min_columns: 6, min_rows: 6 };
  }

  connectedCallback() {
    this._connected = true;
    if (!this._built) this._build();
    this._mq = window.matchMedia ? window.matchMedia(DESKTOP_QUERY) : null;
    this._mq?.addEventListener?.("change", this._onMq);
    this._updateGear();
    if (this._hass) this._init();
  }

  disconnectedCallback() {
    this._connected = false;
    this._mq?.removeEventListener?.("change", this._onMq);
    this._teardown();
    this._voice?.stop?.(true);
    this._closeSettings();
  }

  _connChanged(hass) { return hass?.connection !== this._conn; }

  /* ---- data loading ---- */

  async _init() {
    this._teardown();
    await this._loadAreas();
    this._subscribe();
  }

  _teardown() {
    clearTimeout(this._retryTimer);
    this._retryTimer = null;
    const u = this._unsub;
    this._unsub = null;
    this._subGen = (this._subGen || 0) + 1;
    if (u) { try { u(); } catch (_e) { /* connection gone */ } }
  }

  async _loadAreas() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({ type: "lightcompanion/areas" });
      this._areas = Array.isArray(res?.areas) ? res.areas : [];
      this._loadError = null;
    } catch (err) {
      this._areas = [];
      this._loadError = errorCode(err);
      this._scheduleRetry();
    }
    this._areasLoaded = true;
    try {
      const s = await this._hass.callWS({ type: "lightcompanion/settings/get" });
      this._defaultArea = s?.settings?.default_area || null;
    } catch (_e) { /* optional */ }
    this._resolveArea();
    this._renderAll();
  }

  _scheduleRetry() {
    clearTimeout(this._retryTimer);
    if (!this._connected) return;
    this._retryTimer = setTimeout(() => { if (this._connected) this._init(); }, 10000);
  }

  async _subscribe() {
    if (!this._hass?.connection || !this._connected || this._loadError) return;
    const gen = this._subGen;
    try {
      const unsub = await this._hass.connection.subscribeMessage((msg) => {
        this._status = { engine: msg?.engine || {}, planner: msg?.planner || {} };
        this._renderStatus();
      }, { type: "lightcompanion/subscribe" });
      if (gen !== this._subGen || !this._connected) { unsub(); return; }
      this._unsub = unsub;
    } catch (err) {
      this._loadError = errorCode(err);
      this._renderAll();
      this._scheduleRetry();
    }
  }

  _resolveArea() {
    const ids = this._areas.map((a) => a.area_id);
    let want = this._userPicked && ids.includes(this._area) ? this._area : null;
    if (!want && this._config.area && ids.includes(this._config.area)) want = this._config.area;
    if (!want && this._defaultArea && ids.includes(this._defaultArea)) want = this._defaultArea;
    if (!want) want = ids[0] || null;
    this._area = want;
  }

  _areaObj() { return this._areas.find((a) => a.area_id === this._area) || null; }

  _areaLights() {
    return (this._areaObj()?.lights || []).filter((l) => !l.excluded);
  }

  /* ---- build DOM once ---- */

  _build() {
    this._built = true;
    const root = this.shadowRoot;
    root.append(h("style", { text: STYLE }));

    this._elChips = h("div", { class: "chips", role: "tablist" });
    this._elGear = h("button", { class: "gear", type: "button", hidden: true, onclick: () => this._openSettings() }, icon("gear"));
    this._elHalo = h("div", { class: "halo" });
    this._elOrb = h("div", { class: "orb", role: "img" });
    this._elAvg = h("div", { class: "avg" });
    this._elDots = h("div", { class: "dots" });
    const hero = h("div", { class: "hero" }, this._elHalo, this._elChips, h("div", { class: "orbwrap" }, this._elOrb), this._elAvg, this._elDots, this._elGear);

    this._elStatus = h("div", { class: "status", "aria-live": "polite" });
    this._elMsgs = h("div", { class: "msgs", role: "log", "aria-live": "polite" });

    this._elInput = h("input", { type: "text", enterkeyhint: "send", autocomplete: "off", autocapitalize: "sentences" });
    this._elMic = h("button", { class: "iconbtn tip-up", type: "button", onclick: () => this._toggleVoice() }, icon("mic"));
    this._elSend = h("button", { class: "iconbtn primary tip-up", type: "submit" }, icon("send"));
    this._elForm = h("form", { class: "composer", onsubmit: (e) => { e.preventDefault(); this._send(this._elInput.value); } }, this._elInput, this._elMic, this._elSend);

    this._elCard = h("ha-card", {}, hero, this._elStatus, this._elMsgs, this._elForm);
    this._elModal = h("div", {});
    root.append(this._elCard, this._elModal);
  }

  _renderAll() {
    if (!this._built) return;
    const t = makeT(this._hass);
    this._elInput.placeholder = t("placeholder");
    this._elInput.setAttribute("aria-label", t("placeholder"));
    this._elMic.setAttribute("aria-label", this._voice ? t("micStop") : t("mic"));
    this._elMic.dataset.tip = this._voice ? t("micStop") : t("mic");
    this._elSend.setAttribute("aria-label", t("send"));
    this._elSend.dataset.tip = t("send");
    this._elGear.setAttribute("aria-label", t("settings"));
    this._elGear.dataset.tip = t("settings");
    this._elChips.setAttribute("aria-label", t("rooms"));

    this._elChips.replaceChildren(...this._areas.map((a) => {
      const sel = a.area_id === this._area;
      return h("button", {
        class: "chip", type: "button", role: "tab", "aria-selected": sel ? "true" : "false",
        onclick: () => { this._userPicked = true; this._area = a.area_id; this._renderAll(); },
      }, a.name || a.area_id);
    }));
    this._elChips.hidden = this._areas.length === 0;
    const sel = this._elChips.querySelector('[aria-selected="true"]');
    sel?.scrollIntoView?.({ block: "nearest", inline: "center" });

    this._updateGear();
    this._renderMessages();
    this._renderStatus();
    this._lastSig = "";
    this._updateColors();
    this._updateComposer();
  }

  _updateGear() {
    if (!this._built) return;
    const desktop = !!this._mq?.matches && !this._narrow;
    this._elGear.hidden = !desktop;
    this._elChips.classList.toggle("has-gear", desktop);
    if (!desktop && this._modalEl) this._closeSettings();
  }

  _updateComposer() {
    const busy = this._pending.has(this._area);
    this._elSend.disabled = busy || !this._area;
    this._elInput.disabled = !this._area;
  }

  /* ---- colors ---- */

  _updateColors() {
    if (!this._built) return;
    const t = makeT(this._hass);
    const lights = this._areaLights();
    const data = lights.map((l) => ({ info: l, ...lightColor(this._hass?.states?.[l.entity_id]) }));
    const sig = this._area + "|" + data.map((d) => `${d.on}${d.rgb}${d.weight.toFixed(2)}`).join(";");
    if (sig === this._lastSig) return;
    this._lastSig = sig;
    const avg = averageColor(data);
    const col = css(avg.rgb);
    this._elOrb.style.backgroundColor = col;
    this._elOrb.style.opacity = avg.anyOn ? "1" : ".4";
    this._elOrb.style.boxShadow = avg.anyOn
      ? `0 0 ${30 + avg.level * 50}px ${6 + avg.level * 14}px color-mix(in srgb, ${col} ${Math.round(35 + avg.level * 35)}%, transparent)`
      : "none";
    this._elHalo.style.backgroundColor = col;
    this._elHalo.style.opacity = avg.anyOn ? String(0.12 + avg.level * 0.18) : "0.06";
    this._elOrb.setAttribute("aria-label", `${t("avg")} ${avg.anyOn ? hex(avg.rgb) : t("off")}`);
    this._elAvg.replaceChildren(
      h("span", { text: t("avg") }),
      h("strong", { text: avg.anyOn ? hex(avg.rgb).toUpperCase() : t("off") }),
    );
    this._elDots.replaceChildren(...data.map((d) => h("span", {
      class: "dot tip-up tip-c" + (d.on ? "" : " off"),
      style: d.on ? `background-color:${css(d.rgb)};box-shadow:0 0 8px ${css(d.rgb)}` : null,
      "data-tip": d.info.name || d.info.entity_id,
      "aria-label": d.info.name || d.info.entity_id,
      role: "img",
    })));
  }

  /* ---- status ---- */

  _renderStatus() {
    if (!this._built) return;
    const t = makeT(this._hass);
    const eng = this._status.engine?.[this._area];
    const planner = this._status.planner || {};
    const follow = planner.follow?.[this._area];
    const ai = planner.ai;
    const items = [];
    const active = !!eng?.active;
    this._elOrb.classList.toggle("running", active);

    if (active) {
      const pat = t(`p.${eng.pattern}`) !== `p.${eng.pattern}` ? t(`p.${eng.pattern}`) : eng.pattern || "";
      let label = `${t("running")}: ${pat}`;
      if (eng.source === "music") {
        const title = follow?.title ?? follow?.track?.title;
        label += ` · ${t("sourceMusic")}${title ? ` — ${title}` : ""}`;
      } else if (eng.source === "chat") label += ` · ${t("sourceChat")}`;
      items.push(h("span", { class: "pill live", text: label }));
    } else {
      items.push(h("span", { class: "pill", text: t("idle") }));
    }
    if (ai && typeof ai.used === "number") {
      const limited = ai.limit > 0 && ai.used >= ai.limit;
      items.push(h("span", { class: "pill" + (limited ? " warn" : ""), text: `${t("aiBudget")} ${ai.used}/${ai.limit}` }));
    }
    const rl = follow && (follow.rate_limited || follow.status === "rate_limited" || follow.error === "rate_limited");
    if (rl) items.push(h("span", { class: "pill warn", text: t("rateLimitedNote") }));
    if (active) {
      items.push(h("button", { class: "stopbtn", type: "button", onclick: () => this._stop() }, t("stop")));
    }
    this._elStatus.replaceChildren(...items);
  }

  async _stop() {
    if (!this._area) return;
    try { await this._hass.callWS({ type: "lightcompanion/stop", area_id: this._area }); }
    catch (err) { this._push(this._area, "bot", this._errText(errorCode(err)), true); }
  }

  /* ---- chat ---- */

  _thread(area) {
    if (!this._threads.has(area)) this._threads.set(area, []);
    return this._threads.get(area);
  }

  _push(area, role, text, isErr = false) {
    this._thread(area).push({ role, text, err: isErr });
    if (area === this._area) this._renderMessages();
  }

  _errText(code) {
    const t = makeT(this._hass);
    const k = `err.${code}`;
    return t(k) !== k ? t(k) : t("err.generic");
  }

  _renderMessages() {
    if (!this._built) return;
    const t = makeT(this._hass);
    const nodes = [];
    if (this._loadError) {
      nodes.push(h("div", { class: "notice", text: this._loadError === "not_loaded" || this._loadError === "unknown_command" ? t("notLoaded") : this._errText(this._loadError) }));
    } else if (this._areasLoaded && !this._areas.length) {
      nodes.push(h("div", { class: "notice", text: t("noAreas") }));
    }
    const thread = this._area ? this._thread(this._area) : [];
    if (!thread.length && this._area && !this._pending.has(this._area)) {
      nodes.push(h("div", { class: "empty" },
        h("div", { text: t("emptyHint") }),
        h("div", { class: "sugs" }, (STRINGS[makeLang(this._hass)].suggestions || []).map((s) =>
          h("button", { class: "sug", type: "button", onclick: () => this._send(s) }, s)))));
    }
    for (const m of thread) {
      nodes.push(h("div", { class: `bubble ${m.role === "user" ? "user" : "bot"}${m.err ? " err" : ""}`, text: m.text }));
    }
    if (this._pending.has(this._area)) {
      nodes.push(h("div", { class: "bubble bot typing", role: "status", "aria-label": t("thinking") }, h("span"), h("span"), h("span")));
    }
    this._elMsgs.replaceChildren(...nodes);
    this._elMsgs.scrollTop = this._elMsgs.scrollHeight;
    this._updateComposer();
  }

  async _send(text) {
    text = String(text || "").trim();
    const area = this._area;
    if (!text || !area || this._pending.has(area)) return;
    this._elInput.value = "";
    this._push(area, "user", text);
    this._pending.add(area);
    this._renderMessages();
    const lang = this._hass?.locale?.language || this._hass?.language;
    try {
      const res = await this._hass.callWS({ type: "lightcompanion/chat", area_id: area, text, language: lang || undefined });
      this._pending.delete(area);
      if (res?.error) {
        const friendly = this._errText(res.error);
        this._push(area, "bot", res.reply ? `${res.reply}\n\n${friendly}` : friendly, true);
      } else {
        this._push(area, "bot", res?.reply || "…");
      }
    } catch (err) {
      this._pending.delete(area);
      this._push(area, "bot", this._errText(errorCode(err)), true);
    }
    this._renderMessages();
  }

  /* ---- voice ---- */

  _toggleVoice() {
    if (this._voice) { this._voice.stop(); return; }
    this._startVoice();
  }

  _setListening(on) {
    const t = makeT(this._hass);
    this._elMic.classList.toggle("rec", on);
    this._elMic.setAttribute("aria-label", on ? t("micStop") : t("mic"));
    this._elMic.dataset.tip = on ? t("micStop") : t("mic");
    this._elInput.placeholder = on ? t("listening") : t("placeholder");
  }

  async _startVoice() {
    const t = makeT(this._hass);
    const canAssist = window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.AudioWorkletNode && this._hass?.connection?.socket;
    if (canAssist) {
      try {
        await this._startAssist();
        return;
      } catch (err) {
        console.debug("lightcompanion: Assist STT unavailable, falling back", err);
        this._voice = null;
        this._setListening(false);
      }
    }
    if (!this._startSpeech()) this._push(this._area, "bot", t("noSpeech"), true);
  }

  async _startAssist() {
    const conn = this._hass.connection;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    let ctx, node, url, unsub;
    const cleanupAudio = () => {
      try { node?.disconnect(); } catch (_e) { /* noop */ }
      stream.getTracks().forEach((tr) => tr.stop());
      try { ctx?.close(); } catch (_e) { /* noop */ }
    };
    let handlerId = null;
    let queue = [];
    let audioDone = false;
    let endSent = false;
    let gotText = false;
    let settled = false;
    let safety = null;

    const sendFrame = (buf) => {
      const out = new Uint8Array(1 + (buf ? buf.byteLength : 0));
      out[0] = handlerId;
      if (buf) out.set(new Uint8Array(buf), 1);
      conn.socket.send(out);
    };
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(safety);
      cleanupAudio();
      if (unsub) { try { unsub(); } catch (_e) { /* noop */ } }
      this._voice = null;
      this._setListening(false);
    };
    const endAudio = () => {
      if (audioDone) return;
      audioDone = true;
      cleanupAudio();
      if (handlerId !== null && !endSent) { endSent = true; try { sendFrame(null); } catch (_e) { /* noop */ } }
    };
    const fail = (fallback) => {
      finish();
      if (fallback && !gotText && !this._startSpeech()) this._push(this._area, "bot", makeT(this._hass)("noSpeech"), true);
    };

    this._voice = { stop: (silent) => { endAudio(); if (silent) finish(); } };
    this._setListening(true);

    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const blob = new Blob([WORKLET_SRC], { type: "application/javascript" });
      url = URL.createObjectURL(blob);
      await ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const source = ctx.createMediaStreamSource(stream);
      node = new AudioWorkletNode(ctx, "lc-pcm", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      node.port.onmessage = (ev) => {
        if (audioDone) return;
        if (handlerId === null) queue.push(ev.data);
        else { try { sendFrame(ev.data); } catch (_e) { /* noop */ } }
      };
      const mute = ctx.createGain();
      mute.gain.value = 0;
      source.connect(node);
      node.connect(mute);
      mute.connect(ctx.destination);
      if (ctx.state === "suspended") await ctx.resume();
    } catch (err) {
      finish();
      throw err;
    }

    safety = setTimeout(() => endAudio(), 20000);
    const area = this._area;
    try {
      unsub = await conn.subscribeMessage((ev) => {
        const d = ev?.data || {};
        switch (ev?.type) {
          case "run-start":
            handlerId = d.runner_data?.stt_binary_handler_id ?? null;
            if (handlerId === null) { fail(true); return; }
            for (const b of queue) { try { sendFrame(b); } catch (_e) { /* noop */ } }
            queue = [];
            if (audioDone && !endSent) { endSent = true; sendFrame(null); }
            break;
          case "stt-vad-end":
            endAudio();
            break;
          case "stt-end": {
            const text = d.stt_output?.text;
            gotText = !!text;
            endAudio();
            if (text) {
              this._elInput.value = text;
              this._send(text);
            }
            break;
          }
          case "error":
            endAudio();
            if (d.code === "stt-no-text-recognized") {
              this._push(area, "bot", makeT(this._hass)("noCatch"), true);
              finish();
            } else fail(true);
            break;
          case "run-end":
            finish();
            break;
          default:
        }
      }, { type: "assist_pipeline/run", start_stage: "stt", end_stage: "stt", input: { sample_rate: 16000 } });
    } catch (err) {
      finish();
      throw err;
    }
    if (settled) { try { unsub(); } catch (_e) { /* noop */ } }
  }

  _startSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return false;
    const rec = new SR();
    rec.lang = this._hass?.locale?.language || this._hass?.language || "en";
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = "";
    const done = () => { this._voice = null; this._setListening(false); };
    rec.onresult = (e) => {
      let txt = "";
      for (const r of e.results) { txt += r[0].transcript; if (r.isFinal) finalText = txt; }
      this._elInput.value = txt;
    };
    rec.onerror = () => done();
    rec.onend = () => {
      const had = this._voice;
      done();
      if (had && finalText.trim()) this._send(finalText);
    };
    this._voice = { stop: () => { try { rec.stop(); } catch (_e) { /* noop */ } } };
    this._setListening(true);
    try { rec.start(); } catch (_e) { done(); return false; }
    return true;
  }

  /* ---- settings dialog (desktop only) ---- */

  async _openSettings() {
    if (this._modalEl) return;
    const t = makeT(this._hass);
    this._opener = this.shadowRoot.activeElement;
    const body = h("div", { class: "body" }, h("div", { class: "help", text: t("sLoading") }));
    const dialog = h("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": t("sTitle"), tabindex: "-1" },
      h("header", {}, h("h2", { text: t("sTitle") }),
        h("button", { class: "iconbtn", type: "button", "aria-label": t("sClose"), onclick: () => this._closeSettings() }, icon("close"))),
      body);
    const backdrop = h("div", { class: "backdrop", onmousedown: (e) => { if (e.target === backdrop) this._closeSettings(); } }, dialog);
    this._modalEl = backdrop;
    this._onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); this._closeSettings(); return; }
      if (e.key !== "Tab") return;
      const f = [...dialog.querySelectorAll("button, input, select, [tabindex]:not([tabindex='-1'])")].filter((n) => !n.disabled && n.offsetParent !== null);
      if (!f.length) return;
      const act = this.shadowRoot.activeElement;
      if (e.shiftKey && (act === f[0] || act === dialog)) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && act === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    };
    backdrop.addEventListener("keydown", this._onKey);
    this._elModal.append(backdrop);
    dialog.focus();

    try {
      const data = await this._hass.callWS({ type: "lightcompanion/settings/get" });
      if (this._modalEl !== backdrop) return;
      dialog.replaceChildren(dialog.firstChild, ...this._settingsForm(data, dialog));
      dialog.querySelector("select, input, button.btn")?.focus();
    } catch (err) {
      body.replaceChildren(h("div", { class: "formerr", text: this._errText(errorCode(err)) }));
    }
  }

  _closeSettings() {
    if (!this._modalEl) return;
    this._modalEl.remove();
    this._modalEl = null;
    try { this._opener?.focus?.(); } catch (_e) { /* noop */ }
  }

  _settingsForm(data, dialog) {
    const t = makeT(this._hass);
    const s = data.settings || {};
    const admin = !!data.is_admin;
    const providers = (data.providers || []).map((p) => (typeof p === "string" ? { value: p } : { value: p.value ?? p.id ?? p.key, label: p.label ?? p.name }));
    const provLabel = (p) => (t(`prov.${p.value}`) !== `prov.${p.value}` ? t(`prov.${p.value}`) : p.label || p.value);
    const candidates = data.light_candidates || [];
    const states = this._hass?.states || {};
    const ids = (domain) => Object.keys(states).filter((e) => e.startsWith(domain + ".")).sort();
    const ro = !admin;
    const f = {}; // field refs

    const field = (label, control, help, warn) => h("div", { class: "field" },
      h("label", { text: label }, ), control,
      help ? h("div", { class: "help", text: help }) : null, warn ? h("div", { class: "warn", text: warn }) : null);
    const select = (opts, val) => {
      const el = h("select", { disabled: ro });
      for (const [v, l] of opts) el.append(h("option", { value: v, text: l, selected: String(v) === String(val ?? "") }));
      el.value = String(val ?? "");
      return el;
    };
    const entityOpts = (domain, cur) => {
      const list = ids(domain);
      if (cur && !list.includes(cur)) list.unshift(cur);
      return [["", t("sDefaultEntity")], ...list.map((e) => [e, states[e]?.attributes?.friendly_name || e])];
    };
    const slider = (min, max, val) => {
      const out = h("output", { text: String(val) });
      const input = h("input", { type: "range", min, max, step: 1, value: val, disabled: ro, oninput: () => { out.textContent = input.value; } });
      return { input, wrap: h("div", { class: "row" }, input, out) };
    };

    f.provider = select(providers.map((p) => [p.value, provLabel(p)]), s.llm_provider);
    f.model = h("input", { type: "text", value: s.model || "", disabled: ro, autocomplete: "off" });
    f.key = h("input", { type: "password", value: "", placeholder: s.has_api_key ? t("sApiKeySaved") : "", disabled: ro, autocomplete: "new-password" });
    f.aiTask = select(entityOpts("ai_task", s.ai_task_entity), s.ai_task_entity);
    f.conv = select(entityOpts("conversation", s.conversation_agent), s.conversation_agent);
    const calls = slider(5, 200, s.ai_calls_per_hour ?? 50);
    const rate = slider(1, 10, s.light_rate ?? 4);
    f.calls = calls.input; f.rate = rate.input;
    f.strobe = h("input", { type: "checkbox", checked: !!s.allow_strobe, disabled: ro });
    f.keywords = h("input", { type: "text", value: (s.exclude_keywords || []).join(", "), disabled: ro, autocomplete: "off" });
    f.panel = h("input", { type: "checkbox", checked: !!s.show_panel, disabled: ro });
    f.defArea = select([["", t("sNone")], ...this._areas.map((a) => [a.area_id, a.name || a.area_id])], s.default_area);

    const players = ids("media_player");
    f.players = {};
    const playerRows = this._areas.map((a) => {
      const cur = (s.player_overrides || {})[a.area_id] || "";
      const list = cur && !players.includes(cur) ? [cur, ...players] : players;
      f.players[a.area_id] = select([["", t("sAuto")], ...list.map((e) => [e, states[e]?.attributes?.friendly_name || e])], cur);
      return field(a.name || a.area_id, f.players[a.area_id]);
    });

    const explicit = new Set(s.excluded_lights || []);
    const kw = () => f.keywords.value.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
    f.lightBoxes = [];
    const lightRows = candidates.map((c) => {
      const box = h("input", { type: "checkbox", checked: explicit.has(c.entity_id), disabled: ro });
      const note = h("small", {});
      f.lightBoxes.push({ id: c.entity_id, box, note, hay: `${c.name || ""} ${c.area || ""}`.toLowerCase() });
      return h("label", { class: "check" }, box, h("span", {}, c.name || c.entity_id, " ", h("small", { text: c.area ? `· ${c.area}` : "" }), " ", note));
    });
    const refreshKw = () => {
      const words = kw();
      for (const lb of f.lightBoxes) {
        const hit = words.some((w) => lb.hay.includes(w));
        lb.hit = hit;
        if (hit) { lb.box.checked = true; lb.box.disabled = true; lb.note.textContent = `(${t("sKeyword")})`; }
        else { lb.box.disabled = ro; lb.note.textContent = ""; }
      }
    };
    f.keywords.addEventListener("input", refreshKw);
    refreshKw();

    const providerFields = h("div", { class: "field-group", style: "display:flex;flex-direction:column;gap:14px" });
    const fModel = field(t("sModel"), f.model);
    const fKey = field(t("sApiKey"), f.key, t("sApiKeyHelp"));
    const fAi = field(t("sAiTask"), f.aiTask);
    const fConv = field(t("sConversation"), f.conv);
    providerFields.append(fAi, fConv, fModel, fKey);
    const syncProvider = () => {
      const p = f.provider.value;
      fAi.hidden = p !== "ai_task";
      fConv.hidden = p !== "conversation";
      fModel.hidden = fKey.hidden = !["openai", "anthropic", "google"].includes(p);
    };
    f.provider.addEventListener("change", syncProvider);
    syncProvider();

    const checkRow = (box, label) => h("label", { class: "check" }, box, h("span", { text: label }));
    const err = h("div", { class: "formerr", role: "alert" });

    const bodyEl = h("div", { class: "body" },
      ro ? h("div", { class: "notice", style: "margin:0", text: t("sReadOnly") }) : null,
      field(t("sProvider"), f.provider),
      providerFields,
      field(t("sCalls"), calls.wrap),
      field(t("sRate"), rate.wrap),
      h("div", { class: "field" }, checkRow(f.strobe, t("sStrobe")), h("div", { class: "warn", text: t("sStrobeWarn") })),
      h("div", { class: "field" }, h("span", { class: "lbl", text: t("sExcluded") }), h("div", { class: "list" }, lightRows), h("div", { class: "help", text: t("sExcludedHelp") })),
      field(t("sKeywords"), f.keywords, t("sKeywordsHelp")),
      h("div", { class: "field" }, h("span", { class: "lbl", text: t("sPlayers") }), playerRows),
      field(t("sDefaultArea"), f.defArea),
      h("div", { class: "field" }, checkRow(f.panel, t("sPanel"))),
      err,
    );

    const save = h("button", { class: "btn primary", type: "button", disabled: ro, onclick: async () => {
      const next = {
        llm_provider: f.provider.value,
        ai_task_entity: f.aiTask.value || null,
        conversation_agent: f.conv.value || null,
        model: f.model.value.trim() || null,
        ai_calls_per_hour: Number(f.calls.value),
        light_rate: Number(f.rate.value),
        allow_strobe: f.strobe.checked,
        exclude_keywords: kw(),
        default_area: f.defArea.value || null,
        show_panel: f.panel.checked,
        excluded_lights: f.lightBoxes.filter((lb) => lb.box.checked && !lb.hit).map((lb) => lb.id),
        player_overrides: Object.fromEntries(Object.entries(f.players).filter(([, el]) => el.value).map(([k, el]) => [k, el.value])),
      };
      const norm = (v) => JSON.stringify(Array.isArray(v) ? [...v].sort() : v ?? null);
      const changed = {};
      for (const [k, v] of Object.entries(next)) {
        let before = s[k];
        if (k === "player_overrides") before = s[k] || {};
        if (k === "model" || k === "ai_task_entity" || k === "conversation_agent" || k === "default_area") before = s[k] || null;
        if (k === "player_overrides" ? JSON.stringify(v) !== JSON.stringify(before) : norm(v) !== norm(before)) changed[k] = v;
      }
      if (f.key.value) changed.api_key = f.key.value;
      if (!Object.keys(changed).length) { this._closeSettings(); return; }
      save.disabled = true; save.textContent = t("sSaving"); err.textContent = "";
      try {
        await this._hass.callWS({ type: "lightcompanion/settings/set", options: changed });
        f.key.value = "";
        this._closeSettings();
        this._push(this._area, "bot", t("sSaved"));
        setTimeout(() => { if (this._connected) this._init(); }, 3000);
      } catch (e) {
        save.disabled = false; save.textContent = t("sSave");
        err.textContent = `${t("sFail")}: ${e?.message || errorCode(e)}`;
      }
    } }, t("sSave"));

    return [bodyEl, h("footer", {}, h("button", { class: "btn", type: "button", onclick: () => this._closeSettings() }, t(ro ? "sClose" : "sCancel")), ro ? null : save)];
  }
}

function makeLang(hass) {
  const lang = String(hass?.locale?.language || hass?.language || "en").toLowerCase();
  return lang.startsWith("de") ? "de" : "en";
}

/* ----------------------------------------------------------------- Editor */

class LightCompanionCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._areas = null;
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) { this._config = { ...(config || {}) }; this._render(); }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }

  async _load() {
    try {
      const res = await this._hass.callWS({ type: "lightcompanion/areas" });
      this._areas = res?.areas || [];
    } catch (_e) {
      this._areas = [];
    }
    this._render();
  }

  _changed(area) {
    const config = { ...this._config };
    if (area) config.area = area; else delete config.area;
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }

  _render() {
    const t = makeT(this._hass);
    const root = this.shadowRoot;
    const style = h("style", { text: `
      :host { display: block; }
      label { display: block; font-size: 13px; color: var(--secondary-text-color); margin-bottom: 4px; }
      select, input { width: 100%; box-sizing: border-box; min-height: 44px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
      select:focus-visible, input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }` });
    let control;
    if (this._areas && this._areas.length) {
      control = h("select", { onchange: (e) => this._changed(e.target.value) },
        h("option", { value: "", text: t("eAuto") }),
        ...this._areas.map((a) => h("option", { value: a.area_id, text: a.name || a.area_id, selected: a.area_id === this._config.area })));
      control.value = this._config.area || "";
    } else {
      control = h("input", { type: "text", value: this._config.area || "", placeholder: "area_id", onchange: (e) => this._changed(e.target.value.trim()) });
    }
    root.replaceChildren(style, h("div", {}, h("label", { text: t("eArea") }), control));
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, LightCompanionCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, LightCompanionCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Light Companion",
    description: "Chat or voice control for room lighting effects, with a live average-color glow.",
    preview: true,
  });
}
