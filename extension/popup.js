// humanizer-ru popup: только DOM. Движок в vendor/scan.js, правила в
// vendor/scan-rules.js (копии из docs/, их кладёт scripts/build_extension.py).
// Работает и вне контекста расширения (открыт как файл): chrome.* обёрнуты.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const textEl = $("text"), genreEl = $("genre"), countEl = $("count");
  const resultEl = $("result"), markedWrap = $("marked-wrap"), markedEl = $("marked");
  if (typeof globalThis.humanizerScan !== "function") {
    resultEl.innerHTML = `<p class="empty">Сканер не загрузился: нет vendor/scan.js. Соберите расширение скриптом scripts/build_extension.py.</p>`;
    return;
  }

  // --- chrome.storage с запасным вариантом вне расширения --------------------
  const hasChrome = typeof chrome !== "undefined" && chrome.storage;
  const mem = {};
  const store = {
    async get(area, key) {
      try { if (hasChrome && chrome.storage[area]) return (await chrome.storage[area].get(key))[key]; } catch (e) { /* нет контекста */ }
      return mem[`${area}:${key}`];
    },
    async set(area, key, value) {
      try { if (hasChrome && chrome.storage[area]) { await chrome.storage[area].set({ [key]: value }); return; } } catch (e) { /* нет контекста */ }
      mem[`${area}:${key}`] = value;
    },
    async remove(area, key) {
      try { if (hasChrome && chrome.storage[area]) { await chrome.storage[area].remove(key); return; } } catch (e) { /* нет контекста */ }
      delete mem[`${area}:${key}`];
    },
  };

  // --- Утилиты (как на сайте) -------------------------------------------------
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  };
  const wordsOf = (t) => t.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  const updateCount = () => {
    const n = wordsOf(textEl.value);
    countEl.textContent = `${n} ${plural(n, "слово", "слова", "слов")}`;
  };

  // --- Рендер ---------------------------------------------------------------
  function renderResult(r) {
    const band = r.band === "чисто" ? "good" : r.band === "правка" ? "warn" : "bad";
    const bandText = { good: "чисто: следы ИИ не мешают", warn: "точечная правка", bad: "нужен рерайт" }[band];
    const rows = r.penalties.map((p) => `<li><b>${p.points}</b><span>${esc(p.reason)}</span></li>`).join("");
    const notes = r.notes.map((n) => `<p class="sterile">${esc(n)}</p>`).join("");
    const bans = r.effective_bans.reduce((n, h) => n + h.count, 0);
    const marks = r.muted_markers.reduce((n, h) => n + h.count, 0);
    resultEl.className = band;
    resultEl.innerHTML = `
      <div class="score-row">
        <div class="score-num">${r.score}<small>/100</small></div>
        <div>
          <div class="score-band">${bandText}</div>
          <div class="score-facts">${bans} ${plural(bans, "жёсткий запрет", "жёстких запрета", "жёстких запретов")}, ${marks} ${plural(marks, "маркер", "маркера", "маркеров")}, ${r.words} ${plural(r.words, "слово", "слова", "слов")}</div>
        </div>
      </div>
      <div class="score-bar" role="img" aria-label="Чистота ${r.score} из 100"><span class="score-fill"></span><i class="tick t60"></i><i class="tick t85"></i></div>
      ${rows ? `<ul class="penalties">${rows}</ul>` : `<p class="none">Штрафов нет.</p>`}
      ${notes}`;
    // setTimeout, а не requestAnimationFrame: в неактивной вкладке rAF не тикает,
    // и полоса застывала на нуле.
    setTimeout(() => { const f = resultEl.querySelector(".score-fill"); if (f) f.style.transform = `scaleX(${r.score / 100})`; }, 30);
  }

  function renderMarked(text, r) {
    const spans = [];
    for (const h of r.effective_bans) for (const [a, b] of h.positions) spans.push({ a, b, cls: "ban", name: h.name });
    for (const h of r.muted_markers) for (const [a, b] of h.positions) spans.push({ a, b, cls: "mk", name: `${h.category}: ${h.name}` });
    spans.sort((x, y) => x.a - y.a || (x.cls === "ban" ? -1 : 1));
    let out = "", pos = 0;
    for (const s of spans) {
      if (s.a < pos) continue;
      out += esc(text.slice(pos, s.a));
      out += `<mark class="${s.cls}" title="${esc(s.name)}">${esc(text.slice(s.a, s.b))}</mark>`;
      pos = s.b;
    }
    out += esc(text.slice(pos));
    markedEl.innerHTML = out;
    markedWrap.hidden = spans.length === 0;
  }

  function run() {
    const text = textEl.value;
    if (!text.trim()) {
      resultEl.className = "";
      resultEl.innerHTML = `<p class="empty">Без текста проверять нечего.</p>`;
      markedWrap.hidden = true;
      return;
    }
    const r = globalThis.humanizerScan(text, genreEl.value || null);
    renderResult(r);
    renderMarked(text, r);
    store.set("local", "last", { text, genre: genreEl.value });
  }

  let timer = null;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(run, 300); };
  textEl.addEventListener("input", () => { updateCount(); schedule(); });
  genreEl.addEventListener("change", run);

  // --- Старт: выделение из контекстного меню, иначе прошлый текст -------------
  (async () => {
    if (new URLSearchParams(location.search).get("tab")) document.body.classList.add("as-tab");
    try {
      const v = hasChrome && chrome.runtime && chrome.runtime.getManifest ? chrome.runtime.getManifest().version : "";
      if (v) $("version").textContent = `v${v}`;
    } catch (e) { /* вне расширения */ }
    const pending = await store.get("session", "pending");
    if (pending && pending.text && Date.now() - (pending.at || 0) < 60_000) {
      textEl.value = pending.text;
      await store.remove("session", "pending");
    } else {
      const last = await store.get("local", "last");
      if (last && last.text) { textEl.value = last.text; if (last.genre) genreEl.value = last.genre; }
    }
    updateCount();
    run();
  })();
})();
