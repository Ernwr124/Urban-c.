"""
HR Agent - AI-Powered Job Match Analysis
Compare your resume with job descriptions using Ollama (gpt-oss:20b-cloud)
Minimalist Black & White Design
"""

# ============================================================================
# IMPORTS
# ============================================================================

import os
import io
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import (
    FastAPI, Request, Response, HTTPException, UploadFile, 
    File, Form, Depends, status, Cookie
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, EmailStr
import httpx

# Optional imports for file parsing
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Application configuration"""
    DATABASE_URL = "sqlite:///./hr_agent.db"
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    SESSION_LIFETIME_HOURS = 24
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = "gpt-oss:20b-cloud"
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR = Path("./uploads")
    
    @classmethod
    def init(cls):
        """Initialize configuration"""
        cls.UPLOAD_DIR.mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "avatars").mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "resumes").mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "videos").mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "certificates").mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "portfolio").mkdir(exist_ok=True)


# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()


class User(Base):
    """User model - LinkedIn-style profile"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="candidate")  # 'candidate' or 'hr'
    
    # Profile information
    headline = Column(String, default="")  # e.g. "Senior Software Engineer at Company"
    location = Column(String, default="")
    bio = Column(Text, default="")
    phone = Column(String, default="")
    
    # Profile media
    avatar = Column(String, default="")  # Path to avatar image
    resume_file = Column(String, default="")  # Path to uploaded resume
    video_resume = Column(String, default="")  # Path to video resume (for candidates)
    
    # Skills (manually entered for accurate matching)
    skills = Column(Text, default="")  # Comma-separated or structured text
    
    # Language preference (always Russian)
    language = Column(String, default="ru")  # Always 'ru' for Russian
    
    # Social links
    linkedin_url = Column(String, default="")
    github_url = Column(String, default="")
    website = Column(String, default="")
    whatsapp = Column(String, default="")  # WhatsApp number or link
    instagram = Column(String, default="")  # Instagram username or link
    
    # HR-specific fields
    company_name = Column(String, default="")  # Company name for HR
    company_description = Column(Text, default="")  # Company description for HR
    
    # Ratings
    average_rating = Column(Float, default=0.0)  # Average rating
    total_reviews = Column(Integer, default=0)  # Total number of reviews
    
    # Meta
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)


class Analysis(Base):
    """Job match analysis model"""
    __tablename__ = "analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    filename = Column(String)
    file_path = Column(String)
    job_description = Column(Text)
    match_score = Column(Float)
    analysis_data = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    """Session model"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True)
    user_id = Column(Integer, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class Request(Base):
    """HR requests to candidates"""
    __tablename__ = "requests"
    
    id = Column(Integer, primary_key=True, index=True)
    hr_id = Column(Integer, index=True)  # HR specialist who sent request
    candidate_id = Column(Integer, index=True)  # Candidate who receives request
    message = Column(Text)  # Message from HR
    status = Column(String, default="pending")  # 'pending', 'viewed', 'responded'
    created_at = Column(DateTime, default=datetime.utcnow)
    viewed_at = Column(DateTime, nullable=True)


class Job(Base):
    """Job/Vacancy model for HR specialists"""
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    hr_id = Column(Integer, index=True)  # HR who created the job
    title = Column(String, nullable=False)  # Job title
    description = Column(Text, nullable=False)  # Full job description
    requirements = Column(Text, default="")  # Requirements
    skills_required = Column(Text, default="")  # Required skills
    location = Column(String, default="")
    salary_range = Column(String, default="")  # e.g. "$50k-$80k"
    employment_type = Column(String, default="full-time")  # full-time, part-time, contract
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Portfolio(Base):
    """Portfolio items for candidates"""
    __tablename__ = "portfolio"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    project_url = Column(String, default="")  # Link to project
    image_url = Column(String, default="")  # Screenshot/image
    technologies = Column(Text, default="")  # Technologies used
    created_at = Column(DateTime, default=datetime.utcnow)


class Certificate(Base):
    """Certificates for candidates"""
    __tablename__ = "certificates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String, nullable=False)  # Certificate name
    issuer = Column(String, default="")  # Issuing organization
    issue_date = Column(String, default="")  # Date issued
    credential_id = Column(String, default="")  # Credential ID
    credential_url = Column(String, default="")  # Verification URL
    file_path = Column(String, default="")  # Path to certificate file
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    """Chat messages between HR and candidates"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, index=True)  # User who sent the message
    receiver_id = Column(Integer, index=True)  # User who receives the message
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Review(Base):
    """Reviews between HR and candidates"""
    __tablename__ = "reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    reviewer_id = Column(Integer, index=True)  # User who writes the review
    reviewee_id = Column(Integer, index=True)  # User being reviewed
    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, default="")
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Interview(Base):
    """Video interviews/calls"""
    __tablename__ = "interviews"
    
    id = Column(Integer, primary_key=True, index=True)
    hr_id = Column(Integer, index=True)
    candidate_id = Column(Integer, index=True)
    scheduled_at = Column(DateTime, nullable=True)
    meeting_url = Column(String, default="")  # Zoom/Meet link
    status = Column(String, default="scheduled")  # scheduled, completed, cancelled
    notes = Column(Text, default="")
    recording_url = Column(String, default="")  # Link to recording
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# DATABASE SETUP
# ============================================================================

engine = create_engine(Config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# UTILITIES
# ============================================================================

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password"""
    return hash_password(password) == password_hash


def create_session_token() -> str:
    """Create unique session token"""
    return secrets.token_urlsafe(32)


def parse_pdf(file_content: bytes) -> str:
    """Parse PDF file"""
    if not PDF_SUPPORT:
        return "[PDF parsing not available - install PyPDF2]"
    
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"[Error parsing PDF: {str(e)}]"


def parse_docx(file_content: bytes) -> str:
    """Parse DOCX file"""
    if not DOCX_SUPPORT:
        return "[DOCX parsing not available - install python-docx]"
    
    try:
        doc = Document(io.BytesIO(file_content))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"[Error parsing DOCX: {str(e)}]"


def parse_resume(filename: str, file_content: bytes) -> str:
    """Parse resume based on file type"""
    ext = filename.lower().split('.')[-1]
    
    if ext == 'pdf':
        return parse_pdf(file_content)
    elif ext in ['docx', 'doc']:
        return parse_docx(file_content)
    else:
        return "[Unsupported file format]"


async def compare_resume_with_job(resume_text: str, job_description: str, candidate_skills: str = "", language: str = "ru") -> Dict[str, Any]:
    """Compare resume with job description using Ollama - Always in Russian"""
    
    # Always use Russian language for analysis
    skills_section = ""
    if candidate_skills:
        skills_section = f"""

ПОДТВЕРЖДЁННЫЕ НАВЫКИ КАНДИДАТА:
{candidate_skills}

ВАЖНО: Это навыки, которые кандидат явно подтвердил. 
Используй их как ПЕРВИЧНЫЙ ИСТОЧНИК при оценке соответствия навыков.
Помечай навыки как "совпадающие" ТОЛЬКО если они есть в этом списке подтверждённых навыков.
Если навык есть в резюме, но НЕТ в списке подтверждённых навыков, будь осторожен."""
    
    prompt = f"""Ты - эксперт HR-аналитик и карьерный консультант. Твоя задача - провести МАКСИМАЛЬНО ДЕТАЛЬНЫЙ и ТОЧНЫЙ анализ соответствия резюме кандидата описанию вакансии.

ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ. Все тексты, анализы, рекомендации и оценки должны быть ТОЛЬКО НА РУССКОМ.

ТРЕБОВАНИЯ К АНАЛИЗУ:
1. Будь максимально детальным - давай 7-10 пунктов в каждой категории
2. Будь честным и конструктивным
3. Указывай конкретные примеры из резюме
4. Давай практичные и реализуемые рекомендации
5. Анализируй не только наличие навыков, но и их глубину

Compare this resume with the job description and provide detailed analysis in JSON format.

РЕЗЮМЕ КАНДИДАТА:
{resume_text}
{skills_section}

ОПИСАНИЕ ВАКАНСИИ:
{job_description}

Проведи глубокий анализ и верни ТОЛЬКО валидный JSON со следующей структурой:
{{
    "match_score": 0-100,  // Честная оценка соответствия
    "pros": [
        "Минимум 7-10 конкретных сильных сторон кандидата для этой позиции",
        "Указывай конкретные примеры из резюме",
        "Отмечай глубину опыта и уровень владения навыками",
        "Подчеркивай уникальные достижения и преимущества"
    ],
    "cons": [
        "Минимум 7-10 конкретных пробелов или недостающих требований",
        "Указывай что именно отсутствует или недостаточно развито",
        "Отмечай несоответствия в уровне опыта",
        "Будь конструктивным и указывай пути улучшения"
    ],
    "skills_match": {{
        "matched_skills": ["Навыки кандидата, которые ТОЧНО соответствуют требованиям вакансии"],
        "missing_skills": ["Требуемые навыки, которых НЕТ в резюме"],
        "additional_skills": ["Дополнительные полезные навыки кандидата, не указанные в вакансии"]
    }},
    "experience_match": {{
        "score": 0-100,
        "analysis": "Детальный анализ опыта работы на русском языке: соответствие лет опыта, релевантность проектов, уровень ответственности, достижения. Минимум 3-4 предложения."
    }},
    "education_match": {{
        "score": 0-100,
        "analysis": "Детальный анализ образования на русском языке: соответствие специальности, уровень образования, дополнительные курсы и сертификаты. Минимум 2-3 предложения."
    }},
    "recommendations": [
        "Минимум 7-10 конкретных и практичных действий для улучшения соответствия",
        "Каждая рекомендация должна быть реализуемой и специфичной",
        "Укажи приоритетность действий",
        "Предложи конкретные курсы, сертификаты или направления развития"
    ],
    "summary": "Детальное резюме на русском языке (3-5 предложений): общая оценка кандидата, ключевые сильные стороны, основные пробелы, потенциал для позиции, рекомендация по найму"
}}

КРИТИЧЕСКИ ВАЖНО:
- ВСЕ тексты должны быть ТОЛЬКО на русском языке
- Давай ДЕТАЛЬНЫЙ анализ, а не поверхностный
- Будь ЧЕСТНЫМ в оценках
- Указывай КОНКРЕТНЫЕ примеры
- Рекомендации должны быть РЕАЛИЗУЕМЫМИ

Верни ТОЛЬКО JSON, без дополнительного текста."""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                Config.OLLAMA_API_URL,
                json={
                    "model": Config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "{}")
                
                try:
                    # Try to parse as JSON
                    analysis_data = json.loads(response_text)
                    return analysis_data
                except json.JSONDecodeError:
                    print(f"JSON decode error. Response: {response_text[:200]}")
                    return create_fallback_comparison(resume_text, job_description)
            else:
                print(f"Ollama API error: {response.status_code}")
                return create_fallback_comparison(resume_text, job_description)
                
    except Exception as e:
        print(f"Ollama connection error: {str(e)}")
        return create_fallback_comparison(resume_text, job_description)


def create_fallback_comparison(resume_text: str, job_description: str) -> Dict[str, Any]:
    """Create fallback comparison when Ollama is unavailable"""
    resume_words = set(resume_text.lower().split())
    job_words = set(job_description.lower().split())
    
    common_words = resume_words.intersection(job_words)
    match_score = min(85.0, (len(common_words) / max(len(job_words), 1)) * 100)
    
    return {
        "match_score": match_score,
        "pros": [
            "Resume format is professional and well-structured",
            "Contains relevant industry experience",
            "Demonstrates technical capabilities",
            "Shows career progression",
            "Good educational foundation"
        ],
        "cons": [
            "Some job requirements need verification",
            "Could emphasize more quantifiable achievements",
            "Additional certifications may be beneficial",
            "Some technical skills require confirmation",
            "Experience depth needs manual review"
        ],
        "skills_match": {
            "matched_skills": ["Communication", "Problem Solving", "Teamwork"],
            "missing_skills": ["Waiting for Ollama analysis"],
            "additional_skills": ["Professional experience"]
        },
        "experience_match": {
            "score": 70,
            "analysis": "Resume shows relevant experience. Full analysis requires Ollama connection."
        },
        "education_match": {
            "score": 75,
            "analysis": "Education background present. Detailed comparison requires Ollama."
        },
        "recommendations": [
            "Ensure Ollama is running: ollama serve",
            "Pull model: ollama pull gpt-oss:20b-cloud",
            "Highlight achievements with metrics",
            "Align resume keywords with job description",
            "Add relevant certifications"
        ],
        "summary": f"Basic analysis shows {match_score:.0f}% keyword match. Connect Ollama for full AI-powered analysis using gpt-oss:20b-cloud model."
    }


# ============================================================================
# TRANSLATIONS
# ============================================================================

TRANSLATIONS = {
    "en": {
        # Navigation
        "app_name": "HR Agent",
        "dashboard": "Dashboard",
        "analyze": "Analyze",
        "profile": "Profile",
        "edit_profile": "Edit Profile",
        "sign_in": "Sign in",
        "sign_out": "Sign out",
        "sign_up": "Sign up",
        "get_started": "Get Started",
        
        # Landing page
        "hero_title": "Match Your Resume<br>with Your Dream Job",
        "hero_subtitle": "AI-powered analysis that compares your resume with job descriptions. Get instant feedback on how well you match the position.",
        "match_percentage": "Match Percentage",
        "match_percentage_desc": "See exactly how well your resume aligns with job requirements. Clear percentage score with detailed breakdown.",
        "pros_cons": "Pros & Cons",
        "pros_cons_desc": "Discover your strengths for the position and areas where you need improvement. Honest, actionable feedback.",
        "skills_analysis": "Skills Analysis",
        "skills_analysis_desc": "Identify matched skills, missing requirements, and additional qualifications you bring to the table.",
        "recommendations": "Smart Recommendations",
        "recommendations_desc": "Get specific advice on improving your match score. Powered by Ollama AI (gpt-oss:20b-cloud).",
        
        # Auth
        "welcome_back": "Welcome back",
        "sign_in_subtitle": "Sign in to your HR Agent account",
        "email": "Email",
        "password": "Password",
        "create_account": "Create account",
        "create_account_subtitle": "Get started with HR Agent",
        "full_name": "Full Name",
        "already_have_account": "Already have an account?",
        "dont_have_account": "Don't have an account?",
        "create_one": "Create one",
        
        # Dashboard
        "welcome_back_user": "Welcome back",
        "total_analyses": "Total Analyses",
        "average_match": "Average Match",
        "latest_score": "Latest Score",
        "recent_analyses": "Recent Analyses",
        "new_analysis": "New Analysis",
        "analyses": "Analyses",
        "avg_match": "Avg Match",
        "latest": "Latest",
        "no_analyses": "No analyses yet.",
        "create_first": "Create your first one",
        
        # Profile
        "about": "About",
        "contact_information": "Contact Information",
        "social_links": "Social Links",
        "skills": "Skills",
        "resume": "Resume",
        "activity": "Activity",
        "job_analyses": "Job Analyses",
        "member_since": "Member Since",
        "add_skills": "Add your skills for more accurate job matching.",
        "add_skills_link": "Add skills",
        "upload": "Upload",
        "download": "Download",
        "download_resume": "Download Resume",
        "edit": "Edit",
        
        # Edit Profile
        "update_info": "Update your professional information",
        "back_to_profile": "← Back to Profile",
        "profile_picture": "Profile Picture",
        "upload_photo": "Upload Photo",
        "basic_information": "Basic Information",
        "headline": "Headline",
        "headline_placeholder": "e.g. Senior Software Engineer at Tech Company",
        "location": "Location",
        "location_placeholder": "e.g. San Francisco, CA",
        "about_placeholder": "Tell us about yourself, your experience, and what makes you unique...",
        "email_cannot_change": "Email cannot be changed",
        "phone": "Phone",
        "linkedin_profile": "LinkedIn Profile",
        "github_profile": "GitHub Profile",
        "personal_website": "Personal Website",
        "save_changes": "Save Changes",
        "your_skills": "Your Skills",
        "skills_placeholder": "Enter your skills (one per line or comma-separated)",
        "skills_note": "💡 These skills will be used for accurate job matching. Only add skills you truly possess.",
        "be_honest": "Add your actual skills for more accurate job matching. Be honest!",
        
        # Analyze
        "analyze_match": "Analyze Match",
        "analyze_subtitle": "Upload your resume and paste the job description",
        "upload_resume": "1. Upload Resume",
        "job_description": "2. Job Description",
        "pdf_or_docx": "PDF or DOCX format, max 10MB",
        "paste_job_desc": "Paste the complete job posting including all requirements",
        "click_to_upload": "Click to upload resume",
        "supported_formats": "Supported: PDF, DOCX",
        "use_profile_skills": "💡 Use Your Profile Skills",
        "use_profile_skills_desc": "You have {count} skills in your profile. Use them for more accurate matching!",
        "use_my_skills": "Use my profile skills for accurate matching",
        "use_my_skills_desc": "AI will only match skills you've confirmed in your profile",
        "add_them_now": "Add them now",
        
        # Results
        "excellent_match": "Excellent Match",
        "good_match": "Good Match",
        "needs_work": "Needs Work",
        "strengths": "Strengths",
        "areas_to_address": "Areas to Address",
        "what_makes_fit": "What makes you a great fit",
        "requirements_to_strengthen": "Requirements to strengthen",
        "matched_skills": "MATCHED SKILLS",
        "missing_skills": "MISSING SKILLS",
        "additional_skills": "ADDITIONAL SKILLS YOU BRING",
        "experience_match": "Experience Match",
        "education_match": "Education Match",
        "recommendations_title": "Recommendations",
        "actions_to_improve": "Actions to improve your match",
        "analyze_another": "Analyze Another Position",
        
        # Upload Resume
        "upload_resume_title": "Upload Resume",
        "upload_resume_subtitle": "Upload your resume to your profile for quick job matching",
        "current_resume": "Current Resume",
        "resume_uploaded": "✅ Resume uploaded successfully!",
        "add_your_skills": "Add Your Skills",
        "add_skills_subtitle": "Help us match you accurately by listing your real skills. This makes job matching more precise!",
        "why_add_skills": "Why add skills?",
        "accurate_matching": "✓ More accurate job matching",
        "ai_knows": "✓ AI will know exactly what you can do",
        "better_results": "✓ Better analysis results",
        "avoid_false": "✓ Avoid false positives",
        "save_skills": "Save Skills",
        "skip_now": "Skip for Now",
        
        # Common
        "back_to_dashboard": "← Back to Dashboard",
        "view": "View",
        "view_details": "View Details",
        "file_too_large": "File too large (max 10MB)",
        "unsupported_format": "Only PDF and DOCX files are supported",
        "error_upload": "Please upload an image file",
        "image_too_large": "Image too large (max 5MB)",
    },
    
    "ru": {
        # Навигация
        "app_name": "HR Agent",
        "dashboard": "Панель",
        "analyze": "Анализ",
        "profile": "Профиль",
        "edit_profile": "Редактировать",
        "sign_in": "Войти",
        "sign_out": "Выйти",
        "sign_up": "Регистрация",
        "get_started": "Начать",
        
        # Главная
        "hero_title": "Сравните резюме<br>с работой мечты",
        "hero_subtitle": "ИИ-анализ сравнивает ваше резюме с описанием вакансии. Мгновенная обратная связь о том, насколько вы подходите.",
        "match_percentage": "Процент соответствия",
        "match_percentage_desc": "Узнайте точно, насколько ваше резюме соответствует требованиям. Четкая оценка с детальной разбивкой.",
        "pros_cons": "Плюсы и минусы",
        "pros_cons_desc": "Узнайте ваши сильные стороны для позиции и области для улучшения. Честная и практичная обратная связь.",
        "skills_analysis": "Анализ навыков",
        "skills_analysis_desc": "Определите совпадающие навыки, недостающие требования и дополнительную квалификацию.",
        "recommendations": "Умные рекомендации",
        "recommendations_desc": "Получите конкретные советы по улучшению соответствия. Работает на Ollama AI (gpt-oss:20b-cloud).",
        
        # Авторизация
        "welcome_back": "С возвращением",
        "sign_in_subtitle": "Войдите в свой аккаунт HR Agent",
        "email": "Email",
        "password": "Пароль",
        "create_account": "Создать аккаунт",
        "create_account_subtitle": "Начните работу с HR Agent",
        "full_name": "Полное имя",
        "already_have_account": "Уже есть аккаунт?",
        "dont_have_account": "Нет аккаунта?",
        "create_one": "Создать",
        
        # Панель
        "welcome_back_user": "С возвращением",
        "total_analyses": "Всего анализов",
        "average_match": "Средний процент",
        "latest_score": "Последний",
        "recent_analyses": "Последние анализы",
        "new_analysis": "Новый анализ",
        "analyses": "Анализы",
        "avg_match": "Средний",
        "latest": "Последний",
        "no_analyses": "Пока нет анализов.",
        "create_first": "Создайте первый",
        
        # Профиль
        "about": "О себе",
        "contact_information": "Контактная информация",
        "social_links": "Социальные сети",
        "skills": "Навыки",
        "resume": "Резюме",
        "activity": "Активность",
        "job_analyses": "Анализы вакансий",
        "member_since": "Участник с",
        "add_skills": "Добавьте навыки для более точного подбора.",
        "add_skills_link": "Добавить навыки",
        "upload": "Загрузить",
        "download": "Скачать",
        "download_resume": "Скачать резюме",
        "edit": "Изменить",
        
        # Редактирование
        "update_info": "Обновите вашу профессиональную информацию",
        "back_to_profile": "← Назад к профилю",
        "profile_picture": "Фото профиля",
        "upload_photo": "Загрузить фото",
        "basic_information": "Основная информация",
        "headline": "Заголовок",
        "headline_placeholder": "Например: Senior Software Engineer в Tech Company",
        "location": "Местоположение",
        "location_placeholder": "Например: Алматы, Казахстан",
        "about_placeholder": "Расскажите о себе, своем опыте и что делает вас уникальным...",
        "email_cannot_change": "Email нельзя изменить",
        "phone": "Телефон",
        "linkedin_profile": "Профиль LinkedIn",
        "github_profile": "Профиль GitHub",
        "personal_website": "Личный сайт",
        "save_changes": "Сохранить изменения",
        "your_skills": "Ваши навыки",
        "skills_placeholder": "Введите навыки (по одному в строке или через запятую)",
        "skills_note": "💡 Эти навыки будут использованы для точного подбора. Добавляйте только реальные навыки.",
        "be_honest": "Добавьте реальные навыки для точного подбора. Будьте честны!",
        
        # Анализ
        "analyze_match": "Анализ соответствия",
        "analyze_subtitle": "Загрузите резюме и вставьте описание вакансии",
        "upload_resume": "1. Загрузите резюме",
        "job_description": "2. Описание вакансии",
        "pdf_or_docx": "PDF или DOCX, макс 10MB",
        "paste_job_desc": "Вставьте полное описание вакансии со всеми требованиями",
        "click_to_upload": "Нажмите для загрузки резюме",
        "supported_formats": "Поддерживается: PDF, DOCX",
        "use_profile_skills": "💡 Используйте навыки из профиля",
        "use_profile_skills_desc": "У вас {count} навыков в профиле. Используйте их для точного подбора!",
        "use_my_skills": "Использовать навыки из профиля",
        "use_my_skills_desc": "ИИ будет сопоставлять только подтвержденные навыки",
        "add_them_now": "Добавить сейчас",
        
        # Результаты
        "excellent_match": "Отличное соответствие",
        "good_match": "Хорошее соответствие",
        "needs_work": "Требуется работа",
        "strengths": "Сильные стороны",
        "areas_to_address": "Области для улучшения",
        "what_makes_fit": "Что делает вас подходящим",
        "requirements_to_strengthen": "Требования для усиления",
        "matched_skills": "СОВПАДАЮЩИЕ НАВЫКИ",
        "missing_skills": "НЕДОСТАЮЩИЕ НАВЫКИ",
        "additional_skills": "ДОПОЛНИТЕЛЬНЫЕ НАВЫКИ",
        "experience_match": "Соответствие опыта",
        "education_match": "Соответствие образования",
        "recommendations_title": "Рекомендации",
        "actions_to_improve": "Действия для улучшения соответствия",
        "analyze_another": "Анализировать другую позицию",
        
        # Загрузка резюме
        "upload_resume_title": "Загрузить резюме",
        "upload_resume_subtitle": "Загрузите резюме в профиль для быстрого подбора",
        "current_resume": "Текущее резюме",
        "resume_uploaded": "✅ Резюме успешно загружено!",
        "add_your_skills": "Добавьте навыки",
        "add_skills_subtitle": "Укажите реальные навыки для точного подбора. Это делает анализ более точным!",
        "why_add_skills": "Зачем добавлять навыки?",
        "accurate_matching": "✓ Более точный подбор",
        "ai_knows": "✓ ИИ будет точно знать, что вы умеете",
        "better_results": "✓ Лучшие результаты анализа",
        "avoid_false": "✓ Избежание ложных совпадений",
        "save_skills": "Сохранить навыки",
        "skip_now": "Пропустить",
        
        # Общее
        "back_to_dashboard": "← Назад к панели",
        "view": "Просмотр",
        "view_details": "Подробнее",
        "file_too_large": "Файл слишком большой (макс 10MB)",
        "unsupported_format": "Поддерживаются только PDF и DOCX файлы",
        "error_upload": "Загрузите файл изображения",
        "image_too_large": "Изображение слишком большое (макс 5MB)",
    },
    
    "kk": {
        # Навигация
        "app_name": "HR Agent",
        "dashboard": "Басты бет",
        "analyze": "Талдау",
        "profile": "Профиль",
        "edit_profile": "Өзгерту",
        "sign_in": "Кіру",
        "sign_out": "Шығу",
        "sign_up": "Тіркелу",
        "get_started": "Бастау",
        
        # Басты бет
        "hero_title": "Резюмені<br>арман жұмысымен салыстырыңыз",
        "hero_subtitle": "AI талдауы резюмеңізді жұмыс сипаттамасымен салыстырады. Позицияға қаншалықты сәйкес келетініңізді бірден біліңіз.",
        "match_percentage": "Сәйкестік пайызы",
        "match_percentage_desc": "Резюмеңіздің талаптарға қаншалықты сәйкес келетінін нақты біліңіз. Анық баға мен толық талдау.",
        "pros_cons": "Артықшылықтар мен кемшіліктер",
        "pros_cons_desc": "Позиция үшін күшті жақтарыңызды және жақсарту салаларын біліңіз. Шынайы және практикалық кері байланыс.",
        "skills_analysis": "Дағдылар талдауы",
        "skills_analysis_desc": "Сәйкес келетін дағдыларды, жетіспейтін талаптарды және қосымша біліктілікті анықтаңыз.",
        "recommendations": "Ақылды ұсыныстар",
        "recommendations_desc": "Сәйкестікті жақсарту бойынша нақты кеңестер алыңыз. Ollama AI негізінде (gpt-oss:20b-cloud).",
        
        # Авторизация
        "welcome_back": "Қош келдіңіз",
        "sign_in_subtitle": "HR Agent аккаунтыңызға кіріңіз",
        "email": "Email",
        "password": "Құпия сөз",
        "create_account": "Аккаунт құру",
        "create_account_subtitle": "HR Agent-пен жұмысты бастаңыз",
        "full_name": "Толық аты-жөні",
        "already_have_account": "Аккаунт бар ма?",
        "dont_have_account": "Аккаунт жоқ па?",
        "create_one": "Құру",
        
        # Басты бет
        "welcome_back_user": "Қош келдіңіз",
        "total_analyses": "Барлық талдаулар",
        "average_match": "Орташа пайыз",
        "latest_score": "Соңғы",
        "recent_analyses": "Соңғы талдаулар",
        "new_analysis": "Жаңа талдау",
        "analyses": "Талдаулар",
        "avg_match": "Орташа",
        "latest": "Соңғы",
        "no_analyses": "Әлі талдау жоқ.",
        "create_first": "Бірінші жасаңыз",
        
        # Профиль
        "about": "Өзім туралы",
        "contact_information": "Байланыс ақпараты",
        "social_links": "Әлеуметтік желілер",
        "skills": "Дағдылар",
        "resume": "Резюме",
        "activity": "Белсенділік",
        "job_analyses": "Жұмыс талдаулары",
        "member_since": "Мүше болған уақыт",
        "add_skills": "Дәлірек іріктеу үшін дағдыларды қосыңыз.",
        "add_skills_link": "Дағдылар қосу",
        "upload": "Жүктеу",
        "download": "Жүктеп алу",
        "download_resume": "Резюмені жүктеп алу",
        "edit": "Өзгерту",
        
        # Өңдеу
        "update_info": "Кәсіби ақпаратты жаңартыңыз",
        "back_to_profile": "← Профильге оралу",
        "profile_picture": "Профиль суреті",
        "upload_photo": "Сурет жүктеу",
        "basic_information": "Негізгі ақпарат",
        "headline": "Тақырып",
        "headline_placeholder": "Мысалы: Senior Software Engineer Tech Company-де",
        "location": "Орналасқан жер",
        "location_placeholder": "Мысалы: Алматы, Қазақстан",
        "about_placeholder": "Өзіңіз туралы, тәжірибеңіз және сізді бірегей ететін нәрсе туралы айтыңыз...",
        "email_cannot_change": "Email-ді өзгерту мүмкін емес",
        "phone": "Телефон",
        "linkedin_profile": "LinkedIn профилі",
        "github_profile": "GitHub профилі",
        "personal_website": "Жеке сайт",
        "save_changes": "Өзгерістерді сақтау",
        "your_skills": "Сіздің дағдыларыңыз",
        "skills_placeholder": "Дағдыларды енгізіңіз (әр жолдан немесе үтір арқылы)",
        "skills_note": "💡 Бұл дағдылар дәл іріктеу үшін қолданылады. Тек нақты дағдыларды қосыңыз.",
        "be_honest": "Дәл іріктеу үшін нақты дағдыларды қосыңыз. Шынайы болыңыз!",
        
        # Талдау
        "analyze_match": "Сәйкестік талдауы",
        "analyze_subtitle": "Резюмені жүктеп, жұмыс сипаттамасын қойыңыз",
        "upload_resume": "1. Резюмені жүктеу",
        "job_description": "2. Жұмыс сипаттамасы",
        "pdf_or_docx": "PDF немесе DOCX, макс 10MB",
        "paste_job_desc": "Барлық талаптармен толық жұмыс сипаттамасын қойыңыз",
        "click_to_upload": "Резюме жүктеу үшін басыңыз",
        "supported_formats": "Қолдау көрсетіледі: PDF, DOCX",
        "use_profile_skills": "💡 Профильдегі дағдыларды қолданыңыз",
        "use_profile_skills_desc": "Профильде {count} дағды бар. Дәл іріктеу үшін қолданыңыз!",
        "use_my_skills": "Профильдегі дағдыларды қолдану",
        "use_my_skills_desc": "AI тек расталған дағдыларды салыстырады",
        "add_them_now": "Қазір қосу",
        
        # Нәтижелер
        "excellent_match": "Тамаша сәйкестік",
        "good_match": "Жақсы сәйкестік",
        "needs_work": "Жұмыс қажет",
        "strengths": "Күшті жақтары",
        "areas_to_address": "Жақсартатын салалар",
        "what_makes_fit": "Сізді қандай жасайды",
        "requirements_to_strengthen": "Күшейтетін талаптар",
        "matched_skills": "СӘЙКЕС ДАҒДЫЛАР",
        "missing_skills": "ЖЕТІСПЕЙТІН ДАҒДЫЛАР",
        "additional_skills": "ҚОСЫМША ДАҒДЫЛАР",
        "experience_match": "Тәжірибе сәйкестігі",
        "education_match": "Білім сәйкестігі",
        "recommendations_title": "Ұсыныстар",
        "actions_to_improve": "Сәйкестікті жақсарту әрекеттері",
        "analyze_another": "Басқа позицияны талдау",
        
        # Резюме жүктеу
        "upload_resume_title": "Резюме жүктеу",
        "upload_resume_subtitle": "Жылдам іріктеу үшін профильге резюме жүктеңіз",
        "current_resume": "Ағымдағы резюме",
        "resume_uploaded": "✅ Резюме сәтті жүктелді!",
        "add_your_skills": "Дағдыларды қосыңыз",
        "add_skills_subtitle": "Дәл іріктеу үшін нақты дағдыларды көрсетіңіз. Бұл талдауды дәлірек етеді!",
        "why_add_skills": "Неліктен дағдыларды қосу керек?",
        "accurate_matching": "✓ Дәлірек іріктеу",
        "ai_knows": "✓ AI сіз не істей алатыныңызды нақты біледі",
        "better_results": "✓ Жақсы талдау нәтижелері",
        "avoid_false": "✓ Жалған сәйкестіктен аулақ болу",
        "save_skills": "Дағдыларды сақтау",
        "skip_now": "Өткізіп жіберу",
        
        # Жалпы
        "back_to_dashboard": "← Басты бетке оралу",
        "view": "Қарау",
        "view_details": "Толығырақ",
        "file_too_large": "Файл тым үлкен (макс 10MB)",
        "unsupported_format": "Тек PDF және DOCX файлдары қолдау көрсетіледі",
        "error_upload": "Сурет файлын жүктеңіз",
        "image_too_large": "Сурет тым үлкен (макс 5MB)",
    }
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Get translation for key in specified language"""
    translation = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
    if kwargs:
        try:
            return translation.format(**kwargs)
        except:
            return translation
    return translation


# ============================================================================
# AUTHENTICATION
# ============================================================================

async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current authenticated user"""
    if not session_token:
        return None
    
    session = db.query(Session).filter(
        Session.session_token == session_token,
        Session.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        return None
    
    user = db.query(User).filter(User.id == session.user_id).first()
    return user


def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authentication"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ============================================================================
# MINIMALIST BLACK & WHITE UI
# ============================================================================

MINIMALIST_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --black: #000000;
    --white: #ffffff;
    --gray-light: #f5f5f5;
    --gray-border: #e0e0e0;
    --gray-text: #666666;
    --success: #22c55e;
    --warning: #eab308;
    --danger: #ef4444;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--black);
    color: var(--white);
    line-height: 1.6;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
}

.nav {
    background: var(--black);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    position: sticky;
    top: 0;
    z-index: 50;
    backdrop-filter: blur(10px);
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 72px;
}

.nav-logo {
    font-size: 24px;
    font-weight: 700;
    color: var(--white);
    text-decoration: none;
    letter-spacing: -0.5px;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 32px;
}

.nav-link {
    color: rgba(255, 255, 255, 0.7);
    text-decoration: none;
    font-size: 15px;
    font-weight: 500;
    transition: color 0.2s;
}

.nav-link:hover {
    color: var(--white);
}

.notification-badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background: #ef4444;
    color: white;
    border-radius: 50%;
    width: 20px;
    height: 20px;
    font-size: 11px;
    font-weight: 700;
    display: none;
    align-items: center;
    justify-content: center;
}

.notification-badge.active {
    display: flex;
}

.notifications-dropdown {
    position: relative;
}

.notifications-panel {
    display: none;
    position: absolute;
    top: 50px;
    right: 0;
    width: 400px;
    max-height: 500px;
    overflow-y: auto;
    background: rgba(20, 20, 20, 0.98);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    z-index: 1000;
    backdrop-filter: blur(10px);
}

.notifications-panel.active {
    display: block;
}

.notification-item {
    padding: 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.notification-item:last-child {
    border-bottom: none;
}

.notification-links {
    display: flex;
    gap: 8px;
    margin-top: 12px;
}

.notification-link-btn {
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    color: var(--white);
    text-decoration: none;
    font-size: 13px;
    transition: all 0.2s;
}

.notification-link-btn:hover {
    background: rgba(255, 255, 255, 0.2);
}

.dismiss-btn {
    padding: 8px 16px;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    color: #ef4444;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
}

.dismiss-btn:hover {
    background: rgba(239, 68, 68, 0.2);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 64px 32px;
}

.container-sm {
    max-width: 600px;
    margin: 0 auto;
    padding: 64px 32px;
}

.hero {
    text-align: center;
    padding: 120px 32px 80px;
}

.hero h1 {
    font-size: 64px;
    font-weight: 700;
    margin-bottom: 24px;
    letter-spacing: -2px;
    line-height: 1.1;
}

.hero p {
    font-size: 20px;
    color: rgba(255, 255, 255, 0.7);
    max-width: 600px;
    margin: 0 auto 48px;
    line-height: 1.6;
}

.card {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 40px;
    backdrop-filter: blur(10px);
    margin-bottom: 24px;
}

.card:hover {
    border-color: rgba(255, 255, 255, 0.2);
    transition: border-color 0.3s;
}

h1 {
    font-size: 40px;
    font-weight: 700;
    margin-bottom: 16px;
    letter-spacing: -1px;
}

h2 {
    font-size: 32px;
    font-weight: 600;
    margin-bottom: 16px;
    letter-spacing: -0.5px;
}

h3 {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 16px;
}

.text-muted {
    color: rgba(255, 255, 255, 0.6);
}

.text-sm {
    font-size: 14px;
}

.text-xs {
    font-size: 12px;
}

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 14px 32px;
    font-size: 15px;
    font-weight: 600;
    border-radius: 12px;
    border: 2px solid var(--white);
    background: var(--white);
    color: var(--black);
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    gap: 8px;
}

.btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(255, 255, 255, 0.2);
}

.btn-outline {
    background: transparent;
    color: var(--white);
}

.btn-outline:hover {
    background: var(--white);
    color: var(--black);
}

.btn-large {
    padding: 18px 40px;
    font-size: 16px;
}

.btn-block {
    display: flex;
    width: 100%;
}

.form-group {
    margin-bottom: 24px;
}

.form-label {
    display: block;
    font-weight: 600;
    margin-bottom: 12px;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.form-control {
    width: 100%;
    padding: 16px 20px;
    font-size: 15px;
    color: var(--white);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    outline: none;
    transition: all 0.2s;
    font-family: inherit;
}

.form-control:focus {
    border-color: var(--white);
    background: rgba(255, 255, 255, 0.08);
}

textarea.form-control {
    min-height: 240px;
    resize: vertical;
    line-height: 1.6;
}

.alert {
    padding: 20px 24px;
    border-radius: 12px;
    margin-bottom: 24px;
    border: 1px solid;
}

.alert-success {
    background: rgba(34, 197, 94, 0.1);
    border-color: var(--success);
    color: var(--success);
}

.alert-error {
    background: rgba(239, 68, 68, 0.1);
    border-color: var(--danger);
    color: var(--danger);
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 24px;
    margin-bottom: 48px;
}

.stat-card {
    background: var(--white);
    color: var(--black);
    border-radius: 16px;
    padding: 32px;
    text-align: center;
}

.stat-value {
    font-size: 48px;
    font-weight: 700;
    margin-bottom: 8px;
    letter-spacing: -1px;
}

.stat-label {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.7;
}

.score-display {
    text-align: center;
    padding: 48px;
}

.score-circle {
    width: 180px;
    height: 180px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin: 0 auto 32px;
    border: 8px solid;
    position: relative;
}

.score-circle.excellent {
    background: rgba(34, 197, 94, 0.1);
    border-color: var(--success);
    color: var(--success);
}

.score-circle.good {
    background: rgba(234, 179, 8, 0.1);
    border-color: var(--warning);
    color: var(--warning);
}

.score-circle.poor {
    background: rgba(239, 68, 68, 0.1);
    border-color: var(--danger);
    color: var(--danger);
}

.score-value {
    font-size: 56px;
    font-weight: 700;
    letter-spacing: -2px;
}

.score-label {
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.8;
}

.grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 24px;
}

.feature-list {
    list-style: none;
}

.feature-item {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 16px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.feature-item:last-child {
    border-bottom: none;
}

.feature-icon {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    font-weight: 700;
}

.feature-icon.pro {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success);
}

.feature-icon.con {
    background: rgba(239, 68, 68, 0.2);
    color: var(--danger);
}

.feature-icon.tip {
    background: rgba(255, 255, 255, 0.1);
    color: var(--white);
}

.badge {
    display: inline-flex;
    align-items: center;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 600;
    border-radius: 8px;
    margin: 4px;
}

.badge-success {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success);
    border: 1px solid var(--success);
}

.badge-warning {
    background: rgba(234, 179, 8, 0.2);
    color: var(--warning);
    border: 1px solid var(--warning);
}

.badge-info {
    background: rgba(255, 255, 255, 0.1);
    color: var(--white);
    border: 1px solid rgba(255, 255, 255, 0.2);
}

.table {
    width: 100%;
    border-collapse: collapse;
}

.table th {
    text-align: left;
    padding: 16px 12px;
    font-weight: 600;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.6);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.table td {
    padding: 20px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.table tr:last-child td {
    border-bottom: none;
}

.file-upload {
    border: 2px dashed rgba(255, 255, 255, 0.2);
    border-radius: 16px;
    padding: 64px 32px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s;
    background: rgba(255, 255, 255, 0.02);
}

.file-upload:hover {
    border-color: var(--white);
    background: rgba(255, 255, 255, 0.05);
}

.file-upload input {
    display: none;
}

.file-icon {
    font-size: 56px;
    margin-bottom: 24px;
    opacity: 0.6;
}

.progress-bar {
    width: 100%;
    height: 12px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    overflow: hidden;
    margin: 16px 0;
}

.progress-fill {
    height: 100%;
    background: var(--white);
    border-radius: 6px;
    transition: width 0.5s;
}

.section {
    margin-bottom: 40px;
}

.divider {
    height: 1px;
    background: rgba(255, 255, 255, 0.1);
    margin: 40px 0;
}

.flex-between {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

@media (max-width: 768px) {
    .hero h1 {
        font-size: 40px;
    }
    
    .hero p {
        font-size: 16px;
    }
    
    .nav-container {
        padding: 0 16px;
    }
    
    .container {
        padding: 40px 16px;
    }
    
    .card {
        padding: 24px;
    }
    
    .grid-2 {
        grid-template-columns: 1fr;
    }
    
    .stats-grid {
        grid-template-columns: 1fr;
    }
}
"""


def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Generate base HTML"""
    
    # Always use Russian language
    lang = "ru"
    
    if user:
        # Different navigation for HR and Candidates
        if user.role == "hr":
            nav_links = f"""
                <a href="/dashboard" class="nav-link">Панель</a>
                <a href="/candidates" class="nav-link">Кандидаты</a>
                <a href="/profile" class="nav-link">{user.full_name}</a>
                <a href="/logout" class="nav-link">Выйти</a>
            """
        else:  # candidate
            nav_links = f"""
                <a href="/dashboard" class="nav-link">{t('dashboard', lang)}</a>
                <a href="/analyze" class="nav-link">{t('analyze', lang)}</a>
                <div class="notifications-dropdown" style="position: relative;">
                    <button class="nav-link" onclick="toggleNotifications()" style="background: none; border: none; cursor: pointer; position: relative;">
                        🔔
                        <span class="notification-badge" id="notification-count"></span>
                    </button>
                    <div class="notifications-panel" id="notificationsPanel"></div>
                </div>
                <a href="/profile" class="nav-link">{user.full_name}</a>
                <a href="/logout" class="nav-link">{t('sign_out', lang)}</a>
            """
    else:
        nav_links = f"""
            <a href="/login" class="nav-link">Войти</a>
            <a href="/register" class="btn">Начать</a>
        """
    
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - HR Agent</title>
    <style>{MINIMALIST_CSS}</style>
</head>
<body>
    <nav class="nav">
        <div class="nav-container">
            <a href="/" class="nav-logo">HR Agent</a>
            <div class="nav-links">
                {nav_links}
            </div>
        </div>
    </nav>
    <main>
        {content}
    </main>
    <script>
        // Notifications system
        let notificationsOpen = false;
        
        function toggleNotifications() {{
            const panel = document.getElementById('notificationsPanel');
            notificationsOpen = !notificationsOpen;
            
            if (notificationsOpen) {{
                panel.classList.add('active');
                loadNotifications();
            }} else {{
                panel.classList.remove('active');
            }}
        }}
        
        function loadNotifications() {{
            fetch('/api/my-requests')
                .then(r => r.json())
                .then(data => {{
                    const panel = document.getElementById('notificationsPanel');
                    
                    if (data.requests.length === 0) {{
                        panel.innerHTML = '<div style="padding: 40px; text-align: center; color: #666;">Уведомлений пока нет</div>';
                        return;
                    }}
                    
                    let html = '<div style="padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.1);"><strong>Запросы от HR</strong></div>';
                    
                    data.requests.forEach(req => {{
                        let whatsappLink = '';
                        if (req.whatsapp) {{
                            const whatsappUrl = req.whatsapp.startsWith('http') ? req.whatsapp : 'https://wa.me/' + req.whatsapp;
                            whatsappLink = '<a href="' + whatsappUrl + '" target="_blank" class="notification-link-btn">WhatsApp</a>';
                        }}
                        
                        let instagramLink = '';
                        if (req.instagram) {{
                            const instagramUrl = req.instagram.startsWith('http') ? req.instagram : 'https://instagram.com/' + req.instagram;
                            instagramLink = '<a href="' + instagramUrl + '" target="_blank" class="notification-link-btn">Instagram</a>';
                        }}
                        
                        let linkedinLink = '';
                        if (req.linkedin) {{
                            linkedinLink = '<a href="' + req.linkedin + '" target="_blank" class="notification-link-btn">LinkedIn</a>';
                        }}
                        
                        html += '<div class="notification-item">' +
                            '<strong>' + req.hr_name + '</strong>' +
                            '<p class="text-muted text-xs" style="margin: 4px 0 12px 0;">' + req.hr_headline + '</p>' +
                            '<p class="text-sm" style="margin-bottom: 12px;">' + req.message + '</p>' +
                            '<div class="notification-links">' +
                                whatsappLink + instagramLink + linkedinLink +
                                '<button class="dismiss-btn" onclick="dismissRequest(' + req.id + ')">Отменить</button>' +
                            '</div>' +
                            '<p class="text-muted text-xs" style="margin-top: 12px;">' + req.created_at + '</p>' +
                        '</div>';
                    }});
                    
                    panel.innerHTML = html;
                }});
        }}
        
        function dismissRequest(id) {{
            if (!confirm('Отменить этот запрос?')) return;
            
            fetch('/api/dismiss-request/' + id, {{ method: 'POST' }})
                .then(r => r.json())
                .then(() => {{
                    loadNotifications();
                    updateNotificationCount();
                }});
        }}
        
        function updateNotificationCount() {{
            fetch('/api/notifications-count')
                .then(r => r.json())
                .then(data => {{
                    const badge = document.getElementById('notification-count');
                    if (data.count > 0) {{
                        badge.textContent = data.count;
                        badge.classList.add('active');
                    }} else {{
                        badge.classList.remove('active');
                    }}
                }});
        }}
        
        // Close notifications when clicking outside
        document.addEventListener('click', function(event) {{
            const dropdown = document.querySelector('.notifications-dropdown');
            if (dropdown && !dropdown.contains(event.target)) {{
                document.getElementById('notificationsPanel').classList.remove('active');
                notificationsOpen = false;
            }}
        }});
        
        // Update count on page load
        if (document.getElementById('notification-count')) {{
            updateNotificationCount();
            setInterval(updateNotificationCount, 30000); // Update every 30 seconds
        }}
    </script>
</body>
</html>"""


# ============================================================================
# PAGE TEMPLATES
# ============================================================================

def landing_page() -> str:
    """Landing page - Russian only"""
    content = """
    <div class="hero">
        <h1>Сравните резюме<br>с работой мечты</h1>
        <p>ИИ-анализ сравнивает ваше резюме с описанием вакансии. Мгновенная обратная связь о том, насколько вы подходите на позицию.</p>
        <div style="display: flex; gap: 16px; justify-content: center;">
            <a href="/register" class="btn btn-large">Начать</a>
            <a href="/login" class="btn btn-outline btn-large">Войти</a>
        </div>
    </div>
    
    <div class="container">
        <div class="grid-2">
            <div class="card">
                <h3>Процент соответствия</h3>
                <p class="text-muted">Узнайте точно, насколько ваше резюме соответствует требованиям вакансии. Четкая оценка с детальной разбивкой.</p>
            </div>
            
            <div class="card">
                <h3>Плюсы и минусы</h3>
                <p class="text-muted">Узнайте ваши сильные стороны для позиции и области для улучшения. Честная и практичная обратная связь.</p>
            </div>
            
            <div class="card">
                <h3>Анализ навыков</h3>
                <p class="text-muted">Определите совпадающие навыки, недостающие требования и дополнительную квалификацию, которую вы можете предложить.</p>
            </div>
            
            <div class="card">
                <h3>Умные рекомендации</h3>
                <p class="text-muted">Получите конкретные советы по улучшению соответствия. Работает на Ollama AI (gpt-oss:20b-cloud).</p>
            </div>
        </div>
    </div>
    """
    return get_base_html("Главная", content)


def login_page(error: str = "") -> str:
    """Login page - Russian only"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <div class="card">
            <h2>С возвращением</h2>
            <p class="text-muted" style="margin-bottom: 32px;">Войдите в свой аккаунт HR Agent</p>
            
            {error_html}
            
            <form method="POST" action="/login">
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required placeholder="ваш@email.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Пароль</label>
                    <input type="password" name="password" class="form-control" required placeholder="••••••••">
                </div>
                
                <button type="submit" class="btn btn-block btn-large">Войти</button>
            </form>
            
            <div class="divider"></div>
            
            <p class="text-muted text-sm" style="text-align: center;">
                Нет аккаунта? <a href="/register" style="color: var(--white); text-decoration: underline;">Создать</a>
            </p>
        </div>
    </div>
    """
    return get_base_html("Вход", content)


def register_page(error: str = "") -> str:
    """Register page - Russian only"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <div class="card">
            <h2>Создать аккаунт</h2>
            <p class="text-muted" style="margin-bottom: 32px;">Начните работу с HR Agent</p>
            
            {error_html}
            
            <form method="POST" action="/register">
                <div class="form-group">
                    <label class="form-label">Я регистрируюсь как:</label>
                    <div style="display: flex; gap: 16px; margin-top: 12px;">
                        <label style="flex: 1; cursor: pointer;">
                            <input type="radio" name="role" value="candidate" checked required style="margin-right: 8px;">
                            <span style="font-weight: 500;">👤 Кандидат</span>
                            <p class="text-muted text-xs" style="margin: 4px 0 0 24px;">Ищу работу, хочу анализировать резюме</p>
                        </label>
                        <label style="flex: 1; cursor: pointer;">
                            <input type="radio" name="role" value="hr" required style="margin-right: 8px;">
                            <span style="font-weight: 500;">💼 HR-специалист</span>
                            <p class="text-muted text-xs" style="margin: 4px 0 0 24px;">Ищу кандидатов для вакансий</p>
                        </label>
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Полное имя</label>
                    <input type="text" name="full_name" class="form-control" required placeholder="Иван Иванов">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required placeholder="ваш@email.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Пароль</label>
                    <input type="password" name="password" class="form-control" required minlength="6" placeholder="Минимум 6 символов">
                </div>
                
                <button type="submit" class="btn btn-block btn-large">Создать аккаунт</button>
            </form>
            
            <div class="divider"></div>
            
            <p class="text-muted text-sm" style="text-align: center;">
                Уже есть аккаунт? <a href="/login" style="color: var(--white); text-decoration: underline;">Войти</a>
            </p>
        </div>
    </div>
    """
    return get_base_html("Регистрация", content)


def hr_dashboard_page(user: User, db: Session) -> str:
    """HR Dashboard - Russian only"""
    lang = "ru"
    
    # Statistics for HR
    total_candidates = db.query(User).filter(User.role == "candidate", User.resume_file != "").count()
    my_requests = db.query(Request).filter(Request.hr_id == user.id).count()
    
    # Recent requests
    recent_requests = db.query(Request).filter(
        Request.hr_id == user.id
    ).order_by(Request.created_at.desc()).limit(5).all()
    
    requests_html = ""
    for req in recent_requests:
        candidate = db.query(User).filter(User.id == req.candidate_id).first()
        if candidate:
            status_badge = "badge-success" if req.status == "viewed" else "badge-warning"
            requests_html += f"""
            <div style="padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>{candidate.full_name}</strong>
                        <p class="text-muted text-xs" style="margin: 4px 0;">{req.created_at.strftime('%d.%m.%Y %H:%M')}</p>
                    </div>
                    <span class="{status_badge}">{req.status}</span>
                </div>
            </div>
            """
    
    if not requests_html:
        requests_html = '<p class="text-muted" style="padding: 20px; text-align: center;">Запросов пока нет</p>'
    
    content = f"""
    <div class="container">
        <div class="flex-between" style="margin-bottom: 48px;">
            <div>
                <h1>Панель HR-специалиста</h1>
                <p class="text-muted">Добро пожаловать, {user.full_name}</p>
            </div>
            <a href="/candidates" class="btn btn-large">Найти кандидатов</a>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_candidates}</div>
                <div class="stat-label">Кандидатов в базе</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{my_requests}</div>
                <div class="stat-label">Моих запросов</div>
            </div>
        </div>
        
        <div class="card">
            <h3 style="margin-bottom: 24px;">Последние запросы</h3>
            {requests_html}
        </div>
    </div>
    """
    return get_base_html("Панель HR", content, user)


def dashboard_page(user: User, db: Session) -> str:
    """Dashboard page - Russian only"""
    
    # Route to HR or Candidate dashboard
    if user.role == "hr":
        return hr_dashboard_page(user, db)
    
    # Candidate dashboard
    lang = "ru"  # Always Russian
    
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    recent_analyses = db.query(Analysis).filter(
        Analysis.user_id == user.id
    ).order_by(Analysis.created_at.desc()).limit(10).all()
    
    avg_score = db.query(Analysis).filter(
        Analysis.user_id == user.id,
        Analysis.match_score.isnot(None)
    ).all()
    
    avg_score_value = sum([a.match_score for a in avg_score]) / len(avg_score) if avg_score else 0
    latest_score = recent_analyses[0].match_score if recent_analyses else 0
    
    recent_list = ""
    for analysis in recent_analyses:
        if analysis.match_score >= 70:
            badge_class = "badge-success"
        elif analysis.match_score >= 50:
            badge_class = "badge-warning"
        else:
            badge_class = "badge-warning"
        
        recent_list += f"""
        <tr>
            <td>
                <strong>{analysis.filename}</strong>
                <div class="text-muted text-xs">{analysis.created_at.strftime('%b %d, %Y at %H:%M')}</div>
            </td>
            <td><span class="{badge_class}">{analysis.match_score:.0f}%</span></td>
            <td><a href="/result/{analysis.id}" class="btn btn-outline" style="padding: 8px 20px;">{t('view', lang)}</a></td>
        </tr>
        """
    
    if not recent_list:
        recent_list = f'<tr><td colspan="3" style="text-align: center;" class="text-muted">{t("no_analyses", lang)} <a href="/analyze" style="color: var(--white); text-decoration: underline;">{t("create_first", lang)}</a></td></tr>'
    
    content = f"""
    <div class="container">
        <div class="flex-between" style="margin-bottom: 48px;">
            <div>
                <h1>{t('dashboard', lang)}</h1>
                <p class="text-muted">{t('welcome_back_user', lang)}, {user.full_name}</p>
            </div>
            <a href="/analyze" class="btn btn-large">{t('new_analysis', lang)}</a>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_analyses}</div>
                <div class="stat-label">{t('analyses', lang)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{avg_score_value:.0f}%</div>
                <div class="stat-label">{t('avg_match', lang)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{latest_score:.0f}%</div>
                <div class="stat-label">{t('latest', lang)}</div>
            </div>
        </div>
        
        <div class="card">
            <h3 style="margin-bottom: 24px;">{t('recent_analyses', lang)}</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>{t('resume', lang)}</th>
                        <th>Score</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {recent_list}
                </tbody>
            </table>
        </div>
    </div>
    """
    return get_base_html(t('dashboard', lang), content, user)


def hr_profile_page(user: User, db: Session) -> str:
    """HR-specialist profile page"""
    
    # Get HR's jobs
    jobs = db.query(Job).filter(Job.hr_id == user.id, Job.is_active == True).all()
    
    # Get reviews
    reviews = db.query(Review).filter(Review.reviewee_id == user.id, Review.is_public == True).order_by(Review.created_at.desc()).limit(5).all()
    
    jobs_html = ""
    for job in jobs:
        jobs_html += f'''
        <div class="card" style="margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <h3 style="margin-bottom: 8px;">{job.title}</h3>
                    <p class="text-muted text-sm">{job.location or "Удаленно"} • {job.employment_type} • {job.salary_range or "По договоренности"}</p>
                    <p style="margin-top: 12px;">{job.description[:200]}...</p>
                </div>
                <div style="display: flex; gap: 8px;">
                    <a href="/job/{job.id}/edit" class="btn btn-outline btn-sm">Редактировать</a>
                    <form method="POST" action="/job/{job.id}/delete" style="display: inline;">
                        <button type="submit" class="btn btn-outline btn-sm" style="color: #ef4444;">Удалить</button>
                    </form>
                </div>
            </div>
        </div>
        '''
    
    if not jobs_html:
        jobs_html = '<p class="text-muted" style="text-align: center; padding: 40px;">Вакансий пока нет</p>'
    
    reviews_html = ""
    for review in reviews:
        reviewer = db.query(User).filter(User.id == review.reviewer_id).first()
        if reviewer:
            stars = "⭐" * review.rating + "☆" * (5 - review.rating)
            reviews_html += f'''
            <div style="padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                <div style="display: flex; justify-content: space-between;">
                    <strong>{reviewer.full_name}</strong>
                    <span>{stars}</span>
                </div>
                <p class="text-sm" style="margin-top: 8px;">{review.comment}</p>
                <p class="text-muted text-xs" style="margin-top: 8px;">{review.created_at.strftime("%d.%m.%Y")}</p>
            </div>
            '''
    
    if not reviews_html:
        reviews_html = '<p class="text-muted" style="text-align: center; padding: 20px;">Отзывов пока нет</p>'
    
    avatar = f'<img src="/uploads/avatars/{user.avatar}" style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid rgba(255,255,255,0.2);">' if user.avatar else f'<div style="width: 120px; height: 120px; border-radius: 50%; background: var(--white); color: var(--black); display: flex; align-items: center; justify-content: center; font-size: 48px; font-weight: 700;">{user.full_name[0].upper()}</div>'
    
    rating_stars = "⭐" * int(user.average_rating) + "☆" * (5 - int(user.average_rating)) if user.average_rating > 0 else "☆☆☆☆☆"
    
    content = f"""
    <div class="container">
        <div class="card">
            <div style="display: flex; gap: 32px; align-items: start;">
                {avatar}
                <div style="flex: 1;">
                    <h1 style="margin-bottom: 8px;">{user.full_name}</h1>
                    <p class="text-muted" style="margin-bottom: 8px; font-size: 18px;">HR-специалист{" • " + user.company_name if user.company_name else ""}</p>
                    <p class="text-muted" style="margin-bottom: 16px;">📍 {user.location or "Не указано"}</p>
                    <div style="margin-bottom: 16px;">
                        {rating_stars} <span class="text-muted">({user.average_rating:.1f} / {user.total_reviews} отзывов)</span>
                    </div>
                    <a href="/profile/edit" class="btn btn-outline">Редактировать профиль</a>
                </div>
            </div>
        </div>
        
        {f'<div class="card"><h3 style="margin-bottom: 16px;">О компании</h3><p style="line-height: 1.8;">{user.company_description}</p></div>' if user.company_description else ''}
        
        {f'<div class="card"><h3 style="margin-bottom: 16px;">О себе</h3><p style="line-height: 1.8;">{user.bio}</p></div>' if user.bio else ''}
        
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <h3>Активные вакансии ({len(jobs)})</h3>
                <a href="/jobs/create" class="btn btn-primary">+ Добавить вакансию</a>
            </div>
            {jobs_html}
        </div>
        
        <div class="card">
            <h3 style="margin-bottom: 24px;">Отзывы ({user.total_reviews})</h3>
            {reviews_html}
        </div>
        
        <div class="card">
            <h3 style="margin-bottom: 16px;">Контакты</h3>
            <p><strong>Email:</strong> {user.email}</p>
            {f'<p style="margin-top: 8px;"><strong>Телефон:</strong> {user.phone}</p>' if user.phone else ''}
            {f'<p style="margin-top: 8px;"><strong>WhatsApp:</strong> {user.whatsapp}</p>' if user.whatsapp else ''}
            {f'<p style="margin-top: 8px;"><strong>Instagram:</strong> {user.instagram}</p>' if user.instagram else ''}
            {f'<p style="margin-top: 8px;"><strong>LinkedIn:</strong> <a href="{user.linkedin_url}" target="_blank">{user.linkedin_url}</a></p>' if user.linkedin_url else ''}
        </div>
    </div>
    """
    return get_base_html("Профиль HR", content, user)


def profile_page(user: User, db: Session) -> str:
    """Profile page router - Russian only"""
    
    # Route to different profile based on role
    if user.role == "hr":
        return hr_profile_page(user, db)
    
    # Candidate profile
    lang = "ru"  # Always Russian
    
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    
    # Avatar display
    avatar_url = f"/uploads/avatars/{user.avatar}" if user.avatar else ""
    avatar_html = f'<img src="{avatar_url}" alt="Avatar" class="profile-avatar">' if user.avatar else '<div class="profile-avatar-placeholder">{user.full_name[0].upper()}</div>'
    
    # Resume download
    resume_html = ""
    if user.resume_file:
        resume_html = f'<a href="/download-resume" class="btn btn-outline" style="padding: 8px 20px;">📄 Download Resume</a>'
    
    # Social links
    social_links = ""
    if user.linkedin_url:
        social_links += f'<a href="{user.linkedin_url}" target="_blank" class="social-link">LinkedIn</a>'
    if user.github_url:
        social_links += f'<a href="{user.github_url}" target="_blank" class="social-link">GitHub</a>'
    if user.website:
        social_links += f'<a href="{user.website}" target="_blank" class="social-link">Website</a>'
    
    content = f"""
    <div class="container">
        <!-- Profile Header Card -->
        <div class="profile-header-card">
            <div class="profile-cover"></div>
            <div class="profile-header-content">
                <div class="profile-avatar-section">
                    {avatar_html}
                </div>
                <div class="profile-header-info">
                    <h1 style="font-size: 32px; margin-bottom: 8px;">{user.full_name}</h1>
                    <p class="profile-headline">{user.headline or 'Add your headline'}</p>
                    <p class="text-muted text-sm">{user.location or 'Add your location'} • {total_analyses} analyses</p>
                    <div class="profile-actions">
                        <a href="/edit-profile" class="btn btn-primary">Edit Profile</a>
                        {resume_html}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="grid-2" style="align-items: start;">
            <!-- Left Column -->
            <div>
                <!-- About Section -->
                <div class="card">
                    <div class="flex-between" style="margin-bottom: 20px;">
                        <h3>About</h3>
                        <a href="/edit-profile#about" class="btn btn-outline" style="padding: 6px 16px;">Edit</a>
                    </div>
                    <p class="text-muted">{user.bio or 'Tell us about yourself, your experience, and what makes you unique.'}</p>
                </div>
                
                <!-- Contact Section -->
                <div class="card">
                    <h3 style="margin-bottom: 20px;">Contact Information</h3>
                    <div class="contact-info">
                        <div class="contact-item">
                            <span class="contact-label">Email</span>
                            <span class="contact-value">{user.email}</span>
                        </div>
                        {f'<div class="contact-item"><span class="contact-label">Phone</span><span class="contact-value">{user.phone}</span></div>' if user.phone else ''}
                    </div>
                </div>
                
                <!-- Social Links -->
                {f'<div class="card"><h3 style="margin-bottom: 20px;">Social Links</h3><div style="display: flex; gap: 12px; flex-wrap: wrap;">{social_links}</div></div>' if social_links else ''}
            </div>
            
            <!-- Right Column -->
            <div>
                <!-- Skills Section -->
                <div class="card">
                    <div class="flex-between" style="margin-bottom: 20px;">
                        <h3>Skills</h3>
                        <a href="/edit-profile#skills" class="btn btn-outline" style="padding: 6px 16px;">Edit</a>
                    </div>
                    {f'<div class="skills-list">{" ".join([f"<span class=\"skill-tag\">{skill.strip()}</span>" for skill in user.skills.replace(",", "\n").split("\n") if skill.strip()])}</div>' if user.skills else '<p class="text-muted">Add your skills for more accurate job matching. <a href="/edit-profile" style="color: var(--white); text-decoration: underline;">Add skills</a></p>'}
                </div>
                
                <!-- Resume Section -->
                <div class="card">
                    <div class="flex-between" style="margin-bottom: 20px;">
                        <h3>Resume</h3>
                        <a href="/upload-resume-profile" class="btn btn-outline" style="padding: 6px 16px;">Upload</a>
                    </div>
                    {f'<div class="resume-preview"><p>📄 {user.resume_file.split("/")[-1] if "/" in user.resume_file else user.resume_file}</p><a href="/download-resume" class="btn btn-outline" style="padding: 6px 16px; margin-top: 12px;">Download</a></div>' if user.resume_file else '<p class="text-muted">Upload your resume to use it for quick job matching</p>'}
                </div>
                
                <!-- Stats Section -->
                <div class="card">
                    <h3 style="margin-bottom: 20px;">Activity</h3>
                    <div class="stat-item">
                        <span class="stat-item-value">{total_analyses}</span>
                        <span class="stat-item-label">Job Analyses</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-item-value">{user.created_at.strftime('%b %Y')}</span>
                        <span class="stat-item-label">Member Since</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <style>
        .profile-header-card {{
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        overflow: hidden;
        margin-bottom: 24px;
    }}
    
    .profile-cover {{
        height: 120px;
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
    }}
    
    .profile-header-content {{
        padding: 0 40px 32px;
        position: relative;
    }}
    
    .profile-avatar-section {{
        margin-top: -60px;
        margin-bottom: 16px;
    }}
    
    .profile-avatar {{
        width: 140px;
        height: 140px;
        border-radius: 50%;
        border: 4px solid var(--black);
        object-fit: cover;
    }}
    
    .profile-avatar-placeholder {{
        width: 140px;
        height: 140px;
        border-radius: 50%;
        border: 4px solid var(--black);
        background: var(--white);
        color: var(--black);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 48px;
        font-weight: 700;
    }}
    
    .profile-headline {{
        font-size: 18px;
        margin-bottom: 8px;
        color: rgba(255,255,255,0.9);
    }}
    
    .profile-actions {{
        display: flex;
        gap: 12px;
        margin-top: 20px;
    }}
    
    .contact-info {{
        display: flex;
        flex-direction: column;
        gap: 16px;
    }}
    
    .contact-item {{
        display: flex;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }}
    
    .contact-item:last-child {{
        border-bottom: none;
    }}
    
    .contact-label {{
        color: rgba(255,255,255,0.6);
        font-size: 14px;
    }}
    
    .contact-value {{
        font-weight: 500;
    }}
    
    .social-link {{
        padding: 8px 16px;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        text-decoration: none;
        color: var(--white);
        font-size: 14px;
        transition: all 0.2s;
    }}
    
    .social-link:hover {{
        background: rgba(255,255,255,0.1);
        border-color: var(--white);
    }}
    
    .resume-preview {{
        background: rgba(255,255,255,0.05);
        padding: 20px;
        border-radius: 8px;
        text-align: center;
    }}
    
    .stat-item {{
        display: flex;
        justify-content: space-between;
        padding: 16px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }}
    
    .stat-item:last-child {{
        border-bottom: none;
    }}
    
    .stat-item-value {{
        font-size: 20px;
        font-weight: 600;
    }}
    
    .stat-item-label {{
        color: rgba(255,255,255,0.6);
        font-size: 14px;
    }}
    
    .skills-list {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }}
    
    .skill-tag {{
        display: inline-block;
        padding: 6px 12px;
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        border-radius: 6px;
        font-size: 13px;
        color: var(--white);
    }}
    </style>
    """
    return get_base_html("Profile", content, user)


def edit_profile_page(user: User, error: str = "", success: str = "") -> str:
    """Edit profile page - Russian only"""
    lang = "ru"  # Always Russian
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    success_html = f'<div class="alert alert-success">{success}</div>' if success else ""
    
    # Different sections for HR vs Candidate
    if user.role == "hr":
        profile_sections = f"""
        <div class="card">
            <h3 style="margin-bottom: 20px;">Информация о компании</h3>
            <div class="form-group">
                <label class="form-label">Название компании</label>
                <input type="text" name="company_name" class="form-control" value="{user.company_name or ''}" placeholder="ТОО TechCorp">
            </div>
            <div class="form-group">
                <label class="form-label">О компании</label>
                <textarea name="company_description" class="form-control" style="min-height: 150px;" placeholder="Опишите вашу компанию, миссию, ценности...">{user.company_description or ''}</textarea>
            </div>
        </div>
        """
    else:
        profile_sections = f"""
        <!-- Skills Section -->
        <div class="card" id="skills">
            <h3 style="margin-bottom: 20px;">Навыки</h3>
            <p class="text-muted text-sm" style="margin-bottom: 16px;">Добавьте реальные навыки для точного поиска вакансий</p>
            <div class="form-group">
                <label class="form-label">Ваши навыки</label>
                <textarea name="skills" class="form-control" placeholder="Введите навыки (через запятую или с новой строки):

Примеры:
React.js, Node.js, TypeScript
Python, Django, FastAPI
HTML, CSS, JavaScript, Bootstrap
Git, Docker, Kubernetes
Problem Solving, Team Leadership, Agile" style="min-height: 180px;">{user.skills or ''}</textarea>
                <p class="text-muted text-xs" style="margin-top: 8px;">💡 Эти навыки будут использоваться для точного поиска. Добавляйте только те, которыми реально владеете.</p>
            </div>
        </div>
        """
    
    content = f"""
    <div class="container-sm">
        <div style="margin-bottom: 32px;">
            <a href="/profile" class="btn btn-outline">← Назад к профилю</a>
        </div>
        
        <h1>Редактировать профиль</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Обновите вашу информацию</p>
        
        {error_html}
        {success_html}
        
        <!-- Avatar Upload -->
        <div class="card">
            <h3 style="margin-bottom: 20px;">Фото профиля</h3>
            <form method="POST" action="/upload-avatar" enctype="multipart/form-data" style="display: flex; align-items: center; gap: 24px;">
                <div>
                    {f'<img src="/uploads/avatars/{user.avatar}" alt="Avatar" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(255,255,255,0.2);">' if user.avatar else f'<div style="width: 100px; height: 100px; border-radius: 50%; background: var(--white); color: var(--black); display: flex; align-items: center; justify-content: center; font-size: 36px; font-weight: 700;">{user.full_name[0].upper()}</div>'}
                </div>
                <div style="flex: 1;">
                    <input type="file" name="avatar" accept="image/*" class="form-control" style="margin-bottom: 12px;">
                    <button type="submit" class="btn btn-primary">Загрузить фото</button>
                </div>
            </form>
        </div>
        
        <!-- Basic Information -->
        <form method="POST" action="/update-profile">
            <div class="card">
                <h3 style="margin-bottom: 20px;">Основная информация</h3>
                <div class="form-group">
                    <label class="form-label">Полное имя</label>
                    <input type="text" name="full_name" class="form-control" value="{user.full_name}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Заголовок</label>
                    <input type="text" name="headline" class="form-control" value="{user.headline or ''}" placeholder="Senior Software Engineer at Tech Company">
                </div>
                <div class="form-group">
                    <label class="form-label">Локация</label>
                    <input type="text" name="location" class="form-control" value="{user.location or ''}" placeholder="Алматы, Казахстан">
                </div>
                <div class="form-group">
                    <label class="form-label">О себе</label>
                    <textarea name="bio" class="form-control" placeholder="Расскажите о себе...">{user.bio or ''}</textarea>
                </div>
            </div>
            
            {profile_sections}
            
            <!-- Contact Information -->
            <div class="card">
                <h3 style="margin-bottom: 20px;">Contact Information</h3>
                
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" class="form-control" value="{user.email}" disabled style="opacity: 0.6;">
                    <p class="text-muted text-xs" style="margin-top: 4px;">Email cannot be changed</p>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Phone</label>
                    <input type="tel" name="phone" class="form-control" value="{user.phone or ''}" placeholder="+1 (555) 123-4567">
                </div>
            </div>
            
            <!-- Social Links -->
            <div class="card">
                <h3 style="margin-bottom: 20px;">Social Links</h3>
                
                <div class="form-group">
                    <label class="form-label">LinkedIn Profile</label>
                    <input type="url" name="linkedin_url" class="form-control" value="{user.linkedin_url or ''}" placeholder="https://linkedin.com/in/yourprofile">
                </div>
                
                <div class="form-group">
                    <label class="form-label">GitHub Profile</label>
                    <input type="url" name="github_url" class="form-control" value="{user.github_url or ''}" placeholder="https://github.com/yourusername">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Personal Website</label>
                    <input type="url" name="website" class="form-control" value="{user.website or ''}" placeholder="https://yourwebsite.com">
                </div>
            </div>
            
            {'<div class="card"><h3 style="margin-bottom: 20px;">Контакты для кандидатов</h3><p class="text-muted text-sm" style="margin-bottom: 16px;">Эти контакты будут видны кандидатам при отправке запроса</p><div class="form-group"><label class="form-label">WhatsApp</label><input type="text" name="whatsapp" class="form-control" value="' + (user.whatsapp or '') + '" placeholder="+77001234567 или https://wa.me/..."></div><div class="form-group"><label class="form-label">Instagram</label><input type="text" name="instagram" class="form-control" value="' + (user.instagram or '') + '" placeholder="username или ссылка"></div></div>' if user.role == "hr" else ''}
            
            <button type="submit" class="btn btn-primary btn-block btn-large">Save Changes</button>
        </form>
    </div>
    """
    return get_base_html("Edit Profile", content, user)


def upload_resume_profile_page(user: User, error: str = "", show_skills_form: bool = False) -> str:
    """Upload resume to profile page - Russian only"""
    lang = "ru"  # Always Russian
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    # Show skills form after upload
    if show_skills_form:
        content = f"""
        <div class="container-sm">
            <div class="alert alert-success">✅ Resume uploaded successfully!</div>
            
            <h1>Add Your Skills</h1>
            <p class="text-muted" style="margin-bottom: 32px;">Help us match you accurately by listing your real skills. This makes job matching more precise!</p>
            
            <div class="card">
                <h3 style="margin-bottom: 16px;">Why add skills?</h3>
                <ul style="margin-left: 20px; margin-bottom: 24px; color: rgba(255,255,255,0.7);">
                    <li style="margin-bottom: 8px;">✓ More accurate job matching</li>
                    <li style="margin-bottom: 8px;">✓ AI will know exactly what you can do</li>
                    <li style="margin-bottom: 8px;">✓ Better analysis results</li>
                    <li style="margin-bottom: 8px;">✓ Avoid false positives</li>
                </ul>
                
                <form method="POST" action="/update-skills">
                    <div class="form-group">
                        <label class="form-label">Your Skills (Optional but Recommended)</label>
                        <textarea name="skills" class="form-control" placeholder="Enter your skills, one per line or comma-separated:

Example:
React.js, Node.js, TypeScript
Python, Django, FastAPI
HTML, CSS, JavaScript
Git, Docker, AWS
Problem Solving, Team Leadership">{user.skills or ''}</textarea>
                        <p class="text-muted text-xs" style="margin-top: 8px;">Be honest! Only add skills you actually have. This ensures accurate matching.</p>
                    </div>
                    
                    <div style="display: flex; gap: 12px;">
                        <button type="submit" class="btn btn-primary btn-large" style="flex: 1;">Save Skills</button>
                        <a href="/profile" class="btn btn-outline btn-large" style="flex: 1; display: flex; align-items: center; justify-content: center; text-decoration: none;">Skip for Now</a>
                    </div>
                </form>
            </div>
        </div>
        """
    else:
        content = f"""
        <div class="container-sm">
            <div style="margin-bottom: 32px;">
                <a href="/profile" class="btn btn-outline">← Back to Profile</a>
            </div>
            
            <h1>Upload Resume</h1>
            <p class="text-muted" style="margin-bottom: 32px;">Upload your resume to your profile for quick job matching</p>
            
            {error_html}
            
            <div class="card">
                <form method="POST" action="/upload-resume-profile" enctype="multipart/form-data">
                    <div class="file-upload" onclick="document.getElementById('resume-input').click();">
                        <div class="file-icon">📄</div>
                        <input type="file" id="resume-input" name="resume" accept=".pdf,.docx,.doc" required onchange="updateResumeFileName(this)">
                        <p id="resume-name" style="font-weight: 600; margin-bottom: 8px; font-size: 16px;">Click to upload your resume</p>
                        <p class="text-muted text-xs">PDF or DOCX, max 10MB</p>
                    </div>
                    
                    <button type="submit" class="btn btn-primary btn-block btn-large" style="margin-top: 24px;">Upload Resume</button>
                </form>
            </div>
            
            {f'<div class="card"><h3>Current Resume</h3><p>📄 {user.resume_file.split("/")[-1] if "/" in user.resume_file else user.resume_file}</p><a href="/download-resume" class="btn btn-outline" style="margin-top: 12px;">Download Current Resume</a></div>' if user.resume_file else ''}
        </div>
        
        <script>
        function updateResumeFileName(input) {{
            const fileName = (input.files && input.files[0]) ? input.files[0].name : 'Click to upload your resume';
            document.getElementById('resume-name').textContent = fileName;
        }}
        </script>
        """
    
    return get_base_html("Upload Resume", content, user)


def analyze_page(user: User, error: str = "") -> str:
    """Analyze page - Russian only"""
    lang = "ru"  # Always Russian
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <h1>{t('analyze_match', lang)}</h1>
        <p class="text-muted" style="margin-bottom: 48px;">{t('analyze_subtitle', lang)}</p>
        
        {error_html}
        
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="card">
                <h3>{t('upload_resume', lang)}</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">{t('pdf_or_docx', lang)}</p>
                
                <div class="file-upload" onclick="document.getElementById('file-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="file-input" name="file" accept=".pdf,.docx,.doc" required onchange="updateFileName(this)">
                    <p id="file-name" style="font-weight: 600; margin-bottom: 8px; font-size: 16px;">{t('click_to_upload', lang)}</p>
                    <p class="text-muted text-xs">{t('supported_formats', lang)}</p>
                </div>
            </div>
            
            {f'''<div class="card" style="background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.15);">
                <h3 style="margin-bottom: 16px;">{t('use_profile_skills', lang)}</h3>
                <p class="text-muted text-sm" style="margin-bottom: 16px;">{t('use_profile_skills_desc', lang, count=len([s for s in user.skills.replace(",", "\\n").split("\\n") if s.strip()]))}</p>
                <label style="display: flex; align-items: center; gap: 12px; cursor: pointer; padding: 16px; background: rgba(255,255,255,0.05); border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">
                    <input type="checkbox" name="use_profile_skills" value="yes" checked style="width: 20px; height: 20px; cursor: pointer;">
                    <span style="flex: 1;">
                        <strong>{t('use_my_skills', lang)}</strong><br>
                        <span class="text-muted text-xs">{t('use_my_skills_desc', lang)}</span>
                    </span>
                </label>
                <p class="text-muted text-xs" style="margin-top: 12px;"><a href="/edit-profile#skills" style="color: var(--white); text-decoration: underline;">{t('add_them_now', lang)}</a></p>
            </div>''' if user.skills else ''}
            
            <div class="card">
                <h3>{t('job_description', lang)}</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">{t('paste_job_desc', lang)}</p>
                
                <div class="form-group">
                    <textarea name="job_description" class="form-control" required placeholder="{t('paste_job_desc', lang)}...

Example:
Job Title: Senior Software Engineer
Location: Remote
Salary: $120k-$150k

About the Role:
We're looking for an experienced Software Engineer...

Requirements:
• 5+ years of experience with Python
• Strong background in web development
• Experience with databases and APIs...

Responsibilities:
• Design and implement features..."></textarea>
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary btn-block btn-large">{t('analyze_match', lang)}</button>
        </form>
    </div>
    
    <script>
    function updateFileName(input) {{
        const fileName = (input.files && input.files[0]) ? input.files[0].name : '{t('click_to_upload', lang)}';
        document.getElementById('file-name').textContent = fileName;
    }}
    </script>
    """
    return get_base_html(t('analyze', lang), content, user)


def result_page(user: User, analysis: Analysis) -> str:
    """Result page - Russian only"""
    lang = "ru"  # Always Russian
    
    data = json.loads(analysis.analysis_data)
    score = analysis.match_score
    
    if score >= 70:
        score_class = "excellent"
        score_text = t('excellent_match', lang)
    elif score >= 50:
        score_class = "good"
        score_text = t('good_match', lang)
    else:
        score_class = "poor"
        score_text = t('needs_work', lang)
    
    pros_html = "".join([f'<li class="feature-item"><span class="feature-icon pro">✓</span><span>{p}</span></li>' for p in data.get('pros', [])])
    cons_html = "".join([f'<li class="feature-item"><span class="feature-icon con">✗</span><span>{c}</span></li>' for c in data.get('cons', [])])
    
    matched_skills = data.get('skills_match', {}).get('matched_skills', [])
    missing_skills = data.get('skills_match', {}).get('missing_skills', [])
    additional_skills = data.get('skills_match', {}).get('additional_skills', [])
    
    matched_html = "".join([f'<span class="badge badge-success">{s}</span>' for s in matched_skills])
    missing_html = "".join([f'<span class="badge badge-warning">{s}</span>' for s in missing_skills])
    additional_html = "".join([f'<span class="badge badge-info">{s}</span>' for s in additional_skills])
    
    recommendations_html = "".join([f'<li class="feature-item"><span class="feature-icon tip">💡</span><span>{r}</span></li>' for r in data.get('recommendations', [])])
    
    exp_score = data.get('experience_match', {}).get('score', 0)
    edu_score = data.get('education_match', {}).get('score', 0)
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 32px;">
            <a href="/dashboard" class="btn btn-outline">{t('back_to_dashboard', lang)}</a>
        </div>
        
        <div class="card">
            <div class="score-display">
                <div class="score-circle {score_class}">
                    <div class="score-value">{score:.0f}%</div>
                    <div class="score-label">Match</div>
                </div>
                <h2>{score_text}</h2>
                <p class="text-muted">{data.get('summary', '')}</p>
                <div class="text-muted text-sm" style="margin-top: 20px;">
                    📄 {analysis.filename} • {analysis.created_at.strftime('%B %d, %Y')}
                </div>
            </div>
        </div>
        
        <div class="grid-2">
            <div class="card">
                <h3>{t('strengths', lang)}</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">{t('what_makes_fit', lang)}</p>
                <ul class="feature-list">
                    {pros_html}
                </ul>
            </div>
            
            <div class="card">
                <h3>{t('areas_to_address', lang)}</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">{t('requirements_to_strengthen', lang)}</p>
                <ul class="feature-list">
                    {cons_html}
                </ul>
            </div>
        </div>
        
        <div class="card">
            <h3>{t('skills_analysis', lang)}</h3>
            
            <div class="section">
                <h4 class="text-sm text-muted">{t('matched_skills', lang)}</h4>
                <div style="margin-top: 12px;">
                    {matched_html if matched_html else '<span class="text-muted">-</span>'}
                </div>
            </div>
            
            <div class="section">
                <h4 class="text-sm text-muted">{t('missing_skills', lang)}</h4>
                <div style="margin-top: 12px;">
                    {missing_html if missing_html else '<span class="text-muted">-</span>'}
                </div>
            </div>
            
            <div class="section">
                <h4 class="text-sm text-muted">{t('additional_skills', lang)}</h4>
                <div style="margin-top: 12px;">
                    {additional_html if additional_html else '<span class="text-muted">-</span>'}
                </div>
            </div>
        </div>
        
        <div class="grid-2">
            <div class="card">
                <h3>{t('experience_match', lang)}</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {exp_score}%"></div>
                </div>
                <p style="margin-top: 16px; font-weight: 600; font-size: 18px;">{exp_score}%</p>
                <p class="text-muted text-sm" style="margin-top: 8px;">{data.get('experience_match', {}).get('analysis', '')}</p>
            </div>
            
            <div class="card">
                <h3>{t('education_match', lang)}</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {edu_score}%"></div>
                </div>
                <p style="margin-top: 16px; font-weight: 600; font-size: 18px;">{edu_score}%</p>
                <p class="text-muted text-sm" style="margin-top: 8px;">{data.get('education_match', {}).get('analysis', '')}</p>
            </div>
        </div>
        
        <div class="card">
            <h3>{t('recommendations_title', lang)}</h3>
            <p class="text-muted text-sm" style="margin-bottom: 24px;">{t('actions_to_improve', lang)}</p>
            <ul class="feature-list">
                {recommendations_html}
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 48px;">
            <a href="/analyze" class="btn btn-large">{t('analyze_another', lang)}</a>
        </div>
    </div>
    """
    return get_base_html(t('analyze', lang), content, user)


def candidates_search_page(user: User, db: Session, search_query: str = "") -> str:
    """Candidates search page for HR"""
    
    # Search candidates
    candidates_query = db.query(User).filter(User.role == "candidate")
    
    if search_query:
        # Search by name or skills
        candidates_query = candidates_query.filter(
            (User.full_name.contains(search_query)) |
            (User.skills.contains(search_query)) |
            (User.headline.contains(search_query))
        )
    
    candidates = candidates_query.limit(50).all()
    
    # Build candidates list
    candidates_html = ""
    for candidate in candidates:
        avatar = f'<img src="/uploads/avatars/{candidate.avatar}" style="width: 60px; height: 60px; border-radius: 50%; object-fit: cover;">' if candidate.avatar else f'<div style="width: 60px; height: 60px; border-radius: 50%; background: var(--white); color: var(--black); display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700;">{candidate.full_name[0].upper()}</div>'
        
        skills_preview = candidate.skills[:100] + "..." if len(candidate.skills) > 100 else candidate.skills
        has_resume = "✅ Резюме загружено" if candidate.resume_file else "❌ Нет резюме"
        
        candidates_html += f"""
        <div class="card" style="margin-bottom: 16px;">
            <div style="display: flex; gap: 24px; align-items: start;">
                {avatar}
                <div style="flex: 1;">
                    <h3 style="margin-bottom: 8px;">{candidate.full_name}</h3>
                    <p class="text-muted" style="margin-bottom: 8px;">{candidate.headline or 'Кандидат'}</p>
                    <p class="text-muted text-sm" style="margin-bottom: 12px;">📍 {candidate.location or 'Не указано'}</p>
                    {f'<p class="text-sm" style="margin-bottom: 12px;"><strong>Навыки:</strong> {skills_preview}</p>' if candidate.skills else '<p class="text-muted text-sm">Навыки не указаны</p>'}
                    <p class="text-xs text-muted">{has_resume}</p>
                </div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <a href="/candidate/{candidate.id}" class="btn btn-outline">Посмотреть профиль</a>
                </div>
            </div>
        </div>
        """
    
    if not candidates_html:
        candidates_html = '<div class="card"><p class="text-muted" style="text-align: center; padding: 40px;">Кандидаты не найдены. Попробуйте другой запрос.</p></div>'
    
    content = f"""
    <div class="container">
        <h1 style="margin-bottom: 32px;">Поиск кандидатов</h1>
        
        <form method="GET" action="/candidates" style="margin-bottom: 32px;">
            <div class="form-group">
                <input type="text" name="q" class="form-control" placeholder="Поиск по имени, навыкам или должности..." value="{search_query}" style="font-size: 16px; padding: 16px;">
                <p class="text-muted text-xs" style="margin-top: 8px;">Например: Python, React, Senior Developer</p>
            </div>
        </form>
        
        <p class="text-muted" style="margin-bottom: 24px;">Найдено кандидатов: {len(candidates)}</p>
        
        {candidates_html}
    </div>
    """
    return get_base_html("Поиск кандидатов", content, user)


def candidate_profile_view_page(candidate: User, hr_user: User, db: Session) -> str:
    """View candidate profile (for HR)"""
    
    avatar = f'<img src="/uploads/avatars/{candidate.avatar}" style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid rgba(255,255,255,0.2);">' if candidate.avatar else f'<div style="width: 120px; height: 120px; border-radius: 50%; background: var(--white); color: var(--black); display: flex; align-items: center; justify-content: center; font-size: 48px; font-weight: 700;">{candidate.full_name[0].upper()}</div>'
    
    # Check if already sent request
    existing_request = db.query(Request).filter(
        Request.hr_id == hr_user.id,
        Request.candidate_id == candidate.id
    ).first()
    
    request_section = ""
    if existing_request:
        request_section = f'''
        <div class="card" style="background: rgba(34, 197, 94, 0.1); border-color: rgba(34, 197, 94, 0.3);">
            <p style="color: #22c55e; font-weight: 600;">✅ Запрос уже отправлен</p>
            <p class="text-muted text-sm">Отправлено: {existing_request.created_at.strftime('%d.%m.%Y в %H:%M')}</p>
            <p class="text-sm" style="margin-top: 12px; padding: 12px; background: rgba(0,0,0,0.3); border-radius: 8px;">"{existing_request.message}"</p>
        </div>
        '''
    else:
        request_section = '''
        <div class="card">
            <h3 style="margin-bottom: 16px;">Отправить запрос кандидату</h3>
            <form method="POST" action="/send-request">
                <input type="hidden" name="candidate_id" value="{id}">
                <div class="form-group">
                    <label class="form-label">Ваше сообщение</label>
                    <textarea name="message" class="form-control" required placeholder="Здравствуйте! Мы ищем специалиста на позицию..." rows="5"></textarea>
                </div>
                <button type="submit" class="btn btn-primary btn-large">Отправить запрос</button>
            </form>
        </div>
        '''.format(id=candidate.id)
    
    resume_section = ""
    if candidate.resume_file:
        resume_section = f'''
        <div class="card">
            <h3 style="margin-bottom: 16px;">📄 Резюме</h3>
            <div style="display: flex; gap: 12px;">
                <a href="/view-resume/{candidate.id}" class="btn btn-outline" target="_blank">Открыть резюме</a>
                <a href="/download-resume?user_id={candidate.id}" class="btn btn-outline">Скачать</a>
            </div>
        </div>
        '''
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 32px;">
            <a href="/candidates" class="btn btn-outline">← Назад к поиску</a>
        </div>
        
        <div class="card">
            <div style="display: flex; gap: 32px; align-items: start;">
                {avatar}
                <div style="flex: 1;">
                    <h1 style="margin-bottom: 8px;">{candidate.full_name}</h1>
                    <p class="text-muted" style="margin-bottom: 16px; font-size: 18px;">{candidate.headline or 'Кандидат'}</p>
                    <p class="text-muted">📍 {candidate.location or 'Местоположение не указано'}</p>
                </div>
            </div>
        </div>
        
        {f'<div class="card"><h3>О себе</h3><p style="margin-top: 16px; line-height: 1.8;">{candidate.bio}</p></div>' if candidate.bio else ''}
        
        {f'''<div class="card">
            <h3 style="margin-bottom: 16px;">Навыки</h3>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                {"".join([f'<span class="badge badge-success">{skill.strip()}</span>' for skill in candidate.skills.replace(",", "\\n").split("\\n") if skill.strip()])}
            </div>
        </div>''' if candidate.skills else ''}
        
        {f'''<div class="card">
            <h3 style="margin-bottom: 16px;">Контакты</h3>
            <p><strong>Email:</strong> {candidate.email}</p>
            {f'<p style="margin-top: 8px;"><strong>Телефон:</strong> {candidate.phone}</p>' if candidate.phone else ''}
        </div>''' if candidate.email or candidate.phone else ''}
        
        {resume_section}
        
        {'''
        <div class="card">
            <h3 style="margin-bottom: 16px;">Анализ кандидата</h3>
            <p class="text-muted text-sm" style="margin-bottom: 16px;">Сравните резюме кандидата с вашей вакансией используя AI</p>
            <a href="/hr/analyze-candidate/''' + str(candidate.id) + '''" class="btn btn-primary btn-large">Анализировать с вакансией</a>
        </div>
        ''' if candidate.resume_file else ''}
        
        {request_section}
    </div>
    """
    return get_base_html(f"Профиль: {candidate.full_name}", content, hr_user)


# ============================================================================
# FASTAPI APP & ROUTES
# ============================================================================

app = FastAPI(title="HR Agent", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    Config.init()
    init_db()
    print("=" * 50)
    print("HR Agent initialized successfully")
    print(f"Using Ollama model: {Config.OLLAMA_MODEL}")
    print(f"Ollama URL: {Config.OLLAMA_API_URL}")
    print("=" * 50)


# Language change removed - always Russian now


@app.get("/", response_class=HTMLResponse)
async def index():
    """Landing page"""
    return landing_page()


@app.get("/login", response_class=HTMLResponse)
async def login_get():
    """Login page"""
    return login_page()


@app.post("/login")
async def login_post(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle login"""
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse(login_page(error="Invalid email or password"))
    
    session_token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    
    session = Session(
        session_token=session_token,
        user_id=user.id,
        expires_at=expires_at
    )
    db.add(session)
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=Config.SESSION_LIFETIME_HOURS * 3600
    )
    
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_get():
    """Register page"""
    return register_page()


@app.post("/register")
async def register_post(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),  # 'candidate' or 'hr'
    db: Session = Depends(get_db)
):
    """Handle registration"""
    
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return HTMLResponse(register_page(error="Email уже зарегистрирован"))
    
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role  # Save user role
    )
    db.add(user)
    db.commit()
    
    return RedirectResponse(url="/login", status_code=302)


@app.get("/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Handle logout"""
    if session_token:
        db.query(Session).filter(Session.session_token == session_token).delete()
        db.commit()
    
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Dashboard page"""
    return dashboard_page(user, db)


@app.get("/profile", response_class=HTMLResponse)
async def profile(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Profile page"""
    return profile_page(user, db)


@app.get("/edit-profile", response_class=HTMLResponse)
async def edit_profile_get(user: User = Depends(require_auth)):
    """Edit profile page"""
    return edit_profile_page(user)


@app.post("/update-profile")
async def update_profile(
    full_name: str = Form(...),
    headline: str = Form(""),
    location: str = Form(""),
    bio: str = Form(""),
    phone: str = Form(""),
    skills: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    website: str = Form(""),
    whatsapp: str = Form(""),
    instagram: str = Form(""),
    company_name: str = Form(""),
    company_description: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update profile information"""
    user.full_name = full_name
    user.headline = headline
    user.location = location
    user.bio = bio
    user.phone = phone
    user.linkedin_url = linkedin_url
    user.github_url = github_url
    user.website = website
    
    # HR-specific fields
    if user.role == "hr":
        user.whatsapp = whatsapp
        user.instagram = instagram
        user.company_name = company_name
        user.company_description = company_description
    else:
        # Candidate-specific fields
        user.phone = phone
        user.skills = skills
    
    db.commit()
    
    return RedirectResponse(url="/profile", status_code=302)


@app.post("/update-skills")
async def update_skills(
    skills: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update user skills"""
    user.skills = skills
    db.commit()
    
    return RedirectResponse(url="/profile", status_code=302)


@app.post("/upload-avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Upload profile avatar"""
    
    # Validate file type
    if not avatar.content_type.startswith("image/"):
        return HTMLResponse(edit_profile_page(user, error="Please upload an image file"))
    
    # Validate file size
    file_content = await avatar.read()
    if len(file_content) > 5 * 1024 * 1024:  # 5MB
        return HTMLResponse(edit_profile_page(user, error="Image too large (max 5MB)"))
    
    # Save file
    file_ext = avatar.filename.split(".")[-1] if "." in avatar.filename else "jpg"
    filename = f"{user.id}_{datetime.utcnow().timestamp()}.{file_ext}"
    file_path = Config.UPLOAD_DIR / "avatars" / filename
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Update user
    user.avatar = filename
    db.commit()
    
    return RedirectResponse(url="/edit-profile", status_code=302)


@app.get("/upload-resume-profile", response_class=HTMLResponse)
async def upload_resume_profile_get(user: User = Depends(require_auth)):
    """Upload resume to profile page"""
    return upload_resume_profile_page(user)


@app.post("/upload-resume-profile")
async def upload_resume_profile_post(
    resume: UploadFile = File(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Handle resume upload to profile"""
    
    # Validate file type
    if not (resume.filename.endswith(".pdf") or resume.filename.endswith(".docx") or resume.filename.endswith(".doc")):
        return HTMLResponse(upload_resume_profile_page(user, error="Only PDF and DOCX files are supported"))
    
    # Validate file size
    file_content = await resume.read()
    if len(file_content) > Config.MAX_FILE_SIZE:
        return HTMLResponse(upload_resume_profile_page(user, error="File too large (max 10MB)"))
    
    # Save file
    filename = f"{user.id}_resume_{datetime.utcnow().timestamp()}_{resume.filename}"
    file_path = Config.UPLOAD_DIR / "resumes" / filename
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Update user
    user.resume_file = filename
    db.commit()
    
    # Show skills form after upload
    return HTMLResponse(upload_resume_profile_page(user, show_skills_form=True))


@app.get("/download-resume")
async def download_resume(user: User = Depends(require_auth)):
    """Download user's resume"""
    if not user.resume_file:
        raise HTTPException(status_code=404, detail="No resume uploaded")
    
    file_path = Config.UPLOAD_DIR / "resumes" / user.resume_file
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(file_path, filename=user.resume_file.split("_", 3)[-1] if "_" in user.resume_file else user.resume_file)


@app.get("/uploads/{folder}/{filename}")
async def serve_upload(folder: str, filename: str):
    """Serve uploaded files"""
    file_path = Config.UPLOAD_DIR / folder / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(file_path)


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_get(user: User = Depends(require_auth)):
    """Analyze page"""
    return analyze_page(user)


@app.post("/analyze")
async def analyze_post(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    use_profile_skills: str = Form("no"),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Handle analysis request"""
    
    file_content = await file.read()
    if len(file_content) > Config.MAX_FILE_SIZE:
        return HTMLResponse(analyze_page(user, error="File too large (max 10MB)"))
    
    file_path = Config.UPLOAD_DIR / f"{user.id}_{datetime.utcnow().timestamp()}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    resume_text = parse_resume(file.filename, file_content)
    
    # Use profile skills if requested
    candidate_skills = ""
    if use_profile_skills == "yes" and user.skills:
        candidate_skills = user.skills
    
    # Always use Russian for AI analysis
    analysis_data = await compare_resume_with_job(resume_text, job_description, candidate_skills, "ru")
    
    analysis = Analysis(
        user_id=user.id,
        filename=file.filename,
        file_path=str(file_path),
        job_description=job_description,
        match_score=analysis_data.get("match_score", 0),
        analysis_data=json.dumps(analysis_data)
    )
    db.add(analysis)
    db.commit()
    
    return RedirectResponse(url=f"/result/{analysis.id}", status_code=302)


@app.get("/result/{analysis_id}", response_class=HTMLResponse)
async def result_detail(
    analysis_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Result detail page"""
    
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    return result_page(user, analysis)


# ============================================================================
# HR-SPECIFIC ROUTES
# ============================================================================

@app.get("/candidates", response_class=HTMLResponse)
async def candidates_search(
    q: str = "",
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Search candidates page (HR only)"""
    if user.role != "hr":
        raise HTTPException(status_code=403, detail="HR only")
    return candidates_search_page(user, db, q)


@app.get("/candidate/{candidate_id}", response_class=HTMLResponse)
async def view_candidate(
    candidate_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """View candidate profile (HR only)"""
    if user.role != "hr":
        raise HTTPException(status_code=403, detail="HR only")
    
    candidate = db.query(User).filter(User.id == candidate_id).first()
    if not candidate or candidate.role != "candidate":
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    return candidate_profile_view_page(candidate, user, db)


@app.post("/send-request")
async def send_request_post(
    candidate_id: int = Form(...),
    message: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Send request to candidate (HR only)"""
    if user.role != "hr":
        raise HTTPException(status_code=403, detail="HR only")
    
    existing = db.query(Request).filter(
        Request.hr_id == user.id,
        Request.candidate_id == candidate_id
    ).first()
    
    if existing:
        return RedirectResponse(f"/candidate/{candidate_id}", status_code=303)
    
    request = Request(
        hr_id=user.id,
        candidate_id=candidate_id,
        message=message,
        status="pending"
    )
    db.add(request)
    db.commit()
    
    return RedirectResponse(f"/candidate/{candidate_id}", status_code=303)


@app.get("/view-resume/{user_id}")
async def view_resume(
    user_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """View resume in browser"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user or not target_user.resume_file:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if current_user.role != "hr" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    file_path = Config.UPLOAD_DIR / "resumes" / target_user.resume_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(file_path)


# ============================================================================
# API ROUTES
# ============================================================================

@app.get("/api/notifications-count")
async def get_notifications_count(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get unread notifications count"""
    if user.role != "candidate":
        return {"count": 0}
    
    count = db.query(Request).filter(
        Request.candidate_id == user.id,
        Request.status == "pending"
    ).count()
    return {"count": count}


@app.get("/api/my-requests")
async def get_my_requests(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get my requests"""
    if user.role != "candidate":
        return {"requests": []}
    
    requests = db.query(Request).filter(
        Request.candidate_id == user.id
    ).order_by(Request.created_at.desc()).all()
    
    result = []
    for req in requests:
        hr = db.query(User).filter(User.id == req.hr_id).first()
        if hr:
            result.append({
                "id": req.id,
                "hr_name": hr.full_name,
                "hr_headline": hr.headline or "HR-специалист",
                "message": req.message,
                "status": req.status,
                "created_at": req.created_at.strftime("%d.%m.%Y %H:%M"),
                "whatsapp": hr.whatsapp,
                "instagram": hr.instagram,
                "linkedin": hr.linkedin_url
            })
    
    return {"requests": result}


@app.post("/api/dismiss-request/{request_id}")
async def dismiss_request(
    request_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Dismiss request"""
    if user.role != "candidate":
        raise HTTPException(status_code=403)
    
    request = db.query(Request).filter(
        Request.id == request_id,
        Request.candidate_id == user.id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404)
    
    db.delete(request)
    db.commit()
    return {"success": True}


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model": Config.OLLAMA_MODEL,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# JOB MANAGEMENT ROUTES
# ============================================================================

@app.get("/jobs/create", response_class=HTMLResponse)
async def create_job_get(user: User = Depends(require_auth)):
    """Create job page"""
    if user.role != "hr":
        raise HTTPException(status_code=403)
    
    content = """
    <div class="container-sm">
        <div style="margin-bottom: 32px;"><a href="/profile" class="btn btn-outline">← Назад</a></div>
        <h1>Создать вакансию</h1>
        <form method="POST" action="/jobs/create">
            <div class="card">
                <div class="form-group">
                    <label class="form-label">Название вакансии</label>
                    <input type="text" name="title" class="form-control" required placeholder="Senior Python Developer">
                </div>
                <div class="form-group">
                    <label class="form-label">Описание</label>
                    <textarea name="description" class="form-control" required style="min-height: 200px;" placeholder="Полное описание вакансии..."></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">Требования</label>
                    <textarea name="requirements" class="form-control" style="min-height: 150px;" placeholder="Опыт работы, необходимые знания..."></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">Требуемые навыки</label>
                    <textarea name="skills_required" class="form-control" placeholder="Python, Django, PostgreSQL..."></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">Локация</label>
                    <input type="text" name="location" class="form-control" placeholder="Алматы / Удаленно">
                </div>
                <div class="form-group">
                    <label class="form-label">Зарплата</label>
                    <input type="text" name="salary_range" class="form-control" placeholder="500,000 - 800,000 тг">
                </div>
                <div class="form-group">
                    <label class="form-label">Тип занятости</label>
                    <select name="employment_type" class="form-control">
                        <option value="full-time">Полная занятость</option>
                        <option value="part-time">Частичная занятость</option>
                        <option value="contract">Контракт</option>
                        <option value="freelance">Фриланс</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary btn-large">Создать вакансию</button>
            </div>
        </form>
    </div>
    """
    return get_base_html("Создать вакансию", content, user)

@app.post("/jobs/create")
async def create_job_post(
    title: str = Form(...),
    description: str = Form(...),
    requirements: str = Form(""),
    skills_required: str = Form(""),
    location: str = Form(""),
    salary_range: str = Form(""),
    employment_type: str = Form("full-time"),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if user.role != "hr":
        raise HTTPException(status_code=403)
    
    job = Job(
        hr_id=user.id,
        title=title,
        description=description,
        requirements=requirements,
        skills_required=skills_required,
        location=location,
        salary_range=salary_range,
        employment_type=employment_type
    )
    db.add(job)
    db.commit()
    return RedirectResponse("/profile", status_code=303)

@app.post("/job/{job_id}/delete")
async def delete_job(
    job_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if user.role != "hr":
        raise HTTPException(status_code=403)
    
    job = db.query(Job).filter(Job.id == job_id, Job.hr_id == user.id).first()
    if job:
        db.delete(job)
        db.commit()
    return RedirectResponse("/profile", status_code=303)


# ============================================================================
# HR AI ANALYSIS ROUTES
# ============================================================================

@app.get("/hr/analyze-candidate/{candidate_id}", response_class=HTMLResponse)
async def hr_analyze_candidate_get(
    candidate_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if user.role != "hr":
        raise HTTPException(status_code=403)
    
    candidate = db.query(User).filter(User.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404)
    
    jobs = db.query(Job).filter(Job.hr_id == user.id, Job.is_active == True).all()
    
    jobs_options = ""
    for job in jobs:
        jobs_options += f'<option value="{job.id}">{job.title}</option>'
    
    if not jobs_options:
        jobs_options = '<option value="">Сначала создайте вакансию</option>'
    
    content = f"""
    <div class="container-sm">
        <div style="margin-bottom: 32px;"><a href="/candidate/{candidate_id}" class="btn btn-outline">← Назад</a></div>
        <h1>AI-анализ кандидата</h1>
        <p class="text-muted">Кандидат: {candidate.full_name}</p>
        
        <form method="POST" action="/hr/analyze-candidate">
            <input type="hidden" name="candidate_id" value="{candidate_id}">
            <div class="card">
                <div class="form-group">
                    <label class="form-label">Выберите вакансию</label>
                    <select name="job_id" class="form-control" required>
                        {jobs_options}
                    </select>
                </div>
                <button type="submit" class="btn btn-primary btn-large">Анализировать</button>
            </div>
        </form>
    </div>
    """
    return get_base_html("Анализ кандидата", content, user)

@app.post("/hr/analyze-candidate")
async def hr_analyze_candidate_post(
    candidate_id: int = Form(...),
    job_id: int = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if user.role != "hr":
        raise HTTPException(status_code=403)
    
    candidate = db.query(User).filter(User.id == candidate_id).first()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not candidate or not job:
        raise HTTPException(status_code=404)
    
    # Get candidate resume
    resume_text = "Резюме не загружено"
    if candidate.resume_file:
        resume_path = Config.UPLOAD_DIR / "resumes" / candidate.resume_file
        if resume_path.exists():
            with open(resume_path, "rb") as f:
                resume_content = f.read()
                if candidate.resume_file.endswith('.pdf'):
                    resume_text = parse_pdf(resume_content)
                else:
                    resume_text = parse_docx_file(resume_content)
    
    # AI Analysis
    prompt = f"""
МАКСИМАЛЬНО ДЕТАЛЬНЫЙ анализ кандидата для вакансии на русском языке.

РЕЗЮМЕ: {resume_text}
НАВЫКИ: {candidate.skills}

ВАКАНСИЯ:
Название: {job.title}
Описание: {job.description}
Требования: {job.requirements}
Навыки: {job.skills_required}

Верни ТОЛЬКО JSON:
{{
    "match_score": 0-100,
    "strengths": ["7-10 сильных сторон с примерами"],
    "weaknesses": ["7-10 слабых сторон"],
    "missing_skills": ["недостающие навыки"],
    "interview_questions": ["5-7 вопросов"],
    "recommendations": ["рекомендации HR"],
    "success_probability": "высокая/средняя/низкая",
    "summary": "итог 2-3 предложения"
}}
"""
    
    analysis = {"match_score": 50, "strengths": ["Анализ..."], "weaknesses": ["..."], "missing_skills": [], "interview_questions": ["Расскажите о себе"], "recommendations": ["Оценка..."], "success_probability": "средняя", "summary": "Требуется оценка"}
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(Config.OLLAMA_API_URL, json={"model": Config.OLLAMA_MODEL, "prompt": prompt, "stream": False})
            if response.status_code == 200:
                result = response.json()
                import json, re
                json_match = re.search(r'\{.*\}', result.get("response", ""), re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
    except:
        pass
    
    match_color = "#22c55e" if analysis['match_score'] >= 70 else "#eab308" if analysis['match_score'] >= 50 else "#ef4444"
    
    content = f'''
    <div class="container">
        <div style="margin-bottom: 32px;"><a href="/candidate/{candidate_id}" class="btn btn-outline">← Назад</a></div>
        <h1>Результат анализа</h1>
        <p class="text-muted">Кандидат: {candidate.full_name} | Вакансия: {job.title}</p>
        
        <div class="card" style="text-align: center;">
            <h2 style="font-size: 64px; color: {match_color}; margin: 24px 0;">{analysis['match_score']}%</h2>
            <p class="text-muted">Соответствие вакансии</p>
            <p><strong>Вероятность успеха:</strong> {analysis['success_probability']}</p>
        </div>
        
        <div class="card"><h3>Сильные стороны</h3><ul>{"".join([f"<li>{s}</li>" for s in analysis['strengths']])}</ul></div>
        <div class="card"><h3>Слабые стороны</h3><ul>{"".join([f"<li>{w}</li>" for w in analysis['weaknesses']])}</ul></div>
        <div class="card"><h3>Недостающие навыки</h3><ul>{"".join([f"<li>{m}</li>" for m in analysis['missing_skills']]) if analysis['missing_skills'] else "<li>Все ключевые навыки присутствуют</li>"}</ul></div>
        <div class="card"><h3>Вопросы для собеседования</h3><ul>{"".join([f"<li>{q}</li>" for q in analysis['interview_questions']])}</ul></div>
        <div class="card"><h3>Рекомендации</h3><ul>{"".join([f"<li>{r}</li>" for r in analysis['recommendations']])}</ul></div>
        <div class="card"><h3>Итог</h3><p>{analysis['summary']}</p></div>
    </div>
    '''
    
    return get_base_html("Результат анализа", content, user)


# ============================================================================
# CHAT ROUTES
# ============================================================================

@app.get("/chat/{other_user_id}", response_class=HTMLResponse)
async def chat_page(
    other_user_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    other = db.query(User).filter(User.id == other_user_id).first()
    if not other:
        raise HTTPException(status_code=404)
    
    messages = db.query(Message).filter(
        ((Message.sender_id == user.id) & (Message.receiver_id == other_user_id)) |
        ((Message.sender_id == other_user_id) & (Message.receiver_id == user.id))
    ).order_by(Message.created_at.asc()).all()
    
    msgs_html = ""
    for msg in messages:
        is_mine = msg.sender_id == user.id
        align = "right" if is_mine else "left"
        bg = "rgba(255,255,255,0.1)" if is_mine else "rgba(255,255,255,0.05)"
        msgs_html += f'<div style="text-align: {align}; margin-bottom: 12px;"><div style="display: inline-block; padding: 12px 16px; background: {bg}; border-radius: 12px; max-width: 70%;"><p>{msg.message}</p><p class="text-muted text-xs" style="margin-top: 4px;">{msg.created_at.strftime("%H:%M")}</p></div></div>'
    
    content = f"""
    <div class="container-sm">
        <h1>Чат с {other.full_name}</h1>
        <div class="card" style="min-height: 400px; max-height: 600px; overflow-y: auto;" id="messages">{msgs_html}</div>
        <form method="POST" action="/chat/send" style="margin-top: 16px;">
            <input type="hidden" name="receiver_id" value="{other_user_id}">
            <div style="display: flex; gap: 12px;">
                <input type="text" name="message" class="form-control" required placeholder="Напишите сообщение...">
                <button type="submit" class="btn btn-primary">Отправить</button>
            </div>
        </form>
    </div>
    """
    return get_base_html(f"Чат с {other.full_name}", content, user)

@app.post("/chat/send")
async def send_message(
    receiver_id: int = Form(...),
    message: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    msg = Message(sender_id=user.id, receiver_id=receiver_id, message=message)
    db.add(msg)
    db.commit()
    return RedirectResponse(f"/chat/{receiver_id}", status_code=303)


# ============================================================================
# REVIEW ROUTES
# ============================================================================

@app.post("/review/create")
async def create_review(
    reviewee_id: int = Form(...),
    rating: int = Form(...),
    comment: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    review = Review(reviewer_id=user.id, reviewee_id=reviewee_id, rating=rating, comment=comment)
    db.add(review)
    
    # Update average rating
    reviewee = db.query(User).filter(User.id == reviewee_id).first()
    all_reviews = db.query(Review).filter(Review.reviewee_id == reviewee_id).all()
    reviewee.average_rating = sum(r.rating for r in all_reviews) / len(all_reviews)
    reviewee.total_reviews = len(all_reviews)
    
    db.commit()
    return RedirectResponse("/profile", status_code=303)


# ============================================================================
# PORTFOLIO ROUTES (for candidates)
# ============================================================================

@app.post("/portfolio/add")
async def add_portfolio(
    title: str = Form(...),
    description: str = Form(""),
    project_url: str = Form(""),
    technologies: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    portfolio = Portfolio(user_id=user.id, title=title, description=description, project_url=project_url, technologies=technologies)
    db.add(portfolio)
    db.commit()
    return RedirectResponse("/profile", status_code=303)

@app.post("/certificates/add")
async def add_certificate(
    title: str = Form(...),
    issuer: str = Form(""),
    issue_date: str = Form(""),
    credential_url: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    cert = Certificate(user_id=user.id, title=title, issuer=issuer, issue_date=issue_date, credential_url=credential_url)
    db.add(cert)
    db.commit()
    return RedirectResponse("/profile", status_code=303)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "hr_platform:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
