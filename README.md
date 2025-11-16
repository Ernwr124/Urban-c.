# HR Agent Platform

Professional HR service for intelligent resume analysis, candidate comparison, and compliance checking with Kazakhstan Labor Code.

## 🎯 Features

- **AI-Powered Resume Analysis** - Intelligent analysis using Ollama Cloud
- **Dual Role System** - Separate interfaces for Candidates and HR Specialists
- **Match Scoring** - Automated candidate-vacancy matching
- **Development Plans** - Personalized career development recommendations
- **Labor Code Compliance** - Verify vacancy requirements against TK RK
- **Professional UI** - Clean, corporate design (white & black theme)

## 🛠 Technology Stack

- **Backend**: FastAPI
- **Database**: SQLite
- **AI**: Ollama Cloud (gpt-oss:20b-cloud)
- **Frontend**: HTML + Embedded CSS/JS
- **Architecture**: Single-file modular structure

## 📦 Installation

### Prerequisites

- Python 3.8+
- pip
- (Optional) Tesseract OCR for image parsing

### Quick Start

1. **Clone the repository**
```bash
git clone <repository-url>
cd workspace
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your Ollama API key
```

4. **Run the application**
```bash
python hr_platform.py
```

Or use the startup script:
```bash
chmod +x start.sh
./start.sh
```

5. **Access the platform**
Open your browser and navigate to: `http://localhost:8000`

## 🔧 Configuration

Edit `.env` file:

```env
SECRET_KEY=your-secret-key-here
OLLAMA_API_URL=https://api.ollama.cloud/v1/chat/completions
OLLAMA_API_KEY=your-ollama-api-key-here
```

## 📱 User Roles

### Candidate
- Upload personal resume
- Get AI-powered analysis
- Receive development recommendations
- View skills assessment
- Get resume improvement suggestions

### HR Specialist
- Upload candidate resumes
- Compare multiple candidates
- View match scores
- Check TK RK compliance
- Access analytics dashboard
- Admin panel access

## 🎨 Design System

- **Primary Color**: #2563eb (Blue)
- **Background**: #ffffff (White)
- **Text**: #0f0f0f (Black)
- **Accent**: #0ea5e9 (Success)
- **Error**: #ef4444 (Error)

## 📄 Supported File Formats

- PDF (.pdf)
- Microsoft Word (.docx, .doc)
- Images (.png, .jpg, .jpeg) - with OCR

## 🗄 Database Schema

### Users
- id, email, password_hash, full_name, role, created_at, last_login, is_active

### Analyses
- id, user_id, candidate_name, filename, file_path, analysis_type, match_score, analysis_data, created_at

### Analytics
- id, user_id, action, metadata, created_at

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

### Docker (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hr_platform.py .
COPY .env .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "hr_platform:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🔒 Security Notes

- Session-based authentication
- Password hashing with SHA-256
- HTTP-only cookies
- File size limitations (10MB)
- File type validation

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

### HR Only
- `GET /admin` - Admin panel

### System
- `GET /api/health` - Health check

## 🧪 Testing

Create test user:
```bash
# Register via web interface or directly in database
```

Test file upload:
```bash
# Use web interface at /upload
```

## 📝 License

See LICENSE file

## 🤝 Support

For issues and questions, please contact the development team.

---

**HR Agent Platform** - Professional HR Service
Version 1.0.0
