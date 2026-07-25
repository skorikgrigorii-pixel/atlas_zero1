ATLAS ZERO — PHASE 9: PRODUCTION CLEANUP

Цель:
- исключить из финального аудита установочные пакеты, архивы, workspace и сам аудитор;
- перенести три старых теста RC1 в tests\legacy_rc1;
- убрать оставшиеся пользовательские маркировки RC1 из основных управляющих файлов;
- удалить UTF-8 BOM из активных Python-файлов;
- проверить отсутствие активных импортов RC1 в src\az_enterprise.

Установка:

1. Распакуйте atlas_zero_phase9_production_cleanup в корень репозитория atlas_zero1.

2. Выполните в PowerShell:

$env:PYTHONPATH = "$PWD\src"

python .\atlas_zero_phase9_production_cleanup\APPLY_PHASE9.py
python .\atlas_zero_phase9_production_cleanup\VERIFY_PHASE9.py

3. После успешной проверки повторите аудит:

python .\atlas_zero_rc2_final_audit\RUN_RC2_FINAL_AUDIT.py

Резервная копия:
workspace\backups\phase9_YYYYMMDD_HHMMSS

Отчёт:
workspace\audits\phase9_cleanup_report.json
