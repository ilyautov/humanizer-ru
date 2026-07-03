# Сайт humanizer-ru (GitHub Pages)

SEO/GEO-сайт проекта. Статический HTML, без сборки и без Jekyll.
Адрес: https://humanizer-ru.aifrontier.tech/

## Как включить GitHub Pages

1. Открой репозиторий на GitHub → **Settings** → **Pages**.
2. В разделе **Build and deployment** → **Source** выбери **Deploy from a branch**.
3. Branch: `main`, папка: `/docs`. Сохрани.
4. Через минуту сайт будет на https://humanizer-ru.aifrontier.tech/

## Структура

- `index.html` — лендинг.
- `ai-detektory-na-russkom.html` — работают ли AI-детекторы на русском (GEO-актив).
- `kak-ubrat-sledy-neyroseti.html` — практический гайд.
- `52-priznaka-ai-teksta.html` — справочник маркеров AI-текста.
- `antiplagiat-i-neyroset.html` — антиплагиат против AI-детектора.
- `style.css` — общий стиль.
- `sitemap.xml`, `robots.txt` — для поисковиков.

## Локальный просмотр

```
cd docs && python3 -m http.server 8000
```

Открой http://localhost:8000

## Принципы

- Чистый HTML5 + один CSS, без фреймворков и внешних JS/CDN.
- В каждой странице: уникальные title/description, canonical, Open Graph, Twitter card, JSON-LD.
- Тексты без длинных тире и канцелярита — сайт сам образец того, что делает скилл.
