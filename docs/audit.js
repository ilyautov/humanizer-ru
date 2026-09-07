// humanizer-ru: интерфейс онлайн-аудита на главной. Движок в scan.js,
// правила в scan-rules.js (экспорт из Python). Здесь только DOM.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const textEl = $("audit-text"), genreEl = $("audit-genre"), runBtn = $("audit-run");
  const countEl = $("audit-count"), resultEl = $("audit-result"), sourceEl = $("audit-source");
  const markedWrap = $("audit-marked"), markedEl = $("audit-text-marked"), nextEl = $("audit-next"), installEl = $("install");
  if (!textEl || typeof globalThis.humanizerScan !== "function") return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const EXAMPLES = {
    ai: { id: "ex-ai", source: "Пример: маркетинговый текст, сгенерированный GPT для eval-корпуса репозитория." },
    human: { id: "ex-human", source: "Пример: вводная часть статьи «Байкал» русской Википедии, CC BY-SA 4.0." },
    tech: { id: "ex-tech", source: "Пример: авторский пост с листингом и цитатой из ревью. Код и цитата в счёт не идут." },
  };

  const ENVS = [
    { key: "claude-code", label: "Claude Code", cmd: "/plugin marketplace add ilyautov/humanizer-ru\n/plugin install humanizer-ru@ilyautov-plugins",
      note: "Две команды внутри Claude Code. Дальше скилл включается сам на «очеловечь», «убери канцелярит», «перепиши как человек»." },
    { key: "skills", label: "Cursor и другие", cmd: "npx skills add https://github.com/ilyautov/humanizer-ru/tree/main/skills/humanizer-ru",
      note: "Универсальная установка через skills.sh: Cursor, Copilot, Cline, OpenCode, Goose и ещё десятки агентов, читающих SKILL.md." },
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

  function updateCount() {
    const n = wordsOf(textEl.value);
    countEl.textContent = `${n} ${plural(n, "слово", "слова", "слов")}`;
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

  function renderResult(r) {
    const band = r.band === "чисто" ? "good" : r.band === "правка" ? "warn" : "bad";
    const bandText = { good: "чисто: следы ИИ не мешают", warn: "точечная правка", bad: "нужен рерайт" }[band];
    const rows = r.penalties.map((p) => `<li><b>${p.points}</b><span>${esc(p.reason)}</span></li>`).join("");
    const notes = r.notes.map((n) => `<p class="audit-sterile">${esc(n)}</p>`).join("");
    const bans = r.effective_bans.reduce((n, h) => n + h.count, 0);
    const marks = r.muted_markers.reduce((n, h) => n + h.count, 0);
    resultEl.innerHTML = `
      <div class="score-row ${band}">
        <div class="score-num"><span id="score-value">0</span><small>/100</small></div>
        <div class="score-meta">
          <div class="score-band">${bandText}</div>
          <div class="score-facts">${bans} ${plural(bans, "жёсткий запрет", "жёстких запрета", "жёстких запретов")}, ${marks} ${plural(marks, "маркер", "маркера", "маркеров")}, ${r.words} ${plural(r.words, "слово", "слова", "слов")}</div>
        </div>
      </div>
      <div class="score-bar" role="img" aria-label="Чистота ${r.score} из 100"><span class="score-fill"></span><i class="tick t60"></i><i class="tick t85"></i></div>
      ${rows ? `<ul class="penalties">${rows}</ul>` : `<p class="audit-none">Штрафов нет.</p>`}
      ${notes}`;
    animateNumber($("score-value"), r.score);
    requestAnimationFrame(() => { const f = resultEl.querySelector(".score-fill"); if (f) f.style.transform = `scaleX(${r.score / 100})`; });
  }

  function renderMarked(text, r) {
    const spans = [];
    for (const h of r.effective_bans) for (const [a, b] of h.positions) spans.push({ a, b, cls: "ban", name: h.name });
    for (const h of r.muted_markers) for (const [a, b] of h.positions) spans.push({ a, b, cls: "mk", name: `${h.category}: ${h.name}` });
    spans.sort((x, y) => x.a - y.a || (x.cls === "ban" ? -1 : 1));
    let out = "", pos = 0;
    for (const s of spans) {
      if (s.a < pos) continue; // перекрытие: первый победил
      out += esc(text.slice(pos, s.a));
      out += `<mark class="${s.cls}" title="${esc(s.name)}">${esc(text.slice(s.a, s.b))}</mark>`;
      pos = s.b;
    }
    out += esc(text.slice(pos));
    markedEl.innerHTML = out;
    markedWrap.hidden = spans.length === 0;
  }

  // --- Среды ------------------------------------------------------------------
  let envKey = ENVS[0].key;
  function renderEnvs() {
    const tabs = installEl.querySelector(".env-tabs");
    tabs.innerHTML = ENVS.map((e) =>
      `<button type="button" role="tab" data-env="${e.key}" aria-selected="${e.key === envKey}">${e.label}</button>`).join("");
    const env = ENVS.find((e) => e.key === envKey);
    $("env-cmd").textContent = env.cmd;
    $("env-note").textContent = env.note;
  }
  installEl.querySelector(".env-tabs").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-env]");
    if (!b) return;
    envKey = b.dataset.env;
    renderEnvs();
  });
  $("env-copy").addEventListener("click", async () => {
    const btn = $("env-copy"), label = btn.querySelector("span");
    try {
      await navigator.clipboard.writeText($("env-cmd").textContent);
      label.textContent = "Скопировано";
    } catch (e) {
      label.textContent = "Выделите и скопируйте";
    }
    setTimeout(() => { label.textContent = "Скопировать"; }, 1800);
  });

  // --- Запуск -----------------------------------------------------------------
  function run() {
    const text = textEl.value;
    if (!text.trim()) {
      resultEl.innerHTML = `<div class="audit-empty"><p>Вставьте текст или возьмите пример: без текста проверять нечего.</p></div>`;
      markedWrap.hidden = true; nextEl.hidden = true;
      return;
    }
    const r = globalThis.humanizerScan(text, genreEl.value || null);
    renderResult(r);
    renderMarked(text, r);
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
    sourceEl.textContent = ex.source; sourceEl.hidden = false;
    document.querySelectorAll("[data-example]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    updateCount();
    clearTimeout(timer); run();
  }));

  updateCount();
  renderEnvs();
})();
