// Тема до первой отрисовки, чтобы не мигать: копия выбора в localStorage.
// Отдельным файлом, потому что CSP расширения запрещает встроенные скрипты.
try {
  const t = localStorage.getItem("humanizer-ru:theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
} catch (e) { /* хранилище закрыто */ }
