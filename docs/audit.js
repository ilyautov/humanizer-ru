// humanizer-ru: интерфейс онлайн-аудита на главной. Движок в scan.js,
// правила в scan-rules.js (экспорт из Python). Здесь только DOM.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const textEl = $("audit-text"), genreEl = $("audit-genre"), runBtn = $("audit-run");
  const countEl = $("audit-count"), resultEl = $("audit-result"), sourceEl = $("audit-source");
  const markedWrap = $("audit-marked"), markedEl = $("audit-text-marked"), nextEl = $("audit-next"), installEl = $("install");
  const artEl = $("hero-art");
  if (!textEl || typeof globalThis.humanizerScan !== "function") return;
  const RULES = globalThis.HUMANIZER_RULES || {};

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // У каждого примера свой жанр: справочный текст проверяется как новости,
  // иначе энциклопедия получает штраф за тире, которое у людей норма.
  const EXAMPLES = {
    ai: { id: "ex-ai", genre: "", source: "Пример: маркетинговый текст, сгенерированный GPT для eval-корпуса репозитория." },
    human: { id: "ex-human", genre: "news", source: "Пример: вводная часть статьи «Байкал» русской Википедии, CC BY-SA 4.0. Жанр «новости, энциклопедия»: тире и «является» в справочном тексте не считаются." },
    tech: { id: "ex-tech", genre: "", source: "Пример: авторский пост с листингом и цитатой из ревью. Код и цитата в счёт не идут." },
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
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  };
  const wordsOf = (t) => t.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;

  const num = (n, one, few, many) => `${n} ${plural(n, one, few, many)}`;
  function updateCount() {
    countEl.textContent = num(wordsOf(textEl.value), "слово", "слова", "слов");
  }

  // Строки сканера в слова читателя; сырая строка остаётся в title.
  const HUMAN_REASONS = [
    [/^хард-баны \(фразы\): (\d+)/, (m) => num(+m[1], "запрещённый оборот", "запрещённых оборота", "запрещённых оборотов")],
    [/^артефакты копипасты: (\d+)/, (m) => `${num(+m[1], "след", "следа", "следов")} копирования из чата`],
    [/^маркеры: (\d+) \(([\d.]+)\/100 слов\)/, (m) => `${num(+m[1], "маркер", "маркера", "маркеров")}, ${m[2].replace(".", ",")} на 100 слов`],
    [/^тире: (\d+) \(([\d.]+)\/100 слов\)/, (m) => `длинное тире ${num(+m[1], "раз", "раза", "раз")}, ${m[2].replace(".", ",")} на 100 слов`],
    [/^ровный ритм/, () => "предложения одной длины"],
    [/^ровные абзацы/, () => "абзацы одной длины"],
    [/^листикл \((\d+) пунктов, (\d+)% строк\)/, (m) => `список вместо текста: ${num(+m[1], "пункт", "пункта", "пунктов")}, ${m[2]}% строк`],
  ];
  const humanReason = (reason) => {
    for (const [re, fn] of HUMAN_REASONS) { const m = reason.match(re); if (m) return fn(m); }
    return reason;
  };
  function nextLine(band, hasSpans, r) {
    if (!hasSpans) {
      if (!r.penalties.length) return r.words < 100 ? `Чисто. На ${num(r.words, "слове", "словах", "словах")} это ещё мало что значит: проверьте текст целиком.` : "Чисто: следы ИИ не мешают.";
      const reasons = r.penalties.map((p) => p.reason).join(" ");
      if (/ровный ритм/.test(reasons)) return "Обороты не найдены. Предложения почти одной длины: разбейте длинное или склейте два коротких.";
      if (/ровные абзацы/.test(reasons)) return "Обороты не найдены. Абзацы одной длины: пусть один будет вдвое короче соседнего.";
      if (/листикл/.test(reasons)) return "Обороты не найдены. Слишком много списка: часть пунктов перескажите абзацем.";
      return "Обороты не найдены, штраф только за структуру.";
    }
    if (band === "bad") return "Начните с красного: уберите оборот или скажите то же конкретно. Потом жёлтое.";
    if (band === "warn") return "Точечная правка: пройдитесь по подчёркнутому, структуру не трогайте.";
    return "Следы ИИ не мешают. Подчёркнутое можно поправить, но это уже вкус.";
  }

  // --- Результат -------------------------------------------------------------
  function animateNumber(el, target) {
    if (reduceMotion || document.hidden) { el.textContent = target; return; }
    const t0 = performance.now(), dur = 650;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(target * eased);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  let lastReport = "";
  function renderResult(r, spans) {
    const band = r.band === "чисто" ? "good" : r.band === "правка" ? "warn" : "bad";
    const bandText = { good: "чисто: следы ИИ не мешают", warn: "точечная правка", bad: "нужен рерайт" }[band];
    const rows = r.penalties.map((p) => `<li title="${esc(p.reason)}"><b>${p.points}</b><span>${esc(humanReason(p.reason))}</span></li>`).join("");
    const notes = r.notes.map((n) => `<p class="audit-sterile">${esc(n)}</p>`).join("");
    // Тире сканер штрафует отдельно от фраз, поэтому и считаем отдельно.
    const dashName = (RULES.score && RULES.score.em_dash_name) || "Длинное тире";
    const bans = r.effective_bans.filter((h) => h.name !== dashName).reduce((n, h) => n + h.count, 0);
    const dashes = r.effective_bans.filter((h) => h.name === dashName).reduce((n, h) => n + h.count, 0);
    const marks = r.muted_markers.reduce((n, h) => n + h.count, 0);
    const factParts = [];
    if (bans) factParts.push(num(bans, "запрещённый оборот", "запрещённых оборота", "запрещённых оборотов"));
    if (dashes) factParts.push(`длинное тире ${dashes > 1 ? `×${dashes}` : ""}`.trim());
    if (marks) factParts.push(num(marks, "маркер", "маркера", "маркеров"));
    const facts = factParts.length ? factParts.join(", ") : "оборотов не найдено";
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
      ${notes}
      <div class="audit-actions"><button type="button" id="audit-copy">Скопировать отчёт</button></div>`;
    animateNumber($("score-value"), r.score);
    requestAnimationFrame(() => { const f = resultEl.querySelector(".score-fill"); if (f) f.style.transform = `scaleX(${r.score / 100})`; });

    const found = new Map();
    for (const s of spans) { const k = `${s.cls === "ban" ? "жёсткий запрет" : "маркер"} · ${s.name}`; found.set(k, (found.get(k) || 0) + 1); }
    const genreLabel = genreEl.options[genreEl.selectedIndex].textContent;
    lastReport = [
      `humanizer-ru: ${r.score}/100, ${bandText}`,
      `жанр: ${genreLabel} · ${num(r.words, "слово", "слова", "слов")} · ${facts}`,
      r.penalties.length ? "штрафы:\n" + r.penalties.map((p) => `  ${String(p.points).padStart(4)}  ${humanReason(p.reason)}`).join("\n") : "штрафов нет",
      found.size ? "найдено:\n" + [...found].map(([k, n]) => `  ${k}${n > 1 ? ` ×${n}` : ""}`).join("\n") : "",
      "https://humanizer-ru.aifrontier.tech/",
    ].filter(Boolean).join("\n");
    $("audit-copy").addEventListener("click", async () => {
      const btn = $("audit-copy");
      try { await navigator.clipboard.writeText(lastReport); btn.textContent = "Скопировано"; }
      catch (e) { btn.textContent = "Выделите и скопируйте"; }
      setTimeout(() => { btn.textContent = "Скопировать отчёт"; }, 1800);
    });
  }

  // Конец подсветки тянем до границы слова только для показа: «ключев|ым»
  // режет слово и выглядит ошибкой. Счёт при этом не меняется.
  const wordEnd = (text, b) => { while (b < text.length && /[\p{L}\p{M}]/u.test(text[b])) b++; return b; };
  function collectSpans(text, r) {
    const spans = [];
    for (const h of r.effective_bans) for (const [a, b] of h.positions) spans.push({ a, b: wordEnd(text, b), cls: "ban", name: h.name });
    for (const h of r.muted_markers) for (const [a, b] of h.positions) spans.push({ a, b: wordEnd(text, b), cls: "mk", name: `${h.category}: ${h.name}` });
    spans.sort((x, y) => x.a - y.a || (x.cls === "ban" ? -1 : 1));
    const out = []; let pos = 0;
    for (const s of spans) { if (s.a < pos) continue; out.push(s); pos = s.b; } // перекрытие: первый победил
    return out;
  }

  function renderMarked(text, spans, showText) {
    if (!showText) { markedWrap.hidden = true; markedEl.innerHTML = ""; return; }
    let out = "", pos = 0;
    for (const s of spans) {
      out += esc(text.slice(pos, s.a));
      out += `<mark class="${s.cls}" title="${esc(s.name)}">${esc(text.slice(s.a, s.b))}</mark>`;
      pos = s.b;
    }
    out += esc(text.slice(pos));
    markedEl.innerHTML = out;
    markedWrap.hidden = false;
  }

  // --- Среды ------------------------------------------------------------------
  const TAB_ENVS = ENVS.slice(1); // ENVS[0] набран в разметке как главная команда
  let envKey = TAB_ENVS[0].key;
  function renderEnvs() {
    const tabs = installEl.querySelector(".env-tabs");
    tabs.innerHTML = TAB_ENVS.map((e) =>
      `<button type="button" role="tab" data-env="${e.key}" aria-selected="${e.key === envKey}">${e.label}</button>`).join("");
    const env = TAB_ENVS.find((e) => e.key === envKey);
    $("env-cmd").textContent = env.cmd;
    $("env-note").textContent = env.note;
  }
  installEl.querySelector(".env-tabs").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-env]");
    if (!b) return;
    envKey = b.dataset.env;
    renderEnvs();
  });
  const bindCopy = (btnId, srcId) => $(btnId).addEventListener("click", async () => {
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
  function run() {
    const text = textEl.value;
    if (!text.trim()) {
      // Пусто: на месте результата снова лист редактора, а не пустая рамка.
      resultEl.hidden = true; resultEl.innerHTML = "";
      if (artEl) artEl.hidden = false;
      sourceEl.textContent = "Без текста проверять нечего: вставьте абзац или возьмите пример."; sourceEl.hidden = false;
      markedWrap.hidden = true; nextEl.hidden = true;
      return;
    }
    const r = globalThis.humanizerScan(text, genreEl.value || null);
    const spans = collectSpans(text, r);
    renderResult(r, spans);
    renderMarked(text, spans, spans.length > 0 || r.penalties.length > 0);
    nextEl.hidden = false;
  }

  let timer = null;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(run, 400); };

  textEl.addEventListener("input", () => { updateCount(); sourceEl.hidden = true; schedule(); });
  genreEl.addEventListener("change", run);
  runBtn.addEventListener("click", () => { clearTimeout(timer); run(); });
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => {
    const ex = EXAMPLES[b.dataset.example];
    textEl.value = document.getElementById(ex.id).textContent.trim();
    genreEl.value = ex.genre || "";
    sourceEl.textContent = ex.source; sourceEl.hidden = false;
    document.querySelectorAll("[data-example]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    updateCount();
    clearTimeout(timer); run();
  }));

  updateCount();
  renderEnvs();
})();
