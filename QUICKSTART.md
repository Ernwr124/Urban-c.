# Quick Start - HR Agent

## 🚀 Setup in 3 Steps

### 1. Install Ollama & Model

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull gpt-oss:20b-cloud

# Start Ollama server
ollama serve
```

### 2. Install & Run HR Agent

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python hr_platform.py
```

### 3. Open & Use

Open: **http://localhost:8000**

---

## 📝 Using HR Agent

### Step 1: Create Account
1. Click "Get Started"
2. Enter name, email, password
3. Click "Create Account"

### Step 2: Sign In
1. Enter email and password
2. Click "Sign In"

### Step 3: Analyze Match
1. Click "New Analysis"
2. **Upload Resume** (PDF or DOCX)
3. **Paste Job Description** (complete posting)
4. Click "Analyze Match"
5. Wait 30-60 seconds for AI analysis

### Step 4: Review Results
- Match score (0-100%)
- Your strengths
- Areas to address
- Skills breakdown
- Recommendations

---

## 💡 Tips

### Resume Tips
✅ Professional format
✅ All relevant experience
✅ Skills listed explicitly
✅ Quantifiable achievements
✅ Current information

### Job Description Tips
✅ Copy ENTIRE posting
✅ Include requirements
✅ Include responsibilities
✅ Don't edit or summarize
✅ Include qualifications

---

## 🎯 Understanding Scores

### 🟢 70-100%: Excellent Match
- You're a strong candidate
- Most requirements met
- Apply confidently

### 🟡 50-69%: Good Match
- Solid foundation
- Some gaps exist
- Tailor resume and apply

### 🔴 0-49%: Needs Work
- Significant gaps
- Build skills first
- Or find better-fit roles

---

## 🔧 Ollama Setup Details

### Check if Ollama is Running
```bash
curl http://localhost:11434/api/tags
```

### Start Ollama
```bash
ollama serve
```

### Pull Model (if not done)
```bash
ollama pull gpt-oss:20b-cloud
```

### Test Model
```bash
ollama run gpt-oss:20b-cloud "Hello, how are you?"
```

---

## 🐛 Troubleshooting

### "Connection refused" Error
**Problem**: Ollama not running
**Solution**:
```bash
ollama serve
```

### "Model not found" Error
**Problem**: Model not pulled
**Solution**:
```bash
ollama pull gpt-oss:20b-cloud
```

### PDF Not Parsing
**Solution**:
```bash
pip install PyPDF2
```

### DOCX Not Parsing
**Solution**:
```bash
pip install python-docx
```

### Slow Analysis
**Normal**: First analysis may take 60-90 seconds
**Reason**: Model loading into memory
**After**: Subsequent analyses are faster (10-30 seconds)

---

## 📊 Example Usage

### Scenario: Software Engineer Position

1. **Upload** your developer resume (PDF)
2. **Paste** job description:
```
Senior Software Engineer
Requirements:
- 5+ years Python
- FastAPI experience
- Database knowledge
- Team collaboration
```
3. **Click** "Analyze Match"
4. **Get** results showing:
   - Match score: 75%
   - Pros: Python expertise, FastAPI knowledge
   - Cons: Missing Docker experience
   - Recommendations: Add containerization skills

---

## 🔄 Improving Your Score

1. Note recommendations from analysis
2. Update resume based on feedback
3. Re-upload and analyze again
4. Compare scores
5. Repeat until satisfied

---

## 🌐 Production Deployment

### Local Network Access
```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000
```

### With Systemd (Linux)
Create `/etc/systemd/system/hr-agent.service`:
```ini
[Unit]
Description=HR Agent
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/workspace
ExecStart=/usr/bin/python3 hr_platform.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable hr-agent
sudo systemctl start hr-agent
```

---

## 📁 Project Structure

```
/workspace/
├── hr_platform.py      # Main application
├── hr_agent.db         # Database (auto-created)
├── uploads/            # Resume files (auto-created)
├── requirements.txt    # Python dependencies
└── README.md          # Full documentation
```

---

## ⚡ Performance

- **First Analysis**: 60-90 seconds (model loading)
- **Subsequent**: 10-30 seconds
- **Concurrent Users**: Depends on hardware
- **RAM Usage**: ~2-4GB (model in memory)

---

## 🎨 Design

**Pure Black & White:**
- Black background for focus
- White text for readability
- Color only for data (green/yellow/red)
- Minimalist and professional
- Clean typography

---

**Ready to find your perfect job match!** 🎯
