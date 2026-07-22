ATLAS ZERO — Phase 7 Native Audio Composer

УСТАНОВКА

Распакуйте архив в корень репозитория и выполните:

python .\atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py

Если содержимое архива распаковано прямо в корень:

python .\APPLY_PHASE7.py


ПРОВЕРКА ИМПОРТОВ

$env:PYTHONPATH = "$PWD\src"

python -c "from az_enterprise.core.audio_composer_rc2 import NativeAudioComposerRC2; from az_enterprise.core.audio_renderer_rc2 import AudioRendererRC2; from az_enterprise.core.mux_engine_rc2 import MuxEngineRC2; from az_enterprise.core.render_engine_rc2 import RenderEngineRC2; print('PHASE 7 OK')"


ТЕСТЫ

Copy-Item .\atlas_zero_phase7_native_audio_composer\test_audio_phase7_rc2.py .\tests\test_audio_phase7_rc2.py -Force

python -m pytest .\tests\test_audio_phase7_rc2.py -q


РЕАЛИЗОВАНО

- Native audio timeline
- Voice / music / SFX tracks
- Multi-track mixing
- Music looping
- Fade in / fade out
- Automatic ducking through sidechain compression
- EBU R128 loudness normalization
- True-peak limiting
- AAC audio master
- Final video/audio mux
- audio_report_rc2.json
- mux_report_rc2.json
- final_movie_rc2.mp4

Резервная копия:
workspace\backups\phase7_native_audio_<timestamp>
