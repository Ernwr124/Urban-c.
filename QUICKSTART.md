# Resume Analyzer - Quick Start Guide

## 🚀 Get Started in 3 Minutes

### Step 1: Install

```bash
pip install -r requirements.txt
```

### Step 2: Run

```bash
python hr_platform.py
```

The app will be available at: **http://localhost:8000**

---

## 📝 First Time Setup

### 1. Create Account

- Go to http://localhost:8000
- Click **"Get Started"**
- Fill in:
  - Full name
  - Email address
  - Password (min 6 characters)
- Click **"Create account"**

### 2. Sign In

- Click **"Sign In"**
- Enter your email and password
- Access your dashboard

### 3. Upload Resume

- Click **"Upload Resume"** button
- Select your file (PDF, DOCX, or image)
- Click **"Analyze Resume"**
- Wait for AI analysis (5-30 seconds)

### 4. View Results

Your analysis includes:
- ✅ **Match Score** with color coding:
  - 🟢 Green (70-100%): Excellent
  - 🟡 Yellow (50-69%): Good
  - 🔴 Red (0-49%): Needs improvement
- 📊 **Strengths & Weaknesses**
- 🛠️ **Skills Assessment**
- 💼 **Experience Evaluation**
- 🎓 **Education Review**
- 🚀 **Development Plan**
- 📝 **Resume Recommendations**

---

## 🎨 Interface Overview

### GitHub-Style Dark Theme
- Clean, professional design
- Easy navigation
- Clear visual hierarchy
- Color-coded results

### Key Pages
- **Dashboard** - Overview and history
- **Upload** - Analyze new resume
- **Profile** - Account information
- **Analysis** - Detailed results

---

## 🔧 Optional Configuration

### For Ollama Cloud API

1. Copy environment file:
```bash
cp .env.example .env
```

2. Edit `.env`:
```env
OLLAMA_API_KEY=your-api-key-here
```

3. Restart the application

**Note**: The app works with fallback analysis if Ollama is not configured.

---

## 📁 Supported Files

- **PDF** - Best for formatted resumes
- **DOCX/DOC** - Microsoft Word documents
- **Images** - PNG, JPG (requires Tesseract OCR)

### File Requirements
- Max size: 10MB
- Text should be clear and readable
- Structured format recommended

---

## 🐛 Troubleshooting

### Can't parse PDF?
```bash
pip install PyPDF2
```

### Can't parse DOCX?
```bash
pip install python-docx
```

### Can't parse images?
```bash
# Install Tesseract OCR
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# MacOS
brew install tesseract

# Python library
pip install pytesseract Pillow
```

### Port 8000 already in use?
```bash
# Use different port
python hr_platform.py --port 8080
```

Or edit the file and change port in the last line.

---

## 💡 Tips for Best Results

### Resume Preparation
1. Use clear, readable fonts
2. Include contact information
3. List skills explicitly
4. Quantify achievements
5. Highlight education

### Getting Better Scores
1. Add relevant keywords
2. Include certifications
3. Describe projects in detail
4. Show career progression
5. Follow recommendations from analysis

---

## 📈 Understanding Your Score

- **90-100%**: Outstanding resume, ready for top positions
- **70-89%**: Strong resume, minor improvements recommended
- **50-69%**: Good foundation, several areas to enhance
- **30-49%**: Needs significant improvements
- **0-29%**: Major restructuring required

---

## 🔄 Iterative Improvement

1. Upload current resume
2. Review analysis
3. Apply recommendations
4. Re-upload improved version
5. Compare scores
6. Repeat until satisfied

---

## 🚀 Production Tips

### For VPS Deployment
```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn
gunicorn hr_platform:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### With Nginx Reverse Proxy
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📞 Need Help?

- Check the full README.md
- Review error messages in console
- Ensure all dependencies are installed
- Verify file formats are supported

---

**Ready to improve your resume? Let's get started! 🎯**
