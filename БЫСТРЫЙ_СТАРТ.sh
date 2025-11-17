#!/bin/bash

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           🚀 HR AGENT - БЫСТРЫЙ СТАРТ                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "⚠️  ВНИМАНИЕ: Удаляю старую базу данных..."
rm -f hr_agent.db
echo "✅ Старая БД удалена"
echo ""

echo "📦 Проверка зависимостей..."
pip install -q fastapi uvicorn sqlalchemy pydantic httpx PyPDF2 python-docx 2>/dev/null
echo "✅ Зависимости установлены"
echo ""

echo "🗄️  Создание директорий для загрузок..."
mkdir -p uploads/avatars uploads/resumes uploads/videos uploads/certificates uploads/portfolio
echo "✅ Директории созданы"
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           ✅ ВСЕ ГОТОВО! ЗАПУСКАЮ ПЛАТФОРМУ...                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "📡 Сервер будет доступен по адресу: http://localhost:8000"
echo "🔑 Зарегистрируйтесь как HR-специалист или кандидат"
echo ""
echo "⏸️  Для остановки нажмите Ctrl+C"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 hr_platform.py
