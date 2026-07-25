ATLAS ZERO — RC2 PRODUCTION AUDIT

Этот аудит НЕ изменяет файлы проекта.

Он отвечает на четыре вопроса:

1. Загружается ли архитектура RC2?
2. Проходит ли runtime RC2 и его тесты?
3. Созданы ли итоговый фильм и основные производственные артефакты?
4. Можно ли удалить RC1 без нарушения активной системы?

УСТАНОВКА

Распакуйте папку:

atlas_zero_rc2_production_audit

в корень репозитория atlas_zero1.

ЗАПУСК В POWERSHELL

$env:PYTHONPATH = "$PWD\src"
python .\atlas_zero_rc2_production_audit\RUN_RC2_PRODUCTION_AUDIT.py

РЕЗУЛЬТАТЫ

workspace\audits\rc2_production\rc2_production_audit.json
workspace\audits\rc2_production\rc2_production_audit.md

КОД ВОЗВРАТА

0 — RC2 получила 100/100, все четыре проверки пройдены.
2 — одна или несколько проверок не пройдены.

ВАЖНО

Код 2 не означает поломку самого аудитора.
Он означает, что аудит обнаружил незавершённую часть RC2 либо зависимость от RC1.
