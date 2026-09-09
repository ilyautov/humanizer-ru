// humanizer-ru popup: только DOM. Движок в vendor/scan.js, правила в
// vendor/scan-rules.js (копии из docs/, их кладёт scripts/build_extension.py).
// Работает и вне контекста расширения (открыт как файл): chrome.* обёрнуты.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const textEl = $("text"), genreEl = $("genre"), countEl = $("count"), staleEl = $("stale"), clearBtn = $("clear");
  const emptyEl = $("empty"), resultEl = $("result"), markedWrap = $("marked-wrap"), markedEl = $("marked"), hintEl = $("hint");
  const statusEl = $("status"), siteLink = $("site-link"), copyBtn = $("copy");
  const SITE = "https://humanizer-ru.aifrontier.tech/";
  if (typeof globalThis.humanizerScan !== "function") {
    emptyEl.innerHTML = `<p>Сканер не загрузился: нет vendor/scan.js. Соберите расширение скриптом scripts/build_extension.py.</p>`;
    return;
  }
  const RULES = globalThis.HUMANIZER_RULES || {};
  const CLEAN = (RULES.score && RULES.score.band_clean) || 85;

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
  const num = (n, one, few, many) => `${n} ${plural(n, one, few, many)}`;
  const wordsOf = (t) => t.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  const updateCount = () => { countEl.textContent = num(wordsOf(textEl.value), "слово", "слова", "слов"); };
  const genreLabel = () => genreEl.options[genreEl.selectedIndex].textContent;

  // Пример с сайта (нейрочерновик, 11/100 там же). Данные, не текст интерфейса.
  const EXAMPLE = "В современном мире успешный бизнес — это не просто продукт, а целая экосистема ценностей. Наша компания является надёжным партнёром, который играет ключевую роль в развитии вашего дела. Мы предлагаем комплексный подход, способный вывести ваш бренд на новый уровень и раскрыть его потенциал по-настоящему. Стоит отметить, что в условиях растущей конкуренции важно понимать: связь с аудиторией и доверительные отношения становятся главным активом. Именно поэтому мы выстраиваем индивидуальный подход к каждому клиенту. Наше инновационное решение открывает новые горизонты для роста — от привлечения первых пользователей до масштабирования на международные рынки. Таким образом, выбирая нас, вы выбираете не только сервис, но и команду, которая разделяет ваши амбиции. Можно с уверенностью сказать: вместе мы расширим границы возможного и достигнем результата, который превзойдёт ожидания.";

  // --- Язык результата: строки сканера в слова читателя ----------------------
  // Сырой reason остаётся в title строки, чтобы разработчик видел числа.
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

  // Что делать с находкой: одна фраза на категорию, по каталогу скилла.
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
  ];
  const GENERIC_BAN = "Оборот, по которому нейросеть узнают с первого абзаца. Уберите или скажите то же конкретно.";
  const GENERIC_MK = "Маркер: по одному не приговор, но их плотность выдаёт генерацию. Замените менее ожидаемым словом.";
  const hintFor = (kind, cat, name) => {
    if (kind === "ban") { const h = BAN_HINTS.find(([re]) => re.test(name)); return h ? h[1] : GENERIC_BAN; }
    return HINTS[cat] || GENERIC_MK;
  };

  // --- Находки в тексте --------------------------------------------------------
  // Конец подсветки тянем до границы слова только для показа: «ключев|ым» режет
  // слово и выглядит ошибкой. Счёт при этом не меняется.
  const wordEnd = (text, b) => { while (b < text.length && /[\p{L}\p{M}]/u.test(text[b])) b++; return b; };
  function collectSpans(text, r) {
    const spans = [];
    for (const h of r.effective_bans) for (const [a, b] of h.positions) spans.push({ a, b: wordEnd(text, b), kind: "ban", cat: "", name: h.name });
    for (const h of r.muted_markers) for (const [a, b] of h.positions) spans.push({ a, b: wordEnd(text, b), kind: "mk", cat: h.category, name: h.name });
    spans.sort((x, y) => x.a - y.a || (x.kind === "ban" ? -1 : 1));
    const out = []; let pos = 0;
    for (const s of spans) { if (s.a < pos) continue; out.push(s); pos = s.b; }
    return out;
  }
  const kindLabel = (kind) => (kind === "ban" ? "жёсткий запрет" : "маркер");
  const spanTitle = (s) => (s.kind === "ban" ? s.name : `${s.cat}: ${s.name}`);

  function renderMarked(text, spans, showText) {
    hintEl.hidden = true;
    if (!showText) { markedWrap.hidden = true; markedEl.innerHTML = ""; return; }
    let out = "", pos = 0;
    spans.forEach((s, i) => {
      out += esc(text.slice(pos, s.a));
      out += `<mark class="${s.kind}" tabindex="0" role="button" aria-pressed="false" data-i="${i}" aria-label="${esc(kindLabel(s.kind))}: ${esc(spanTitle(s))}">${esc(text.slice(s.a, s.b))}</mark>`;
      pos = s.b;
    });
    out += esc(text.slice(pos));
    markedEl.innerHTML = out;
    markedWrap.hidden = false;
  }

  let lastSpans = [];
  function showHint(mark) {
    const s = lastSpans[+mark.dataset.i];
    if (!s) return;
    const pressed = mark.getAttribute("aria-pressed") === "true";
    markedEl.querySelectorAll('mark[aria-pressed="true"]').forEach((m) => m.setAttribute("aria-pressed", "false"));
    if (pressed) { hintEl.hidden = true; return; }
    mark.setAttribute("aria-pressed", "true");
    hintEl.innerHTML = `<b class="${s.kind}">${esc(kindLabel(s.kind))}, ${esc(spanTitle(s))}.</b> ${esc(hintFor(s.kind, s.cat, s.name))}`;
    hintEl.hidden = false;
  }
  markedEl.addEventListener("click", (ev) => { const m = ev.target.closest("mark"); if (m) showHint(m); });
  markedEl.addEventListener("keydown", (ev) => {
    const m = ev.target.closest("mark");
    if (!m) return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); showHint(m); }
    if (ev.key === "Escape") { m.setAttribute("aria-pressed", "false"); hintEl.hidden = true; }
  });

  // --- Следующий шаг после балла -----------------------------------------------
  function nextLine(band, spans, r) {
    if (!spans.length) {
      if (!r.penalties.length) {
        return r.words < 100
          ? `Чисто. На ${num(r.words, "слове", "словах", "словах")} это ещё мало что значит: проверьте текст целиком.`
          : "Чисто: следы ИИ не мешают.";
      }
      const reasons = r.penalties.map((p) => p.reason).join(" ");
      if (/ровный ритм/.test(reasons)) return "Обороты не найдены. Предложения почти одной длины: разбейте длинное или склейте два коротких.";
      if (/ровные абзацы/.test(reasons)) return "Обороты не найдены. Абзацы одной длины: пусть один будет вдвое короче соседнего.";
      if (/листикл/.test(reasons)) return "Обороты не найдены. Слишком много списка: часть пунктов перескажите абзацем.";
      return "Обороты не найдены, штраф только за структуру: список ниже.";
    }
    if (band === "bad") return "Начните с красного: уберите оборот или скажите то же конкретно. Потом жёлтое.";
    if (band === "warn") return "Точечная правка: пройдитесь по подчёркнутому, структуру не трогайте.";
    return "Следы ИИ не мешают. Подчёркнутое можно поправить, но это уже вкус.";
  }

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

  // --- Рендер результата ---------------------------------------------------------
  let lastReport = "";
  function renderResult(text, r) {
    const band = r.band === "чисто" ? "good" : r.band === "правка" ? "warn" : "bad";
    const bandText = { good: "чисто: следы ИИ не мешают", warn: "точечная правка", bad: "нужен рерайт" }[band];
    // Тире сканер штрафует отдельно от фраз, поэтому и считаем отдельно:
    // иначе «13 запретов» наверху спорит с «-45 за 11 оборотов» ниже.
    const dashName = (RULES.score && RULES.score.em_dash_name) || "Длинное тире";
    const bans = r.effective_bans.filter((h) => h.name !== dashName).reduce((n, h) => n + h.count, 0);
    const dashes = r.effective_bans.filter((h) => h.name === dashName).reduce((n, h) => n + h.count, 0);
    const marks = r.muted_markers.reduce((n, h) => n + h.count, 0);
    const spans = collectSpans(text, r);
    lastSpans = spans;

    emptyEl.hidden = true;
    resultEl.hidden = false;
    resultEl.className = band;
    $("score").textContent = r.score;
    $("band").textContent = bandText;
    const factParts = [];
    if (bans) factParts.push(num(bans, "запрещённый оборот", "запрещённых оборота", "запрещённых оборотов"));
    if (dashes) factParts.push(`длинное тире ${dashes > 1 ? `×${dashes}` : ""}`.trim());
    if (marks) factParts.push(num(marks, "маркер", "маркера", "маркеров"));
    $("facts").textContent = factParts.length ? factParts.join(", ") : "оборотов не найдено";
    $("bar").setAttribute("aria-label", `Чистота ${r.score} из 100`);
    // setTimeout, а не requestAnimationFrame: в неактивной вкладке rAF не тикает,
    // и полоса застывала на нуле. Элемент один и тот же, поэтому полоса едет
    // от прошлого значения, а не от нуля при каждом нажатии клавиши.
    setTimeout(() => { $("fill").style.transform = `scaleX(${r.score / 100})`; }, 30);
    $("next").textContent = nextLine(band, spans, r);
    const gn = genreNote();
    $("genre-note").textContent = gn; $("genre-note").hidden = !gn;
    $("penalties").innerHTML = r.penalties.map((p) => `<li title="${esc(p.reason)}"><b>${p.points}</b><span>${esc(humanReason(p.reason))}</span></li>`).join("");
    $("notes").textContent = r.notes.join(" "); $("notes").hidden = !r.notes.length;
    statusEl.textContent = `Чистота ${r.score} из 100, ${bandText}`;
    if (r.score < CLEAN) { siteLink.textContent = "Как исправить: скилл для агентов"; siteLink.href = SITE + "#install"; }
    else { siteLink.textContent = "Сайт и скилл для агентов"; siteLink.href = SITE; }

    renderMarked(text, spans, spans.length > 0 || r.penalties.length > 0);

    const found = new Map();
    for (const s of spans) { const k = `${kindLabel(s.kind)} · ${spanTitle(s)}`; found.set(k, (found.get(k) || 0) + 1); }
    lastReport = [
      `humanizer-ru: ${r.score}/100, ${bandText}`,
      `жанр: ${genreLabel()} · ${num(r.words, "слово", "слова", "слов")} · ${$("facts").textContent}`,
      r.penalties.length ? "штрафы:\n" + r.penalties.map((p) => `  ${String(p.points).padStart(4)}  ${humanReason(p.reason)}`).join("\n") : "штрафов нет",
      found.size ? "найдено:\n" + [...found].map(([k, n]) => `  ${k}${n > 1 ? ` ×${n}` : ""}`).join("\n") : "",
      SITE,
    ].filter(Boolean).join("\n");
  }

  copyBtn.addEventListener("click", async () => {
    const label = copyBtn.textContent;
    try { await navigator.clipboard.writeText(lastReport); copyBtn.textContent = "Скопировано"; }
    catch (e) { copyBtn.textContent = "Не удалось скопировать"; }
    setTimeout(() => { copyBtn.textContent = label; }, 1800);
  });

  function showEmpty() {
    emptyEl.hidden = false; resultEl.hidden = true; markedWrap.hidden = true; hintEl.hidden = true;
    resultEl.className = ""; $("fill").style.transform = "scaleX(0)";
    statusEl.textContent = "";
    siteLink.textContent = "Сайт и скилл для агентов"; siteLink.href = SITE;
    lastReport = ""; lastSpans = [];
  }

  function run() {
    const text = textEl.value;
    clearBtn.hidden = !text;
    if (!text.trim()) { showEmpty(); return; }
    renderResult(text, globalThis.humanizerScan(text, genreEl.value || null));
    store.set("local", "last", { text });
  }

  let timer = null;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(run, 300); };
  textEl.addEventListener("input", () => { staleEl.hidden = true; updateCount(); schedule(); });
  genreEl.addEventListener("change", () => { store.set("local", "genre", genreEl.value); run(); });
  $("example").addEventListener("click", () => {
    textEl.value = EXAMPLE; staleEl.hidden = true; updateCount(); run();
    textEl.focus(); textEl.setSelectionRange(0, 0); textEl.scrollTop = 0;
  });
  clearBtn.addEventListener("click", () => { textEl.value = ""; staleEl.hidden = true; updateCount(); store.remove("local", "last"); run(); textEl.focus(); });

  // --- Старт: выделение из контекстного меню, иначе прошлый текст -------------
  (async () => {
    if (new URLSearchParams(location.search).get("tab")) document.body.classList.add("as-tab");
    try {
      const v = hasChrome && chrome.runtime && chrome.runtime.getManifest ? chrome.runtime.getManifest().version : "";
      if (v) $("version").textContent = `v${v}`;
    } catch (e) { /* вне расширения */ }
    // Жанр это настройка, а не свойство текста: живёт отдельно и переживает
    // выделение из контекстного меню.
    const genre = await store.get("local", "genre");
    if (genre && [...genreEl.options].some((o) => o.value === genre)) genreEl.value = genre;
    const pending = await store.get("session", "pending");
    if (pending && pending.text && Date.now() - (pending.at || 0) < 60_000) {
      textEl.value = pending.text;
      await store.remove("session", "pending");
    } else {
      const last = await store.get("local", "last");
      if (last && last.text) { textEl.value = last.text; staleEl.hidden = false; }
    }
    textEl.scrollTop = 0;
    updateCount();
    run();
  })();
})();
