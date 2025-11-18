# Project-0 - AI MVP Generator (Production SaaS)

🚀 Transform your ideas into production-ready MVPs using AI

## Features

### ✨ Core Features
- **AI-Powered Generation**: Generate complete MVPs from simple text descriptions
- **Real-time Streaming**: See your MVP being created in real-time
- **Live Preview**: Instant preview of generated code
- **Download Projects**: Export complete projects as ZIP files

### 🔐 Authentication & Security
- **User Registration**: Create account with username, email, and password
- **Secure Login**: Encrypted password storage with SHA256
- **JWT Sessions**: Secure session management with 30-day tokens
- **Auto-login**: Persistent sessions for returning users
- **Profile Management**: User profile with account information

### 🎨 Design
- **Landing Page**: Beautiful black & white minimalist design
- **3D Auth Panel**: Modern authentication forms with smooth animations
- **Profile Menu**: Circular profile button with dropdown menu
- **Responsive**: Mobile-first, works on all devices
- **v0.dev Inspired**: Clean, minimalist interface

## Installation

1. **Install Dependencies**
```bash
pip install -r requirements_project_zero.txt
```

2. **Make sure Ollama is running**
```bash
# Install Ollama if you haven't: https://ollama.ai
ollama run glm-4.6:cloud
```

3. **Run the Application**
```bash
python project_zero.py
```

4. **Open in Browser**
```
http://localhost:8000
```

## Usage

### First Time Users

1. Visit `http://localhost:8000`
2. You'll see the landing page
3. Click **"Try it Now"** button
4. Register with:
   - Username (any name you like)
   - Email (any email format)
   - Password (any secure password)
5. You'll be automatically logged in

### Returning Users

1. Visit `http://localhost:8000`
2. If your session is saved, you'll go directly to the app
3. Otherwise, click **"Sign In"** and enter your credentials

### Generating MVPs

1. Describe your idea in the text input
2. Press Enter or click the lightning button
3. Watch as AI generates your MVP in real-time
4. Preview appears automatically on the right
5. Download as ZIP file with one click

### Profile Menu

1. Click the circular profile button (top right)
2. View your profile information
3. Logout when needed

## Architecture

### Backend
- **FastAPI**: Modern async Python web framework
- **SQLite**: Lightweight database for users and MVPs
- **JWT**: Secure token-based authentication
- **Ollama**: Local AI model for MVP generation

### Security
- **Password Hashing**: SHA256 with salt
- **HTTP-only Cookies**: Secure session storage
- **User Isolation**: Each user only sees their own MVPs
- **SQL Injection Prevention**: Parameterized queries

### Database Schema

**Users Table**
```sql
- id: INTEGER PRIMARY KEY
- username: TEXT UNIQUE
- email: TEXT UNIQUE
- password_hash: TEXT (encrypted)
- created_at: TIMESTAMP
- last_login: TIMESTAMP
```

**MVPs Table**
```sql
- id: TEXT PRIMARY KEY
- user_id: INTEGER (foreign key)
- idea: TEXT
- code: TEXT
- markdown: TEXT
- created_at: TIMESTAMP
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `POST /api/auth/logout` - Logout user
- `GET /api/auth/me` - Get current user info

### MVP Generation
- `POST /api/generate` - Generate MVP (streaming)
- `GET /api/mvp/{mvp_id}` - Get MVP data
- `GET /preview/{mvp_id}` - Preview MVP
- `GET /api/download/{mvp_id}` - Download project ZIP

### System
- `GET /api/health` - Health check
- `GET /` - Landing page or main app (based on auth)

## Configuration

Edit these variables in `project_zero.py`:

```python
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "glm-4.6:cloud"
DATABASE_NAME = "project_zero.db"
```

## Features in Detail

### Landing Page
- Animated hero section with call-to-action
- Feature cards showcasing capabilities
- Smooth transitions and modern design
- Dark theme with white text

### Authentication Panel
- 3D card effect with shadows
- Tab switching between login/register
- Real-time form validation
- Error handling and user feedback
- Auto-focus and keyboard shortcuts

### Main Application
- Split-screen layout (chat + preview)
- Example ideas for quick start
- Streaming AI responses
- Markdown rendering
- Code syntax highlighting
- Action buttons for quick access

### Profile System
- Circular profile avatar with initial
- Dropdown menu with user info
- One-click logout
- Session persistence

## Security Best Practices

1. **Never share your database file** - Contains encrypted user data
2. **Use strong passwords** - Minimum 8 characters recommended
3. **Keep dependencies updated** - Run `pip install -U` regularly
4. **Backup your database** - Save `project_zero.db` regularly
5. **Use HTTPS in production** - Add SSL/TLS certificate

## Troubleshooting

### Ollama not running
```bash
# Start Ollama
ollama serve

# In another terminal, pull the model
ollama pull glm-4.6:cloud
```

### Database errors
```bash
# Delete database to reset
rm project_zero.db

# Restart application
python project_zero.py
```

### Port already in use
```python
# Change port in last line of project_zero.py
uvicorn.run(app, host="0.0.0.0", port=8001)  # Changed to 8001
```

## Development

### Project Structure
```
project_zero.py          # Main application file
requirements_project_zero.txt  # Python dependencies
project_zero.db         # SQLite database (auto-created)
README_PROJECT_ZERO.md  # This file
```

### Adding Features
1. Authentication logic is in the `/api/auth/` endpoints
2. MVP generation is in the `/api/generate` endpoint
3. Frontend is in the HTML templates at the bottom
4. Modify `SYSTEM_PROMPT` to change AI behavior

## License

This project is open source and available under the MIT License.

## Credits

- **Design Inspiration**: v0.dev
- **AI Model**: Ollama
- **Framework**: FastAPI
- **Creator**: Project-0 Team

---

**Built with ❤️ for developers and entrepreneurs**

Need help? Open an issue or contact support.
