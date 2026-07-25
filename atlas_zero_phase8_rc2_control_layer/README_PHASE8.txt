ATLAS ZERO — PHASE 8: RC2 CONTROL LAYER MIGRATION

Распакуйте папку в корень репозитория atlas_zero1.

Запуск:

$env:PYTHONPATH = "$PWD\src"

python .\atlas_zero_phase8_rc2_control_layer\APPLY_PHASE8.py
python .\atlas_zero_phase8_rc2_control_layer\VERIFY_PHASE8.py

Изменения:

- удаление RenderEngineRC1 из cli.py;
- удаление команды render-rc1;
- video_ready переводится на TimelineEngineRC2 и RenderEngineRC2;
- RC1CompletionPlanner заменяется на RC2ReadinessPlanner;
- интерфейс переводится на маркировку RC2;
- добавляется единый RC2ControlLayer;
- создаются автоматические резервные копии.

Резервная копия:

workspace\backups\phase8_YYYYMMDD_HHMMSS
