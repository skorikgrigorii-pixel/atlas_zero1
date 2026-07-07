# ATLAS ZERO Franklin — операторский runbook

## 1. Подготовка
**Действие:** Запустить start_pipeline.bat

**Результат:** Созданы exports/franklin и отчёты

**Артефакт:** `start_pipeline.bat`

## 2. Проверка
**Действие:** Открыть preflight_report.html

**Результат:** Понятны блокеры рабочей станции

**Артефакт:** `workspace/exports/franklin/preflight_report.html`

## 3. Материалы
**Действие:** Открыть visual_contact_sheet.jpg и визуальный_анализ.csv

**Результат:** Проверена визуальная библиотека

**Артефакт:** `workspace/exports/franklin/визуальный_анализ.csv`

## 4. Монтаж
**Действие:** Открыть timeline_viewer.html

**Результат:** Понятен видеоряд 165 шотов

**Артефакт:** `workspace/exports/franklin/timeline_viewer.html`

## 5. CapCut
**Действие:** Открыть capcut_guide.md

**Результат:** Понятны шаги импорта в CapCut

**Артефакт:** `workspace/exports/franklin/capcut_guide.md`

## 6. Недостающее
**Действие:** Открыть missing_prioritized.csv

**Результат:** Понятно, какие кадры генерировать первыми

**Артефакт:** `workspace/exports/franklin/missing_prioritized.csv`

## 7. Контроль
**Действие:** Открыть franklin_acceptance.html

**Результат:** Проверена локальная готовность Franklin

**Артефакт:** `workspace/exports/franklin/franklin_acceptance.html`

## 8. API
**Действие:** Заполнить .env и проверить api_готовность.json

**Результат:** Интеграции подготовлены к live-режиму

**Артефакт:** `.env.example`

## 9. Финал
**Действие:** После сборки в CapCut экспортировать preview и обновить QC

**Результат:** Фильм готовится к публикации

**Артефакт:** `06_Export`
