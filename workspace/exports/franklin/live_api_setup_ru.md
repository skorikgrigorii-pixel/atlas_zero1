# Настройка live API для ATLAS ZERO Enterprise RC1

По умолчанию ОС не делает платные запросы. Для live-режима нужны переменные окружения:

## Leonardo
ENV: `LEONARDO_API_KEY`
Действие: generate_image
Статус: missing

## ElevenLabs
ENV: `ELEVENLABS_API_KEY`
Действие: text_to_speech
Статус: missing

## OpenAI
ENV: `OPENAI_API_KEY`
Действие: vision_and_reasoning
Статус: missing

## YouTube
ENV: `YOUTUBE_OAUTH_TOKEN`
Действие: analytics_and_upload
Статус: missing

## Suno
ENV: `SUNO_API_KEY`
Действие: music_generation
Статус: missing

## Canva
ENV: `CANVA_API_KEY`
Действие: design_assets
Статус: missing

Для включения live-проверок установите `AZ_ENABLE_LIVE_CALLS=1`. Платные генерации всё равно требуют отдельного подтверждения allow_paid=True в коде адаптера.