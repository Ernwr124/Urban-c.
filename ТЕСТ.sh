#!/bin/bash

# Быстрый тест HR Agent

echo "🧪 Тестирование HR Agent..."
echo ""

# Проверка файлов
echo "📁 Проверка файлов..."
files=("hr.py" "ЗАПУСК.sh" "README_HR_AGENT.md" "ГОТОВО.txt")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file - НЕ НАЙДЕН!"
    fi
done
echo ""

# Проверка синтаксиса Python
echo "🐍 Проверка синтаксиса Python..."
if python3 -m py_compile hr.py 2>/dev/null; then
    echo "  ✅ Синтаксис правильный"
else
    echo "  ❌ Ошибка синтаксиса!"
    exit 1
fi
echo ""

# Подсчет строк
echo "📊 Статистика кода..."
echo "  📄 Строк в hr.py: $(wc -l < hr.py)"
echo ""

# Проверка Ollama
echo "🤖 Проверка Ollama..."
if command -v ollama &> /dev/null; then
    echo "  ✅ Ollama установлен"
    if ollama list | grep -q "gpt-oss:20b-cloud"; then
        echo "  ✅ Модель gpt-oss:20b-cloud загружена"
    else
        echo "  ⚠️  Модель не загружена. Запустите: ollama pull gpt-oss:20b-cloud"
    fi
else
    echo "  ⚠️  Ollama не установлен"
fi
echo ""

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
deps=("fastapi" "uvicorn" "sqlalchemy" "httpx")
for dep in "${deps[@]}"; do
    if python3 -c "import $dep" 2>/dev/null; then
        echo "  ✅ $dep"
    else
        echo "  ⚠️  $dep - не установлен"
    fi
done
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Тестирование завершено!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🚀 Для запуска используйте:"
echo "   ./ЗАПУСК.sh"
echo ""
