ATLAS ZERO — RC2 FINALIZATION

Пакет выполняет целевую финализацию RC2:

1. Создаёт резервную копию изменяемых файлов.
2. Добавляет ReleaseGate.evaluate_release().
3. Переводит pipeline_runtime.py на evaluate_release().
4. Сохраняет evaluate_rc1() только как временный совместимый alias.
5. Переносит RC1-тесты в tests/legacy_rc1.
6. Переносит инструменты, напрямую использующие MovieRuntimeRC1 и RenderEngineRC1,
   в tools/legacy_rc1.
7. Обновляет RC2_PRODUCTION_AUDIT, чтобы архивные инструменты не считались
   активными production-зависимостями.
8. Не удаляет core RC1-файлы автоматически.

УСТАНОВКА

Распакуйте папку atlas_zero_rc2_finalization в корень репозитория atlas_zero1.

ЗАПУСК

$env:PYTHONPATH = "$PWD\src"
python .\atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py
python .\atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py
python .\atlas_zero_rc2_production_audit\RUN_RC2_PRODUCTION_AUDIT.py

ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

Architecture loads: YES
RC2 runtime passes: YES
Final artifacts exist: YES
Safe to remove RC1: YES
Score: 100/100

РЕЗЕРВНАЯ КОПИЯ

workspace/backups/rc2_finalization_<timestamp>
