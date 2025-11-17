# 🚀 Project-0 - Professional AI MVP Platform

> **The Complete Full-Stack MVP Generator with Authentication & Project Management**

## ✨ What's New - Full Platform!

**Project-0** is now a complete professional platform with:

- 🎨 **Beautiful Landing Page** with logo
- 🔐 **User Authentication** (Register & Login)
- 📊 **Project Dashboard** with project list
- 🤖 **AI Chat** with project context memory
- 👁️ **Live Preview** without running servers
- 📦 **ZIP Download** with auto-run scripts
- 🇬🇧 **English Interface**

## 🎯 What It Does

### Landing Page
- Beautiful hero section
- Feature showcase
- Professional design
- "Try It Now" CTA

### Authentication
- **Register**: Name, Email, Password (encrypted SHA-256)
- **Login**: Email, Password
- Secure session management
- Persistent login (localStorage)

### Dashboard
- View all your projects
- Create new projects
- Click to open/edit projects
- Project metadata (created date, description)

### AI Chat Interface
- **Split-screen**: Chat (55%) + Preview (45%)
- **Project Context**: AI remembers previous conversations
- **Live Preview**: See results instantly in iframe
- **File Viewer**: Collapsible file list
- **Download**: Get complete project as ZIP

### AI Capabilities
- **Context Memory**: Remembers project requirements
- **Incremental Updates**: Modify existing code
- **Full-Stack Generation**: Backend + Frontend + DB
- **Production-Ready**: Complete, working code

## 🚀 Quick Start

```bash
# Run the platform
python project0.py

# Open browser
http://localhost:8000
```

## 📖 User Flow

### 1. Landing Page
```
Landing → "Try It Now" → Auth
```

### 2. Sign Up
```
Name: John Doe
Email: john@example.com
Password: ******
→ Creates account → Auto login → Dashboard
```

### 3. Dashboard
```
Projects List (empty at first)
→ Click "New Project"
```

### 4. Create Project
```
Project Name: Task Manager
Description: Build a task management app with user auth, 
SQLite database, and modern UI

→ Click "Create Project" → Opens Chat
```

### 5. Chat with AI
```
AI: "What would you like to build?"

You: "Create a complete task manager with:
- User authentication
- SQLite database
- CRUD operations for tasks
- Beautiful UI with Tailwind CSS
- Responsive design"

AI: *Generates complete project*
→ Shows files in preview
→ Live preview in iframe (if HTML available)
```

### 6. Edit/Modify
```
You: "Add a dark mode toggle to the UI"

AI: *Remembers project context*
     *Updates existing files*
     *Maintains code consistency*
```

### 7. Download
```
Click "Download ZIP"
→ Gets project-name.zip
→ Contains:
   backend/
   ├── server.js
   ├── package.json
   ├── database.js
   └── .env.example
   frontend/
   └── index.html
   start.sh   ← Run this!
   start.bat  ← Windows version
```

### 8. Deploy
```bash
unzip project-name.zip
cd project-name
chmod +x start.sh
./start.sh

# Or manually:
cd backend
npm install
npm start
```

## 🎨 Features Detail

### Landing Page
- Hero section with gradient title
- 4 feature cards:
  - ⚡ Lightning Fast
  - 🏗️ Full-Stack Ready
  - 🎨 Beautiful UI
  - 🔐 Production Ready

### Authentication System
- **Secure**: SHA-256 password hashing
- **SQLite Database**: Users, Projects, Sessions tables
- **Session Management**: Token-based auth
- **Persistent**: localStorage for auto-login

### Dashboard
- **Project Cards**: Grid layout, hover effects
- **Create Button**: Modal form for new projects
- **User Info**: Avatar, name, logout button
- **Responsive**: Works on all devices

### Chat Interface
```
┌─────────────────────────┬──────────────────────┐
│ SIDEBAR │  CHAT (55%)    │   PREVIEW (45%)      │
├─────────┼────────────────┼──────────────────────┤
│         │                │                      │
│ Back to │  Messages      │  Live Preview        │
│ Project │  • User        │  (iframe or files)   │
│         │  • AI          │                      │
│         │                │  [Download ZIP]      │
│         │  Input Area    │                      │
│         │  [Send ⚡]     │                      │
└─────────┴────────────────┴──────────────────────┘
```

### AI Context Memory
```python
# AI remembers:
- Project description
- Previous requests
- Generated files
- User modifications

# Example conversation:
User: "Create a blog platform"
AI: *generates complete MVP*

User: "Add categories to posts"
AI: *remembers blog context*
     *updates existing code*
     *adds category feature*
```

### Live Preview
- **iframe**: Shows `frontend/index.html` live
- **No Server**: Runs directly in browser
- **Interactive**: Full functionality preview
- **File List**: If no HTML, shows collapsible files

### ZIP Download
```
project-name.zip
├── backend/
│   ├── server.js
│   ├── package.json
│   ├── database.js
│   └── .env.example
├── frontend/
│   └── index.html
├── README.md
├── start.sh      ← chmod +x && ./start.sh
└── start.bat     ← Windows: double-click
```

## 💻 Technical Stack

### Platform Backend (Python)
- **FastAPI**: Web framework
- **SQLite**: Database (project0.db)
- **Ollama**: AI inference
- **Sessions**: Token-based auth

### Generated Backend (Node.js)
- **Express**: Web framework
- **SQLite/MongoDB**: Database
- **CORS**: Cross-origin support
- **dotenv**: Environment variables

### Generated Frontend
- **HTML5**: Semantic markup
- **Tailwind CSS**: Utility-first styling
- **JavaScript**: Vanilla or React
- **Responsive**: Mobile-first design

## 🗄️ Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP
);
```

### Projects Table
```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    name TEXT NOT NULL,
    description TEXT,
    context TEXT,          -- Conversation history
    files TEXT,            -- JSON of generated files
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### Sessions Table
```sql
CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER,
    created_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## 🔐 Security

- ✅ Password hashing (SHA-256)
- ✅ SQL injection protection (parameterized queries)
- ✅ Session tokens (32-byte secure random)
- ✅ CORS configured
- ✅ Input validation
- ✅ XSS prevention (escapeHtml)

## 🎨 UI/UX

### Design System
- **Font**: Inter (Google Fonts)
- **Colors**: 
  - Primary: #2563eb (blue)
  - Success: #10b981 (green)
  - Error: #ef4444 (red)
- **Spacing**: 8px base grid
- **Radius**: 8-20px rounded corners
- **Shadows**: Layered, colored shadows
- **Animations**: Cubic-bezier, smooth

### Responsive
- Mobile: 320px+
- Tablet: 768px+
- Desktop: 1024px+

## 📝 API Endpoints

### Authentication
```
POST /api/register
POST /api/login
```

### Projects
```
GET  /api/projects?token=xxx
POST /api/projects?token=xxx
GET  /api/project/:id?token=xxx
```

### Chat
```
POST /api/chat?token=xxx
```

### Download
```
GET /api/download/:id?token=xxx
```

## 🔧 Configuration

File: `project0.py`

```python
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "glm-4.6:cloud"
DB_FILE = "project0.db"
```

## 🚀 Deployment

### Development
```bash
python project0.py
```

### Production
```bash
# With Gunicorn
pip install gunicorn
gunicorn project0:app -w 4 -k uvicorn.workers.UvicornWorker

# With Docker
docker build -t project0 .
docker run -p 8000:8000 project0
```

## 📊 File Size

```
project0.py: 1692 lines, 56 KB
Everything in ONE file! ✅
```

## ✨ What's Included

- ✅ Landing page with hero
- ✅ Authentication system
- ✅ User dashboard
- ✅ Project management
- ✅ AI chat with context
- ✅ Live preview
- ✅ File viewer
- ✅ ZIP download
- ✅ Auto-run scripts
- ✅ Responsive design
- ✅ Dark theme
- ✅ Professional UI
- ✅ Security built-in
- ✅ All in English

## 🎯 Example Projects

### Task Manager
```
Name: Task Manager Pro
Description: Build a task management app with user authentication, 
SQLite database, categories, due dates, and dark mode

AI Generates:
→ Express backend with JWT auth
→ SQLite database (users, tasks, categories)
→ CRUD API endpoints
→ Beautiful Tailwind UI
→ Dark mode toggle
→ Responsive design
```

### Blog Platform
```
Name: My Blog
Description: Create a blog platform with posts, comments, 
categories, and rich text editor

AI Generates:
→ Node.js + Express backend
→ MongoDB database
→ Post/Comment models
→ Rich text editor
→ Category system
→ Modern UI
```

## 🎉 Ready to Use!

```bash
# 1. Start platform
python project0.py

# 2. Open browser
http://localhost:8000

# 3. Sign up / Login

# 4. Create project

# 5. Chat with AI

# 6. Download ZIP

# 7. Run project
./start.sh
```

## 📄 License

MIT License - Build amazing things!

---

**Made with ❤️ for rapid MVP development**

Transform ideas into production-ready applications! 🚀
