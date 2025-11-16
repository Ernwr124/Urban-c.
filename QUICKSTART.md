# Quick Start Guide - Resume Analyzer

## 🚀 Get Started in 3 Steps

### 1. Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python hr_platform.py
```

Open: **http://localhost:8000**

---

## 📝 Using the Platform

### Step 1: Create Account

1. Click **"Get Started"** on homepage
2. Enter your name, email, and password
3. Click **"Create Account"**

### Step 2: Analyze Resume

1. Click **"New Analysis"** button
2. **Upload your resume**
   - PDF or DOCX format
   - Max 10MB
   - Click the upload box or drag & drop
3. **Paste job description**
   - Copy entire job posting
   - Include requirements, responsibilities, qualifications
   - Paste in the text area

4. Click **"Analyze Match"**

### Step 3: View Results

You'll see:
- 🎯 **Match Score** (0-100%) with color indicator
- ✅ **Your Strengths** - What makes you a great fit
- ⚠️ **Areas to Address** - Gaps or missing requirements
- 🎯 **Skills Analysis** - Matched, missing, and additional skills
- 💼 **Experience Match** - How your experience aligns
- 🎓 **Education Match** - Educational background fit
- 💡 **Recommendations** - Actions to improve your match

---

## 💡 Tips for Best Results

### Resume Tips
- ✅ Use professional formatting
- ✅ Include all relevant experience
- ✅ List skills explicitly
- ✅ Add quantifiable achievements
- ✅ Keep it current

### Job Description Tips
- ✅ Copy the ENTIRE job posting
- ✅ Don't edit or summarize
- ✅ Include requirements section
- ✅ Include responsibilities
- ✅ Include qualifications/nice-to-haves

---

## 🎨 Understanding Your Score

### 🟢 70-100%: Excellent Match
- You're a strong candidate
- Most requirements met
- Apply with confidence

### 🟡 50-69%: Good Match
- Solid foundation
- Some gaps to address
- Consider applying with tailored cover letter

### 🔴 0-49%: Needs Improvement
- Significant gaps
- Consider skill development first
- Or look for better-fit positions

---

## 📊 Sample Workflow

### Example 1: Checking Before Applying

1. Find interesting job posting
2. Upload your current resume
3. Paste job description
4. Get match score
5. If 70%+: Apply!
6. If 50-69%: Tailor resume, then apply
7. If <50%: Build skills first

### Example 2: Resume Optimization

1. Upload resume
2. Paste dream job description
3. Review "Areas to Address"
4. Update resume based on recommendations
5. Re-analyze to see improvement
6. Repeat until satisfied

### Example 3: Multiple Positions

1. Save job descriptions in a document
2. Analyze same resume with different jobs
3. Compare match scores
4. Focus on best-fit opportunities
5. Track all analyses in dashboard

---

## 🔧 Configuration (Optional)

### For AI-Powered Analysis

Create `.env` file:
```env
OLLAMA_API_KEY=your-api-key-here
```

**Note**: The platform works with fallback analysis if not configured.

---

## 🐛 Common Issues

### "File too large"
- Resume must be under 10MB
- Compress PDF or save as newer format

### "Unsupported format"
- Only PDF and DOCX supported
- Convert other formats before uploading

### PDF not parsing correctly
```bash
pip install --upgrade PyPDF2
```

### DOCX not parsing correctly
```bash
pip install python-docx
```

---

## 📱 Dashboard Features

### Statistics
- **Total Analyses** - All your job matches
- **Average Match** - Your overall compatibility
- **Latest Score** - Most recent analysis

### History
- View all past analyses
- Compare different positions
- Track improvements over time
- Re-visit old results

---

## 🎯 Pro Tips

1. **Be Specific**: More detailed job descriptions = better analysis
2. **Complete Resume**: Include all relevant experience and skills
3. **Update Regularly**: Keep resume current between analyses
4. **Compare Multiple Jobs**: Analyze several positions to find best fit
5. **Track Progress**: Re-analyze same position after improvements

---

## 🚀 Production Deployment

### VPS/Server

```bash
# Install dependencies
pip install -r requirements.txt gunicorn

# Run with Gunicorn
gunicorn hr_platform:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### With Nginx

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

### Docker

```bash
docker build -t resume-analyzer .
docker run -d -p 8000:8000 --env-file .env resume-analyzer
```

---

## 📞 Need Help?

- Check README.md for full documentation
- Review error messages in browser console
- Ensure all dependencies installed
- Verify file formats (PDF, DOCX only)

---

**Happy Analyzing! Find your perfect job match! 🎯**
