#!/bin/bash

# Скрипт запуска для Render.com
echo "🚀 Запуск AutoBaza API на Render.com..."

# Создаем директорию для логов если её нет
mkdir -p logs

# Запускаем приложение с Gunicorn
exec gunicorn main:app \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --preload \
    --log-level info \
    --access-logfile - \
    --error-logfile - 