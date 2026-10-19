"use strict";
(() => {
    const el = (id) => { const node = document.getElementById(id); if (!node)
        throw new Error(`Missing element ${id}`); return node; };
    const cases = [
        { label: 'ПОСТ ДЛЯ БЛОГА', genre: 'marketing', before: 'Стоит отметить, что данный инструмент помогает редактору находить канцелярит. Проверка занимает около двух минут. Результат нужно перечитать.', after: 'Этот инструмент помогает редактору находить канцелярит. Проверка занимает около двух минут. Результат нужно перечитать.', edit: 'Убрали пустую подводку. «Данный» заменили на «этот». Остальной текст не трогали.', check: '«Около двух минут» осталось приблизительной оценкой. Просьба перечитать результат сохранена.' },
        { label: 'ПИСЬМО КЛИЕНТУ', genre: 'marketing', before: 'В связи с этим просим вас осуществить проверку документов до 15 октября. Стоит отметить, что без подписи мы не сможем отправить заявку.', after: 'Просим вас проверить документы до 15 октября. Без подписи мы не сможем отправить заявку.', edit: '«Осуществить проверку» заменили глаголом. Сняли вводные обороты, сохранили просьбу.', check: 'Срок 15 октября и условие отправки заявки на месте. Вежливая форма обращения сохранена.' },
        { label: 'ОПИСАНИЕ ПРОДУКТА', genre: 'marketing', before: 'Данный сервис может уменьшить число возвратов, если в карточке товара есть точные размеры. Стоимость начинается от 1500 рублей в месяц.', after: 'Этот сервис может уменьшить число возвратов, если в карточке товара есть точные размеры. Стоимость начинается от 1500 рублей в месяц.', edit: 'Заменили только «данный». Полезную оговорку нельзя убирать ради более уверенного тона.', check: '«Может», условие про размеры и «от 1500 рублей в месяц» сохранены. Возможность не стала гарантией.' }
    ];
    let currentCase = 0, currentStep = 0;
    const stageTitles = ['Сначала найдём лишнее.', 'Теперь снимем оболочку.', 'И перечитаем рядом с исходником.'];
    const stageNotes = ['Сканер отмечает обороты. Решение о правке зависит от смысла и жанра.', 'Меняем конкретные места. Всё, что уже работает, оставляем.', 'Сверяем утверждения, числа, условия и голос. Одного балла для этого мало.'];
    // Подсветка в учебном пульте: без подсказок, только место оборота.
    function markText(target, text, findings) {
        const ranges = findings.flatMap(f => f.positions).filter(([a, b]) => a >= 0 && b > a && b <= text.length).sort((a, b) => a[0] - b[0]);
        const merged = [];
        for (const [a, b] of ranges) {
            const last = merged[merged.length - 1];
            if (last && a <= last[1])
                last[1] = Math.max(last[1], b);
            else
                merged.push([a, b]);
        }
        target.replaceChildren();
        let position = 0;
        for (const [a, b] of merged) {
            target.append(document.createTextNode(text.slice(position, a)));
            const mark = document.createElement('mark');
            mark.textContent = text.slice(a, b);
            target.append(mark);
            position = b;
        }
        target.append(document.createTextNode(text.slice(position)));
    }
    function renderStory() {
        const c = cases[currentCase], text = currentStep === 0 ? c.before : c.after, before = humanizerScan(c.before, c.genre), after = humanizerScan(c.after, c.genre), r = currentStep === 0 ? before : after;
        el('case-label').textContent = c.label + ' / ' + (currentStep === 0 ? 'ЧЕРНОВИК' : 'ПРАВКА');
        el('page-label').textContent = 'ЛИСТ 0' + (currentCase + 1);
        el('stage-label').textContent = ['01 / ДИАГНОСТИКА', '02 / ЛОКАЛЬНАЯ ПРАВКА', '03 / СВЕРКА С ИСХОДНИКОМ'][currentStep];
        el('stage-title').textContent = stageTitles[currentStep];
        el('stage-note').textContent = stageNotes[currentStep];
        el('screen-title').textContent = ['Где текст буксует', 'Читается проще', 'Что мы сохранили'][currentStep];
        el('story-score').textContent = String(r.score);
        markText(el('story-text'), text, currentStep === 0 ? [...r.effective_bans, ...r.muted_markers] : []);
        el('editor-note').textContent = currentStep === 0 ? 'Подчёркнуты совпадения с правилами сканера. Перейдите к правке.' : currentStep === 1 ? c.edit : c.check;
        el('screen-status').textContent = currentStep === 2 ? `БАЛЛ ${before.score} → ${after.score} / СВЕРКА ВРУЧНУЮ` : 'УЧЕБНЫЙ ПРИМЕР / ' + (currentStep === 0 ? 'ИСХОДНИК' : 'ПРАВКА');
        document.querySelectorAll('[data-case]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.case) === currentCase)));
        document.querySelectorAll('[data-step]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.step) === currentStep)));
    }
    document.querySelectorAll('[data-case]').forEach(b => b.addEventListener('click', () => { currentCase = Number(b.dataset.case); currentStep = 0; renderStory(); }));
    document.querySelectorAll('[data-step]').forEach(b => b.addEventListener('click', () => { currentStep = Number(b.dataset.step); renderStory(); }));
    renderStory();
    const input = el('audit-input'), genre = el('genre'), afterInput = el('after-input');
    let reportText = '';
    let toastTimer;
    let scanTimer;
    let spans = [];
    const H = humanizerHints;
    function toast(message) { el('toast').textContent = message; el('toast').hidden = false; window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => el('toast').hidden = true, 3500); }
    async function copy(text) { try {
        await navigator.clipboard.writeText(text);
        toast('Скопировано.');
    }
    catch {
        toast('Не удалось скопировать. Выделите текст и скопируйте вручную.');
    } }
    const russian = (text) => humanizerIsRussian(text);
    function showPanel(which) { el('empty-result').hidden = which !== 'empty'; el('lang-note').hidden = which !== 'lang'; el('result-content').hidden = which !== 'result'; }
    function invalidate() { reportText = ''; el('char-count').textContent = `${input.value.length.toLocaleString('ru-RU')} / 30 000`; el('compare-result').textContent = ''; }
    // Проверка сама: сразу после вставки и через полсекунды после набора, как на странице-инструменте.
    function schedule(delay) { window.clearTimeout(scanTimer); scanTimer = window.setTimeout(() => scan(false), delay); }
    input.addEventListener('input', () => { invalidate(); schedule(500); });
    input.addEventListener('paste', () => schedule(0));
    genre.addEventListener('change', () => { invalidate(); if (input.value.trim())
        scan(false); });
    afterInput.addEventListener('input', () => el('compare-result').textContent = '');
    // Края подсветки тянем до границы слова только для показа: счёт не меняется.
    const wordEnd = (text, b) => { while (b < text.length && /[\p{L}\p{M}]/u.test(text[b]))
        b++; return b; };
    function collectSpans(text, r) {
        const all = [];
        for (const h of r.effective_bans)
            for (const [a, b] of h.positions)
                all.push({ a, b: wordEnd(text, b), kind: 'ban', cat: '', name: h.name });
        for (const h of r.muted_markers)
            for (const [a, b] of h.positions)
                all.push({ a, b: wordEnd(text, b), kind: 'mk', cat: h.category, name: h.name });
        all.sort((x, y) => x.a - y.a || (x.kind === 'ban' ? -1 : 1));
        const out = [];
        let pos = 0;
        for (const s of all) {
            if (s.a < pos || s.b > text.length)
                continue;
            out.push(s);
            pos = s.b;
        }
        return out;
    }
    const spanTitle = (s) => H.ruleName(s.kind === 'ban' ? s.name : `${s.cat}: ${s.name}`);
    // Подчёркивание нажимается: под текстом появляется правило и что с ним сделать.
    function markInteractive(target, text, list) {
        target.replaceChildren();
        let position = 0;
        list.forEach((s, i) => { target.append(document.createTextNode(text.slice(position, s.a))); const mark = document.createElement('mark'); mark.className = s.kind; mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-pressed', 'false'); mark.dataset.i = String(i); mark.setAttribute('aria-label', `${H.kindLabel(s.kind)}: ${spanTitle(s)}`); mark.textContent = text.slice(s.a, s.b); target.append(mark); position = s.b; });
        target.append(document.createTextNode(text.slice(position)));
    }
    function showHint(mark) {
        const s = spans[Number(mark.dataset.i)], hint = el('mark-hint');
        if (!s)
            return;
        const pressed = mark.getAttribute('aria-pressed') === 'true';
        el('highlighted-text').querySelectorAll('mark[aria-pressed="true"]').forEach(m => m.setAttribute('aria-pressed', 'false'));
        if (pressed) {
            hint.hidden = true;
            return;
        }
        mark.setAttribute('aria-pressed', 'true');
        hint.replaceChildren();
        const b = document.createElement('b');
        b.className = s.kind;
        b.textContent = `${H.kindLabel(s.kind)}, ${spanTitle(s)}.`;
        hint.append(b, document.createTextNode(' ' + H.hintFor(s.kind, s.cat, s.name)));
        hint.hidden = false;
    }
    el('highlighted-text').addEventListener('click', e => { const m = e.target.closest('mark'); if (m)
        showHint(m); });
    el('highlighted-text').addEventListener('keydown', e => { const m = e.target.closest('mark'); if (!m)
        return; if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        showHint(m);
    } if (e.key === 'Escape') {
        m.setAttribute('aria-pressed', 'false');
        el('mark-hint').hidden = true;
    } });
    function scan(manual = true) {
        window.clearTimeout(scanTimer);
        const text = input.value;
        if (!text.trim()) {
            showPanel('empty');
            if (manual) {
                toast('Сначала вставьте текст.');
                input.focus();
            }
            return;
        }
        // Не русский текст: балла нет, иначе английский абзац получил бы 100 «чисто».
        if (!russian(text)) {
            reportText = '';
            el('lang-note').textContent = H.NOT_RUSSIAN;
            showPanel('lang');
            return;
        }
        try {
            const r = humanizerScan(text, genre.value);
            showPanel('result');
            el('scan-score').textContent = String(r.score);
            const bandKey = H.bandOf(r), band = el('score-band');
            band.textContent = bandKey === 'good' ? 'МАЛО МАРКЕРОВ' : bandKey === 'warn' ? 'ЕСТЬ ЧТО ПОПРАВИТЬ' : 'МНОГО МАРКЕРОВ';
            band.dataset.band = bandKey === 'warn' ? 'mid' : bandKey;
            spans = collectSpans(text, r);
            const groups = new Map();
            for (const s of spans) {
                const key = s.kind + '|' + s.cat + '|' + s.name;
                const g = groups.get(key);
                if (g)
                    g.n++;
                else
                    groups.set(key, { s, n: 1 });
            }
            const unique = [...groups.values()].sort((x, y) => x.s.kind === y.s.kind ? x.s.a - y.s.a : x.s.kind === 'ban' ? -1 : 1);
            el('scan-summary').textContent = unique.length ? `Найдено правил с совпадениями: ${unique.length}. Нажмите на подчёркнутое, чтобы увидеть подсказку.` : 'Совпадений с лексическими правилами нет. Прочитайте текст целиком: смысл и польза не измеряются этим баллом.';
            el('scan-next').textContent = H.nextLine(bandKey, spans.length > 0, r);
            markInteractive(el('highlighted-text'), text, spans);
            el('mark-hint').hidden = true;
            el('mark-legend').hidden = !spans.length;
            const list = el('findings');
            list.replaceChildren();
            for (const { s, n } of unique.slice(0, 12)) {
                const li = document.createElement('li');
                li.className = s.kind;
                const b = document.createElement('b');
                b.textContent = spanTitle(s) + (n > 1 ? ` ×${n}` : '');
                li.append(b, document.createTextNode('. ' + H.hintFor(s.kind, s.cat, s.name)));
                list.append(li);
            }
            if (unique.length > 12) {
                const li = document.createElement('li');
                li.textContent = `Ещё правил с совпадениями: ${unique.length - 12}. Полный список в скопированном отчёте и в полном разборе.`;
                list.append(li);
            }
            if (r.penalties.length) {
                for (const p of r.penalties.filter(p => !/^хард-баны|^маркеры/.test(p.reason))) {
                    const li = document.createElement('li');
                    li.textContent = `${H.penaltyCategory(p.reason)}: ${H.humanReason(p.reason)}, ${p.points}.`;
                    list.append(li);
                }
            }
            const gap = H.unmeasuredLine(r);
            reportText = `humanizer-ru / жанр: ${genre.selectedOptions[0].textContent}\nЧистота: ${r.score}/100\n` + unique.map(({ s, n }) => `${spanTitle(s)}: ${n}`).join('\n') + '\nШтрафы:\n' + r.penalties.map(p => `${H.humanReason(p.reason)}: ${p.points}`).join('\n') + (gap ? '\n' + gap : '') + '\nБалл не определяет авторство и не подтверждает сохранение смысла.';
        }
        catch {
            toast('Сканер не запустился. Обновите страницу или используйте CLI.');
        }
    }
    el('scan-button').addEventListener('click', () => scan(true));
    input.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter')
        scan(true); });
    el('load-example').addEventListener('click', () => { input.value = cases[currentCase].before; genre.value = cases[currentCase].genre; invalidate(); scan(true); });
    el('clear-button').addEventListener('click', () => { input.value = ''; afterInput.value = ''; invalidate(); showPanel('empty'); input.focus(); });
    el('copy-report').addEventListener('click', () => { if (reportText)
        void copy(reportText); });
    // «Полный разбор» открывает тот же текст на странице-инструменте: черновик
    // кладётся в localStorage этого браузера по явному клику, как там же делает «Очистить».
    el('full-review').addEventListener('click', () => { if (!input.value.trim())
        return; try {
        localStorage.setItem('humanizer-ru:draft', JSON.stringify({ text: input.value, genre: genre.value === 'marketing' ? '' : genre.value, after: afterInput.value }));
    }
    catch { /* хранилище закрыто: страница откроется пустой */ } });
    // Полная проверка фактов из facts.js (числа, имена, месяцы, ссылки, кванторы), как в расширении; без неё только числа.
    function factsOf(before, after) {
        if (typeof humanizerFacts !== 'undefined' && humanizerFacts)
            return humanizerFacts.factsDiff(before, after);
        const x = humanizerNumericFacts(before), y = humanizerNumericFacts(after);
        return { lost: [...x].filter(([k]) => !y.has(k)).map(([, v]) => v), added: [...y].filter(([k]) => !x.has(k)).map(([, v]) => v), claimsAdded: [], kept: [...x].filter(([k]) => y.has(k)).length, total: x.size };
    }
    el('compare-button').addEventListener('click', () => {
        if (!input.value.trim() || !afterInput.value.trim()) {
            el('compare-result').textContent = 'Для сравнения нужны исходник и правка.';
            return;
        }
        if (!russian(input.value) || !russian(afterInput.value)) {
            el('compare-result').textContent = 'Обе версии должны быть на русском языке.';
            return;
        }
        const a = humanizerScan(input.value, genre.value), b = humanizerScan(afterInput.value, genre.value), fd = factsOf(input.value, afterInput.value), lost = fd.lost, added = [...fd.added, ...fd.claimsAdded];
        el('compare-result').textContent = `Чистота: ${a.score} → ${b.score}/100.\n` + (lost.length ? `Пропало: ${[...new Set(lost)].join('; ')}.\n` : '') + (added.length ? `Появилось: ${[...new Set(added)].join('; ')}.\n` : '') + (!lost.length && !added.length ? 'В числах, именах, датах и ссылках различий не найдено.\n' : 'Проверьте, намеренно ли изменены значения.\n') + 'Сохранение смысла не проверено. Сверьте, к чему относятся числа, и не пропали ли условия.';
    });
    const installs = {
        skill: { label: 'ОДНА КОМАНДА', title: 'Добавьте скилл своему агенту.', description: 'Установщик предложит доступные агенты и место установки. Нужен Node.js с npx.', command: 'npx skills add ilyautov/humanizer-ru', task: '«Отредактируй этот текст. Убери канцелярит, сохрани факты, оговорки и мой тон».' },
        claude: { label: 'CLAUDE CODE / PLUGIN', title: 'Установите через marketplace.', description: 'Выполните обе команды внутри Claude Code. Скилл будет доступен в среде агента.', command: '/plugin marketplace add ilyautov/humanizer-ru\n/plugin install humanizer-ru@ilyautov-plugins', task: '«Проверь этот текст: покажи, что мешает читать. Пока ничего не переписывай».' },
        cli: { label: 'PYTHON / CLI + MCP', title: 'Проверка из терминала.', description: 'Для команд нужен uv. Первая проверяет файл; вторая запускает MCP-сервер для подключения из клиента.', command: 'uvx ru-humanizer text.txt\nuvx ru-humanizer mcp', task: 'Для сверки своей правки: uvx ru-humanizer after.txt --before before.txt. Подробности подключения MCP есть в README.' },
        browser: { label: 'CHROME / РАСШИРЕНИЕ', title: 'Проверяйте текст на странице.', description: 'Установите расширение из Chrome Web Store. Выделите русский текст и выберите проверку в контекстном меню.', command: '', task: 'Расширение показывает балл и найденные обороты. Переписать текст можно вручную или с помощью скилла в агенте.' }
    };
    let installKey = 'skill';
    document.querySelectorAll('[data-install]').forEach(button => button.addEventListener('click', () => { installKey = button.dataset.install || 'skill'; const item = installs[installKey]; el('install-label').textContent = item.label; el('install-title').textContent = item.title; el('install-description').textContent = item.description; el('install-command').textContent = item.command; el('first-task').textContent = item.task; el('command-box').hidden = !item.command; el('install-external').hidden = Boolean(item.command); document.querySelectorAll('[data-install]').forEach(b => b.setAttribute('aria-pressed', String(b === button))); }));
    el('copy-command').addEventListener('click', () => void copy(installs[installKey].command));
    const motion = matchMedia('(prefers-reduced-motion: reduce)'), desktop = matchMedia('(min-width: 761px)');
    let scheduled = false;
    function updateTilt() { scheduled = false; const consoleEl = el('console'); if (motion.matches || !desktop.matches) {
        consoleEl.style.transform = 'none';
        return;
    } const box = el('story').getBoundingClientRect(), progress = Math.min(1, Math.max(0, (innerHeight - box.top) / (innerHeight + box.height))); consoleEl.style.transform = `rotateY(${-7 + progress * 11}deg) rotateX(${7 - progress * 10}deg) rotateZ(${2 - progress * 3}deg)`; }
    function queueTilt() { if (!scheduled) {
        scheduled = true;
        requestAnimationFrame(updateTilt);
    } }
    addEventListener('scroll', queueTilt, { passive: true });
    addEventListener('resize', queueTilt, { passive: true });
    motion.addEventListener('change', queueTilt);
    desktop.addEventListener('change', queueTilt);
    queueTilt();
})();
