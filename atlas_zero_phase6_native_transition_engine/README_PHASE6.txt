ATLAS ZERO — Phase 6 Native Transition Engine

УСТАНОВКА

Архив можно распаковать:
- прямо в корень репозитория; или
- в отдельную папку внутри репозитория.

Установщик сам найдёт:
src\az_enterprise\core

Из корня репозитория запустите:

python .\atlas_zero_phase6_native_transition_engine\APPLY_PHASE6.py

Если содержимое архива распаковано прямо в корень:

python .\APPLY_PHASE6.py


ПРОВЕРКА ИМПОРТОВ

$env:PYTHONPATH = "$PWD\src"

python -c "from az_enterprise.core.transition_engine_rc2 import TransitionEngineRC2, FFmpegTransitionGraphBuilder; from az_enterprise.core.visual_renderer_rc2 import VisualRendererRC2; from az_enterprise.core.render_engine_rc2 import RenderEngineRC2; print('PHASE 6 OK')"


ПРОВЕРКА ТЕСТОВ

python -m pytest .\tests\test_transition_engine_rc2.py -q


РЕАЛИЗОВАНО

- cut / hard_cut
- crossfade
- dissolve
- fade
- fade_black / fade_white
- dip_to_black / dip_to_white
- wipe_left / wipe_right / wipe_up / wipe_down
- slide_left / slide_right / slide_up / slide_down
- push_left / push_right / push_up / push_down
- circle_open / circle_close
- pixelize
- radial
- smooth_left / smooth_right / smooth_up / smooth_down
- zoom_in / zoom_out
- custom fallback

Архитектура:
Timeline -> CameraMotionEngine -> segment render -> TransitionEngineRC2
-> FFmpeg xfade groups -> hard-cut concat between groups -> visual_master_rc2.mp4

Резервная копия создаётся автоматически:
workspace\backups\phase6_transition_engine_<timestamp>
