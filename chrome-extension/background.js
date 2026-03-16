// Background service worker for global on/off state
// Persists active state across all tabs via chrome.storage.local

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ active: false, chineseMode: true });
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "getState") {
    chrome.storage.local.get(["active", "chineseMode"], (data) => {
      sendResponse({ active: !!data.active, chineseMode: data.chineseMode !== false });
    });
    return true;
  }

  if (msg.type === "setState") {
    const update = {};
    if (msg.active !== undefined) update.active = msg.active;
    if (msg.chineseMode !== undefined) update.chineseMode = msg.chineseMode;
    chrome.storage.local.set(update, () => {
      chrome.tabs.query({}, (tabs) => {
        for (const tab of tabs) {
          chrome.tabs.sendMessage(tab.id, {
            type: "stateChanged",
            active: msg.active,
            chineseMode: msg.chineseMode,
          }).catch(() => {});
        }
      });
      sendResponse({ ok: true });
    });
    return true;
  }
});
