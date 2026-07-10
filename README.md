# ATLAS ZERO Enterprise RC1 Alpha 2.5 — Director AI

Эта версия продолжает развитие текущей ОС, не начинает новый проект.

## Главное в Alpha 2.5

- **Director AI 2.5**
  - интеграция с Story Engine;
  - автоматический анализ полноты проекта по сценам и шотам;
  - обнаружение недостающих материалов;
  - автоматическое создание production tasks и operator tasks;
  - связь с существующим dashboard и pipeline;
  - сохранение обратной совместимости с текущей архитектурой.

- **Director AI Runtime 2.4**
  - анализ качества проекта;
  - анализ покрытия сцен;
  - поиск повторов материалов;
  - оценка технического качества по CV Runtime;
  - принятие решений по недостающим материалам;
  - автоматическое создание задач.

- **Новые таблицы SQLite**
  - `director_quality_reports`
  - `director_issues`
  - `director_tasks`
  - `director_decision_matrix`

- **Новые экспорты**
  - `director_ai_2_4.html`
  - `director_ai_2_4_report.json`
  - `director_tasks.csv`
  - `director_issues.csv`
  - `director_decision_matrix.csv`

- **Интеграция в конвейер**
  - этап `director_ai_2_4` запускается после Story Engine 2.3;
  - задачи генерации создаются в `api_jobs`;
  - если Live API не подключены, задачи получают статус `waiting_api`.

## Запуск

Распаковать в короткий путь Windows:

`C:\AZ\ATLAS_ZERO_RC1_ALPHA_2_4`

Запустить:

`start_os.bat`

В ОС нажать:

`Запустить конвейер`

## Проверка

Внутренний smoke test пройден: полный Franklin pipeline завершается до экспортов.
