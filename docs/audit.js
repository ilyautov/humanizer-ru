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
  // Что именно выключает выбранный жанр: читатель видит, почему научный текст
  // не тонет в «является», а не гадает, куда делись маркеры.
  function genreNote() {
    const g = genreEl.value;
    if (!g) return "";
    const cats = ((RULES.genre_muted_categories || {})[g] || []).map((c) => c.toLowerCase());
    const bans = ((RULES.genre_muted_bans || {})[g] || []).map((b) => (typeof b === "string" ? b : b.name)).filter(Boolean);
    const parts = [];
    if (cats.length) parts.push(cats.join(", "));
    if (bans.length) parts.push(`${num(bans.length, "запрет", "запрета", "запретов")} вроде ${bans.slice(0, 2).map((b) => `«${b.split(" / ")[0]}»`).join(" и ")}`);
    return parts.length ? `Жанр «${genreLabel()}»: не считаются ${parts.join(" и ")}.` : `Жанр «${genreLabel()}»: часть маркеров не считается.`;
  }

  // --- Подсказки по клику: что делать с находкой -----------------------------
  // Одна фраза на категорию, по каталогу скилла. Те же тексты в расширении.
  const HINTS = {
    "Канцелярит": "Отглагольное существительное. Верните глагол: не «осуществление проверки», а «проверить».",
    "Кальки": "Калька с английского. Уберите связку или замените глаголом по смыслу, двоеточием, точкой.",
    "Раздувание": "Слово-усилитель. Уберите его: если смысл не изменился, это была вода.",
    "Формула-выводы": "Вывод по формуле. Скажите сам вывод, без «таким образом» и «подводя итог».",
    "Чатбот": "Реплика ассистента, а не текст. Удалите целиком.",
    "Параллелизмы": "«Не просто X, а Y». Оставьте Y: про X читатель и так не думал.",
    "Вводные-открытия": "Пустое открытие. Начните с первого предложения по делу.",
    "Модальные хеджи": "Хедж. Решите, так это или нет, и напишите утверждение.",
    "Мотивационные клише": "Клише из мотивационных постов. Замените конкретным действием или результатом.",
    "Контекстуализаторы": "Обстоятельство ни о чём: «в условиях», «в рамках». Уберите или назовите условие точно.",
    "Маркетинговые штампы": "Штамп. Скажите, что именно получит читатель: числом, сроком, примером.",
    "Псевдо-сократические": "Вопрос самому себе и ответ. Оставьте ответ.",
    "Авторитетные трюизмы": "Анонс вывода вместо вывода. Уберите анонс, оставьте тезис.",
    "Псевдо-терапевтические": "Интонация психолога из чата. Уберите, если текст не о чувствах.",
    "Самомаркировка честности": "Честность не объявляют. Уберите «честно говоря» и «без прикрас».",
    "Эмодзи-декор": "Эмодзи как маркер списка или украшение. Уберите.",
    "Технические маркеры": "Артефакт генерации: латиница внутри русского слова или лишний символ. Исправьте.",
    "Неодушевлённый субъект": "Предмет не «подчёркивает» и не «демонстрирует». Кто это делает? Назовите человека.",
    "Триада-отрицание": "«Без X. Без Y. Только Z.» Скажите одним предложением, что есть.",
    "Финальная мораль": "Мораль в финале. Читатель решит сам: закончите фактом или действием.",
    "Артефакты копипасты": "След копирования из чата: служебная разметка или ссылка-цитата. Удалите.",
  };
  const BAN_HINTS = [
    [/тире/i, "Тире через предложение выдаёт генерацию. Замените точкой, запятой или двоеточием."],
    [/^данн/i, "«Данный» замените на «этот» или уберите совсем."],
    [/^явля/i, "«Является» уберите: «X это Y», «X стал Y» или глагол по смыслу."],
    [/не просто/i, "Оставьте вторую часть: про первую читатель и так не думал."],
    [/не только/i, "Перечислите обе вещи через запятую или оставьте одну, главную."],
    [/важно/i, "Если это важно, скажите само утверждение. Анонс важности уберите."],
    [/стоит отметить|следует отметить/i, "Уберите анонс и оставьте то, что хотели отметить."],
    [/современном мире/i, "Пустое открытие. Начните с первого предложения по делу."],
    [/горизонт/i, "Штамп. Скажите, что именно откроется: рынок, число, срок."],
    [/погруз|окунит/i, "Штамп приглашения. Скажите, что читатель увидит или сделает."],
    [/ключев|важную роль/i, "Раздувание значимости. Оставьте то, ПОЧЕМУ это важно, если оно есть в тексте."],
    [/комплексн/i, "Значит всё и ничего. Перечислите, что входит, или уберите."],
    [/потенциал|новый уровень/i, "Мотивационный штамп. Назовите конкретный результат или удалите."],
    [/в связи с этим/i, "Формульная связка. Уберите или покажите связь словами текста."],
    [/уверенностью/i, "Преамбула перед утверждением. Скажите само утверждение."],
    [/таким образом|подводя итог/i, "Вывод по формуле. Уберите вводное и начните вывод с действия."],
  ];
  const GENERIC_BAN = "Оборот, по которому нейросеть узнают с первого абзаца. Уберите или скажите то же конкретно.";
  const GENERIC_MK = "Маркер: по одному не приговор, но их плотность выдаёт генерацию. Замените менее ожидаемым словом.";
  const hintFor = (s) => {
    if (s.cls === "ban") { const h = BAN_HINTS.find(([re]) => re.test(s.name)); return h ? h[1] : GENERIC_BAN; }
    return HINTS[s.cat] || GENERIC_MK;
  };
  const kindLabel = (cls) => (cls === "ban" ? "жёсткий запрет" : "маркер");
  const spanTitle = (s) => (s.cls === "ban" ? s.name : `${s.cat}: ${s.name}`);

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

  const bandOf = (r) => (r.band === "чисто" ? "good" : r.band === "правка" ? "warn" : "bad");
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

  // --- Факт-замок в браузере ---------------------------------------------------
  // Упрощённый порт humanizer_metrics/facts.py без морфологии: числа, ссылки,
  // месяцы, имена с заглавной не в начале предложения, латиница с заглавной,
  // крупные числительные словами и кванторы-утверждения («единственный»,
  // «впервые»). Сравниваются множества: что пропало и что появилось.
  const URL_RE = /https?:\/\/[^\s)>\]»]+|\b[a-z0-9-]+\.(?:ru|com|org|net|io|tech|dev|ai|su|рф)(?:\/[^\s)>\]»]*)?/gi;
  const CODE_RE = /`([^`\n]+)`/g;
  const MONTH_RE = /\b(январ|феврал|март|апрел|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-яё]*\b/gi;
  const TOKEN_RE = /[A-Za-z][A-Za-z\d-]*|[А-Яа-яЁё][А-Яа-яЁё-]*|\d[\d.,:/-]*/g;
  const CLAIM_PHRASE_RE = /\bдо сих пор\b|\bв мире\b|\bв россии\b/gi;
  const HARD_NUMERALS = new Set(["четыре", "пять", "шесть", "семь", "восемь", "девять", "десять", "одиннадцать", "двенадцать", "пятнадцать", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто", "сто", "двести", "триста", "тысяча", "миллион", "миллиард", "десяток", "сотня", "дюжина"]);
  // Кванторы ловятся по основе с любым окончанием: «первые», «единственная»,
  // «крупнейшим». Полные формы наречий и местоимений перечислены целиком.
  const CLAIM_RE = /^(?:перв(?:ый|ая|ое|ые|ым|ой|ых|ыми|ому|ую|ого)|единственн[а-я]+|впервые|сам(?:ый|ая|ое|ые|ым|ой|ых|ыми|ому|ую|ого)|рекордн[а-я]+|крупнейш[а-я]+|старейш[а-я]+|никогда|никто|навсегда|беспрецедентн[а-я]+)$/;
  const stem = (w) => w.toLowerCase().replace(/ё/g, "е").replace(/-+$/, "").slice(0, 5);
  function sentenceStarts(text) {
    const starts = new Set([0]);
    for (const m of text.matchAll(/[.!?…]\s+|^[>\-*]\s+|«|\n/gm)) starts.add(m.index + m[0].length);
    return starts;
  }
  function extractFacts(text) {
    const hard = new Map(), claims = new Map(); // ключ → как показать
    for (const m of text.matchAll(URL_RE)) {
      const url = m[0].replace(/^https?:\/\/(?:www\.)?/, "").replace(/[.,;:]+$/, "").toLowerCase().replace(/\/+$/, "");
      hard.set("ссылка:" + url, url);
    }
    for (const m of text.matchAll(CODE_RE)) hard.set("код:" + m[1].trim(), "`" + m[1].trim() + "`");
    const body = text.replace(CODE_RE, " ").replace(URL_RE, " ");
    for (const m of body.matchAll(MONTH_RE)) hard.set("месяц:" + m[1].toLowerCase(), m[0]);
    for (const m of body.matchAll(CLAIM_PHRASE_RE)) claims.set("утверждение:" + m[0].toLowerCase().replace(/ё/g, "е"), m[0]);
    const starts = sentenceStarts(body);
    for (const m of body.matchAll(TOKEN_RE)) {
      const tok = m[0], at = m.index;
      if (/^\d/.test(tok)) {
        const n = tok.replace(/[.,:/-]+$/, "").replace(/,/g, ".");
        if (n) hard.set("число:" + n, tok.replace(/[.,:/-]+$/, ""));
        continue;
      }
      const low = tok.toLowerCase().replace(/ё/g, "е");
      if (HARD_NUMERALS.has(low)) { hard.set("число:" + low, tok); continue; }
      if (CLAIM_RE.test(low)) { claims.set("утверждение:" + stem(low), tok); continue; }
      if (!/^[A-ZА-ЯЁ]/.test(tok)) continue;
      if (/^[A-Za-z]/.test(tok)) { hard.set("имя:" + low, tok); continue; }
      if (!starts.has(at)) hard.set("имя:" + stem(low), tok);
    }
    return { hard, claims };
  }
  function factsDiff(before, after) {
    const a = extractFacts(before), b = extractFacts(after);
    const lost = [...a.hard].filter(([k]) => !b.hard.has(k)).map(([, v]) => v);
    const added = [...b.hard].filter(([k]) => !a.hard.has(k)).map(([, v]) => v);
    const claimsAdded = [...b.claims].filter(([k]) => !a.claims.has(k)).map(([, v]) => v);
    const kept = [...a.hard].filter(([k]) => b.hard.has(k)).length;
    return { lost, added, claimsAdded, kept, total: a.hard.size };
  }

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
    const rAfter = globalThis.humanizerScan(after, genreEl.value || null);
    const d = rAfter.score - rBefore.score;
    const delta = d > 0 ? `+${d}` : String(d);
    const fd = factsDiff(before, after);
    const aBand = bandOf(rAfter), bBand = bandOf(rBefore);
    const verdict = d > 0 ? "Правка сняла следы ИИ." : d < 0 ? "Правка добавила следов ИИ." : "Балл не изменился.";
    const afterLine = factsLine(rAfter), beforeLine = factsLine(rBefore);
    const tally = afterLine === NO_FINDINGS
      ? `В правке следов не осталось. В исходнике было: ${beforeLine}.`
      : `В правке осталось: ${afterLine}. В исходнике было: ${beforeLine}.`;
    const factRows = [];
    if (fd.lost.length) factRows.push(`<li class="fact-lost"><b>Пропало</b> ${list(fd.lost, "lost")}</li>`);
    if (fd.added.length) factRows.push(`<li class="fact-added"><b>Появилось</b> ${list(fd.added, "added")}</li>`);
    if (fd.claimsAdded.length) factRows.push(`<li class="fact-claim"><b>Новый квантор</b> ${list(fd.claimsAdded, "added")}</li>`);
    const factVerdict = !fd.added.length && !fd.claimsAdded.length
      ? (fd.total ? `Факт-замок: ${fd.kept} из ${num(fd.total, "факта исходника", "фактов исходника", "фактов исходника")} на месте, новых нет.` : "Факт-замок: чисел, имён и ссылок в исходнике нет, сравнивать нечего.")
      : "Факт-замок: в правке есть то, чего не было в исходнике. Выдуманная цифра хуже канцелярита: проверьте глазами.";
    cmpOut.hidden = false;
    cmpOut.innerHTML = `
      <div class="cmp-scores">
        <span class="cmp-was ${bBand}">было <b>${rBefore.score}</b></span>
        <span class="cmp-arrow" aria-hidden="true">→</span>
        <span class="cmp-now ${aBand}">стало <b>${rAfter.score}</b></span>
        <span class="cmp-delta ${d > 0 ? "good" : d < 0 ? "bad" : ""}">${delta}</span>
      </div>
      <p class="cmp-verdict">${esc(verdict)} ${esc(tally)}</p>
      <p class="cmp-facts ${fd.added.length || fd.claimsAdded.length ? "warn" : "good"}">${esc(factVerdict)}</p>
      ${factRows.length ? `<ul class="fact-list">${factRows.join("")}</ul>` : ""}`;
    lastCompareReport = [
      `правка: было ${rBefore.score}, стало ${rAfter.score} (${delta})`,
      fd.lost.length ? `  пропало: ${fd.lost.join(", ")}` : "",
      fd.added.length ? `  появилось: ${fd.added.join(", ")}` : "",
      fd.claimsAdded.length ? `  новый квантор: ${fd.claimsAdded.join(", ")}` : "",
      !fd.added.length && !fd.claimsAdded.length && fd.total ? `  факт-замок: ${fd.kept}/${fd.total} на месте` : "",
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
  function run() {
    const text = textEl.value;
    if (!text.trim()) { showEmpty("Без текста проверять нечего: вставьте абзац или возьмите пример."); return; }
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
    textEl.value = document.getElementById(ex.id).textContent.trim();
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
