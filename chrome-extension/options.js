"use strict";

const DEFAULTS = Object.freeze({
  toggleKey: "`",
  interceptPassword: false,
});

const toggleKeyInput = document.getElementById("toggleKey");
const interceptPasswordInput = document.getElementById("interceptPassword");
const statusEl = document.getElementById("status");

function setStatus(msg) {
  statusEl.textContent = msg || "";
}

function applyToForm(settings) {
  toggleKeyInput.value = settings.toggleKey || DEFAULTS.toggleKey;
  interceptPasswordInput.checked = !!settings.interceptPassword;
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
  const key = (toggleKeyInput.value || "").trim();
  if (!key) {
    setStatus("開關按鍵唔可以留空");
    return;
  }
  save({
    toggleKey: key,
    interceptPassword: interceptPasswordInput.checked,
  });
});

document.getElementById("reset").addEventListener("click", () => {
  applyToForm(DEFAULTS);
  save({ ...DEFAULTS });
  setStatus("已還原預設");
});

load();
