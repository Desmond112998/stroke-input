"use strict";

const DEFAULTS = Object.freeze({
  toggleKey: "`",
  interceptPassword: false,
  wubiHuaMode: false,
  showAssociations: true,
  numpadStrokes: false,
  chinesePunctuation: true,
  g6PhraseCodes: true,
});

const toggleKeyInput = document.getElementById("toggleKey");
const interceptPasswordInput = document.getElementById("interceptPassword");
const wubiHuaModeInput = document.getElementById("wubiHuaMode");
const showAssociationsInput = document.getElementById("showAssociations");
const numpadStrokesInput = document.getElementById("numpadStrokes");
const chinesePunctuationInput = document.getElementById("chinesePunctuation");
const g6PhraseCodesInput = document.getElementById("g6PhraseCodes");
const statusEl = document.getElementById("status");

function setStatus(msg) {
  statusEl.textContent = msg || "";
}

function readForm() {
  return {
    toggleKey: (toggleKeyInput.value || "").trim() || DEFAULTS.toggleKey,
    interceptPassword: interceptPasswordInput.checked,
    wubiHuaMode: wubiHuaModeInput.checked,
    showAssociations: showAssociationsInput.checked,
    numpadStrokes: numpadStrokesInput.checked,
    chinesePunctuation: chinesePunctuationInput.checked,
    g6PhraseCodes: g6PhraseCodesInput.checked,
  };
}

function applyToForm(settings) {
  const s = { ...DEFAULTS, ...(settings || {}) };
  toggleKeyInput.value = s.toggleKey || DEFAULTS.toggleKey;
  interceptPasswordInput.checked = !!s.interceptPassword;
  wubiHuaModeInput.checked = !!s.wubiHuaMode;
  showAssociationsInput.checked = s.showAssociations !== false;
  numpadStrokesInput.checked = !!s.numpadStrokes;
  chinesePunctuationInput.checked = s.chinesePunctuation !== false;
  g6PhraseCodesInput.checked = s.g6PhraseCodes !== false;
}

function load() {
  chrome.storage.local.get(["imeSettings"], (data) => {
    if (chrome.runtime.lastError) {
      setStatus("讀取設定失敗");
      applyToForm(DEFAULTS);
      return;
    }
    applyToForm({ ...DEFAULTS, ...(data.imeSettings || {}) });
  });
}

function save(settings) {
  chrome.storage.local.set({ imeSettings: settings }, () => {
    if (chrome.runtime.lastError) {
      setStatus("儲存失敗");
      return;
    }
    setStatus("已儲存");
  });
}

toggleKeyInput.addEventListener("keydown", (e) => {
  // Capture the physical key the user intends as the toggle.
  if (e.key === "Tab") return;
  e.preventDefault();
  if (e.key === "Shift" || e.key === "Control" || e.key === "Alt" || e.key === "Meta") {
    return;
  }
  toggleKeyInput.value = e.key;
});

document.getElementById("save").addEventListener("click", () => {
  const settings = readForm();
  if (!settings.toggleKey) {
    setStatus("開關按鍵唔可以留空");
    return;
  }
  save(settings);
});

document.getElementById("reset").addEventListener("click", () => {
  applyToForm(DEFAULTS);
  save({ ...DEFAULTS });
  setStatus("已還原預設");
});

load();
