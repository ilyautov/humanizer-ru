// humanizer-ru: попап и вкладка. Только DOM: движок в
// vendor/scan.js, правила в vendor/scan-rules.js, факт-замок в vendor/facts.js
// (копии из docs/, их кладёт scripts/build_extension.py). Режим задаёт класс на
// body: as-tab (?tab=1, широкий режим для длинного текста), без класса попап.
// Работает и вне контекста расширения (открыт как файл): chrome.* обёрнуты.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const params = new URLSearchParams(location.search);
  if (params.get("tab")) body.classList.add("as-tab");
  const isPopup = !body.classList.contains("as-tab");

  const textEl = $("text"), genreEl = $("genre"), countEl = $("count"), clearBtn = $("clear");
  const editEl = $("edit"), emptyEl = $("empty"), resultEl = $("result"), runBtn = $("run");
  const markedEl = $("marked"), hintEl = $("hint"), statusEl = $("status"), siteLink = $("site-link");
  const copyBtn = $("copy"), promptBtn = $("prompt"), copiedEl = $("copied");
  const cmpToggle = $("cmp-toggle"), cmpEl = $("cmp"), afterEl = $("after"), cmpOut = $("cmp-out");
  const SITE = "https://humanizer-ru.aifrontier.tech/";
  if (typeof globalThis.humanizerScan !== "function") {
    emptyEl.innerHTML = "<p>Сканер не загрузился: нет vendor/scan.js. Соберите расширение скриптом scripts/build_extension.py.</p>";
    return;
  }
  const RULES = globalThis.HUMANIZER_RULES || {};
  const CLEAN = (RULES.score && RULES.score.band_clean) || 85;
  const DASH_NAME = (RULES.score && RULES.score.em_dash_name) || "Длинное тире";
  const facts = globalThis.humanizerFacts || null;

  // --- chrome.* с запасным вариантом вне расширения ---------------------------
  const hasChrome = typeof chrome !== "undefined" && !!chrome.storage;
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

  // --- Утилиты ------------------------------------------------------------------
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const plural = (n, one, few, many) => {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  };
  const num = (n, one, few, many) => `${n} ${plural(n, one, few, many)}`;
  const wordsOf = (t) => t.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  const genreLabel = () => genreEl.options[genreEl.selectedIndex].textContent;
  // Имена правил иногда содержат длинное тире («X [тире] это Y»). В интерфейсе
  // его нет: показываем словом, как в SKILL.md.
  const ruleName = (s) => String(s).replace(/\s*\u2014\s*/g, " [тире] ");
  const updateCount = () => {
    countEl.textContent = num(wordsOf(textEl.value), "слово", "слова", "слов");
    clearBtn.hidden = !textEl.value;
    emptyEl.hidden = !!textEl.value.trim();
    runBtn.disabled = !textEl.value.trim();
  };

  // Пример с сайта (нейрочерновик для eval-корпуса). Данные, не текст интерфейса.
  const EXAMPLE = "В современном мире успешный бизнес \u2014 это не просто продукт, а целая экосистема ценностей. Наша компания является надёжным партнёром, который играет ключевую роль в развитии вашего дела. Мы предлагаем комплексный подход, способный вывести ваш бренд на новый уровень и раскрыть его потенциал по-настоящему. Стоит отметить, что в условиях растущей конкуренции важно понимать: связь с аудиторией и доверительные отношения становятся главным активом. Именно поэтому мы выстраиваем индивидуальный подход к каждому клиенту. Наше инновационное решение открывает новые горизонты для роста \u2014 от привлечения первых пользователей до масштабирования на международные рынки. Таким образом, выбирая нас, вы выбираете не только сервис, но и команду, которая разделяет ваши амбиции. Можно с уверенностью сказать: вместе мы расширим границы возможного и достигнем результата, который превзойдёт ожидания.";

  // --- Язык результата: строки сканера в слова читателя ----------------------
  // Сырой reason остаётся в title строки, чтобы разработчик видел числа.
  const HUMAN_REASONS = [
    [/^хард-баны \(фразы\): (\d+)/, (m) => num(+m[1], "запрещённый оборот", "запрещённых оборота", "запрещённых оборотов")],
    [/^артефакты копипасты: (\d+)/, (m) => `${num(+m[1], "след", "следа", "следов")} копирования из чата`],
    [/^почерк модели: (\d+)/, (m) => `${num(+m[1], "оборот", "оборота", "оборотов")} из почерка свежих моделей`],
    [/^обвязка чата: (\d+)/, (m) => `${num(+m[1], "след", "следа", "следов")} ответа чат-бота: разметка, «Вариант 1», оферта доработать`],
    [/^маркеры: (\d+) \(([\d.]+)\/100 слов\)/, (m) => `${num(+m[1], "маркер", "маркера", "маркеров")}, ${m[2].replace(".", ",")} на 100 слов`],
    [/^тире: (\d+) \(([\d.]+)\/100 слов\)/, (m) => `длинное тире ${num(+m[1], "раз", "раза", "раз")}, ${m[2].replace(".", ",")} на 100 слов`],
    [/^ровный ритм/, () => "предложения одной длины"],
    [/^ровные абзацы/, () => "абзацы одной длины"],
    [/^лексическое разнообразие/, () => "слова почти не повторяются: синоним там, где человек повторил бы слово"],
    [/^листикл \((\d+) пунктов, (\d+)% строк\)/, (m) => `список вместо текста: ${num(+m[1], "пункт", "пункта", "пунктов")}, ${m[2]}% строк`],
  ];
  const humanReason = (reason) => {
    for (const [re, fn] of HUMAN_REASONS) { const m = reason.match(re); if (m) return fn(m); }
    return reason;
  };
  // Что делать со штрафом за структуру: у него нет подсвеченного оборота.
  const STRUCT_HINTS = [
    [/^ровный ритм/, "Разбейте длинное предложение или склейте два коротких."],
    [/^ровные абзацы/, "Пусть один абзац будет вдвое короче соседнего."],
    [/^лексическое разнообразие/, "Где подобран синоним, верните то же слово или «он», «это»."],
    [/^листикл/, "Часть пунктов перескажите абзацем."],
  ];
  const structHint = (reason) => { const h = STRUCT_HINTS.find(([re]) => re.test(reason)); return h ? h[1] : ""; };

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
    "Почерк модели": "Оборот из почерка свежих моделей. Один бывает и у человека, два-три в тексте выдают генерацию. Скажите то же проще или конкретнее.",
    "Обвязка чата": "Кусок ответа чат-бота, а не текста: разметка, «Вариант 1», плейсхолдер, предложение доработать. Удалите или впишите свои данные.",
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
  const spanTitle = (s) => ruleName(s.kind === "ban" ? s.name : `${s.cat}: ${s.name}`);

  function renderMarked(text, spans) {
    hintEl.hidden = true;
    let out = "", pos = 0;
    spans.forEach((s, i) => {
      out += esc(text.slice(pos, s.a));
      out += `<mark class="${s.kind}" tabindex="0" role="button" aria-pressed="false" data-i="${i}" aria-label="${esc(kindLabel(s.kind))}: ${esc(spanTitle(s))}">${esc(text.slice(s.a, s.b))}</mark>`;
      pos = s.b;
    });
    out += esc(text.slice(pos));
    markedEl.innerHTML = out;
    $("legend").hidden = !spans.length;
  }

  let lastSpans = [];
  function showHint(mark) {
    const s = lastSpans[+mark.dataset.i];
    if (!s) return;
    const pressed = mark.getAttribute("aria-pressed") === "true";
    markedEl.querySelectorAll('mark[aria-pressed="true"]').forEach((m) => m.setAttribute("aria-pressed", "false"));
    if (pressed) { hintEl.hidden = true; return; }
    mark.setAttribute("aria-pressed", "true");
    hintEl.className = `hint ${s.kind}`;
    hintEl.innerHTML = `<span class="label">${esc(kindLabel(s.kind))} / ${esc(spanTitle(s))}</span>${esc(hintFor(s.kind, s.cat, s.name))}`;
    hintEl.hidden = false;
  }
  markedEl.addEventListener("click", (ev) => { const m = ev.target.closest("mark"); if (m) showHint(m); });
  markedEl.addEventListener("keydown", (ev) => {
    const m = ev.target.closest("mark");
    if (!m) return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); showHint(m); }
    if (ev.key === "Escape") { m.setAttribute("aria-pressed", "false"); hintEl.hidden = true; }
  });

  // --- Вердикт словами ------------------------------------------------------------
  const bandOf = (r) => (r.band === "чисто" ? "good" : r.band === "правка" ? "warn" : "bad");
  const TAG = { good: "чисто", warn: "правка", bad: "переработка" };
  function verdictOf(band, r, spans) {
    if (band === "good") return r.words < 100 && !spans.length ? "Чисто, но текста пока мало" : "Текст чистый";
    if (band === "warn") return "Нужна точечная правка";
    return "Много шаблонных оборотов: нужна переработка";
  }
  function nextLine(band, spans, r) {
    if (!spans.length) {
      if (!r.penalties.length) {
        return r.words < 100
          ? `На ${num(r.words, "слове", "словах", "словах")} балл мало что значит: проверьте текст целиком.`
          : "Шаблонных оборотов не найдено.";
      }
      return "Обороты не найдены, штраф только за структуру: причины ниже.";
    }
    if (band === "bad") return "Начните с жёстких запретов (сплошная линия), потом маркеры (пунктир).";
    if (band === "warn") return "Пройдитесь по подчёркнутому, структуру не трогайте.";
    return "Подчёркнутое можно поправить, но это уже вкус.";
  }

  // Подробность к причине: какие именно обороты или что делать со структурой.
  function reasonDetail(reason, r) {
    if (/^хард-баны/.test(reason)) {
      const names = r.effective_bans.filter((h) => h.name !== DASH_NAME).map((h) => `«${ruleName(h.name)}»`);
      return names.slice(0, 3).join(", ") + (names.length > 3 ? ` и ещё ${names.length - 3}` : "");
    }
    if (/^маркеры/.test(reason)) {
      const cats = new Map();
      for (const h of r.muted_markers) cats.set(h.category, (cats.get(h.category) || 0) + h.count);
      return [...cats].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([c, n]) => `${c.toLowerCase()}${n > 1 ? ` ×${n}` : ""}`).join(", ");
    }
    return structHint(reason);
  }
  const reasonRow = (p, r) => {
    const detail = reasonDetail(p.reason, r);
    return `<li title="${esc(p.reason)}"><span class="txt">${esc(humanReason(p.reason))}${detail ? `<br><span class="note">${esc(detail)}</span>` : ""}</span><span class="pts">${esc(String(p.points).replace("-", "−"))}</span></li>`;
  };

  function genreNote() {
    const g = genreEl.value;
    if (!g) return "";
    const cats = ((RULES.genre_muted_categories || {})[g] || []).map((c) => c.toLowerCase());
    if (((RULES.score || {}).lex_muted_genres || []).includes(g)) cats.push("лексическое разнообразие");
    const bans = ((RULES.genre_muted_bans || {})[g] || []).map((b) => (typeof b === "string" ? b : b.name)).filter(Boolean);
    const parts = [];
    if (cats.length) parts.push(cats.join(", "));
    if (bans.length) parts.push(`${num(bans.length, "запрет", "запрета", "запретов")} вроде ${bans.slice(0, 2).map((b) => `«${ruleName(b.split(" / ")[0])}»`).join(" и ")}`);
    return parts.length ? `Жанр «${genreLabel()}»: не считаются ${parts.join(" и ")}.` : `Жанр «${genreLabel()}»: часть маркеров не считается.`;
  }

  // Чего расширение посчитать не может: без морфологического разбора нет штрафа
  // за номинальность. Разница всегда в пользу текста, поэтому о ней говорим вслух.
  function unmeasuredLine(r) {
    const gaps = r.unmeasured || [];
    if (!gaps.length) return "";
    const names = gaps.map((g) => `${g.name}, до ${g.max_points} баллов`).join("; ");
    return `Не измерено в браузере: ${names}. Счёт в скилле для агентов может быть ниже на эту величину.`;
  }

  // --- Режимы: ввод и результат -------------------------------------------------
  let checked = null; // { text, r, spans }
  function setMode(mode) {
    const edit = mode === "edit";
    editEl.hidden = !edit;
    resultEl.hidden = edit;
    body.dataset.mode = mode;
    if (edit) { hintEl.hidden = true; updateCount(); }
  }

  let lastReport = "";
  function renderResult(text, r, stale) {
    const band = bandOf(r);
    const spans = collectSpans(text, r);
    lastSpans = spans;
    checked = { text, r, spans };

    resultEl.className = band;
    $("score").textContent = r.score;
    $("tag").textContent = TAG[band];
    $("gauge").setAttribute("aria-label", `Чистота ${r.score} из 100`);
    // setTimeout, а не requestAnimationFrame: в неактивной вкладке rAF не тикает.
    setTimeout(() => { $("fill").style.transform = `scaleX(${r.score / 100})`; }, 30);
    const verdict = verdictOf(band, r, spans);
    $("verdict").textContent = verdict;
    $("next").textContent = nextLine(band, spans, r);

    const pens = [...r.penalties].sort((a, b) => a.points - b.points);
    // В попапе две главные причины, во вкладке три: текст должен попасть в экран.
    const nTop = isPopup ? 2 : 3;
    const top = pens.slice(0, nTop), rest = pens.slice(nTop);
    $("reasons-wrap").hidden = !pens.length;
    $("reasons").innerHTML = top.map((p) => reasonRow(p, r)).join("");
    $("more").hidden = !rest.length;
    $("more").open = false;
    $("more-sum").textContent = `ещё ${rest.length}`;
    $("reasons-more").style.counterReset = `r ${nTop}`;
    $("reasons-more").innerHTML = rest.map((p) => reasonRow(p, r)).join("");

    const gn = genreNote();
    $("genre-note").textContent = gn; $("genre-note").hidden = !gn;
    $("notes").textContent = r.notes.join(" "); $("notes").hidden = !r.notes.length;
    const gap = unmeasuredLine(r);
    $("unmeasured").textContent = gap; $("unmeasured").hidden = !gap;
    $("text-meta").textContent = `Текст / ${num(r.words, "слово", "слова", "слов")}${stale ? " / прошлая проверка" : ""}`;
    promptBtn.className = `btn ${r.score < CLEAN || spans.length ? "btn-cta" : "btn-ghost"}`;
    statusEl.textContent = `Чистота ${r.score} из 100. ${verdict}.`;
    if (r.score < CLEAN) { siteLink.textContent = "Скилл для агентов: правка по тем же правилам"; siteLink.href = SITE + "#install"; }
    else { siteLink.textContent = "Сайт и скилл для агентов"; siteLink.href = SITE; }

    renderMarked(text, spans);
    renderCompare();

    const bans = r.effective_bans.reduce((n, h) => n + h.count, 0);
    const marks = r.muted_markers.reduce((n, h) => n + h.count, 0);
    const found = new Map();
    for (const s of spans) { const k = `${kindLabel(s.kind)} / ${spanTitle(s)}`; found.set(k, (found.get(k) || 0) + 1); }
    lastReport = [
      `humanizer-ru: чистота ${r.score}/100, ${verdict.toLowerCase()}`,
      `жанр: ${genreLabel()} / ${num(r.words, "слово", "слова", "слов")} / запретов ${bans}, маркеров ${marks}`,
      pens.length ? "штрафы:\n" + pens.map((p) => `  ${String(p.points).padStart(4)}  ${humanReason(p.reason)}`).join("\n") : "штрафов нет",
      found.size ? "найдено:\n" + [...found].map(([k, n]) => `  ${k}${n > 1 ? ` ×${n}` : ""}`).join("\n") : "",
      gap,
      "Балл считают правила сканера, это не вероятность авторства ИИ.",
      SITE,
    ].filter(Boolean).join("\n");
  }

  function check(opts = {}) {
    const text = textEl.value;
    if (!text.trim()) { setMode("edit"); return false; }
    renderResult(text, globalThis.humanizerScan(text, genreEl.value || null), !!opts.stale);
    setMode("view");
    if (!opts.stale) store.set("local", "last", { text, after: afterEl.value });
    if (opts.focus) $("verdict").focus();
    return true;
  }

  // --- Промпт для правки ------------------------------------------------------------
  // Принципы дословно по skills/humanizer-ru/SKILL.md: «удаляй, не дописывай»,
  // факт-замок, запрет тире, «верни итоговый текст». Новых правил здесь нет.
  const PROMPT_RULES = [
    "Удаляй, не дописывай. Оборот снимается удалением оболочки или перестройкой фразы из тех же слов. Эмоции, оценки, шутки, образы и частицы, которых нет в исходнике, в текст не идут.",
    "Не добавляй факты, которых в исходнике нет: цифры, исследования, кейсы, имена. В исходнике нет конкретики, а оборот пустой? Удали оборот. Выдуманная цифра хуже канцелярита.",
    "Числа, даты, имена, названия, проценты, единицы, условия и оговорки исходника переноси без искажений. Оговорка при факте («может быть», «часто», «обычно», «примерно») задаёт его точность и не снимается.",
    "Без длинного тире. Длинное тире и короткое вне числовых диапазонов замени запятой, двоеточием, точкой или перестрой фразу.",
    "Верни только итоговый текст: без вступления, балла, списка правок и пояснений.",
  ];
  // Фрагмент для промпта: от начала слова, без пунктуации по краям.
  const wordStart = (text, a) => { while (a > 0 && /[\p{L}\p{M}]/u.test(text[a - 1])) a--; return a; };
  const fragment = (text, a, b) => {
    while (a < b && /[\s.,;:!?]/.test(text[a])) a++;
    return text.slice(wordStart(text, a), wordEnd(text, b)).replace(/\s+/g, " ").replace(/[\s,;:]+$/, "");
  };
  function buildPrompt() {
    if (!checked) return "";
    const { text, r } = checked;
    // Все находки, а не только подсвеченные: подсветка прячет пересечения.
    // Маркер внутри запрета («стоит отметить» в «Стоит отметить, что») не дублируем.
    const banRanges = [];
    const groups = [];
    for (const h of r.effective_bans) {
      h.positions.forEach(([a, b]) => banRanges.push([a, b]));
      groups.push({ s: { kind: "ban", cat: "", name: h.name }, n: h.count, frags: [...new Set(h.positions.map(([a, b]) => fragment(text, a, b)))] });
    }
    for (const h of r.muted_markers) {
      const own = h.positions.filter(([a, b]) => !banRanges.some(([x, y]) => a < y && b > x));
      if (!own.length) continue;
      groups.push({ s: { kind: "mk", cat: h.category, name: h.name }, n: own.length, frags: [...new Set(own.map(([a, b]) => fragment(text, a, b)))] });
    }
    const sorted = groups;
    const MAX = 30;
    const found = sorted.slice(0, MAX).map(({ s, n, frags }) => {
      const where = frags.slice(0, 3).map((f) => `«${f}»`).join(", ") + (n > 1 ? ` \u00d7${n}` : "");
      return `- ${where} (${kindLabel(s.kind)}: ${spanTitle(s)}). ${hintFor(s.kind, s.cat, s.name)}`;
    });
    if (sorted.length > MAX) found.push(`- и ещё ${sorted.length - MAX} похожих оборотов.`);
    for (const p of r.penalties) {
      const h = structHint(p.reason);
      if (h) found.push(`- Структура: ${humanReason(p.reason)}. ${h}`);
    }
    return [
      "Отредактируй русский текст ниже. Убери шаблонные обороты, канцелярит и нейросетевую манеру, не сломав смысл, факты и голос автора.",
      "",
      "Правила:",
      ...PROMPT_RULES.map((x, i) => `${i + 1}. ${x}`),
      "",
      `Что нашла проверка humanizer-ru (чистота ${r.score}/100, жанр: ${genreLabel()}):`,
      ...(found.length ? found : ["- шаблонных оборотов не найдено; правь только то, что мешает читателю."]),
      "",
      "Текст:",
      "<<<",
      text.trim(),
      ">>>",
    ].join("\n");
  }

  async function copyText(btn, value, okMsg) {
    let ok = false;
    try { await navigator.clipboard.writeText(value); ok = true; } catch (e) { /* нет доступа к буферу */ }
    copiedEl.textContent = ok ? okMsg : "Не удалось скопировать: браузер не дал доступ к буферу обмена.";
    copiedEl.hidden = false;
    statusEl.textContent = copiedEl.textContent;
    clearTimeout(copyText.t);
    copyText.t = setTimeout(() => { copiedEl.hidden = true; }, 4000);
  }
  promptBtn.addEventListener("click", () => copyText(promptBtn, buildPrompt(), "Промпт скопирован. Вставьте его в любой чат-бот, а ответ сравните здесь: «Было / стало»."));
  copyBtn.addEventListener("click", () => copyText(copyBtn, lastReport + (lastCompareReport ? "\n" + lastCompareReport : ""), "Отчёт скопирован."));

  // --- Было / стало ------------------------------------------------------------------
  let lastCompareReport = "";
  const findingsOf = (r) => {
    const m = new Map();
    for (const h of r.effective_bans) m.set(`ban|${h.name}`, { label: ruleName(h.name), n: h.count, kind: "ban" });
    for (const h of r.muted_markers) m.set(`mk|${h.category}|${h.name}`, { label: ruleName(h.name), n: h.count, kind: "mk" });
    return m;
  };
  // Больше восьми плашек не читается: остальное одной плашкой «ещё N».
  const CHIPS_MAX = 8;
  const chips = (items, cls) => {
    const shown = items.slice(0, CHIPS_MAX).map(([label, n]) => `<li class="${cls}">${esc(label)}${n > 1 ? ` ×${n}` : ""}</li>`);
    if (items.length > CHIPS_MAX) shown.push(`<li class="more">ещё ${items.length - CHIPS_MAX}</li>`);
    return `<ul class="chips">${shown.join("")}</ul>`;
  };
  function openCompare(open) {
    cmpEl.hidden = !open;
    cmpToggle.setAttribute("aria-expanded", String(open));
    if (open) renderCompare();
  }
  function renderCompare() {
    lastCompareReport = "";
    if (cmpEl.hidden || !checked) return;
    const after = afterEl.value;
    if (!after.trim()) { cmpOut.hidden = true; cmpOut.innerHTML = ""; return; }
    const rBefore = checked.r, rAfter = globalThis.humanizerScan(after, genreEl.value || null);
    const d = rAfter.score - rBefore.score;
    const delta = d > 0 ? `+${d}` : d < 0 ? `−${-d}` : "0";
    const fb = findingsOf(rBefore), fa = findingsOf(rAfter);
    const gone = [], stayed = [], fresh = [];
    for (const [k, v] of fb) {
      const n = fa.has(k) ? fa.get(k).n : 0;
      if (n < v.n) gone.push([v.label, v.n - n]);
      if (n > 0) stayed.push([v.label, Math.min(n, v.n)]);
    }
    for (const [k, v] of fa) {
      const was = fb.has(k) ? fb.get(k).n : 0;
      if (v.n > was) fresh.push([v.label, v.n - was]);
    }
    const sum = (xs) => xs.reduce((n, [, c]) => n + c, 0);
    const fd = facts ? facts.factsDiff(checked.text, after) : null;
    const risky = fd && (fd.added.length || fd.claimsAdded.length);
    let lockText;
    if (!fd) lockText = "Факт-замок не загрузился: сверьте числа и имена глазами.";
    else if (risky) lockText = "В правке есть то, чего не было в исходнике. Выдуманная цифра хуже канцелярита: проверьте глазами.";
    else if (fd.lost.length) lockText = `Новых фактов нет, но часть исходных пропала: ${fd.kept} из ${fd.total} на месте. Проверьте, не ушёл ли смысл.`;
    else if (fd.total) lockText = `${fd.kept} из ${num(fd.total, "факта исходника", "фактов исходника", "фактов исходника")} на месте, новых нет.`;
    else lockText = "Чисел, имён и ссылок в исходнике нет, сравнивать нечего.";
    const lockRows = [];
    if (fd && fd.lost.length) lockRows.push(`<div class="cmp-block"><span class="label">Пропало</span>${chips(fd.lost.map((x) => [x, 1]), "lost")}</div>`);
    if (fd && fd.added.length) lockRows.push(`<div class="cmp-block"><span class="label">Появилось</span>${chips(fd.added.map((x) => [x, 1]), "added")}</div>`);
    if (fd && fd.claimsAdded.length) lockRows.push(`<div class="cmp-block"><span class="label">Новый квантор</span>${chips(fd.claimsAdded.map((x) => [x, 1]), "added")}</div>`);
    const bBand = bandOf(rBefore), aBand = bandOf(rAfter);
    const verdict = d > 0 ? "Правка сняла шаблонные обороты." : d < 0 ? "После правки оборотов стало больше." : "Балл не изменился.";
    cmpOut.hidden = false;
    cmpOut.innerHTML = `
      <div class="cmp-scores" role="group" aria-label="Балл до и после">
        <span><span class="label">Было</span> <b class="z-${bBand}">${rBefore.score}</b></span>
        <span class="cmp-arrow" aria-hidden="true">→</span>
        <span><span class="label">Стало</span> <b class="z-${aBand}">${rAfter.score}</b></span>
        <span class="cmp-delta ${d > 0 ? "up" : d < 0 ? "down" : ""}">${delta}</span>
      </div>
      <p class="next">${esc(verdict)}</p>
      ${gone.length ? `<div class="cmp-block"><span class="label">Ушли / ${sum(gone)}</span>${chips(gone, "gone")}</div>` : ""}
      ${stayed.length ? `<div class="cmp-block"><span class="label">Остались / ${sum(stayed)}</span>${chips(stayed, "")}</div>` : ""}
      ${fresh.length ? `<div class="cmp-block"><span class="label">Появились / ${sum(fresh)}</span>${chips(fresh, "added")}</div>` : ""}
      <div class="lock ${risky || (fd && fd.lost.length) || !fd ? "warn" : ""}">
        <span class="label">Факт-замок</span>
        <p>${esc(lockText)}</p>
        ${lockRows.join("")}
      </div>
      <div class="row actions"><button type="button" id="adopt" class="btn btn-ghost btn-sm">Сделать правку основным текстом</button></div>`;
    lastCompareReport = [
      `правка: было ${rBefore.score}, стало ${rAfter.score} (${delta.replace("−", "-")})`,
      gone.length ? `  ушли: ${gone.map(([l, n]) => l + (n > 1 ? ` ×${n}` : "")).join(", ")}` : "",
      fresh.length ? `  появились: ${fresh.map(([l, n]) => l + (n > 1 ? ` ×${n}` : "")).join(", ")}` : "",
      fd && fd.lost.length ? `  факт-замок, пропало: ${fd.lost.join(", ")}` : "",
      fd && fd.added.length ? `  факт-замок, появилось: ${fd.added.join(", ")}` : "",
      fd && fd.claimsAdded.length ? `  факт-замок, новый квантор: ${fd.claimsAdded.join(", ")}` : "",
      fd && !risky && !fd.lost.length && fd.total ? `  факт-замок: ${fd.kept}/${fd.total} на месте` : "",
    ].filter(Boolean).join("\n");
  }
  cmpToggle.addEventListener("click", () => {
    const open = cmpEl.hidden;
    openCompare(open);
    if (open) afterEl.focus();
  });
  cmpOut.addEventListener("click", (ev) => {
    if (!ev.target.closest("#adopt")) return;
    textEl.value = afterEl.value; afterEl.value = "";
    openCompare(false);
    check({ focus: true });
  });
  let cmpTimer = null;
  afterEl.addEventListener("input", () => {
    clearTimeout(cmpTimer);
    cmpTimer = setTimeout(() => { renderCompare(); if (checked) store.set("local", "last", { text: checked.text, after: afterEl.value }); }, 250);
  });

  // --- События ввода --------------------------------------------------------------
  textEl.addEventListener("input", updateCount);
  // Вставка в пустое поле сразу проверяет: вставил и видишь результат.
  textEl.addEventListener("paste", () => {
    if (textEl.value.trim()) return;
    setTimeout(() => { updateCount(); check({ focus: true }); }, 0);
  });
  textEl.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); check({ focus: true }); }
  });
  runBtn.addEventListener("click", () => check({ focus: true }));
  if (/Mac/i.test(navigator.platform || navigator.userAgent)) document.querySelector(".kbd-hint").textContent = "Cmd+Enter";
  $("edit-btn").addEventListener("click", () => {
    openCompare(false);
    setMode("edit");
    textEl.focus();
  });
  genreEl.addEventListener("change", () => {
    store.set("local", "genre", genreEl.value);
    if (body.dataset.mode === "view") check();
  });
  $("example").addEventListener("click", () => { textEl.value = EXAMPLE; afterEl.value = ""; updateCount(); check({ focus: true }); });
  // Сброс: пустое поле, прошлая проверка забыта. Из режима просмотра тоже:
  // кнопка «Новый текст» рядом с «Изменить текст».
  function resetText() {
    textEl.value = ""; afterEl.value = ""; checked = null;
    store.remove("local", "last");
    setMode("edit");
    updateCount(); textEl.focus();
  }
  clearBtn.addEventListener("click", resetText);
  $("new-btn").addEventListener("click", resetText);

  // --- Во вкладке ------------------------------------------------------------------------
  // Широкий режим для длинного текста: та же страница вкладкой (?tab=1).
  // chrome.tabs.create со своим адресом разрешений не требует. Текст едет через
  // storage.session, как из контекстного меню.
  const toTab = $("to-tab");
  const canTab = hasChrome && chrome.tabs && chrome.runtime && chrome.runtime.getURL;
  if (isPopup) toTab.hidden = false;
  toTab.addEventListener("click", async () => {
    if (!canTab) { copiedEl.textContent = "Вкладка открывается только в установленном расширении."; copiedEl.hidden = false; statusEl.textContent = copiedEl.textContent; return; }
    const text = textEl.value;
    if (text.trim()) await store.set("session", "pending", { text, at: Date.now() });
    await chrome.tabs.create({ url: chrome.runtime.getURL("popup.html?tab=1") });
    window.close();
  });

  // --- Тема: авто, светлая, тёмная ------------------------------------------------------
  // Выбор в chrome.storage.local; копия в localStorage нужна, чтобы применить
  // тему до первой отрисовки и не мигать. Вне расширения живёт в памяти.
  const THEMES = ["auto", "light", "dark"];
  const themeBtns = [...document.querySelectorAll("[data-theme-set]")];
  function applyTheme(t) {
    if (!THEMES.includes(t)) t = "auto";
    if (t === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
    themeBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeSet === t)));
    try { localStorage.setItem("humanizer-ru:theme", t); } catch (e) { /* хранилище закрыто */ }
  }
  try { applyTheme(localStorage.getItem("humanizer-ru:theme") || "auto"); } catch (e) { applyTheme("auto"); }
  themeBtns.forEach((b) => b.addEventListener("click", () => { applyTheme(b.dataset.themeSet); store.set("local", "theme", b.dataset.themeSet); }));

  // Выделение из контекстного меню: при старте и, если вкладка уже открыта, по
  // событию storage.onChanged.
  async function takePending() {
    const pending = await store.get("session", "pending");
    if (!(pending && pending.text && Date.now() - (pending.at || 0) < 60000)) return false;
    await store.remove("session", "pending");
    textEl.value = pending.text; afterEl.value = "";
    openCompare(false);
    updateCount();
    check();
    return true;
  }
  try {
    // Только вкладка: попап сам кладёт pending для вкладки и не должен его перехватить.
    if (!isPopup && hasChrome && chrome.storage.onChanged) {
      chrome.storage.onChanged.addListener((changes, area) => {
        if (area === "session" && changes.pending && changes.pending.newValue) takePending();
      });
    }
  } catch (e) { /* вне расширения */ }

  // --- Старт ------------------------------------------------------------------------------
  (async () => {
    try {
      const v = hasChrome && chrome.runtime && chrome.runtime.getManifest ? chrome.runtime.getManifest().version : "";
      if (v) $("version").textContent = `v${v}`;
    } catch (e) { /* вне расширения */ }
    const theme = await store.get("local", "theme");
    if (theme) applyTheme(theme);
    // Жанр это настройка, а не свойство текста: живёт отдельно.
    const genre = await store.get("local", "genre");
    if (genre && [...genreEl.options].some((o) => o.value === genre)) genreEl.value = genre;
    if (await takePending()) return;
    const last = await store.get("local", "last");
    if (last && last.text) {
      textEl.value = last.text;
      afterEl.value = last.after || "";
      updateCount();
      check({ stale: true });
    } else {
      setMode("edit");
      updateCount();
      textEl.focus();
    }
  })();
})();
