# Сайт humanizer-ru (GitHub Pages)

Статический сайт проекта: https://humanizer-ru.aifrontier.tech/
Без Jekyll и без сборщика. Единственная сборка: `workshop.ts` компилируется в
`workshop.js` (см. ниже). Аналитики и внешних CDN нет.

## Как включить GitHub Pages

1. Репозиторий на GitHub, **Settings**, **Pages**.
2. **Build and deployment**, **Source**: **Deploy from a branch**.
3. Branch: `main`, папка: `/docs`. Сохранить.

## Страницы

- `index.html`: главная. Первый экран для человека без агента («Проверить текст»), сканер с подсказками, пример правки на пульте, установка скилла, FAQ.
- `proverit-tekst-na-neyroset.html`: страница-инструмент, полный разбор текста с подсказками, жанрами и сравнением «было и стало».
- `52-priznaka-ai-teksta.html`: каталог признаков AI-текста (адрес исторический, признаков 67).
- `kak-ubrat-sledy-neyroseti.html`: как редактировать AI-текст по шагам.
- `kancelyarit.html`: канцелярит, признаки и примеры.
- `ai-detektory-na-russkom.html`: работают ли AI-детекторы на русском.
- `antiplagiat-i-neyroset.html`: антиплагиат и AI-детектор, в чём разница.
- `gumanizator-teksta.html`: как выбрать гуманизатор, перефразирование против редактуры.
- `privacy.html`: приватность расширения Chrome (что хранится и где).
- `style.css`: общий стиль.
- `sitemap.xml`, `robots.txt`: для поисковиков.

Служебное: `sitemap.xml` (собирает `scripts/build_sitemap.py`), `robots.txt`, `llms.txt`, `CNAME`, файл-ключ `b4061b69….txt` для поисковиков.

## Скрипты

Сканер считается в браузере, текст никуда не отправляется.

- `scan-rules.js`: правила сканера. **Не править руками**: генерирует `scripts/export_web_rules.py` из Python-правил, гейт `--check` в CI.
- `scan.js`: движок сканера (порт `humanizer_metrics`), `humanizerScan()` и `humanizerIsRussian()`. Паритет с Python: `scripts/test_web_parity.py`.
- `facts.js`: браузерный факт-замок для сравнения «было и стало».
- `hints.js`: подсказки к находкам, причины штрафов, строка «что дальше». Общий модуль для главной, страницы-инструмента и расширения.
- `audit.js`: интерфейс страницы-инструмента.
- `workshop.ts`: интерфейс главной, исходник. `workshop.js` собирается из него `tsc` по `tsconfig.json`; паритет проверяет `scripts/check_workshop_build.py` в CI.

Расширение Chrome в `extension/` везёт копии `scan.js`, `scan-rules.js`, `facts.js`, `hints.js` в `extension/vendor/`; их кладёт и сверяет `scripts/build_extension.py`.

## Стили и шрифты

- `workshop.css`: главная. `style.css`: статьи и страница-инструмент.
- Шрифты в `assets/fonts/`: Alumni Sans и Onest (variable), JetBrains Mono; лицензии OFL рядом.
- Картинки в `assets/`: обложка главной в трёх ширинах для `srcset` (800, 1200, 1672), фоны мастерской, `social-preview.jpg` для превью ссылок.

## Локальный просмотр и сборка

```
cd docs && python3 -m http.server 8000      # http://localhost:8000
cd docs && npm ci                            # TypeScript для workshop.ts
python scripts/check_workshop_build.py --write   # пересобрать workshop.js
```

## Принципы

- Чистый HTML5 + один CSS, без фреймворков и внешних JS/CDN.
- В каждой странице: уникальные title и description, canonical, Open Graph, Twitter card, JSON-LD.
- Тексты без длинного тире и канцелярита: `scripts/self_scan.py` проверяет страницы и строки скриптов.
- Честная рамка: балл это повод для правки, а не вердикт об авторстве. Сайт не обещает обход детекторов.
