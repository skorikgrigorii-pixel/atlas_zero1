ATLAS ZERO — RC2 Final Audit + End-to-End Integration Test

1. Распакуйте папку atlas_zero_rc2_final_audit в корень репозитория.

2. Запустите:

$env:PYTHONPATH = "$PWD\src"

python .\atlas_zero_rc2_final_audit\RUN_RC2_FINAL_AUDIT.py

Скрипт выполнит:

- поиск всех RC1 импортов;
- поиск наследования от RC1;
- поиск строковых ссылок RC1;
- проверку обязательных RC2-модулей;
- импортный smoke test;
- повторный запуск тестов Phase 6 и Phase 7;
- создание dependency_audit_rc2.json;
- создание dependency_report.md;
- генерацию тестовых видео/аудиоматериалов через FFmpeg;
- полный тест NativeAudioComposerRC2;
- создание финального тестового final_movie_rc2.mp4;
- проверку наличия аудио и видео через FFprobe.

Результаты:

workspace\audits\rc2_final\dependency_audit_rc2.json
workspace\audits\rc2_final\dependency_report.md

workspace\integration_tests\rc2_e2e\final_movie_rc2.mp4
workspace\integration_tests\rc2_e2e\rc2_e2e_report.json

Возможные статусы:

READY_FOR_HOGUERAS
READY_WITH_WARNINGS
NOT_READY_REQUIRES_FIXES
BLOCKED

Важно:
Ссылки RC1 внутри архивов workspace\backups исключены из проверки.
