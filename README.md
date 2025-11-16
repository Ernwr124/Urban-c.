# Resume Analyzer - Job Match Platform

AI-powered platform that compares your resume with job descriptions and shows how well you match the position.

## ✨ Features

- **Upload Resume** - Support for PDF and DOCX formats
- **Job Description Analysis** - Paste full job posting for comparison
- **Match Percentage** - Get clear % score showing your fit
- **Pros & Cons** - See your strengths and areas to improve
- **Skills Analysis** - Matched, missing, and additional skills
- **Experience & Education Match** - Detailed scoring with progress bars
- **Recommendations** - Actionable advice to improve your match
- **Beautiful UI** - v0.dev-inspired clean and modern design

## 🎨 Design

Inspired by Vercel's v0.dev platform:
- Clean, minimalist interface
- Subtle gradients and shadows
- Modern typography (Inter font)
- Responsive layout
- Smooth transitions

## 🚀 Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Run

```bash
python hr_platform.py
```

Or:

```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000
```

Open: **http://localhost:8000**

## 📋 How It Works

1. **Sign Up** - Create your account
2. **Upload Resume** - PDF or DOCX format
3. **Paste Job Description** - Full job posting with requirements
4. **Get Results** - Instant AI-powered analysis showing:
   - Match percentage (0-100%)
   - Your strengths for this role
   - Areas needing improvement
   - Skills breakdown
   - Experience and education match
   - Actionable recommendations

## 🎯 Match Scoring

- **70-100%** 🟢 Excellent Match - You're a strong candidate
- **50-69%** 🟡 Good Match - Some gaps to address
- **0-49%** 🔴 Needs Work - Significant improvements needed

## 🛠 Technology

- **Backend**: FastAPI
- **Database**: SQLite
- **AI**: Ollama Cloud (gpt-oss:20b-cloud)
- **Frontend**: Pure HTML/CSS (no frameworks)
- **Styling**: v0.dev-inspired custom CSS

## 📄 Supported Formats

- **PDF** - Best for formatted resumes
- **DOCX** - Microsoft Word documents

## 🔧 Configuration

Create `.env` file:

```env
SECRET_KEY=your-secret-key
OLLAMA_API_URL=https://api.ollama.cloud/v1/chat/completions
OLLAMA_API_KEY=your-api-key
```

**Note**: The platform works with fallback analysis if Ollama is not configured.

## 📊 Analysis Output

The AI compares your resume with the job description and provides:

### Match Score
- Overall percentage (0-100%)
- Color-coded indicator
- Summary assessment

### Pros (Strengths)
- 5-7 strong matches between your resume and job requirements
- What makes you a great fit
- Your competitive advantages

### Cons (Areas to Address)
- 5-7 gaps or missing requirements
- Skills you need to develop
- Experience areas to strengthen

### Skills Match
- **Matched Skills**: Your skills that align with requirements
- **Missing Skills**: Required skills not in your resume
- **Additional Skills**: Extra qualifications you bring

### Experience Match
- Percentage score
- Detailed analysis of your experience vs requirements
- Progress bar visualization

### Education Match
- Percentage score
- Analysis of education vs requirements
- Progress bar visualization

### Recommendations
- 5-7 specific actions to improve your match
- Tailored advice for this position
- Practical next steps

## 🗄 Database

SQLite database with tables:
- `users` - User accounts
- `analyses` - Job match analyses
- `sessions` - Authentication sessions

## 🔒 Security

- Session-based authentication
- Password hashing (SHA-256)
- HTTP-only cookies
- File size limits (10MB)
- File type validation

## 📱 Pages

- **Landing** - Hero section with features
- **Sign In/Up** - Authentication pages
- **Dashboard** - Overview with statistics
- **Analyze** - Upload resume + job description
- **Results** - Detailed match analysis
- **Profile** - Account information

## 🎨 UI Components

- Gradient stat cards
- Circular score indicator
- Progress bars
- Feature lists with icons
- Skill badges
- Responsive tables
- Modern forms

## 💡 Tips for Best Results

### Resume Preparation
1. Use clear, professional formatting
2. Include all relevant experience
3. List technical and soft skills explicitly
4. Quantify achievements
5. Keep it updated

### Job Description
1. Copy the entire job posting
2. Include all requirements
3. Add responsibilities section
4. Include qualifications
5. Don't edit or summarize

## 🚀 Production Deployment

### Uvicorn
```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000 --workers 4
```

### Gunicorn
```bash
gunicorn hr_platform:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker
```bash
docker build -t resume-analyzer .
docker run -d -p 8000:8000 --env-file .env resume-analyzer
```

## 🐛 Troubleshooting

### PDF parsing issues
```bash
pip install PyPDF2
```

### DOCX parsing issues
```bash
pip install python-docx
```

### Port in use
Change port in `hr_platform.py` or run:
```bash
uvicorn hr_platform:app --port 8080
```

## 📈 Example Use Cases

1. **Job Applications** - Check match before applying
2. **Resume Optimization** - Tailor resume to job postings
3. **Career Planning** - Identify skills to develop
4. **Interview Prep** - Know your strengths and gaps
5. **Multiple Positions** - Compare fit for different roles

## 🤝 Contributing

This is a production-ready single-file application. Easy to:
- Deploy anywhere
- Customize styling
- Extend functionality
- Integrate with other tools

## 📝 License

See LICENSE file

---

**Resume Analyzer** - Match Your Resume with Your Dream Job
Version 3.0.0
