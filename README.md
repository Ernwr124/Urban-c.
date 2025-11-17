# HR Agent

AI-powered job match analysis platform. Upload your resume, paste a job description, and get instant AI feedback on how well you match.

**🌐 Multilingual Support**: Full support for **English**, **Russian (Русский)**, and **Kazakh (Қазақша)**! See [MULTILINGUAL_SETUP.md](./MULTILINGUAL_SETUP.md) for details.

## ✨ Features

- **🌐 Multilingual Interface** - Switch between English, Russian, and Kazakh
  - Full UI translation
  - AI analysis in your preferred language
  - Easy language switching from navigation bar
- **Resume Upload** - PDF and DOCX support
- **Job Description Input** - Paste complete job posting
- **AI Analysis** - Powered by Ollama (gpt-oss:20b-cloud)
- **Match Percentage** - 0-100% score with color coding
- **Pros & Cons** - Detailed strengths and weaknesses
- **Skills Breakdown** - Matched, missing, and additional skills
- **Experience & Education Match** - Progress bars with scores
- **Recommendations** - Actionable advice to improve
- **Minimalist Design** - Pure black & white interface
- **Profile Management** - LinkedIn-style profiles with skills
- **Skill-based Matching** - Add your skills for more accurate analysis

## 🌍 Language Support

HR Agent is available in three languages:

| Language | Native Name | AI Analysis | UI Translation |
|----------|-------------|-------------|----------------|
| English  | English     | ✅          | ✅             |
| Russian  | Русский     | ✅          | ✅             |
| Kazakh   | Қазақша     | ✅          | ✅             |

**How to change language:**
1. Log in to your account
2. Click on the language selector in the navigation bar (e.g., "English ▾")
3. Select your preferred language
4. All pages and AI results will be in your language!

See [MULTILINGUAL_SETUP.md](./MULTILINGUAL_SETUP.md) for detailed documentation.

## 🎨 Design

**Minimalist Black & White:**
- Black background (#000000)
- White text and buttons (#ffffff)
- Color accents only for results:
  - 🟢 Green (70-100%) - Excellent match
  - 🟡 Yellow (50-69%) - Good match
  - 🔴 Red (0-49%) - Needs improvement

## 🤖 AI Model

Uses **Ollama** with model: `gpt-oss:20b-cloud`

### Setup Ollama

1. **Install Ollama**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

2. **Pull the model**
```bash
ollama pull gpt-oss:20b-cloud
```

3. **Start Ollama server**
```bash
ollama serve
```

The platform will connect to Ollama at: `http://localhost:11434`

For detailed Ollama setup, see [OLLAMA_SETUP.md](./OLLAMA_SETUP.md)

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Run

```bash
python hr_platform.py
```

Open: **http://localhost:8000**

### First Time Setup

**IMPORTANT:** If you're upgrading from an older version, delete the old database to apply the new schema with language support:

```bash
rm hr_agent.db
python hr_platform.py
```

## 📋 How to Use

1. **Create Account** - Sign up with email and password
2. **Set Up Profile** - Add your skills for accurate matching
3. **Go to Analyze** - Click "New Analysis" button
4. **Upload Resume** - PDF or DOCX file
5. **Paste Job Description** - Full job posting with requirements
6. **Get Results** - Instant AI-powered analysis in your language

## 📊 Results Include

### Match Score
- Overall percentage (0-100%)
- Color-coded circular indicator
- Summary assessment

### Pros (Strengths)
- 5-7 key matches with job requirements
- Your competitive advantages
- What makes you stand out

### Cons (Weaknesses)
- 5-7 gaps or missing requirements
- Skills to develop
- Experience areas to strengthen

### Skills Analysis
- **Matched Skills** - Your skills that align
- **Missing Skills** - Required but not in resume
- **Additional Skills** - Extra value you bring

### Match Scores
- **Experience Match** - % with progress bar
- **Education Match** - % with progress bar

### Recommendations
- 5-7 specific actions
- Tailored to the position
- Practical next steps

## 🛠 Technology

- **Backend**: FastAPI
- **Database**: SQLite (hr_agent.db)
- **AI**: Ollama (gpt-oss:20b-cloud)
- **Frontend**: Pure HTML/CSS
- **Style**: Minimalist black & white
- **i18n**: Built-in translation system

## 📄 Supported Formats

- **PDF** (.pdf)
- **DOCX** (.docx, .doc)

## 🔧 Configuration

The platform uses Ollama locally by default. No API keys needed!

**Default Ollama URL:** `http://localhost:11434/api/generate`

To change, set environment variable:
```bash
export OLLAMA_API_URL="http://your-ollama-server:11434/api/generate"
```

## 🗄 Database

SQLite database: `hr_agent.db`

Tables:
- `users` - User accounts (with language preference)
- `analyses` - Job match analyses with results
- `sessions` - Authentication sessions

## 🎯 Scoring System

- **70-100%** 🟢 Excellent Match - Strong candidate
- **50-69%** 🟡 Good Match - Some gaps to address
- **0-49%** 🔴 Needs Work - Significant improvements needed

## 📱 Pages

- **Landing** - Hero section with features
- **Sign In/Up** - Authentication
- **Dashboard** - Statistics and history
- **Profile** - LinkedIn-style profile with skills
- **Edit Profile** - Update personal info and skills
- **Analyze** - Upload and analyze
- **Results** - Detailed match analysis

## 💡 Tips

### For Best Results

**Resume:**
- Use clear, professional format
- Include all relevant experience
- List skills explicitly
- Add quantifiable achievements

**Job Description:**
- Copy ENTIRE job posting
- Include requirements section
- Include responsibilities
- Don't edit or summarize

**Profile Skills:**
- Add your real skills to profile
- Use them for accurate matching
- AI will only match confirmed skills
- Reduces false positives

### If Ollama Not Working

The platform has fallback analysis that works without Ollama. Results will show a message to set up Ollama for full AI analysis.

**Common Issues:**

1. **Model not found**
```bash
ollama pull gpt-oss:20b-cloud
```

2. **Server not running**
```bash
ollama serve
```

3. **Connection refused**
- Check Ollama is running: `curl http://localhost:11434/api/tags`
- Verify port 11434 is not blocked

## 🚀 Production Deployment

### With Uvicorn
```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000 --workers 4
```

### With Gunicorn
```bash
gunicorn hr_platform:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker
Build image:
```bash
docker build -t hr-agent .
```

Run container:
```bash
docker run -d -p 8000:8000 --network host hr-agent
```

Note: Use `--network host` to connect to Ollama on host machine.

## 🔒 Security

- Session-based authentication
- Password hashing (SHA-256)
- HTTP-only cookies
- File size limits (10MB)
- File type validation
- No API keys needed (local Ollama)

## 🐛 Troubleshooting

### PDF not parsing
```bash
pip install PyPDF2
```

### DOCX not parsing
```bash
pip install python-docx
```

### Ollama connection issues
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Pull model if needed
ollama pull gpt-oss:20b-cloud
```

### Database schema errors
If you encounter database errors after updating:
```bash
rm hr_agent.db
python hr_platform.py
```

## 📈 Example Workflow

1. Find job posting you're interested in
2. Upload your current resume
3. Paste entire job description
4. Click "Analyze Match"
5. Review results (30-60 seconds)
6. Note recommendations
7. Update resume based on feedback
8. Re-analyze to see improvement

## 🌍 Translations

Want to improve translations or add a new language? Contributions welcome!

See [MULTILINGUAL_SETUP.md](./MULTILINGUAL_SETUP.md) for translation guidelines.

## 🤝 Contributing

Single-file application for easy deployment and customization.

## 📝 License

See LICENSE file

---

**HR Agent** - AI-Powered Job Matching  
Available in English, Русский, Қазақша  
Version 2.0.0 (Multilingual Edition)
