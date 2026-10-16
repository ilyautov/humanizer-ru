// humanizer-ru: интерфейс онлайн-аудита на главной и на странице-инструменте.
// Движок в scan.js, правила в scan-rules.js (экспорт из Python). Здесь только DOM:
// балл и штрафы, подсветка с подсказкой по клику, сравнение «было и стало»
// с браузерным факт-замком, черновик в localStorage этого браузера.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const textEl = $("audit-text"), genreEl = $("audit-genre"), runBtn = $("audit-run");
  const countEl = $("audit-count"), resultEl = $("audit-result"), sourceEl = $("audit-source");
  const markedWrap = $("audit-marked"), markedEl = $("audit-text-marked"), nextEl = $("audit-next"), installEl = $("install");
  const artEl = $("audit-scale-line"), hintEl = $("audit-hint"), clearBtn = $("audit-clear");
  const cmpToggle = $("audit-compare-toggle"), cmpWrap = $("audit-compare"), afterEl = $("audit-after"), cmpOut = $("audit-compare-result");
  if (!textEl || typeof globalThis.humanizerScan !== "function" || !globalThis.humanizerHints) return;
  const RULES = globalThis.HUMANIZER_RULES || {};
  // Подсказки, причины штрафов, жанровая и «не измерено» строки живут в
  // hints.js: те же тексты на главной и в расширении.
  const H = globalThis.humanizerHints;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // У каждого примера свой жанр: справочный текст проверяется как новости,
  // иначе энциклопедия получает штраф за тире, которое у людей норма.
  // Тексты примеров это данные, а не интерфейс: длинное тире в них записано
  // escape-последовательностью, как EXAMPLE в extension/popup.js.
  const EXAMPLES = {
    ai: { genre: "", source: "Пример: маркетинговый текст, сгенерированный GPT для eval-корпуса репозитория.",
      text: "В современном мире успешный бизнес \u2014 это не просто продукт, а целая экосистема ценностей. Наша компания является надёжным партнёром, который играет ключевую роль в развитии вашего дела. Мы предлагаем комплексный подход, способный вывести ваш бренд на новый уровень и раскрыть его потенциал по-настоящему. Стоит отметить, что в условиях растущей конкуренции важно понимать: связь с аудиторией и доверительные отношения становятся главным активом. Именно поэтому мы выстраиваем индивидуальный подход к каждому клиенту. Наше инновационное решение открывает новые горизонты для роста \u2014 от привлечения первых пользователей до масштабирования на международные рынки. Таким образом, выбирая нас, вы выбираете не только сервис, но и команду, которая разделяет ваши амбиции. Можно с уверенностью сказать: вместе мы расширим границы возможного и достигнем результата, который превзойдёт ожидания." },
    human: { genre: "news", source: "Пример: вводная часть статьи «Байкал» русской Википедии, CC BY-SA 4.0. Жанр «новости, энциклопедия»: тире и «является» в справочном тексте не считаются.",
      text: "Байкал (бур. Байгал далай) \u2014 озеро тектонического происхождения в южной части Восточной Сибири площадью 31 722 км². Самое глубокое озеро на планете, крупнейший природный резервуар пресной воды и самое большое по площади пресноводное озеро Евразии.\n\nОзеро и прибрежные территории являются уникальным биогеоценозом, бо́льшая часть видов животных которых эндемична. Озеро имеет сток \u2014 реку Ангара." },
    tech: { genre: "", source: "Пример: авторский пост с листингом и цитатой из ревью. Код и цитата в счёт не идут.",
      text: "Переписал вчера парсер логов: старый падал на строках с пустым полем длительности. Причина оказалась в одной строке.\n\n```python\ndef parse(line):\n    # В современном мире данный код является примером\n    return line.split(\"|\")[3] or None\n```\n\nКоллега в ревью написал:\n\n> Стоит отметить, что данный подход открывает новые горизонты и играет ключевую роль в оптимизации.\n\nЯ не понял ни слова, но тест зелёный. Оставил как есть, только переименовал функцию и добавил кейс на пустую строку. Три минуты работы, неделя тишины в алертах." },
  };

  const ENVS = [
    { key: "skills", label: "Любой агент", cmd: "npx skills add ilyautov/humanizer-ru",
      note: "Одна команда через skills.sh: Claude Code, Cursor, Codex, Copilot, Cline, OpenCode, Goose и ещё десятки агентов, читающих SKILL.md. CLI найдёт установленных агентов и спросит, куда ставить. Дальше скилл включается сам на «очеловечь», «убери канцелярит», «перепиши как человек»." },
    { key: "claude-code", label: "Плагин Claude Code", cmd: "/plugin marketplace add ilyautov/humanizer-ru\n/plugin install humanizer-ru@ilyautov-plugins",
      note: "Две команды внутри Claude Code. Плагин обновляется через /plugin, скилл включается сам по тем же фразам." },
    { key: "claude-ai", label: "Claude.ai", cmd: "https://github.com/ilyautov/humanizer-ru/releases/latest/download/humanizer-ru.zip",
      note: "Скачайте архив, затем Settings → Capabilities → Skills → Upload skill. Без установки чего-либо на компьютер." },
    { key: "codex", label: "Codex CLI", cmd: "git clone --depth 1 https://github.com/ilyautov/humanizer-ru\nmkdir -p ~/.codex/skills\ncp -r humanizer-ru/skills/humanizer-ru ~/.codex/skills/",
      note: "После установки перезапустите Codex. Вызов: $humanizer-ru или автоматически по триггер-фразам." },
    { key: "dsh", label: "DeepSeek Harness", cmd: "dsh plugin --profile web add humanizer-ru",
      note: "Бандл из npm. Профиль web, tui или headless, тот же пакет. Свежий main: github:ilyautov/humanizer-ru." },
  ];

  // --- Утилиты --------------------------------------------------------------
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const wordsOf = (t) => t.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;

  const num = H.num;
  function updateCount() {
    countEl.textContent = num(wordsOf(textEl.value), "слово", "слова", "слов");
  }
  const genreLabel = () => genreEl.options[genreEl.selectedIndex].textContent;

  // --- Черновик в этом браузере ---------------------------------------------
  // localStorage живёт только на этой машине и не уходит с сайта: обещание
  // «текст никуда не отправляется» остаётся в силе. Примеры не сохраняем.
  const DRAFT_KEY = "humanizer-ru:draft";
  let draftIsExample = false;
  const saveDraft = () => {
    try {
      if (draftIsExample || !textEl.value.trim()) { localStorage.removeItem(DRAFT_KEY); return; }
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ text: textEl.value, genre: genreEl.value, after: afterEl ? afterEl.value : "" }));
    } catch (e) { /* приватный режим или запрет хранения: работаем без черновика */ }
  };
  const loadDraft = () => {
    try {
      const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      if (!d || !d.text) return false;
      textEl.value = d.text; genreEl.value = d.genre || "";
      if (afterEl && d.after) { afterEl.value = d.after; openCompare(); }
      return true;
    } catch (e) { return false; }
  };

  const humanReason = H.humanReason;
  const nextLine = H.nextLine;
  const genreNote = () => H.genreNote(genreEl.value, genreLabel(), RULES);
  const unmeasuredLine = H.unmeasuredLine;
  const hintFor = (s) => H.hintFor(s.cls, s.cat, s.name);
  const kindLabel = H.kindLabel;
  const spanTitle = (s) => H.ruleName(s.cls === "ban" ? s.name : `${s.cat}: ${s.name}`);

  // --- Результат -------------------------------------------------------------
  function animateNumber(el, target) {
    if (reduceMotion || document.hidden) { el.textContent = target; return; }
    const t0 = performance.now(), dur = 650;
    const step = (now) => {
      // Метка кадра rAF бывает раньше t0: без нижней границы мелькнёт отрицательный балл.
      const k = Math.max(0, Math.min(1, (now - t0) / dur));
      const eased = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(target * eased);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  const bandOf = H.bandOf;
  const BAND_TEXT = { good: "чисто: следы ИИ не мешают", warn: "точечная правка", bad: "нужен рерайт" };
  const NO_FINDINGS = "оборотов не найдено";
  function factsLine(r) {
    // Тире сканер штрафует отдельно от фраз, поэтому и считаем отдельно.
    const dashName = (RULES.score && RULES.score.em_dash_name) || "Длинное тире";
    const bans = r.effective_bans.filter((h) => h.name !== dashName).reduce((n, h) => n + h.count, 0);
    const dashes = r.effective_bans.filter((h) => h.name === dashName).reduce((n, h) => n + h.count, 0);
    const marks = r.muted_markers.reduce((n, h) => n + h.count, 0);
    const parts = [];
    if (bans) parts.push(num(bans, "запрещённый оборот", "запрещённых оборота", "запрещённых оборотов"));
    if (dashes) parts.push(`длинное тире ${dashes > 1 ? `×${dashes}` : ""}`.trim());
    if (marks) parts.push(num(marks, "маркер", "маркера", "маркеров"));
    return parts.length ? parts.join(", ") : NO_FINDINGS;
  }

  let lastReport = "";
  let lastCompareReport = "";
  function renderResult(r, spans) {
    const band = bandOf(r);
    const bandText = BAND_TEXT[band];
    const rows = r.penalties.map((p) => `<li title="${esc(p.reason)}"><b>${p.points}</b><span>${esc(humanReason(p.reason))}</span></li>`).join("");
    const notes = r.notes.map((n) => `<p class="audit-sterile">${esc(n)}</p>`).join("");
    const gap = unmeasuredLine(r);
    const facts = factsLine(r);
    const gnote = genreNote();
    resultEl.hidden = false;
    if (artEl) artEl.hidden = true;
    resultEl.innerHTML = `
      <div class="score-row ${band}">
        <div class="score-num"><span id="score-value">0</span><small>/100</small></div>
        <div class="score-meta">
          <div class="score-band">${bandText}</div>
          <div class="score-facts">${esc(facts)}</div>
        </div>
      </div>
      <div class="score-bar" role="img" aria-label="Чистота ${r.score} из 100"><span class="score-fill"></span><i class="tick t60"></i><i class="tick t85"></i></div>
      <div class="score-labels" aria-hidden="true"><span class="l60">60</span><span class="l85">85</span></div>
      <p class="score-next">${esc(nextLine(band, spans.length > 0, r))}</p>
      ${rows ? `<ul class="penalties">${rows}</ul>` : `<p class="audit-none">Штрафов нет.</p>`}
      ${gnote ? `<p class="audit-genre-note">${esc(gnote)}</p>` : ""}
      ${notes}
      ${gap ? `<p class="audit-unmeasured">${esc(gap)}</p>` : ""}
      <div class="audit-actions"><button type="button" id="audit-copy">Скопировать отчёт</button></div>`;
    animateNumber($("score-value"), r.score);
    requestAnimationFrame(() => { const f = resultEl.querySelector(".score-fill"); if (f) f.style.transform = `scaleX(${r.score / 100})`; });

    const found = new Map();
    for (const s of spans) { const k = `${kindLabel(s.cls)} · ${spanTitle(s)}`; found.set(k, (found.get(k) || 0) + 1); }
    lastReport = [
      `humanizer-ru: ${r.score}/100, ${bandText}`,
      `жанр: ${genreLabel()} · ${num(r.words, "слово", "слова", "слов")} · ${facts}`,
      r.penalties.length ? "штрафы:\n" + r.penalties.map((p) => `  ${String(p.points).padStart(4)}  ${humanReason(p.reason)}`).join("\n") : "штрафов нет",
      found.size ? "найдено:\n" + [...found].map(([k, n]) => `  ${k}${n > 1 ? ` ×${n}` : ""}`).join("\n") : "",
      gap,
    ].filter(Boolean).join("\n");
    $("audit-copy").addEventListener("click", async () => {
      const btn = $("audit-copy");
      const report = [lastReport, lastCompareReport, "https://humanizer-ru.aifrontier.tech/"].filter(Boolean).join("\n");
      try { await navigator.clipboard.writeText(report); btn.textContent = "Скопировано"; }
      catch (e) { btn.textContent = "Выделите и скопируйте"; }
      setTimeout(() => { btn.textContent = "Скопировать отчёт"; }, 1800);
    });
  }

  // Конец подсветки тянем до границы слова только для показа: «ключев|ым»
  // режет слово и выглядит ошибкой. Счёт при этом не меняется.
  const wordEnd = (text, b) => { while (b < text.length && /[\p{L}\p{M}]/u.test(text[b])) b++; return b; };
  function collectSpans(text, r) {
    const spans = [];
    for (const h of r.effective_bans) for (const [a, b] of h.positions) spans.push({ a, b: wordEnd(text, b), cls: "ban", cat: "", name: h.name });
    for (const h of r.muted_markers) for (const [a, b] of h.positions) spans.push({ a, b: wordEnd(text, b), cls: "mk", cat: h.category, name: h.name });
    spans.sort((x, y) => x.a - y.a || (x.cls === "ban" ? -1 : 1));
    const out = []; let pos = 0;
    for (const s of spans) { if (s.a < pos) continue; out.push(s); pos = s.b; } // перекрытие: первый победил
    return out;
  }

  let lastSpans = [];
  function renderMarked(text, spans, showText) {
    if (hintEl) hintEl.hidden = true;
    lastSpans = spans;
    if (!showText) { markedWrap.hidden = true; markedEl.innerHTML = ""; return; }
    let out = "", pos = 0;
    spans.forEach((s, i) => {
      out += esc(text.slice(pos, s.a));
      out += `<mark class="${s.cls}" tabindex="0" role="button" aria-pressed="false" data-i="${i}" aria-label="${esc(kindLabel(s.cls))}: ${esc(spanTitle(s))}">${esc(text.slice(s.a, s.b))}</mark>`;
      pos = s.b;
    });
    out += esc(text.slice(pos));
    markedEl.innerHTML = out;
    markedWrap.hidden = false;
  }
  function showHint(mark) {
    const s = lastSpans[+mark.dataset.i];
    if (!s || !hintEl) return;
    const pressed = mark.getAttribute("aria-pressed") === "true";
    markedEl.querySelectorAll('mark[aria-pressed="true"]').forEach((m) => m.setAttribute("aria-pressed", "false"));
    if (pressed) { hintEl.hidden = true; return; }
    mark.setAttribute("aria-pressed", "true");
    hintEl.innerHTML = `<b class="${s.cls}">${esc(kindLabel(s.cls))}, ${esc(spanTitle(s))}.</b> ${esc(hintFor(s))}`;
    hintEl.hidden = false;
  }
  markedEl.addEventListener("click", (ev) => { const m = ev.target.closest("mark"); if (m) showHint(m); });
  markedEl.addEventListener("keydown", (ev) => {
    const m = ev.target.closest("mark");
    if (!m) return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); showHint(m); }
    if (ev.key === "Escape") { m.setAttribute("aria-pressed", "false"); if (hintEl) hintEl.hidden = true; }
  });

  // Факт-замок (числа, имена, ссылки, кванторы) живёт в facts.js: тот же код
  // едет в Chrome-расширение. Нет файла, нет и сравнения, аудит работает.
  const factsDiff = (globalThis.humanizerFacts || {}).factsDiff;

  // --- Сравнение «было и стало» ------------------------------------------------
  function openCompare() {
    if (!cmpWrap) return;
    cmpWrap.hidden = false;
    cmpToggle.setAttribute("aria-expanded", "true");
    cmpToggle.textContent = "Скрыть сравнение";
  }
  function closeCompare() {
    if (!cmpWrap) return;
    cmpWrap.hidden = true; cmpOut.hidden = true; cmpOut.innerHTML = "";
    cmpToggle.setAttribute("aria-expanded", "false");
    cmpToggle.textContent = "Сравнить с правкой";
    lastCompareReport = "";
  }
  const list = (items, cls) => items.map((x) => `<code class="${cls}">${esc(x)}</code>`).join(" ");
  function renderCompare(before, rBefore) {
    if (!cmpWrap || cmpWrap.hidden) return;
    const after = afterEl.value;
    lastCompareReport = "";
    if (!after.trim()) { cmpOut.hidden = true; cmpOut.innerHTML = ""; return; }
    if (!globalThis.humanizerIsRussian(after)) { cmpOut.hidden = false; cmpOut.innerHTML = `<p class="audit-lang">${esc(H.NOT_RUSSIAN)}</p>`; return; }
    const rAfter = globalThis.humanizerScan(after, genreEl.value || null);
    const d = rAfter.score - rBefore.score;
    const delta = d > 0 ? `+${d}` : String(d);
    const fd = factsDiff ? factsDiff(before, after) : { lost: [], added: [], claimsAdded: [], kept: 0, total: 0 };
    const aBand = bandOf(rAfter), bBand = bandOf(rBefore);
    const verdict = d > 0 ? "Правка уменьшила штраф по правилам сканера." : d < 0 ? "Правка увеличила штраф по правилам сканера." : "Балл не изменился.";
    const afterLine = factsLine(rAfter), beforeLine = factsLine(rBefore);
    const tally = afterLine === NO_FINDINGS
      ? `В правке следов не осталось. В исходнике было: ${beforeLine}.`
      : `В правке осталось: ${afterLine}. В исходнике было: ${beforeLine}.`;
    const factRows = [];
    if (fd.lost.length) factRows.push(`<li class="fact-lost"><b>Пропало</b> ${list(fd.lost, "lost")}</li>`);
    if (fd.added.length) factRows.push(`<li class="fact-added"><b>Появилось</b> ${list(fd.added, "added")}</li>`);
    if (fd.claimsAdded.length) factRows.push(`<li class="fact-claim"><b>Новый квантор</b> ${list(fd.claimsAdded, "added")}</li>`);
    const factVerdict = (fd.added.length || fd.lost.length || fd.claimsAdded.length
      ? "Состав извлечённых элементов изменился. Проверьте различия. "
      : `Совпало извлечённых элементов: ${fd.kept}. `) +
      "Смысл, единицы вне словаря и связь чисел с утверждениями требуют ручной сверки.";
    cmpOut.hidden = false;
    cmpOut.innerHTML = `
      <div class="cmp-scores">
        <span class="cmp-was ${bBand}">было <b>${rBefore.score}</b></span>
        <span class="cmp-arrow" aria-hidden="true">→</span>
        <span class="cmp-now ${aBand}">стало <b>${rAfter.score}</b></span>
        <span class="cmp-delta ${d > 0 ? "good" : d < 0 ? "bad" : ""}">${delta}</span>
      </div>
      <p class="cmp-verdict">${esc(verdict)} ${esc(tally)}</p>
      <p class="cmp-facts ${fd.added.length || fd.lost.length || fd.claimsAdded.length ? "warn" : "neutral"}">${esc(factVerdict)}</p>
      ${factRows.length ? `<ul class="fact-list">${factRows.join("")}</ul>` : ""}`;
    lastCompareReport = [
      `правка: было ${rBefore.score}, стало ${rAfter.score} (${delta})`,
      fd.lost.length ? `  пропало: ${fd.lost.join(", ")}` : "",
      fd.added.length ? `  появилось: ${fd.added.join(", ")}` : "",
      fd.claimsAdded.length ? `  новый квантор: ${fd.claimsAdded.join(", ")}` : "",
      !fd.added.length && !fd.claimsAdded.length && fd.total ? `  совпало элементов: ${fd.kept}/${fd.total}; смысл не проверен` : "",
    ].filter(Boolean).join("\n");
  }

  // --- Среды ------------------------------------------------------------------
  // Блок установки есть только на главной. На странице-инструменте её нет, и
  // тогда весь этот кусок пропускается: сканер выше от него не зависит.
  const tabsEl = installEl && installEl.querySelector(".env-tabs");
  const TAB_ENVS = ENVS.slice(1); // ENVS[0] набран в разметке как главная команда
  let envKey = TAB_ENVS[0].key;
  function renderEnvs() {
    if (!tabsEl) return;
    tabsEl.innerHTML = TAB_ENVS.map((e) =>
      `<button type="button" role="tab" data-env="${e.key}" aria-selected="${e.key === envKey}">${e.label}</button>`).join("");
    const env = TAB_ENVS.find((e) => e.key === envKey);
    $("env-cmd").textContent = env.cmd;
    $("env-note").textContent = env.note;
  }
  if (tabsEl) tabsEl.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-env]");
    if (!b) return;
    envKey = b.dataset.env;
    renderEnvs();
  });
  const bindCopy = (btnId, srcId) => $(btnId) && $(btnId).addEventListener("click", async () => {
    const btn = $(btnId), label = btn.querySelector("span");
    try {
      await navigator.clipboard.writeText($(srcId).textContent);
      label.textContent = "Скопировано";
    } catch (e) {
      label.textContent = "Выделите и скопируйте";
    }
    setTimeout(() => { label.textContent = "Скопировать"; }, 1800);
  });
  bindCopy("env-copy", "env-cmd");
  bindCopy("env-copy-main", "env-cmd-main");

  // --- Запуск -----------------------------------------------------------------
  function showEmpty(message) {
    // Пусто: на месте результата снова лист редактора, а не пустая рамка.
    resultEl.hidden = true; resultEl.innerHTML = "";
    if (artEl) artEl.hidden = false;
    if (message) { sourceEl.textContent = message; sourceEl.hidden = false; }
    markedWrap.hidden = true; nextEl.hidden = true;
    if (hintEl) hintEl.hidden = true;
    if (cmpOut) { cmpOut.hidden = true; cmpOut.innerHTML = ""; }
    lastCompareReport = "";
  }
  function showNotRussian() {
    showEmpty("");
    if (artEl) artEl.hidden = true;
    resultEl.hidden = false;
    resultEl.innerHTML = `<p class="audit-lang" role="status">${esc(H.NOT_RUSSIAN)}</p>`;
    lastReport = "";
  }
  function run() {
    const text = textEl.value;
    if (!text.trim()) { showEmpty("Без текста проверять нечего: вставьте абзац или возьмите пример."); return; }
    // Не русский текст: балла нет совсем, иначе английский абзац получил бы 100.
    if (!globalThis.humanizerIsRussian(text)) { showNotRussian(); return; }
    const r = globalThis.humanizerScan(text, genreEl.value || null);
    const spans = collectSpans(text, r);
    renderResult(r, spans);
    renderMarked(text, spans, spans.length > 0 || r.penalties.length > 0);
    renderCompare(text, r);
    nextEl.hidden = false;
  }

  let timer = null;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(run, 400); };

  textEl.addEventListener("input", () => { draftIsExample = false; updateCount(); sourceEl.hidden = true; saveDraft(); schedule(); });
  genreEl.addEventListener("change", () => { saveDraft(); run(); });
  runBtn.addEventListener("click", () => { clearTimeout(timer); run(); });
  if (afterEl) afterEl.addEventListener("input", () => { saveDraft(); schedule(); });
  if (cmpToggle) cmpToggle.addEventListener("click", () => {
    if (cmpWrap.hidden) { openCompare(); afterEl.focus(); if (afterEl.value.trim()) run(); }
    else { closeCompare(); saveDraft(); }
  });
  if (clearBtn) clearBtn.addEventListener("click", () => {
    textEl.value = ""; if (afterEl) afterEl.value = "";
    draftIsExample = false; saveDraft(); updateCount();
    closeCompare();
    document.querySelectorAll("[data-example]").forEach((x) => x.setAttribute("aria-pressed", "false"));
    showEmpty(""); sourceEl.hidden = true;
    textEl.focus();
  });
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => {
    const ex = EXAMPLES[b.dataset.example];
    textEl.value = ex.text;
    genreEl.value = ex.genre || "";
    draftIsExample = true; saveDraft();
    sourceEl.textContent = ex.source; sourceEl.hidden = false;
    document.querySelectorAll("[data-example]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    updateCount();
    clearTimeout(timer); run();
  }));

  const restored = loadDraft();
  updateCount();
  renderEnvs();
  if (restored) {
    sourceEl.textContent = "Черновик из прошлого раза восстановлен из памяти этого браузера. «Очистить» удалит его.";
    sourceEl.hidden = false;
    run();
  }
})();
