# Resume Analyzer

AI-powered resume analysis platform for job seekers. Get instant feedback, detailed insights, and personalized development recommendations.

## 🎯 Features

- **AI-Powered Analysis** - Intelligent resume analysis using Ollama Cloud
- **Match Scoring** - Get a comprehensive score (0-100%) for your resume
- **Detailed Insights** - Strengths, weaknesses, and areas for improvement
- **Skills Assessment** - Technical skills, soft skills, and recommendations
- **Development Plan** - Personalized career growth recommendations
- **Resume Improvements** - Specific suggestions to enhance your resume
- **GitHub-Style UI** - Modern, clean dark theme interface

## 🛠 Technology Stack

- **Backend**: FastAPI
- **Database**: SQLite
- **AI**: Ollama Cloud (gpt-oss:20b-cloud)
- **Frontend**: HTML + Embedded CSS/JS
- **Architecture**: Single-file modular structure

## 🎨 Design System

Inspired by GitHub's interface:
- **Dark Theme**: Professional and modern
- **Color Palette**: 
  - Background: `#0d1117` (dark)
  - Foreground: `#e6edf3` (light)
  - Borders: `#30363d`
  - Accent: `#58a6ff` (blue)
  - Success: `#3fb950` (green) - 70%+
  - Warning: `#d29922` (yellow) - 50-69%
  - Danger: `#f85149` (red) - <50%

## 📦 Installation

### Prerequisites

- Python 3.8+
- pip
- (Optional) Tesseract OCR for image parsing

### Quick Start

1. **Install dependencies**
```bash
pip install -r requirements.txt
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your Ollama API key
```

3. **Run the application**
```bash
python hr_platform.py
```

Or:
```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000
```

4. **Access the platform**
Open: `http://localhost:8000`

## 🔧 Configuration

Edit `.env` file:

```env
SECRET_KEY=your-secret-key-here
OLLAMA_API_URL=https://api.ollama.cloud/v1/chat/completions
OLLAMA_API_KEY=your-ollama-api-key-here
```

## 📱 User Flow

1. **Register** - Create your account
2. **Login** - Sign in to your dashboard
3. **Upload** - Upload your resume (PDF, DOCX, or image)
4. **Analyze** - AI analyzes your resume automatically
5. **Review** - Get detailed insights and recommendations
6. **Improve** - Apply suggestions and re-upload

## 📄 Supported File Formats

- PDF (.pdf)
- Microsoft Word (.docx, .doc)
- Images (.png, .jpg, .jpeg) - with OCR

## 🗄 Database Schema

### Users
- id, email, password_hash, full_name, created_at, last_login, is_active

### Analyses
- id, user_id, filename, file_path, match_score, analysis_data, created_at

### Sessions
- id, session_token, user_id, expires_at, created_at

## 🚀 Production Deployment

### Using Uvicorn

```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000 --workers 4
```

### Using Gunicorn

```bash
gunicorn hr_platform:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker

```bash
docker build -t resume-analyzer .
docker run -d -p 8000:8000 --env-file .env resume-analyzer
```

Or with Docker Compose:

```bash
docker-compose up -d
```

## 🔒 Security Features

- Session-based authentication
- Password hashing with SHA-256
- HTTP-only cookies
- File size limitations (10MB)
- File type validation
- CSRF protection

## 📊 API Endpoints

### Public
- `GET /` - Landing page
- `GET /login` - Login page
- `POST /login` - Login handler
- `GET /register` - Registration page
- `POST /register` - Registration handler

### Authenticated
- `GET /dashboard` - User dashboard
- `GET /profile` - User profile
- `GET /upload` - Upload page
- `POST /upload` - File upload handler
- `GET /analysis/{id}` - Analysis results
- `GET /logout` - Logout handler

### System
- `GET /api/health` - Health check

## 📈 Analysis Output

The AI provides:

- **Match Score** (0-100%)
- **Strengths** - Key positive points
- **Weaknesses** - Areas needing improvement
- **Skills Match**:
  - Technical skills detected
  - Soft skills detected
  - Missing skills recommendations
- **Experience Assessment** - Detailed evaluation
- **Education Assessment** - Academic background review
- **Development Plan** - Career growth steps
- **Resume Recommendations** - Specific improvements
- **Summary** - Overall assessment

## 🧪 Testing

```bash
# Create test account via web interface
# Upload sample resume
# View analysis results
```

## 📝 License

See LICENSE file

## 🤝 Support

For issues and questions, please open an issue on GitHub.

---

**Resume Analyzer** - AI-Powered Career Development Tool
Version 2.0.0
