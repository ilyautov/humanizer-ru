// humanizer-ru: фоновый воркер расширения. Одна обязанность: пункт контекстного
// меню на выделенном тексте, который передаёт выделение в попап через
// chrome.storage.session и открывает попап. Сеть не используется, ничего не
// отправляется: сканер целиком в popup (vendor/scan.js + vendor/scan-rules.js).

const MENU_ID = "humanizer-ru-scan-selection";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Проверить на следы нейросети",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) return;
  await chrome.storage.session.set({ pending: { text: info.selectionText, at: Date.now() } });
  try {
    await chrome.action.openPopup();
  } catch (e) {
    // openPopup недоступен (старый Chrome или окно без фокуса): открываем
    // попап обычной вкладкой, он сам заберёт pending из storage.session.
    await chrome.tabs.create({ url: chrome.runtime.getURL("popup.html?tab=1") });
  }
});
