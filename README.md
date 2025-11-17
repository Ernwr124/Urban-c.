# 🚀 Project-0 - Professional AI MVP Platform

> **The Complete Full-Stack MVP Generator with Authentication & Project Management**

## ✨ What's New - Enhanced Version!

**Project-0** is now even better with:

- 📏 **Resizable Preview Panel** - Drag to adjust width
- 📜 **Chat History** - Full conversation context saved
- 🔒 **Enhanced Security** - Real token expiration & session management
- 🎨 **Modern Professional Design** - Darker colors, glow effects
- 🎯 **Smooth Navigation** - Scroll animations on landing
- 💾 **Persistent Storage** - Everything saved server-side
- 📊 **Empty States** - Beautiful placeholders
- ⚡ **Better UX** - Cubic-bezier animations

## 🎯 What It Does

### Landing Page
- Beautiful hero section with gradient title
- Feature showcase cards
- Smooth scroll to sections
- Professional design with modern colors

### Authentication System
- **Register**: Name, Email, Password (min 6 chars)
- **Login**: Email, Password with validation
- **Security**: SHA-256 + salt hashing
- **Sessions**: 7-day expiry with secure tokens
- **Logout**: Server-side session cleanup

### Dashboard
- View all your projects in grid
- Create new projects with modal
- Click project to open with full history
- User avatar and profile info
- Empty state when no projects

### AI Chat Interface
- **Resizable Panels**: Drag the divider to adjust width!
- **Chat History**: All messages saved and restored
- **Project Context**: AI remembers everything
- **Live Preview**: iframe with HTML or file list
- **Download**: Get complete ZIP with auto-run scripts

### AI Capabilities
- **Context Memory**: Remembers all project details
- **Incremental Updates**: Edit existing code
- **Full-Stack**: Node.js + Database + Frontend
- **Production-Ready**: Complete, tested code

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install fastapi uvicorn httpx pydantic

# 2. Start Ollama
ollama serve

# 3. Pull model
ollama pull glm-4.6:cloud

# 4. Run platform
python project0.py

# 5. Open browser
http://localhost:8000
```

## 📖 User Flow

### 1. Landing Page
```
→ Click "Learn More" (smooth scroll to features)
→ Click "Try It Now" (go to auth)
```

### 2. Sign Up / Login
```
Register:
- Name: John Doe
- Email: john@example.com  
- Password: ******** (min 6 chars)
→ Auto login → Dashboard

Login:
- Email + Password
- 7-day session
- Remember me functionality
```

### 3. Dashboard
```
→ View all projects (grid layout)
→ Click "+ New Project"
→ Enter name and description
→ Opens chat interface
```

### 4. Chat with AI
```
You: "Create a task manager with auth and SQLite"

AI: *Generates complete project*
    → Shows files in preview
    → History saved automatically

You: "Add dark mode toggle"

AI: *Remembers context*
    → Updates existing code
    → Maintains consistency
```

### 5. Resize Preview
```
→ Find thin line between chat and preview
→ Hover (cursor changes to col-resize)
→ Click and drag left/right
→ Panel resizes smoothly!
→ Min: 300px, Max: 70% of screen
```

### 6. Download & Deploy
```
→ Click "Download ZIP"
→ Extract files
→ Run: ./start.sh
→ Backend starts automatically!
```

## 🎨 Design System

### Color Palette

**Background:**
- Primary: `#0A0A0F` (deep black)
- Secondary: `#13131A` (darker)
- Tertiary: `#1A1A24` (cards)

**Accent:**
- Primary: `#0066FF` (professional blue)
- Secondary: `#0052CC` (darker blue)
- Light: `#3385FF` (light blue)
- Glow: `rgba(0, 102, 255, 0.2)` (glow effect)

**Text:**
- Primary: `#FFFFFF` (white)
- Secondary: `#B4B4C8` (silver)
- Tertiary: `#7878A0` (gray)

**Status:**
- Success: `#00C853` (green)
- Warning: `#FF9100` (orange)
- Error: `#FF1744` (red)

### Typography
- Font: Inter (Google Fonts)
- Weights: 300, 400, 500, 600, 700, 800, 900
- Letter spacing on titles
- Line height: 1.6

### Effects
- Backdrop blur on sticky elements
- Box shadows with layers
- Cubic-bezier transitions
- Gradient buttons with glow
- Hover transform effects

## 💻 Technical Stack

### Platform Backend (Python)
- **FastAPI**: High-performance web framework
- **SQLite**: Lightweight database
- **Ollama**: AI inference
- **Sessions**: Token-based auth with expiry

### Generated Backend (Node.js)
- **Express**: Minimal web framework
- **SQLite/MongoDB**: Database options
- **CORS**: Cross-origin support
- **dotenv**: Environment config

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
    password_hash TEXT NOT NULL,  -- SHA-256 + salt
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
    context TEXT,          -- AI conversation context
    files TEXT,            -- JSON of generated files
    chat_history TEXT,     -- 🆕 Full chat history
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### Sessions Table
```sql
CREATE TABLE sessions (
    token TEXT PRIMARY KEY,       -- 48-byte secure token
    user_id INTEGER,
    created_at TIMESTAMP,
    expires_at TIMESTAMP,          -- 🆕 7-day expiry
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## 🔐 Security Features

- ✅ **Password Hashing**: SHA-256 with salt
- ✅ **Secure Tokens**: 48-byte random tokens
- ✅ **Session Expiry**: 7-day automatic expiration
- ✅ **SQL Injection**: Parameterized queries
- ✅ **XSS Prevention**: HTML escaping
- ✅ **CORS**: Configured properly
- ✅ **Logout**: Server-side session cleanup
- ✅ **Validation**: Min password length (6 chars)

## 📝 API Endpoints

### Authentication
```
POST /api/register     - Create new account
POST /api/login        - Login with credentials
POST /api/logout       - Logout and clear session
```

### Projects
```
GET  /api/projects?token=xxx           - Get user's projects
POST /api/projects?token=xxx           - Create new project
GET  /api/project/:id?token=xxx        - Get project with history
```

### Chat
```
POST /api/chat?token=xxx               - Chat with AI (streaming)
```

### Download
```
GET /api/download/:id?token=xxx        - Download project ZIP
```

## 🎯 New Features Explained

### 1. Resizable Preview Panel

The preview panel can now be resized by dragging:

```javascript
// How it works:
1. Hover over the thin line between chat and preview
2. Cursor changes to col-resize (↔)
3. Click and drag left/right
4. Panel resizes smoothly
5. Min width: 300px
6. Max width: 70% of screen
```

**Why it's useful:**
- Long code? Expand preview to see it all
- Focus on chat? Shrink preview
- Perfect for any screen size

### 2. Chat History Storage

Every message is saved and restored:

```javascript
// What's saved:
{
  "role": "user" | "assistant",
  "content": "message text",
  "timestamp": "2024-11-17T18:37:00"
}

// When you open a project:
- All previous messages load
- Context is restored
- Continue from where you left off
```

### 3. Enhanced Security

Real security implementation:

```python
# Password hashing with salt
salt = "project0_secure_salt_2024"
hash = sha256(password + salt)

# Secure session tokens
token = secrets.token_urlsafe(48)  # 48 bytes

# Session expiry
expires = now + 7_days

# Token validation
if token_expired:
    return 401_Unauthorized

# Logout cleanup
DELETE FROM sessions WHERE token = ?
```

### 4. Smooth Navigation

Landing page with smooth scroll:

```javascript
// "Learn More" button
scrollToFeatures() {
  document.getElementById('features')
    .scrollIntoView({ 
      behavior: 'smooth', 
      block: 'center' 
    });
}
```

### 5. Modern Design

Professional dark theme:

```css
/* Deep blacks */
--bg-primary: #0A0A0F;
--bg-secondary: #13131A;

/* Professional blue */
--accent-primary: #0066FF;

/* Glow effects */
box-shadow: 0 4px 20px rgba(0, 102, 255, 0.2);

/* Smooth animations */
transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

## 🎉 Usage Examples

### Example 1: Task Manager
```
Project Name: Task Manager Pro

Description:
Build a task management app with:
- User authentication (JWT)
- SQLite database
- CRUD operations for tasks
- Categories and tags
- Due dates and priorities
- Dark mode toggle
- Responsive design

→ AI generates complete project
→ Shows live preview
→ Download and run!
```

### Example 2: Blog Platform
```
Project Name: My Blog

Description:
Create a blog platform with:
- Posts with rich text editor
- Comments system
- Categories and tags
- User profiles
- Image uploads
- Search functionality
- SEO optimized

→ AI creates full-stack blog
→ MongoDB for flexibility
→ Modern UI with Tailwind
```

### Example 3: E-commerce
```
Project Name: Shop MVP

Description:
E-commerce site with:
- Product catalog
- Shopping cart
- Checkout process
- Payment integration (Stripe)
- Order management
- Admin panel
- Email notifications

→ Complete e-commerce platform
→ Secure payment flow
→ Production ready
```

## 🔧 Configuration

Edit in `project0.py`:

```python
# Ollama settings
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "glm-4.6:cloud"

# Database
DB_FILE = "project0.db"

# Security
SALT = "project0_secure_salt_2024"
SESSION_EXPIRY_DAYS = 7
TOKEN_LENGTH = 48
```

## 🚀 Deployment

### Development
```bash
python project0.py
```

### Production (Gunicorn)
```bash
pip install gunicorn
gunicorn project0:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY project0.py .
CMD ["python", "project0.py"]
```

## 📊 File Size

```
project0.py: 1979 lines, 68 KB
Everything in ONE file! ✅
```

## ✨ Complete Feature List

**Landing Page:**
- ✅ Hero section with gradient
- ✅ Feature cards
- ✅ Smooth scroll animation
- ✅ Modern logo (SVG)
- ✅ Professional colors

**Authentication:**
- ✅ Register with validation
- ✅ Login with remember me
- ✅ Secure password hashing
- ✅ Session management
- ✅ Token expiration
- ✅ Logout cleanup

**Dashboard:**
- ✅ Project grid view
- ✅ Create project modal
- ✅ User profile display
- ✅ Empty states
- ✅ Hover effects

**Chat Interface:**
- ✅ Split-screen layout
- ✅ Resizable panels (NEW!)
- ✅ Chat history (NEW!)
- ✅ Real-time streaming
- ✅ Markdown rendering
- ✅ Code highlighting
- ✅ Status indicators

**Preview Panel:**
- ✅ Live iframe preview
- ✅ File list viewer
- ✅ Collapsible sections
- ✅ Drag to resize (NEW!)
- ✅ Syntax highlighting

**Download:**
- ✅ ZIP generation
- ✅ Auto-run scripts
- ✅ Complete project structure
- ✅ README included

**Design:**
- ✅ Dark professional theme
- ✅ Modern blue accents
- ✅ Glow effects
- ✅ Smooth animations
- ✅ Responsive layout
- ✅ Custom scrollbars

**Security:**
- ✅ Password encryption
- ✅ Secure sessions
- ✅ Token validation
- ✅ SQL injection protection
- ✅ XSS prevention
- ✅ CORS configuration

## 🎯 Pro Tips

### 1. Use Resizable Panel
When code is long, drag the preview panel wider to see everything!

### 2. Check History
Open an old project - your entire conversation is saved!

### 3. Be Specific
More details = better results:
```
❌ "Make a todo app"
✅ "Create a todo app with user auth, categories, due dates, 
    dark mode, and SQLite database"
```

### 4. Iterative Development
Start simple, then enhance:
```
1. "Create basic blog"
2. "Add comments"
3. "Add categories"
4. "Add search"
```

### 5. Context Matters
AI remembers your project! You can say:
```
"Update the login page"
"Add error handling to the API"
"Refactor the database schema"
```

## 🐛 Troubleshooting

**Q: Preview panel not showing?**
A: Make sure AI generated frontend/index.html file

**Q: Can't resize preview?**
A: Look for the thin blue line between panels, hover and drag

**Q: History not loading?**
A: Check if you're logged in and token is valid

**Q: Session expired?**
A: Sessions expire after 7 days, just login again

**Q: Ollama not responding?**
A: Make sure `ollama serve` is running

**Q: Model not found?**
A: Run `ollama pull glm-4.6:cloud`

## 📚 Learn More

- Check `START.txt` for quick start guide
- Read the code - it's well-commented!
- Try the examples above
- Experiment with different projects

## 📄 License

MIT License - Build amazing things!

---

**Made with ❤️ for rapid MVP development**

Transform ideas into production-ready applications! 🚀

**New in this version:**
- Resizable preview panel
- Complete chat history
- Enhanced security
- Modern professional design
- Smooth navigation
- Better UX everywhere
