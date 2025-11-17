# 🚀 Project-0 - Professional AI MVP Platform

> **Generate REAL production-ready MVPs with Node.js, Database & Beautiful UI**

## ✨ Что это?

**Project-0** - это профессиональная AI-платформа на базе **Ollama GLM-4.6:cloud**, которая генерирует **РЕАЛЬНЫЕ, РАБОТАЮЩИЕ MVP** с полным бэкендом, базой данных и современным UI.

### Ключевые возможности:

- 🎯 **Node.js Backend** - Express.js сервер с роутингом и middleware
- 💾 **База данных** - SQLite или MongoDB с моделями
- 🎨 **Профессиональный UI** - с официальными цветовыми схемами
- ⚛️ **Modern Frontend** - HTML5 + Tailwind CSS + JavaScript/React
- 📝 **Множество файлов** - полная структура проекта
- 🔐 **Production-ready** - с error handling, validation, security
- 📖 **Markdown документация** - красиво оформленная
- 🎨 **4 цветовые темы** - Professional Blue, Success Green, Modern Purple, Warm Orange

## 🚀 Быстрый старт

```bash
# Запустите платформу
python project0.py

# Откройте браузер
http://localhost:8000
```

## 🎨 Официальные цветовые схемы

### 1. Professional Blue (по умолчанию)
```css
Primary: #2563eb    /* blue-600 */
Secondary: #3b82f6  /* blue-500 */
Accent: #60a5fa     /* blue-400 */
Dark: #1e40af       /* blue-800 */
```

### 2. Success Green
```css
Primary: #10b981    /* emerald-500 */
Secondary: #34d399  /* emerald-400 */
Accent: #6ee7b7     /* emerald-300 */
Dark: #059669       /* emerald-600 */
```

### 3. Modern Purple
```css
Primary: #8b5cf6    /* violet-500 */
Secondary: #a78bfa  /* violet-400 */
Accent: #c4b5fd     /* violet-300 */
Dark: #7c3aed       /* violet-600 */
```

### 4. Warm Orange
```css
Primary: #f59e0b    /* amber-500 */
Secondary: #fbbf24  /* amber-400 */
Accent: #fcd34d     /* amber-300 */
Dark: #d97706       /* amber-600 */
```

## 💡 Что генерирует AI?

### Backend (Node.js + Express):
```
backend/
├── package.json          # Dependencies (express, cors, sqlite3, etc.)
├── server.js            # Main Express server
├── database.js          # Database connection & models
├── .env.example         # Environment variables template
└── routes/              # API endpoints
```

### Frontend:
```
frontend/
├── index.html           # Main HTML with Tailwind CSS
├── app.js              # Frontend logic & API calls
└── styles.css          # Additional custom styles (if needed)
```

### Documentation:
```
README.md               # Complete setup & deployment guide
```

## 🏗️ Архитектура MVP

**AI генерирует полный стек:**

1. **Backend:**
   - Express.js сервер на порту 3000
   - CORS middleware
   - Body parser
   - Error handling
   - Database connection (SQLite/MongoDB)
   - RESTful API endpoints
   - Data validation
   - Security best practices

2. **Database:**
   - Schema/Models определения
   - Миграции (если нужны)
   - Seed data (примеры)
   - CRUD операции
   - Индексы и оптимизация

3. **Frontend:**
   - Semantic HTML5
   - Tailwind CSS styling
   - Responsive design
   - JavaScript/React компоненты
   - API integration
   - Form validation
   - Error handling
   - Loading states

## 📖 Примеры использования

### Пример 1: Task Manager MVP

**Запрос:**
```
Create a task management platform with user authentication, 
SQLite database, and real-time updates
```

**AI создаёт:**
```
✓ backend/server.js - Express server with auth
✓ backend/database.js - SQLite models (Users, Tasks)
✓ backend/package.json - All dependencies
✓ frontend/index.html - Beautiful UI with task list
✓ frontend/app.js - CRUD operations
✓ README.md - Setup instructions
```

### Пример 2: Blog Platform

**Запрос:**
```
Build a blog platform with user accounts, post creation, 
comments, and categories using MongoDB
```

**AI создаёт:**
```
✓ backend/server.js - Express + MongoDB
✓ backend/models/ - User, Post, Comment models
✓ backend/routes/ - API endpoints
✓ frontend/index.html - Blog UI with editor
✓ README.md - Deployment guide
```

## 🎨 UI Стиль

### Современный профессиональный дизайн:

- **Шрифт:** Inter (Google Fonts)
- **Layout:** Split-screen (50/50)
- **Цвета:** CSS Variables для тем
- **Анимации:** Smooth transitions, cubic-bezier
- **Компоненты:**
  - Gradient buttons with shadows
  - Hover effects with transform
  - Professional spacing (Tailwind-like)
  - Beautiful typography
  - Card-based layouts
  - Responsive grid systems

### Темная тема:
```css
--bg-primary: #000000
--bg-secondary: #0a0a0a
--bg-tertiary: #1a1a1a
--border-color: #2a2a2a
--text-primary: #ffffff
--text-secondary: #a0a0a0
```

## 📦 Структура файла

**`project0.py`** (1265 строк, 44 KB)

Включает:
- Enhanced System Prompt для реальных MVP
- Node.js + Express генерация
- Database integration (SQLite/MongoDB)
- Multiple file extraction
- Professional UI с 4 цветовыми темами
- Enhanced markdown rendering
- File viewer в preview панели
- Download функция для всех файлов

## 🛠️ Требования

1. **Python 3.8+**
   ```bash
   pip install -r requirements.txt
   ```

2. **Ollama с GLM-4.6**
   ```bash
   ollama serve
   ollama pull glm-4.6:cloud
   ```

## 🎯 Workflow

1. **Опишите идею MVP** (можно неполную):
   ```
   "Создай платформу для управления задачами с аутентификацией"
   ```

2. **AI анализирует и дополняет:**
   - Определяет нужные технологии
   - Выбирает БД (SQLite/MongoDB)
   - Планирует архитектуру
   - Выбирает цветовую схему

3. **Генерирует полный стек:**
   - Backend: Node.js + Express
   - Database: Models + Connection
   - Frontend: HTML + Tailwind + JS
   - Documentation: README

4. **Показывает файлы:**
   - Все файлы в preview панели
   - Можно развернуть/свернуть
   - Синтаксис подсветка
   - Кнопка Download All

## 💻 API Endpoints

### POST `/api/generate`
Генерация MVP

**Request:**
```json
{
  "idea": "Create a task manager with auth..."
}
```

**Response:** Server-Sent Events
```
data: {"type": "status", "content": "🧠 Analyzing..."}
data: {"type": "status", "content": "🏗️ Designing architecture..."}
data: {"type": "status", "content": "⚡ Generating backend..."}
data: {"type": "content", "content": "## 📋 Project Overview..."}
data: {"type": "done", "mvp_id": "123", "file_count": 6}
```

### GET `/api/mvp/{mvp_id}`
Получить все файлы MVP

**Response:**
```json
{
  "files": {
    "backend/server.js": "...",
    "backend/package.json": "...",
    "frontend/index.html": "..."
  },
  "markdown": "...",
  "idea": "...",
  "timestamp": "..."
}
```

## 🎨 Интерфейс

```
┌─────────────────────────┬─────────────────────────┐
│   CHAT PANEL (50%)      │   FILES PANEL (50%)     │
│                         │                         │
│  Project-0 Logo         │  Project Files Header   │
│  [AI Ready Badge]       │  [Download All Button]  │
├─────────────────────────┼─────────────────────────┤
│                         │                         │
│  Welcome Screen:        │  Placeholder:           │
│  • Professional logo    │  "Ready to Build"       │
│  • Modern title         │                         │
│  • 4 example ideas      │  ↓ After generation:    │
│                         │                         │
│  Chat Messages:         │  File List:             │
│  • User requests        │  • backend/server.js    │
│  • AI responses         │  • backend/package.json │
│  • Enhanced markdown    │  • frontend/index.html  │
│  • Status indicators    │  • README.md            │
│                         │  (collapsible)          │
├─────────────────────────┤                         │
│  Enhanced Textarea      │                         │
│  [⚡ Generate Button]   │                         │
└─────────────────────────┴─────────────────────────┘
```

## 🌟 Улучшения UI

### Что нового:

1. **Professional Design:**
   - Inter font (Google Fonts)
   - CSS Variables для тем
   - Smooth animations
   - Gradient buttons
   - Box shadows

2. **Enhanced Markdown:**
   - Better typography
   - Code blocks с подсветкой
   - Headers с borders
   - Blockquotes
   - Lists

3. **File Viewer:**
   - Collapsible file items
   - Syntax highlighting
   - Copy buttons (TODO)
   - Download all function

4. **Color Themes:**
   - 4 официальные схемы
   - CSS variables
   - Easy customization

## 🚀 Production Deployment

### Setup Script:
```bash
# 1. Install Node.js dependencies
cd backend
npm install

# 2. Setup environment
cp .env.example .env
nano .env  # Edit variables

# 3. Initialize database
node database.js

# 4. Start server
npm start
```

### Docker:
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY backend/ ./
RUN npm install
EXPOSE 3000
CMD ["node", "server.js"]
```

## 📝 Что генерируется

Для каждого MVP AI создаёт:

- ✅ `backend/package.json` - полный с зависимостями
- ✅ `backend/server.js` - Express server
- ✅ `backend/database.js` - DB connection & models
- ✅ `backend/.env.example` - environment template
- ✅ `frontend/index.html` - полный UI
- ✅ `frontend/app.js` - логика (опционально)
- ✅ `README.md` - setup instructions

## 🎯 Roadmap

- [x] Node.js backend generation
- [x] Database integration
- [x] Professional UI
- [x] Color schemes
- [x] Enhanced markdown
- [x] Multiple files
- [ ] Copy to clipboard для кода
- [ ] Project templates
- [ ] Deploy integration
- [ ] ZIP download

## 📄 Лицензия

MIT License

---

**Made with ❤️ for professional developers**

От идеи до production-ready MVP за минуты! 🚀
