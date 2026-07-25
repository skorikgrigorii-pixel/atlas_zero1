ATLAS ZERO — Director AI 2.5

Этот пакет не создаёт нового Director AI.

Он:
- добавляет внутренний PostProductionQualityRC2;
- подключает его к существующему DirectorAIRuntime;
- подключает обязательные проверки к QualityGateRC2;
- добавляет тесты.

Порядок:

1. Распакуйте архив.
2. Скопируйте три файла в корень репозитория atlas_zero1.
3. Создайте ветку:

git checkout -b feature/director-ai-2.5-postproduction

4. Выполните:

python .\apply_director_ai_25.py

5. Запустите тесты:

python -m unittest tests.test_postproduction_quality_rc2 -v
python -m unittest tests.test_director_ai_alpha25 -v

6. Затем полный набор:

python -m unittest discover -s tests -v
