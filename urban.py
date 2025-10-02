from flask import Flask, request, redirect, url_for, flash, jsonify, make_response, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO
import base64
from datetime import datetime, timedelta
import os
import math
from sqlalchemy import inspect, text
from PIL import Image, ImageDraw  # <-- ДОБАВЛЕНО: Для обрезки изображений
# --- НОВЫЕ ИМПОРТЫ ДЛЯ PDF ---
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
# from reportlab.platypus import Image # Не используется напрямую
# from reportlab.pdfbase import pdfmetrics # Импортируется внутри функции
# from reportlab.pdfbase.ttfonts import TTFont # Импортируется внутри функции
import uuid
# ----------------------------
# --- ИМПОРТ ДЛЯ ПЛАНИРОВЩИКА ЗАДАЧ ---
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
# ----------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = "Secret-Key-2025"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///urban.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # <-- ДОБАВЛЕНО: Папка для загрузок
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
# Убедимся, что папка для загрузок существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
# --- ИНИЦИАЛИЗАЦИЯ ПЛАНИРОВЩИКА ---
scheduler = BackgroundScheduler()
# ----------------------------------
# Модели данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), default='student')  # student, organizer, admin
    total_hours = db.Column(db.Integer, default=0)
    coin_balance = db.Column(db.Float, default=0.0)  # Баланс койнов
    faculty = db.Column(db.String(100), default='Не указан')
    # --- НОВЫЕ ПОЛЯ ---
    phone = db.Column(db.String(20), nullable=True)  # Номер телефона
    group = db.Column(db.String(50), nullable=True)  # Группа
    avatar_filename = db.Column(db.String(255), nullable=True)  # Имя файла аватара
    bio = db.Column(db.Text, nullable=True)  # Биография/описание
    # -----------------
    # Связь с посещениями
    attendances = db.relationship('Attendance', backref='user', lazy=True)
    # Связь с записями о входе/выходе
    event_entries = db.relationship('EventEntry', backref='user', lazy=True)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.DateTime, nullable=False)
    hours = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(200), default='Не указано')
    registration_qr_code = db.Column(db.Text)  # base64 QR-код для регистрации
    qr_uuid = db.Column(db.String(36), unique=True) # UUID для проверки актуальности QR-кода
    exit_qr_code = db.Column(db.Text)  # base64 QR-код для выхода
    exit_qr_uuid = db.Column(db.String(36), unique=True) # UUID для QR-кода выхода
    # Связь с посещениями
    attendances = db.relationship('Attendance', backref='event', lazy=True)
    # Связь с записями о входе/выходе
    event_entries = db.relationship('EventEntry', backref='event', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    registration_time = db.Column(db.DateTime)  # Время регистрации
    credited_time = db.Column(db.DateTime)      # Время, когда зачислены часы (registration_time + 5 сек)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- НОВАЯ МОДЕЛЬ: ТОВАР В МАГАЗИНЕ ---
class ShopItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)  # Цена в койнах
    image_filename = db.Column(db.String(255), nullable=False)  # Имя файла изображения
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
# ---------------------------------------

# --- НОВАЯ МОДЕЛЬ: Отслеживание времени входа/выхода на мероприятия ---
class EventEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    entry_time = db.Column(db.DateTime)  # Время входа
    exit_time = db.Column(db.DateTime)   # Время выхода
    total_minutes = db.Column(db.Integer, default=0)  # Общее время в минутах
    coins_earned = db.Column(db.Float, default=0.0)  # Заработанные койны
    # user = db.relationship('User', backref='event_entries')
    # event = db.relationship('Event', backref='event_entries')
    # </CHANGE>

# --- КОНЕЦ НОВОЙ МОДЕЛИ ---

@login_manager.user_loader
def load_user(user_id):
    # Используем современный способ получения пользователя
    return db.session.get(User, int(user_id))
# Создание базы данных с миграцией
def create_tables():
    with app.app_context():
        # Проверяем существование таблиц
        if not inspect(db.engine).has_table("user"):
            # Создаем все таблицы, если их нет
            db.create_all()
        else:
            # Проверяем и добавляем недостающие столбцы
            inspector = inspect(db.engine)
            existing_columns = [col['name'] for col in inspector.get_columns('event')]
            # Добавляем недостающие столбцы
            with db.engine.connect() as conn:
                trans = conn.begin()
                try:
                    if 'registration_qr_code' not in existing_columns:
                        conn.execute(text('ALTER TABLE event ADD COLUMN registration_qr_code TEXT'))
                    if 'qr_uuid' not in existing_columns:
                        conn.execute(text('ALTER TABLE event ADD COLUMN qr_uuid TEXT'))
                    if 'exit_qr_code' not in existing_columns:
                        conn.execute(text('ALTER TABLE event ADD COLUMN exit_qr_code TEXT'))
                    if 'exit_qr_uuid' not in existing_columns:
                        conn.execute(text('ALTER TABLE event ADD COLUMN exit_qr_uuid TEXT'))
                    
                    # Для таблицы attendance
                    existing_attendance_columns = [col['name'] for col in inspector.get_columns('attendance')]
                    if 'registration_time' not in existing_attendance_columns:
                        conn.execute(text('ALTER TABLE attendance ADD COLUMN registration_time DATETIME'))
                    if 'credited_time' not in existing_attendance_columns:
                        conn.execute(text('ALTER TABLE attendance ADD COLUMN credited_time DATETIME'))
                    # Для таблицы user
                    existing_user_columns = [col['name'] for col in inspector.get_columns('user')]
                    if 'coin_balance' not in existing_user_columns:
                        conn.execute(text('ALTER TABLE user ADD COLUMN coin_balance FLOAT DEFAULT 0.0'))
                    # --- ДОБАВЛЕНО: Проверка на существование таблицы ShopItem ---
                    if not inspector.has_table('shop_item'):
                        ShopItem.__table__.create(db.engine)
                    if not inspector.has_table('event_entry'):
                        EventEntry.__table__.create(db.engine)
                    # --- ДОБАВЛЕНО: Проверка на новые поля в таблице user ---
                    if 'phone' not in existing_user_columns:
                        conn.execute(text('ALTER TABLE user ADD COLUMN phone VARCHAR(20)'))
                    if 'group' not in existing_user_columns:
                        conn.execute(text('ALTER TABLE user ADD COLUMN "group" VARCHAR(50)'))
                    if 'avatar_filename' not in existing_user_columns:
                        conn.execute(text('ALTER TABLE user ADD COLUMN avatar_filename VARCHAR(255)'))
                    if 'bio' not in existing_user_columns:
                        conn.execute(text('ALTER TABLE user ADD COLUMN bio TEXT'))
                    # ----------------------------------------------------
                    trans.commit()
                except:
                    trans.rollback()
                    raise
# Создание базы данных
create_tables()
# --- ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ PDF СЕРТИФИКАТА ---
def generate_certificate_pdf(user):
    """Генерирует PDF-сертификат для пользователя с улучшенным дизайном (без полосы, рамка ближе к краям)."""
    from datetime import datetime, timezone
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # 🎨 Фон (светлый)
    c.setFillColorRGB(0.97, 0.99, 1.0)
    c.rect(0, 0, width, height, fill=1)
    
    # 🔲 Декоративная рамка (ближе к краю)
    c.setStrokeColorRGB(0.26, 0.38, 0.92)  # синий
    c.setLineWidth(3)
    margin = 0.3 * inch
    c.roundRect(margin, margin, width - 2*margin, height - 2*margin, 15, stroke=1, fill=0)
    
    # 🏆 Заголовок
    c.setFont("Helvetica-Bold", 40)
    c.setFillColorRGB(0.1, 0.2, 0.5)
    c.drawCentredString(width / 2.0, height - 2.5*inch, "CERTIFICATE")
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2.0, height - 3.2*inch, "Achievement and Recognition")
    
    # 👤 Имя студента
    c.setFont("Helvetica-Bold", 28)
    c.setFillColorRGB(0.26, 0.38, 0.92)
    c.drawCentredString(width / 2.0, height - 4.2*inch, user.username)
    
    # 📜 Текст сертификата
    c.setFont("Helvetica", 14)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    lines = [
        "is awarded for successful completion of the program",
        "«Urban vconnect community» and active participation",
        "in community work.",
        "",
        "This achievement confirms the student's commitment",
        "to the values of volunteering, responsibility and leadership."
    ]
    y = height - 5.2*inch
    for line in lines:
        c.drawCentredString(width / 2.0, y, line)
        y -= 0.35*inch
    
    # 📅 Дата
    current_date = datetime.now(timezone.utc)
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2.0, 1.5*inch, f"Issue date: {current_date.strftime('%d.%m.%Y')}")
    
    # ✍️ Подпись
    c.setFont("Helvetica-Bold", 12)
    c.drawString(width - 2*inch, 1.2*inch, "Signature:")
    c.line(width - 2*inch, 1.0*inch, width - 0.5*inch, 1.0*inch)
    
    # 🔒 QR-код
    verification_url = f"https://urban-platform.com/profile/{user.id}"
    qr = qrcode.QRCode(version=1, box_size=4, border=4)
    qr.add_data(verification_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    temp_qr_filename = f"/tmp/cert_qr_{uuid.uuid4().hex}.png"
    try:
        qr_img.save(temp_qr_filename)
        qr_size = 1.5 * inch
        c.drawImage(temp_qr_filename, margin + 0.2*inch, 1.0*inch, width=qr_size, height=qr_size)
        c.setFont("Helvetica", 8)
        c.drawString(margin + 0.2*inch, 0.8*inch, "Verify authenticity")
    finally:
        try:
            os.remove(temp_qr_filename)
        except OSError:
            pass
    
    c.save()
    buffer.seek(0)
    return buffer
# </CHANGE>
# ----------------------------
# --- ФУНКЦИЯ ДЛЯ ОБНОВЛЕНИЯ QR-КОДОВ ВСЕХ СОБЫТИЙ ---
def update_all_qr_codes():
    """Генерирует новые UUID и QR-коды для всех событий."""
    print(f"[{datetime.now()}] Запуск обновления QR-кодов для всех событий...")
    with app.app_context():
        try:
            all_events = db.session.execute(db.select(Event)).scalars().all()
            for event in all_events:
                # Генерируем новый UUID
                new_uuid = str(uuid.uuid4())
                event.qr_uuid = new_uuid
                # Генерируем новый QR-код с новым UUID
                registration_qr_data = f"/event_registration_{event.id}?uuid={new_uuid}"
                registration_qr = qrcode.QRCode(version=1, box_size=8, border=4)
                registration_qr.add_data(registration_qr_data)
                registration_qr.make(fit=True)
                registration_img = registration_qr.make_image(fill='black', back_color='white')
                registration_buffer = BytesIO()
                registration_img.save(registration_buffer, format='PNG')
                event.registration_qr_code = base64.b64encode(registration_buffer.getvalue()).decode()
                print(f"  Обновлен QR-код для события '{event.title}' (ID: {event.id})")
            db.session.commit()
            print(f"[{datetime.now()}] Обновление QR-кодов завершено успешно.")
        except Exception as e:
            db.session.rollback()
            print(f"[{datetime.now()}] Ошибка при обновлении QR-кодов: {e}")
# ----------------------------------------------------
# --- ФУНКЦИЯ ДЛЯ ИНИЦИАЛИЗАЦИИ ПЛАНИРОВЩИКА ---
def init_scheduler():
    """Инициализирует и запускает планировщик задач."""
    # Запланировать обновление QR-кодов каждые 30 секунд (для демонстрации)
    # В реальном приложении, возможно, лучше раз в час, день или по кнопке админа.
    # scheduler.add_job(func=update_all_qr_codes, trigger="interval", seconds=30)
    # Запланировать обновление QR-кодов каждые 60 минут
    scheduler.add_job(func=update_all_qr_codes, trigger="interval", minutes=1)
    scheduler.start()
    print("Планировщик задач запущен. QR-коды будут обновляться каждые 1 минут.")
    # При завершении приложения останавливаем планировщик
    atexit.register(lambda: scheduler.shutdown())
# ------------------------------------------------
# ----------------------------
# HTML шаблоны (обновлены)
# ... (весь остальной код приложения остается без изменений) ...
TEMPLATES = {
    'base': '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Urban community</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Montserrat:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="  https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css  ">
    <style>
        :root {
            /* --- ЦВЕТА В СТИЛЕ ASTANA HUB --- */
            --ah-primary: #1A2B6B;       /* Основной синий Astana Hub */
            --ah-primary-dark: #0F1A40;  /* Темный синий */
            --ah-secondary: #00C2FF;     /* Акцентный голубой */
            --ah-accent: #FF6B35;        /* Акцентный оранжевый (по желанию) */
            --ah-light: #F5F7FA;         /* Светлый фон */
            --ah-dark: #1A1A1A;          /* Основной текст */
            --ah-gray-100: #F0F2F5;      /* Очень светлый серый */
            --ah-gray-200: #E1E5EA;      /* Светлый серый */
            --ah-gray-300: #C9D1D9;      /* Средний серый */
            --ah-gray-600: #6A737D;      /* Темный серый */
            --ah-success: #28a745;       /* Зеленый для успеха */
            --ah-warning: #ffc107;       /* Желтый для предупреждений */
            --ah-danger: #dc3545;        /* Красный для ошибок */
            /* ------------------------------ */
            /* --- ОСНОВНЫЕ ПЕРЕМЕННЫЕ --- */
            --primary: var(--ah-primary);
            --primary-gradient: linear-gradient(135deg, var(--ah-primary), var(--ah-secondary));
            --secondary: var(--ah-secondary);
            --accent: var(--ah-accent);
            --light: var(--ah-light);
            --dark: var(--ah-dark);
            --success: var(--ah-success);
            --warning: var(--ah-warning);
            --danger: var(--ah-danger);
            --gray: var(--ah-gray-600);
            --light-gray: var(--ah-gray-200);
            --card-padding: 25px;
            --element-margin: 20px;
            --font-size-base: 1rem;
            --font-size-small: 0.9rem;
            --font-size-large: 1.2rem;
            --border-radius: 16px;
            --box-shadow: 0 10px 25px rgba(26, 43, 107, 0.1);
            --box-shadow-hover: 0 15px 35px rgba(26, 43, 107, 0.15);
            --transition-speed: 0.3s;
            /* --------------------------- */
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #f0f4f8, #e6ecf3);
            color: var(--dark);
            line-height: 1.7;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            font-size: var(--font-size-base);
        }
        .container {
            width: 100%;
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 25px;
        }
        header {
            background: white;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
        }
        .logo {
            font-family: 'Montserrat', sans-serif;
            font-weight: 800;
            font-size: 1.6rem;
            display: flex;
            align-items: center;
            color: var(--primary);
            text-decoration: none;
            transition: transform var(--transition-speed);
        }
        .logo:hover {
            transform: scale(1.02);
        }
        .logo i {
            margin-right: 12px;
            color: var(--secondary);
            font-size: 1.5rem;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        nav ul {
            display: flex;
            list-style: none;
            margin: 0;
            padding: 0;
            gap: 8px;
        }
        nav ul li a {
            color: var(--ah-gray-600);
            text-decoration: none;
            font-weight: 600;
            padding: 10px 18px;
            border-radius: 12px;
            transition: all var(--transition-speed) ease;
            font-size: var(--font-size-base);
            display: flex;
            align-items: center;
            position: relative;
            overflow: hidden;
        }
        nav ul li a::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: var(--primary-gradient);
            opacity: 0;
            transition: opacity var(--transition-speed);
            z-index: -1;
        }
        nav ul li a:hover {
            color: white;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(26, 43, 107, 0.2);
        }
        nav ul li a:hover::before {
            opacity: 1;
        }
        nav ul li a.active {
            color: white;
            background: var(--primary-gradient);
            box-shadow: 0 5px 15px rgba(26, 43, 107, 0.2);
        }
        nav ul li a i {
            margin-right: 8px;
            font-size: 1rem;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 12px 24px;
            background: var(--primary-gradient);
            color: white;
            border: none;
            border-radius: var(--border-radius);
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all var(--transition-speed) cubic-bezier(0.4, 0, 0.2, 1);
            text-align: center;
            font-size: var(--font-size-base);
            min-height: 48px;
            box-shadow: 0 4px 15px rgba(26, 43, 107, 0.2);
            position: relative;
            overflow: hidden;
        }
        .btn::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(255,255,255,0.2), rgba(255,255,255,0));
            transform: translateX(-100%);
            transition: transform 0.6s ease;
        }
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: var(--box-shadow-hover);
        }
        .btn:hover::after {
            transform: translateX(100%);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
            box-shadow: none;
        }
        .btn-outline:hover {
            background: rgba(26, 43, 107, 0.05);
            box-shadow: 0 4px 15px rgba(26, 43, 107, 0.1);
        }
        .btn-success {
            background: linear-gradient(135deg, var(--success), #1e7e34);
        }
        .btn-success:hover {
            background: linear-gradient(135deg, #218838, #155724);
        }
        .btn-warning {
            background: linear-gradient(135deg, var(--warning), #d39e00);
            color: var(--dark);
        }
        .btn-warning:hover {
            background: linear-gradient(135deg, #e0a800, #c69500);
        }
        .btn-danger {
            background: linear-gradient(135deg, var(--danger), #bd2130);
        }
        .btn-danger:hover {
            background: linear-gradient(135deg, #c82333, #a71d2a);
        }
        .btn-sm {
            padding: 8px 16px;
            font-size: var(--font-size-small);
            min-height: 36px;
        }
        .card {
            background: white;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            padding: var(--card-padding);
            margin-bottom: var(--element-margin);
            transition: all var(--transition-speed) cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(0,0,0,0.03);
        }
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: var(--primary-gradient);
        }
        .card:hover {
            transform: translateY(-5px);
            box-shadow: var(--box-shadow-hover);
        }
        .card-header {
            border-bottom: 1px solid var(--ah-gray-200);
            padding-bottom: 20px;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .card-title {
            font-family: 'Montserrat', sans-serif;
            font-weight: 700;
            color: var(--primary);
            margin: 0;
            font-size: 1.6rem;
            display: flex;
            align-items: center;
        }
        .card-title i {
            margin-right: 12px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .form-group {
            margin-bottom: 25px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            font-size: var(--font-size-small);
            color: var(--ah-gray-600);
        }
        .form-control {
            width: 100%;
            padding: 14px 18px;
            border: 2px solid var(--ah-gray-200);
            border-radius: var(--border-radius);
            font-size: var(--font-size-base);
            transition: all var(--transition-speed) ease;
            background-color: white;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.03);
        }
        .form-control:focus {
            border-color: var(--primary);
            outline: none;
            box-shadow: 0 0 0 4px rgba(26, 43, 107, 0.15);
        }
        .alert {
            padding: 18px 22px;
            border-radius: var(--border-radius);
            margin-bottom: 20px;
            font-size: var(--font-size-small);
            display: flex;
            align-items: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }
        .alert i {
            margin-right: 12px;
            font-size: 1.2rem;
        }
        .alert-success {
            background: linear-gradient(135deg, rgba(40, 167, 69, 0.15), rgba(40, 167, 69, 0.05));
            border: 1px solid var(--success);
            color: #155724;
        }
        .alert-error {
            background: linear-gradient(135deg, rgba(220, 53, 69, 0.15), rgba(220, 53, 69, 0.05));
            border: 1px solid var(--danger);
            color: #721c24;
        }
        .alert-info {
            background: linear-gradient(135deg, rgba(26, 43, 107, 0.1), rgba(26, 43, 107, 0.03));
            border: 1px solid var(--primary);
            color: var(--primary);
        }
        .progress-container {
            background: var(--ah-gray-100);
            border-radius: 50px;
            height: 16px;
            margin: 20px 0;
            overflow: hidden;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
        }
        .progress-bar {
            height: 100%;
            background: var(--primary-gradient);
            border-radius: 50px;
            transition: width 1.5s cubic-bezier(0.22, 0.61, 0.36, 1);
            position: relative;
            overflow: hidden;
        }
        .progress-bar::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            animation: shimmer 2s infinite;
        }
        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 25px;
            margin: 30px 0;
        }
        .stat-card {
            background: white;
            border-radius: var(--border-radius);
            padding: 25px;
            text-align: center;
            box-shadow: var(--box-shadow);
            transition: all var(--transition-speed) ease;
            border: 1px solid rgba(0,0,0,0.03);
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: var(--primary-gradient);
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: var(--box-shadow-hover);
        }
        .stat-card i {
            font-size: 2.5rem;
            margin-bottom: 15px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stat-value {
            font-size: 2.2rem;
            font-weight: 800;
            color: var(--primary);
            margin: 15px 0 10px 0;
            font-family: 'Montserrat', sans-serif;
        }
        .stat-label {
            color: var(--gray);
            font-size: 0.9rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .event-card {
            display: flex;
            flex-direction: row;
            margin-bottom: 20px;
            background: white;
            border-radius: var(--border-radius);
            overflow: hidden;
            box-shadow: var(--box-shadow);
            transition: all var(--transition-speed) ease;
            border-left: 5px solid var(--primary);
        }
        .event-card:hover {
            transform: translateY(-3px);
            box-shadow: var(--box-shadow-hover);
        }
        .event-date {
            min-width: 90px;
            text-align: center;
            padding: 20px 12px;
            background: rgba(26, 43, 107, 0.05);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        .event-day {
            font-size: 1.8rem;
            font-weight: 800;
            color: var(--primary);
            line-height: 1;
            font-family: 'Montserrat', sans-serif;
        }
        .event-month {
            font-size: 0.9rem;
            color: var(--gray);
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 1px;
        }
        .event-content {
            padding: 20px;
            flex-grow: 1;
        }
        .event-title {
            font-weight: 700;
            margin-bottom: 12px;
            font-size: 1.2rem;
            color: var(--dark);
        }
        .event-meta {
            display: flex;
            flex-wrap: wrap;
            color: var(--gray);
            font-size: 0.85rem;
            margin-top: 15px;
            gap: 15px;
        }
        .event-meta div {
            display: flex;
            align-items: center;
        }
        .event-meta i {
            margin-right: 6px;
            font-size: 0.85rem;
            color: var(--primary);
        }
        footer {
            text-align: center;
            padding: 35px 0;
            color: var(--ah-gray-600);
            font-size: 0.9rem;
            background-color: white;
            margin-top: auto;
            border-top: 1px solid var(--ah-gray-200);
        }
        main {
            flex: 1;
            padding: 40px 0;
        }
        #video-container {
            width: 100%;
            max-width: 400px;
            margin: 30px auto;
            position: relative;
            aspect-ratio: 1 / 1;
            overflow: hidden;
            border-radius: var(--border-radius);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border: 5px solid white;
        }
        #video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        #canvas {
            display: none;
        }
        .qr-result {
            margin-top: 20px;
            padding: 18px;
            border-radius: var(--border-radius);
            text-align: center;
            font-weight: 600;
            font-size: var(--font-size-base);
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }
        .qr-success {
            background: linear-gradient(135deg, rgba(40, 167, 69, 0.15), rgba(40, 167, 69, 0.05));
            border: 1px solid var(--success);
            color: #155724;
        }
        .qr-error {
            background: linear-gradient(135deg, rgba(220, 53, 69, 0.15), rgba(220, 53, 69, 0.05));
            border: 1px solid var(--danger);
            color: #721c24;
        }
        .qr-info {
            background: linear-gradient(135deg, rgba(26, 43, 107, 0.1), rgba(26, 43, 107, 0.03));
            border: 1px solid var(--primary);
            color: var(--primary);
        }
        .qr-scanner-ui {
            position: relative;
            width: 100%;
            height: 100%;
        }
        .scanner-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }
        .scanner-frame {
            position: absolute;
            top: 50%;
            left: 50%;
            width: 75%;
            height: 75%;
            transform: translate(-50%, -50%);
            border: 3px solid var(--secondary);
            box-shadow: 0 0 0 1000px rgba(0, 0, 0, 0.4);
            border-radius: 20px;
        }
        .scanner-line {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: var(--secondary);
            box-shadow: 0 0 10px var(--secondary);
            animation: scan 2s infinite linear;
        }
        @keyframes scan {
            0% { top: 0; }
            100% { top: 100%; }
        }
        .delete-form {
            display: inline-block;
            margin-left: 12px;
        }
        .registrations-list {
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid var(--ah-gray-200);
        }
        .registrations-list h4 {
            margin-bottom: 15px;
            color: var(--primary);
            font-size: 1.1rem;
        }
        .registrations-list ul {
            list-style: none;
            padding-left: 0;
            margin: 0;
        }
        .registrations-list li {
            padding: 10px 0;
            border-bottom: 1px solid var(--ah-gray-100);
            font-size: 0.9rem;
        }
        .registrations-list li:last-child {
            border-bottom: none;
        }
        /* --- СТИЛИ ПРОФИЛЯ --- */
        .profile-header {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 40px;
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 1px solid var(--ah-gray-200);
        }
        .avatar-container {
            position: relative;
            width: 180px;
            height: 180px;
            flex-shrink: 0;
            border-radius: 50%;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border: 5px solid white;
        }
        .avatar {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .avatar-placeholder {
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, var(--ah-gray-200), var(--ah-gray-300));
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ah-gray-600);
            font-size: 4rem;
        }
        .user-info {
            flex-grow: 1;
        }
        .user-name {
            font-family: 'Montserrat', sans-serif;
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--dark);
            margin: 0 0 15px 0;
        }
        .user-email {
            font-size: 1.1rem;
            color: var(--ah-gray-600);
            margin: 0 0 20px 0;
            display: flex;
            align-items: center;
        }
        .user-email i {
            margin-right: 10px;
            color: var(--primary);
        }
        .user-bio {
            font-size: 1rem;
            color: var(--dark);
            margin: 0 0 25px 0;
            line-height: 1.6;
            padding: 15px;
            background: rgba(26, 43, 107, 0.03);
            border-radius: var(--border-radius);
            border-left: 4px solid var(--primary);
        }
        .user-details {
            display: flex;
            flex-wrap: wrap;
            gap: 25px;
            font-size: 1rem;
            color: var(--gray);
        }
        .user-detail-item {
            display: flex;
            align-items: center;
            padding: 10px 15px;
            background: rgba(26, 43, 107, 0.03);
            border-radius: 12px;
        }
        .user-detail-item i {
            margin-right: 10px;
            color: var(--primary);
            font-size: 1.1rem;
        }
        /* --- СТИЛИ НАСТРОЕК --- */
        .settings-form {
            max-width: 700px;
            margin: 0 auto;
        }
        .avatar-upload-group {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 35px;
            padding: 30px;
            background: rgba(26, 43, 107, 0.03);
            border-radius: var(--border-radius);
        }
        .current-avatar {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            object-fit: cover;
            margin-bottom: 20px;
            border: 3px solid var(--primary);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .current-avatar-placeholder {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--ah-gray-200), var(--ah-gray-300));
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--ah-gray-600);
            font-size: 2.5rem;
            margin-bottom: 20px;
            border: 3px solid var(--primary);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .form-actions {
            display: flex;
            justify-content: flex-end;
            gap: 20px;
            margin-top: 40px;
        }
        /* --- СТИЛИ ДЛЯ МАГАЗИНА --- */
        .shop-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 35px;
            margin-top: 35px;
        }
        .shop-item {
            background: white;
            border-radius: var(--border-radius);
            overflow: hidden;
            box-shadow: var(--box-shadow);
            transition: all var(--transition-speed) cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            display: flex;
            flex-direction: column;
            border: 1px solid rgba(0,0,0,0.03);
        }
        .shop-item:hover {
            transform: translateY(-8px);
            box-shadow: var(--box-shadow-hover);
        }
        .shop-item-image-container {
            width: 100%;
            aspect-ratio: 1 / 1;
            overflow: hidden;
            background: linear-gradient(135deg, var(--ah-gray-100), var(--ah-gray-200));
        }
        .shop-item img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s ease;
        }
        .shop-item:hover img {
            transform: scale(1.05);
        }
        .shop-item-content {
            padding: 25px;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
        }
        .shop-item-title {
            font-family: 'Montserrat', sans-serif;
            font-weight: 700;
            font-size: 1.4rem;
            color: var(--dark);
            margin: 0 0 15px 0;
            line-height: 1.3;
        }
        .shop-item-price {
            font-weight: 800;
            font-size: 1.8rem;
            color: var(--primary);
            margin: 15px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .shop-item-price::before {
            content: "🪙";
            font-size: 1.4em;
        }
        .shop-item-description {
            font-size: 1rem;
            color: var(--gray);
            margin: 0 0 20px 0;
            line-height: 1.6;
            flex-grow: 1;
        }
        .btn-buy {
            width: 100%;
            padding: 14px;
            font-weight: 700;
            background: var(--primary-gradient);
            border: none;
            border-radius: 12px;
            color: white;
            cursor: pointer;
            transition: all var(--transition-speed) ease;
            font-size: 1rem;
            box-shadow: 0 4px 15px rgba(26, 43, 107, 0.2);
        }
        .btn-buy:hover {
            transform: translateY(-3px);
            box-shadow: 0 7px 20px rgba(26, 43, 107, 0.3);
        }
        .btn-buy:disabled {
            background: linear-gradient(135deg, var(--ah-gray-200), var(--ah-gray-300));
            color: var(--ah-gray-600);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        .out-of-stock {
            position: absolute;
            top: 20px;
            right: 20px;
            background: var(--danger);
            color: white;
            padding: 8px 16px;
            border-radius: 25px;
            font-size: 0.9rem;
            font-weight: 700;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        }
        /* --- СТИЛИ ДЛЯ НАВИГАЦИОННЫХ КНОПОК --- */
        .nav-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin: 30px 0;
            padding: 25px;
            background: rgba(26, 43, 107, 0.03);
            border-radius: var(--border-radius);
            border: 1px solid rgba(0,0,0,0.03);
        }
        .nav-buttons .btn {
            flex: 1;
            min-width: 180px;
            justify-content: center;
            padding: 16px 20px;
            font-size: 1.1rem;
            font-weight: 600;
        }
        .nav-buttons .btn i {
            margin-right: 10px;
        }
        
        /* --- СТИЛИ ДЛЯ МОДАЛЬНОГО ОКНА QR-КОДА --- */
        .qr-modal {
            display: none;
            position: fixed;
            z-index: 10000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.9);
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
        }
        .qr-modal.show {
            display: flex;
            justify-content: center;
            align-items: center;
            opacity: 1;
        }
        .qr-modal-content {
            position: relative;
            background-color: #fefefe;
            padding: 20px;
            border: 1px solid #888;
            border-radius: 8px;
            max-width: 80vw;
            max-height: 80vh;
            transform: scale(0.8);
            transition: transform 0.3s ease-in-out;
        }
        .qr-modal.show .qr-modal-content {
            transform: scale(1);
        }
        .close-qr-modal {
            color: #aaa;
            position: absolute;
            top: 10px;
            right: 15px;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            z-index: 10001;
        }
        .close-qr-modal:hover,
        .close-qr-modal:focus {
            color: black;
            text-decoration: none;
        }
        .qr-modal-img {
            max-width: 100%;
            max-height: 100%;
            display: block;
            margin: 0 auto;
        }
        .qr-code-container {
            cursor: pointer;
            display: inline-block;
            transition: transform 0.2s ease-in-out;
        }
        .qr-code-container:hover {
            transform: scale(1.05);
        }
        /* --- КОНЕЦ СТИЛЕЙ ДЛЯ МОДАЛЬНОГО ОКНА QR-КОДА --- */
        
        @media (max-width: 768px) {
            :root {
                --card-padding: 20px;
                --element-margin: 15px;
                --font-size-base: 0.95rem;
                --font-size-small: 0.85rem;
            }
            .header-content {
                flex-direction: column;
                align-items: flex-start;
                padding: 15px 0;
            }
            nav ul {
                margin-top: 15px;
                flex-wrap: wrap;
                width: 100%;
                gap: 6px;
            }
            nav ul li a {
                font-size: 0.9rem;
                padding: 8px 14px;
            }
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            .btn {
                padding: 10px 20px;
                font-size: 0.95rem;
                min-height: 44px;
            }
            .card-title {
                font-size: 1.4rem;
            }
            .event-card {
                flex-direction: column;
            }
            .event-date {
                flex-direction: row;
                justify-content: flex-start;
                padding: 15px 20px;
                min-width: 100%;
                gap: 15px;
            }
            .event-day, .event-month {
                font-size: 1.2rem;
            }
            /* --- СТИЛИ ПРОФИЛЯ (МОБИЛЬНЫЕ) --- */
            .profile-header {
                flex-direction: column;
                text-align: center;
            }
            .avatar-container {
                width: 150px;
                height: 150px;
            }
            .user-name {
                font-size: 2rem;
            }
            .user-details {
                justify-content: center;
            }
            .nav-buttons {
                flex-direction: column;
            }
            .nav-buttons .btn {
                width: 100%;
            }
        }
        @media (max-width: 480px) {
            :root {
                --card-padding: 18px;
                --element-margin: 12px;
                --font-size-base: 0.9rem;
                --font-size-small: 0.8rem;
            }
            .container {
                padding: 0 15px;
            }
            .stats-grid {
                grid-template-columns: 1fr;
            }
            .event-meta div {
                margin-right: 10px;
                font-size: 0.8rem;
            }
            .btn {
                padding: 10px 16px;
                font-size: 0.9rem;
                min-height: 40px;
            }
            .card-title {
                font-size: 1.3rem;
            }
            .shop-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="container header-content">
            <a href="/" class="logo">
                <i class="fas fa-graduation-cap"></i>
                Urban community
            </a>
            <nav>
                <ul>
                    <!--NAVIGATION_PLACEHOLDER -->
                </ul>
            </nav>
        </div>
    </header>
    <main class="container">
        <!-- MESSAGES_PLACEHOLDER -->
        <!-- CONTENT_PLACEHOLDER -->
    </main>
    <footer>
        <div class="container">
            <p>&copy; 2025 Urban community. Мощная платформа для развития.</p>
        </div>
    </footer>
    
    <!-- МОДАЛЬНОЕ ОКНО ДЛЯ QR-КОДА -->
    <div id="qrModal" class="qr-modal">
        <span class="close-qr-modal">&times;</span>
        <div class="qr-modal-content">
            <img class="qr-modal-img" id="qrModalImg" src="/placeholder.svg" alt="Увеличенный QR-код">
        </div>
    </div>
    <!-- КОНЕЦ МОДАЛЬНОГО ОКНА -->
    
    <script>
        // Анимация прогресс-бара
        document.addEventListener('DOMContentLoaded', function() {
            const progressBars = document.querySelectorAll('.progress-bar');
            progressBars.forEach(bar => {
                const width = bar.style.width;
                bar.style.width = '0';
                setTimeout(() => {
                    bar.style.width = width;
                }, 300);
            });
        });
        // Функция для показа/скрытия списка зарегистрированных
        function toggleRegistrations(eventId) {
            const list = document.getElementById('registrations-list-' + eventId);
            if (list.style.display === 'none' || list.style.display === '') {
                list.style.display = 'block';
            } else {
                list.style.display = 'none';
            }
        }
        
        // --- СКРИПТ ДЛЯ МОДАЛЬНОГО ОКНА QR-КОДА ---
        document.addEventListener('DOMContentLoaded', function() {
            const qrContainers = document.querySelectorAll('.qr-code-container');
            const modal = document.getElementById("qrModal");
            const modalImg = document.getElementById("qrModalImg");
            const span = document.getElementsByClassName("close-qr-modal")[0];

            // Функция для открытия модального окна
            function openQrModal(imgSrc) {
                if (modal && modalImg) {
                    modalImg.src = imgSrc;
                    modal.classList.add("show");
                    document.body.style.overflow = 'hidden'; // Предотвратить прокрутку фона
                }
            }

            // Функция для закрытия модального окна
            function closeQrModal() {
                if (modal) {
                    modal.classList.remove("show");
                    // Добавляем небольшую задержку перед восстановлением прокрутки
                    // чтобы анимация закрытия завершилась
                    setTimeout(() => {
                         document.body.style.overflow = 'auto';
                    }, 300);
                }
            }

            // Добавляем обработчики кликов для каждого контейнера QR-кода
            qrContainers.forEach(container => {
                const img = container.querySelector('img'); // Находим изображение внутри контейнера
                if (img) {
                    container.addEventListener('click', function() {
                        openQrModal(img.src);
                    });
                }
            });

            // Закрытие по клику на крестик
            if (span) {
                span.addEventListener('click', closeQrModal);
            }

            // Закрытие по клику вне изображения
            if (modal) {
                modal.addEventListener('click', function(event) {
                    if (event.target === modal) {
                        closeQrModal();
                    }
                });
            }

            // Закрытие по нажатию Escape
            document.addEventListener('keydown', function(event) {
                if (event.key === "Escape") {
                    closeQrModal();
                }
            });
        });
        // --- КОНЕЦ СКРИПТА ДЛЯ МОДАЛЬНОГО ОКНА QR-КОДА ---
    </script>
</body>
</html>''',
    'login': '''
<div class="card" style="max-width: 550px; margin: 50px auto;">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-sign-in-alt"></i> Вход в систему</h2>
    </div>
    <form method="POST">
        <div class="form-group">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="password">Пароль</label>
            <input type="password" id="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn" style="width: 100%; padding: 14px; font-size: 1.1rem;">
            <i class="fas fa-sign-in-alt"></i> Войти
        </button>
    </form>
    <div style="text-align: center; margin-top: 25px;">
        <p style="font-size: 1rem;">Нет аккаунта? <a href="/register" style="color: var(--primary); text-decoration: none; font-weight: 600;">Зарегистрируйтесь</a></p>
    </div>
</div>
    ''',
    'register': '''
<div class="card" style="max-width: 550px; margin: 50px auto;">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-user-plus"></i> Регистрация</h2>
    </div>
    <form method="POST">
        <div class="form-group">
            <label for="username">Имя пользователя</label>
            <input type="text" id="username" name="username" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="password">Пароль</label>
            <input type="password" id="password" name="password" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="faculty">Факультет</label>
            <select id="faculty" name="faculty" class="form-control" required>
                <option value="">Выберите факультет</option>
                <option value="Информационные технологии">Информационные технологии</option>
                <option value="Экономика и управление">Экономика и управление</option>
                <option value="Инженерия">Инженерия</option>
                <option value="Гуманитарные науки">Гуманитарные науки</option>
                <option value="Медицина">Медицина</option>
                <option value="Другое">Другое</option>
            </select>
        </div>
        <!-- НОВЫЕ ПОЛЯ -->
        <div class="form-group">
            <label for="phone">Номер телефона</label>
            <input type="tel" id="phone" name="phone" class="form-control" placeholder="+7 (XXX) XXX-XXXX" required>
        </div>
        <div class="form-group">
            <label for="group">Группа</label>
            <input type="text" id="group" name="group" class="form-control" placeholder="Введите вашу группу" required>
        </div>
        <!-- КОНЕЦ НОВЫХ ПОЛЕЙ -->
        <button type="submit" class="btn" style="width: 100%; padding: 14px; font-size: 1.1rem;">
            <i class="fas fa-user-plus"></i> Зарегистрироваться
        </button>
    </form>
    <div style="text-align: center; margin-top: 25px;">
        <p style="font-size: 1rem;">Уже есть аккаунт? <a href="/login" style="color: var(--primary); text-decoration: none; font-weight: 600;">Войдите</a></p>
    </div>
</div>
    ''',
    'dashboard': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title">Привет,&nbsp;<span style="color: var(--primary);">USERNAME_PLACEHOLDER</span>!</h2>
    </div>
    <div style="text-align: center; margin: 40px 0;">
        <h3 style="font-size: 1.5rem; margin-bottom: 25px; color: var(--gray);">Ваш прогресс</h3>
        <div style="font-size: 1.8rem; font-weight: 700; margin-bottom: 15px; color: var(--primary);">TOTAL_HOURS_PLACEHOLDER / 300 часов</div>
        <div class="progress-container">
            <div class="progress-bar" style="width: PROGRESS_PERCENT_PLACEHOLDER%"></div>
        </div>
        <div style="font-size: 1.2rem; margin-top: 15px; font-weight: 600;">PROGRESS_PERCENT_PLACEHOLDER% завершено</div>
        <!-- CERTIFICATE_BUTTON_PLACEHOLDER -->
    </div>
    <!-- --- ДОБАВЛЕНО: Блок с отображением койнов --- -->
    <div style="text-align: center; margin: 30px 0; padding: 20px; background: linear-gradient(135deg, rgba(76, 201, 240, 0.15), rgba(76, 201, 240, 0.05)); border-radius: var(--border-radius); border: 1px solid rgba(76, 201, 240, 0.2);">
        <h4 style="margin: 0 0 10px 0; font-size: 1.3rem; color: var(--dark); display: flex; align-items: center; justify-content: center;">
            <i class="fas fa-coins" style="margin-right: 10px; color: #FFD700;"></i> Ваш баланс койнов
        </h4>
        <div style="font-size: 2rem; font-weight: 800; color: var(--primary);">COIN_BALANCE_PLACEHOLDER <span style="font-size: 1.5rem;">🪙</span></div>
        <p style="font-size: 1rem; margin: 10px 0 0 0; color: var(--gray);">Койны начисляются за участие в мероприятиях.</p>
    </div>
    <!-- ---------------------------------------- -->
    
    <!-- --- ДОБАВЛЕНО: Кнопки навигации --- -->
    <div class="nav-buttons">
        <a href="/scan_qr" class="btn">
            <i class="fas fa-qrcode"></i> Сканировать QR
        </a>
        <a href="/events" class="btn btn-outline">
            <i class="fas fa-calendar-alt"></i> Все события
        </a>
        <a href="/shop" class="btn">
            <i class="fas fa-shopping-cart"></i> Магазин койнов
        </a>
        <a href="/profile" class="btn btn-outline">
            <i class="fas fa-user"></i> Мой профиль
        </a>
    </div>
    <!-- --------------------------------- -->
    
</div>
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-calendar-check"></i> Ближайшие события</h2>
    </div>
    <!-- EVENTS_PLACEHOLDER -->
</div>
    ''',
    'profile': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-user"></i> Ваш профиль</h2>
        <a href="/settings" class="btn btn-outline btn-sm">
            <i class="fas fa-cog"></i> Настройки
        </a>
    </div>
    <div class="profile-header">
        <div class="avatar-container">
            <!-- AVATAR_PLACEHOLDER -->
        </div>
        <div class="user-info">
            <h1 class="user-name">USERNAME_PLACEHOLDER</h1>
            <p class="user-email"><i class="fas fa-envelope"></i> EMAIL_PLACEHOLDER</p>
            <!-- BIO_PLACEHOLDER -->
            <div class="user-details">
                <div class="user-detail-item">
                    <i class="fas fa-building"></i> <span>FACULTY_PLACEHOLDER</span>
                </div>
                <div class="user-detail-item">
                    <i class="fas fa-users"></i> <span>GROUP_PLACEHOLDER</span>
                </div>
                <div class="user-detail-item">
                    <i class="fas fa-phone"></i> <span>PHONE_PLACEHOLDER</span>
                </div>
                <div class="user-detail-item">
                    <i class="fas fa-user-tag"></i> <span>ROLE_PLACEHOLDER</span>
                </div>
            </div>
        </div>
    </div>
    <div class="stats-grid">
        <div class="stat-card">
            <i class="fas fa-clock"></i>
            <div class="stat-value">TOTAL_HOURS_PLACEHOLDER</div>
            <div class="stat-label">Накоплено часов</div>
        </div>
        <div class="stat-card">
            <i class="fas fa-chart-line"></i>
            <div class="stat-value">PROGRESS_PERCENT_PLACEHOLDER%</div>
            <div class="stat-label">Прогресс к 300 часам</div>
        </div>
        <div class="stat-card">
            <i class="fas fa-coins"></i>
            <div class="stat-value">COIN_BALANCE_PLACEHOLDER</div>
            <div class="stat-label">Койны</div>
        </div>
    </div>
    <!-- CERTIFICATE_BUTTON_PLACEHOLDER -->
    
    <!-- --- ДОБАВЛЕНО: Кнопки навигации --- -->
    <div class="nav-buttons">
        <a href="/dashboard" class="btn">
            <i class="fas fa-home"></i> Главная
        </a>
        <a href="/scan_qr" class="btn btn-outline">
            <i class="fas fa-qrcode"></i> Сканировать QR
        </a>
        <a href="/events" class="btn">
            <i class="fas fa-calendar-alt"></i> Все события
        </a>
        <a href="/shop" class="btn btn-outline">
            <i class="fas fa-shopping-cart"></i> Магазин
        </a>
    </div>
    <!-- --------------------------------- -->
    
</div>
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-history"></i> История участия</h2>
    </div>
    <!-- ATTENDANCES_PLACEHOLDER -->
</div>
    ''',
    'settings': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-cog"></i> Настройки профиля</h2>
    </div>
    <form method="POST" enctype="multipart/form-data" class="settings-form">
        <div class="avatar-upload-group">
            <!-- CURRENT_AVATAR_PLACEHOLDER -->
            <div class="form-group" style="margin-bottom: 0; width: 100%;">
                <label for="avatar">Изменить аватар</label>
                <input type="file" id="avatar" name="avatar" class="form-control" accept="image/*">
                <small class="form-text text-muted">Изображение будет автоматически обрезано до круга.</small>
            </div>
        </div>
        <div class="form-group">
            <label for="username">Имя пользователя</label>
            <input type="text" id="username" name="username" class="form-control" value="USERNAME_PLACEHOLDER" required>
        </div>
        <div class="form-group">
            <label for="faculty">Факультет</label>
            <select id="faculty" name="faculty" class="form-control" required>
                <option value="Не указан" SELECTED_PLACEHOLDER_Не указан>Не указан</option>
                <option value="Информационные технологии" SELECTED_PLACEHOLDER_Информационные технологии>Информационные технологии</option>
                <option value="Экономика и управление" SELECTED_PLACEHOLDER_Экономика и управление>Экономика и управление</option>
                <option value="Инженерия" SELECTED_PLACEHOLDER_Инженерия>Инженерия</option>
                <option value="Гуманитарные науки" SELECTED_PLACEHOLDER_Гуманитарные науки>Гуманитарные науки</option>
                <option value="Медицина" SELECTED_PLACEHOLDER_Медицина>Медицина</option>
                <option value="Другое" SELECTED_PLACEHOLDER_Другое>Другое</option>
            </select>
        </div>
        <div class="form-group">
            <label for="phone">Номер телефона</label>
            <input type="tel" id="phone" name="phone" class="form-control" value="PHONE_PLACEHOLDER">
        </div>
        <div class="form-group">
            <label for="group">Группа</label>
            <input type="text" id="group" name="group" class="form-control" value="GROUP_PLACEHOLDER">
        </div>
        <div class="form-group">
            <label for="bio">О себе</label>
            <textarea id="bio" name="bio" class="form-control" rows="5">BIO_PLACEHOLDER</textarea>
        </div>
        <div class="form-actions">
            <a href="/profile" class="btn btn-outline">Отмена</a>
            <button type="submit" class="btn">
                <i class="fas fa-save"></i> Сохранить изменения
            </button>
        </div>
    </form>
</div>
    ''',
    'events': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-calendar-alt"></i> Все события</h2>
    </div>
    <!-- ALL_EVENTS_PLACEHOLDER -->
</div>
    ''',
    'scan_qr': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-qrcode"></i> Сканирование QR-кода</h2>
    </div>
    <div style="text-align: center; margin: 40px 0;">
        <p style="font-size: 1.2rem; margin-bottom: 30px; color: var(--gray);">Отсканируйте QR-код на мероприятии для фиксации участия</p>
        <div id="video-container">
            <div class="qr-scanner-ui">
                <video id="video" playsinline></video>
                <div class="scanner-overlay">
                    <div class="scanner-frame">
                        <div class="scanner-line"></div>
                    </div>
                </div>
            </div>
            <canvas id="canvas"></canvas>
        </div>
        <button id="start-camera" class="btn" style="margin: 25px 0; width: 100%; max-width: 400px;">
            <i class="fas fa-video"></i> Включить камеру
        </button>
        <div id="qr-result" class="qr-result" style="display: none;"></div>
        <form method="POST" id="manual-form" style="max-width: 550px; margin: 30px auto; display: none;">
            <div class="form-group">
                <label for="qr_data">Данные QR-кода (вручную)</label>
                <input type="text" id="qr_data" name="qr_data" class="form-control" placeholder="Введите данные QR-кода">
            </div>
            <button type="submit" class="btn" style="width: 100%; padding: 14px; font-size: 1.1rem;">
                <i class="fas fa-check-circle"></i> Подтвердить участие
            </button>
        </form>
        <button id="manual-entry" class="btn btn-outline" style="margin-top: 20px; width: 100%; max-width: 400px;">
            <i class="fas fa-keyboard"></i> Ввести данные вручную
        </button>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js"></script>
<script>
    // Получаем элементы DOM
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const startButton = document.getElementById('start-camera');
const manualForm = document.getElementById('manual-form');
const manualEntryButton = document.getElementById('manual-entry');
const qrResult = document.getElementById('qr-result');

let scanning = false;
let stream = null; // Переменная для хранения текущего медиа-потока

// --- НАЧАЛО ИЗМЕНЁННОГО/УЛУЧШЕННОГО КОДА ---

// Запрос разрешения на использование камеры
startButton.addEventListener('click', async () => {
    try {
        // --- УЛУЧШЕНИЕ 1: Остановка предыдущего потока ---
        // Всегда пытаемся остановить предыдущий поток, если он существует
        if (stream) {
            console.log("Остановка предыдущего потока камеры...");
            const tracks = stream.getTracks();
            tracks.forEach(track => {
                console.log(`Остановка трека: ${track.kind}`);
                track.stop();
            });
            stream = null; // Сбрасываем переменную потока
        }

        // --- ИЗМЕНЕНИЕ: Скрытие сообщений об ошибках перед новой попыткой ---
        qrResult.style.display = 'none';
        qrResult.className = 'qr-result'; // Сброс классов

        // --- УЛУЧШЕНИЕ 2: Индикатор загрузки ---
        console.log("Запрос доступа к камере...");
        qrResult.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Запрашиваем доступ к камере...';
        qrResult.className = 'qr-result qr-info'; // Используем информационный стиль
        qrResult.style.display = 'block';

        // --- ИЗМЕНЕНИЕ: Запрос нового потока ---
        // Запрашиваем доступ к камере с предпочтением задней камеры
        stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: "environment", // Предпочтительно использовать заднюю камеру
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        });

        console.log("Доступ к камере получен.");
        // --- ИЗМЕНЕНИЕ: Настройка видео потока ---
        video.srcObject = stream;
        video.setAttribute("playsinline", true); // Для корректной работы на iOS

        // --- ИЗМЕНЕНИЕ: Ожидание начала воспроизведения ---
        // Дожидаемся начала воспроизведения видео перед скрытием кнопки
        await video.play();
        console.log("Видео начало воспроизводиться.");

        // --- ИЗМЕНЕНИЕ: Управление видимостью UI ---
        // Скрываем кнопку включения камеры
        startButton.style.display = 'none';
        // Показываем кнопку ручного ввода
        manualEntryButton.style.display = 'inline-block';
        // Скрываем форму ручного ввода, если она была открыта
        manualForm.style.display = 'none';
        // Скрываем предыдущие сообщения
        qrResult.style.display = 'none';

        // --- ИЗМЕНЕНИЕ: Начало сканирования ---
        scanning = true;
        console.log("Начало сканирования...");
        tick(); // Запускаем цикл сканирования

    } catch (err) {
        console.error("Ошибка доступа к камере: ", err);
        // --- УЛУЧШЕНИЕ 3: Детализированное сообщение об ошибке ---
        let errorMessage = 'Не удалось получить доступ к камере. ';
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
            errorMessage += 'Доступ запрещен пользователем. Пожалуйста, разрешите доступ к камере в настройках браузера и попробуйте снова.';
        } else if (err.name === 'NotFoundError' || err.name === 'OverconstrainedError') {
            errorMessage += 'Камера не найдена или не поддерживает запрашиваемое разрешение.';
        } else {
            errorMessage += 'Проверьте подключение камеры и настройки браузера. Ошибка: ' + err.message;
        }

        // Отображаем сообщение об ошибке
        qrResult.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${errorMessage}`;
        qrResult.className = 'qr-result qr-error';
        qrResult.style.display = 'block';

        // --- ИЗМЕНЕНИЕ: Управление видимостью UI при ошибке ---
        // Показываем форму ручного ввода
        manualForm.style.display = 'block';
        // Показываем кнопку включения камеры снова, чтобы можно было повторить попытку
        startButton.style.display = 'inline-block';
        // Скрываем кнопку ручного ввода, так как мы уже в режиме ошибки
        manualEntryButton.style.display = 'none';
        // Останавливаем сканирование
        scanning = false;
        stream = null; // Убедимся, что поток помечен как отсутствующий
    }
});

// --- КОНЕЦ ИЗМЕНЁННОГО/УЛУЧШЕННОГО КОДА ---

// Переключение на ручной ввод (остальная часть этой функции также улучшена)
manualEntryButton.addEventListener('click', () => {
    console.log("Переключение на ручной ввод.");
    // Останавливаем камеру при переходе на ручной ввод
    if (stream) {
        console.log("Остановка камеры при переходе на ручной ввод.");
        const tracks = stream.getTracks();
        tracks.forEach(track => track.stop());
        stream = null;
    }
    scanning = false;
    video.srcObject = null; // Очищаем источник видео
    manualForm.style.display = 'block';
    startButton.style.display = 'inline-block'; // Показываем кнопку включения камеры снова
    manualEntryButton.style.display = 'none'; // Скрываем кнопку ручного ввода
    qrResult.style.display = 'none'; // Скрываем сообщения сканера
});

// Основной цикл сканирования (без изменений, но для контекста)
function tick() {
    if (video.readyState === video.HAVE_ENOUGH_DATA && scanning) {
        canvas.height = video.videoHeight;
        canvas.width = video.videoWidth;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQR(imageData.data, imageData.width, imageData.height, {
            inversionAttempts: "dontInvert",
        });
        if (code) {
            console.log("QR-код найден.");
            handleQRCode(code.data);
            scanning = false;
        } else {
            setTimeout(tick, 100);
        }
    } else if (scanning) {
        setTimeout(tick, 100);
    }
}

// Обработка найденного QR-кода (без изменений, но для контекста)
function handleQRCode(data) {
    console.log("Обработка QR-кода:", data);
    // Останавливаем камеру после сканирования
    if (stream) {
        console.log("Остановка камеры после сканирования.");
        const tracks = stream.getTracks();
        tracks.forEach(track => track.stop());
        stream = null;
    }
    scanning = false;
    video.srcObject = null;

    qrResult.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Обработка QR-кода...`;
    qrResult.className = 'qr-result qr-info';
    qrResult.style.display = 'block';

    fetch('/process_qr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', },
        body: JSON.stringify({ qr_data: data }) // Исправлена опечатка: было qr_ data
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            qrResult.innerHTML = `<i class="fas fa-check-circle"></i> ${data.message}`;
            qrResult.className = 'qr-result qr-success';
            setTimeout(() => {
                window.location.href = data.redirect_url || '/dashboard';
            }, 2000);
        } else {
            qrResult.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${data.message}`;
            qrResult.className = 'qr-result qr-error';
            // Возобновляем сканирование или показываем кнопку повтора
            setTimeout(() => {
                 startButton.style.display = 'inline-block';
                 manualEntryButton.style.display = 'none';
                 manualForm.style.display = 'none'; // Скрываем форму, если была показана сервером
            }, 3000);
        }
        qrResult.style.display = 'block';
    })
    .catch(error => {
        console.error('Ошибка обработки QR-кода:', error);
        qrResult.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Ошибка обработки QR-кода';
        qrResult.className = 'qr-result qr-error';
        setTimeout(() => {
             startButton.style.display = 'inline-block';
             manualEntryButton.style.display = 'none';
        }, 3000);
        qrResult.style.display = 'block';
    });
    }
    // Останавливаем камеру при закрытии страницы
    window.addEventListener('beforeunload', () => {
        if (stream) {
            const tracks = stream.getTracks();
            tracks.forEach(track => track.stop());
        }
    });
</script>
    ''',
    'admin_login': '''
<div class="card" style="max-width: 550px; margin: 50px auto;">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-lock"></i> Вход в админ-панель</h2>
    </div>
    <form method="POST">
        <div class="form-group">
            <label for="username">Логин</label>
            <input type="text" id="username" name="username" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="password">Пароль</label>
            <input type="password" id="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn" style="width: 100%; padding: 14px; font-size: 1.1rem;">
            <i class="fas fa-sign-in-alt"></i> Войти
        </button>
    </form>
</div>
    ''',
    'admin_panel': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-cogs"></i> Админ-панель</h2>
    </div>
    <div class="stats-grid">
        <div class="stat-card">
            <i class="fas fa-users"></i>
            <div class="stat-value">TOTAL_USERS_PLACEHOLDER</div>
            <div class="stat-label">Пользователей</div>
        </div>
        <div class="stat-card">
            <i class="fas fa-calendar-day"></i>
            <div class="stat-value">TOTAL_EVENTS_PLACEHOLDER</div>
            <div class="stat-label">Событий</div>
        </div>
        <div class="stat-card">
            <i class="fas fa-user-check"></i>
            <div class="stat-value">TOTAL_ATTENDANCES_PLACEHOLDER</div>
            <div class="stat-label">Участий</div>
        </div>
    </div>
</div>
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-plus-circle"></i> Создать новое событие</h2>
    </div>
    <form method="POST">
        <div class="form-group">
            <label for="title">Название события</label>
            <input type="text" id="title" name="title" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="description">Описание</label>
            <textarea id="description" name="description" class="form-control" rows="5" required></textarea>
        </div>
        <div class="form-group">
            <label for="date">Дата и время</label>
            <input type="datetime-local" id="date" name="date" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="hours">Количество часов</label>
            <input type="number" id="hours" name="hours" class="form-control" min="1" max="24" required>
        </div>
        <div class="form-group">
            <label for="location">Место проведения</label>
            <input type="text" id="location" name="location" class="form-control" required>
        </div>
        <button type="submit" class="btn" style="width: 100%; padding: 14px; font-size: 1.1rem;">
            <i class="fas fa-plus-circle"></i> Создать событие
        </button>
    </form>
</div>
<!-- --- НОВЫЙ БЛОК: ДОБАВИТЬ ТОВАР В МАГАЗИН --- -->
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-tag"></i> Добавить товар в магазин</h2>
    </div>
    <form method="POST" action="/admin_add_item" enctype="multipart/form-data">
        <div class="form-group">
            <label for="item_name">Название товара</label>
            <input type="text" id="item_name" name="name" class="form-control" required placeholder="Введите название товара">
        </div>
        <div class="form-group">
            <label for="item_description">Описание (необязательно)</label>
            <textarea id="item_description" name="description" class="form-control" rows="4" placeholder="Краткое описание товара"></textarea>
        </div>
        <div class="form-group">
            <label for="item_price">Цена в койнах (макс. 100)</label>
            <input type="number" id="item_price" name="price" class="form-control" min="1" max="100" required placeholder="Введите цену">
        </div>
        <div class="form-group">
            <label for="item_image">Изображение товара</label>
            <input type="file" id="item_image" name="image" class="form-control" accept="image/*" required>
            <small class="form-text text-muted">Изображение будет автоматически обрезано до соотношения 1:1.</small>
        </div>
        <button type="submit" class="btn" style="width: 100%; padding: 14px; font-size: 1.1rem; background: linear-gradient(135deg, var(--secondary), var(--primary));">
            <i class="fas fa-upload"></i> Загрузить товар
        </button>
    </form>
</div>
<!-- ---------------------------------------- -->
<!-- --- НОВЫЙ БЛОК: УПРАВЛЕНИЕ ТОВАРАМИ МАГАЗИНА --- -->
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-tags"></i> Товары магазина</h2>
    </div>
    <!-- SHOP_ITEMS_PLACEHOLDER -->
</div>
<!-- --------------------------------------------- -->
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-calendar-alt"></i> Все события</h2>
    </div>
    <!-- ALL_EVENTS_PLACEHOLDER -->
</div>
    ''',
    'shop': '''
<div class="card">
    <div class="card-header">
        <h2 class="card-title"><i class="fas fa-shopping-cart"></i> Магазин койнов</h2>
    </div>
    <div style="text-align: center; margin: 30px 0; padding: 25px; background: linear-gradient(135deg, var(--primary), var(--secondary)); color: white; border-radius: var(--border-radius); box-shadow: 0 10px 30px rgba(26, 43, 107, 0.2);">
        <h3 style="margin: 0 0 15px 0; font-size: 1.8rem; font-weight: 700;">
            <i class="fas fa-wallet"></i> Ваш баланс
        </h3>
        <div style="font-size: 2.5rem; font-weight: 800; color: var(--primary);">COIN_BALANCE_PLACEHOLDER <span style="font-size: 2rem;">🪙</span></div>
        <p style="margin: 0; font-size: 1.2rem;">Тратьте койны на эксклюзивные товары и привилегии!</p>
    </div>
</div>
<!-- --- СОВРЕМЕННЫЙ СТИЛЬ МАГАЗИНА --- -->
<div class="shop-grid">
    <!-- SHOP_ITEMS_PLACEHOLDER -->
</div>
<!-- -------------------------------- -->
    '''
}

def render_template(template_name, **context):
    template = TEMPLATES[template_name]
    # Для базового шаблона
    if template_name == 'base':
        # Навигация
        if current_user.is_authenticated:
            nav_html = '''
                <li><a href="/dashboard"><i class="fas fa-home"></i> Главная</a></li>
                <li><a href="/events"><i class="fas fa-calendar-alt"></i> События</a></li>
                <li><a href="/profile"><i class="fas fa-user"></i> Профиль</a></li>
                <li><a href="/scan_qr"><i class="fas fa-qrcode"></i> Сканировать QR</a></li>
                <li><a href="/shop"><i class="fas fa-shopping-cart"></i> Магазин</a></li>
                <li><a href="/logout"><i class="fas fa-sign-out-alt"></i> Выйти</a></li>
            '''
        else:
            nav_html = '''
                <li><a href="/login"><i class="fas fa-sign-in-alt"></i> Вход</a></li>
                <li><a href="/register"><i class="fas fa-user-plus"></i> Регистрация</a></li>
            '''
        template = template.replace('<!--NAVIGATION_PLACEHOLDER -->', nav_html)
        # Сообщения
        messages_html = ''
        # Обработка flash-сообщений
        for category, message in flash.get_flashed_messages(with_categories=True):
            alert_class = 'alert-success' if category == 'success' else 'alert-error' if category == 'error' else 'alert-info'
            icon_class = 'fas fa-check-circle' if category == 'success' else 'fas fa-exclamation-circle' if category == 'error' else 'fas fa-info-circle'
            messages_html += f'''
            <div class="alert {alert_class}">
                <i class="{icon_class}"></i> {message}
            </div>
            '''
        template = template.replace('<!-- MESSAGES_PLACEHOLDER -->', messages_html)
        return template
    # Для других шаблонов - расширяем базовый
    base_template = TEMPLATES['base']
    # Заменяем контент
    template = template.replace('USERNAME_PLACEHOLDER', str(context.get('username', '')))
    template = template.replace('TOTAL_HOURS_PLACEHOLDER', str(context.get('total_hours', '')))
    template = template.replace('PROGRESS_PERCENT_PLACEHOLDER', str(context.get('progress_percent', '')))
    template = template.replace('EMAIL_PLACEHOLDER', str(context.get('email', '')))
    template = template.replace('FACULTY_PLACEHOLDER', str(context.get('faculty', '')))
    template = template.replace('PHONE_PLACEHOLDER', str(context.get('phone', 'Не указан')))
    template = template.replace('GROUP_PLACEHOLDER', str(context.get('group', 'Не указана')))
    template = template.replace('ROLE_PLACEHOLDER', str(context.get('role', '')))
    template = template.replace('TOTAL_USERS_PLACEHOLDER', str(context.get('total_users', '')))
    template = template.replace('TOTAL_EVENTS_PLACEHOLDER', str(context.get('total_events', '')))
    template = template.replace('TOTAL_ATTENDANCES_PLACEHOLDER', str(context.get('total_attendances', '')))
    template = template.replace('COIN_BALANCE_PLACEHOLDER', str(context.get('coin_balance', '0.0')))
    template = template.replace('BIO_PLACEHOLDER', str(context.get('bio', '')))
    # --- ДОБАВЛЕНИЕ КНОПКИ СЕРТИФИКАТА ---
    certificate_button_html = ''
    if current_user.is_authenticated and current_user.total_hours >= 300: # Показываем кнопку, если пользователь авторизован и достиг 300 часов
        certificate_button_html = '''
        <div style="margin-top: 25px; text-align: center;">
            <a href="/generate_certificate" class="btn btn-success" style="padding: 14px 24px; font-size: 1.1rem;">
                <i class="fas fa-download"></i> Скачать сертификат
            </a>
        </div>
        '''
    # Заменяем в шаблонах dashboard и profile
    template = template.replace('<!-- CERTIFICATE_BUTTON_PLACEHOLDER -->', certificate_button_html)
    # ------------------------------------
    # --- ЗАМЕНЫ ДЛЯ ПРОФИЛЯ ---
    if template_name == 'profile':
        # Заменяем аватар
        avatar_filename = context.get('avatar_filename')
        if avatar_filename:
            avatar_html = f'<img src="{url_for("uploaded_file", filename=avatar_filename)}" alt="Аватар" class="avatar">'
        else:
            avatar_html = '<div class="avatar-placeholder"><i class="fas fa-user"></i></div>'
        template = template.replace('<!-- AVATAR_PLACEHOLDER -->', avatar_html)
        # Заменяем био
        bio = context.get('bio')
        if bio:
            bio_html = f'<p class="user-bio">{bio}</p>'
        else:
            bio_html = ''
        template = template.replace('<!-- BIO_PLACEHOLDER -->', bio_html)
    # --- ЗАМЕНЫ ДЛЯ НАСТРОЕК ---
    if template_name == 'settings':
        # Заменяем текущий аватар
        avatar_filename = context.get('avatar_filename')
        if avatar_filename:
            current_avatar_html = f'<img src="{url_for("uploaded_file", filename=avatar_filename)}" alt="Текущий аватар" class="current-avatar">'
        else:
            current_avatar_html = '<div class="current-avatar-placeholder"><i class="fas fa-user"></i></div>'
        template = template.replace('<!-- CURRENT_AVATAR_PLACEHOLDER -->', current_avatar_html)
        # Заменяем selected для факультета
        faculty = context.get('faculty', '')
        for option_value in ["Не указан", "Информационные технологии", "Экономика и управление", "Инженерия", "Гуманитарные науки", "Медицина", "Другое"]:
            if faculty == option_value:
                template = template.replace(f'SELECTED_PLACEHOLDER_{option_value}', 'selected')
            else:
                template = template.replace(f'SELECTED_PLACEHOLDER_{option_value}', '')
    # ------------------------------------
    # Заменяем события
    if 'events' in context:
        events_html = ''
        for event in context['events']:
            # Проверяем, зарегистрирован ли текущий пользователь на это событие
            is_registered = False
            if current_user.is_authenticated:
                is_registered = db.session.execute(
                    db.select(Attendance)
                    .filter_by(user_id=current_user.id, event_id=event.id)
                ).scalar() is not None
            
            # Кнопка "Присоединиться" или "Уже зарегистрированы"
            join_button_html = ''
            if current_user.is_authenticated:
                if is_registered:
                    join_button_html = '<button class="btn btn-success btn-sm" disabled><i class="fas fa-check-circle"></i> Зарегистрированы</button>'
                else:
                    # Проверяем, не началось ли событие
                    if datetime.now() < event.date:
                        join_button_html = f'<a href="/join_event/{event.id}" class="btn btn-primary btn-sm"><i class="fas fa-calendar-plus"></i> Присоединиться</a>'
                    else:
                        join_button_html = '<button class="btn btn-secondary btn-sm" disabled><i class="fas fa-clock"></i> Событие началось/завершилось</button>'
            else:
                join_button_html = f'<a href="/login" class="btn btn-outline btn-sm"><i class="fas fa-sign-in-alt"></i> Войти</a>'
            
            events_html += f'''
            <div class="event-card">
                <div class="event-date">
                    <div class="event-day">{event.date.strftime('%d')}</div>
                    <div class="event-month">{event.date.strftime('%b')}</div>
                </div>
                <div class="event-content">
                    <div class="event-title">{event.title}</div>
                    <p>{event.description[:80]}{'...' if len(event.description) > 80 else ''}</p>
                    <div class="event-meta">
                        <div><i class="fas fa-clock"></i> {event.hours} ч</div>
                        <div><i class="fas fa-map-marker-alt"></i> {event.location}</div>
                    </div>
                    <div style="margin-top: 15px;">
                        {join_button_html}
                    </div>
                </div>
            </div>
            '''
        template = template.replace('<!-- EVENTS_PLACEHOLDER -->', events_html)
    # Заменяем все события
    if 'events' in context:
        all_events_html = ''
        for event in context['events']:
            # Добавляем QR-код, если он есть
            qr_codes_html = ''
            if event.registration_qr_code:
                qr_codes_html += f'''
<div style="margin-top: 15px;">
    <p style="font-size: 0.9rem; font-weight: 600;"><i class="fas fa-qrcode"></i> QR-код входа:</p>
    <div class="qr-code-container">
        <img src="data:image/png;base64,{event.registration_qr_code}" alt="QR-код входа" style="max-width: 120px; height: auto; border: 2px solid var(--ah-gray-200); border-radius: 8px;">
    </div>
</div>'''
            
            exit_qr_button = ''
            # Проверяем, является ли текущий пользователь админом
            is_admin = current_user.is_authenticated and current_user.role == 'admin'
            if is_admin:
                exit_qr_button = f'''
                <button onclick="generateExitQR({event.id})" class="btn btn-warning btn-sm" style="margin-top: 10px;">
                    <i class="fas fa-qrcode"></i> Генерировать QR выхода
                </button>
                <div id="exit-qr-{event.id}" style="display: none; margin-top: 10px;">
                    <p style="font-size: 0.9rem; font-weight: 600;"><i class="fas fa-sign-out-alt"></i> QR-код выхода:</p>
                    <div class="qr-code-container">
                        <img id="exit-qr-img-{event.id}" src="/placeholder.svg" alt="QR-код выхода" style="max-width: 120px; height: auto; border: 2px solid var(--ah-gray-200); border-radius: 8px;">
                    </div>
                </div>
                '''
            
            # Форма удаления события (только для админа)
            delete_form_html = ''
            if is_admin:
                delete_form_html = f'''
                <form method="POST" action="/delete_event/{event.id}" class="delete-form" onsubmit="return confirm('Вы уверены, что хотите удалить событие \'{event.title}\'? Это действие необратимо.');">
                    <button type="submit" class="btn btn-danger" style="padding: 8px 14px; font-size: 0.85rem;">
                        <i class="fas fa-trash"></i> Удалить
                    </button>
                </form>
                '''
            # Список зарегистрированных пользователей (только для админа)
            registrations_html = ''
            if is_admin:
                # Получаем список пользователей, которые зарегистрировались
                registrations = db.session.execute(
                    db.select(User.username, User.group, User.faculty, Attendance.registration_time, Attendance.credited_time)
                    .join(Attendance, User.id == Attendance.user_id)
                    .filter(Attendance.event_id == event.id)
                    .order_by(Attendance.timestamp.desc()) # Сортировка по времени регистрации (новые первые)
                ).all()
                if registrations:
                    registrations_list_html = '<ul>'
                    for reg in registrations:
                        registration_time_str = reg.registration_time.strftime('%d.%m.%Y %H:%M:%S') if reg.registration_time else "Не отмечена"
                        credited_time_str = reg.credited_time.strftime('%d.%m.%Y %H:%M:%S') if reg.credited_time else "Не зачислено"
                        # --- ДОБАВЛЕНО: Имя, группа, факультет ---
                        user_info = f"<strong>{reg.username}</strong> (Группа: {reg.group or 'Не указана'}, Факультет: {reg.faculty or 'Не указан'})"
                        registrations_list_html += f'<li>{user_info} - Регистрация: {registration_time_str}, Часы зачислены: {credited_time_str}</li>'
                    registrations_list_html += '</ul>'
                    registrations_html = f'''
                    <div class="registrations-list">
                        <h4>Зарегистрированные участники:</h4>
                        {registrations_list_html}
                    </div>
                    '''
                # Кнопка для показа/скрытия списка
                show_registrations_button = f'''
                <button class="btn btn-outline btn-sm" onclick="toggleRegistrations({event.id})" style="margin-top: 15px;">
                    <i class="fas fa-users"></i> Показать/скрыть список
                </button>
                <div id="registrations-list-{event.id}" style="display: none;">
                    {registrations_html}
                </div>
                '''
            else:
                show_registrations_button = ''
            all_events_html += f'''
            <div class="event-card">
                <div class="event-date">
                    <div class="event-day">{event.date.strftime('%d')}</div>
                    <div class="event-month">{event.date.strftime('%b')}</div>
                </div>
                <div class="event-content">
                    <div class="event-title">{event.title}</div>
                    <p style="font-size: 0.95rem;">{event.description}</p>
                    <div class="event-meta">
                        <div><i class="fas fa-clock"></i> {event.hours} часов</div>
                        <div><i class="fas fa-map-marker-alt"></i> {event.location}</div>
                        <div><i class="fas fa-calendar"></i> {event.date.strftime('%d.%m.%Y в %H:%M')}</div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; align-items: center; margin-top: 15px; gap: 10px;">
                        {qr_codes_html}
                        {exit_qr_button}
                        {delete_form_html}
                    </div>
                    {show_registrations_button}
                </div>
            </div>
            '''
        template = template.replace('<!-- ALL_EVENTS_PLACEHOLDER -->', all_events_html)
    # --- НОВОЕ: Заменяем товары магазина ---
    if 'shop_items' in context:
        shop_items_html = ''
        for item in context['shop_items']:
            # Формируем путь к изображению
            image_url = url_for('uploaded_file', filename=item.image_filename)
            shop_items_html += f'''
            <div class="shop-item">
                <div class="shop-item-image-container">
                    <img src="{image_url}" alt="{item.name}">
                </div>
                <div class="shop-item-content">
                    <h3 class="shop-item-title">{item.name}</h3>
                    <p class="shop-item-description">{item.description or 'Описание отсутствует'}</p>
                    <div class="shop-item-price">{item.price:.1f}</div>
                    <button class="btn-buy" onclick="alert('Функция покупки будет реализована в следующем обновлении!')" {'disabled' if current_user.coin_balance < item.price else ''}>
                        Купить за {item.price:.1f} 🪙
                    </button>
                </div>
            </div>
            '''
        template = template.replace('<!-- SHOP_ITEMS_PLACEHOLDER -->', shop_items_html)
    else:
        template = template.replace('<!-- SHOP_ITEMS_PLACEHOLDER -->', '<p style="text-align: center; padding: 50px; color: var(--gray); font-size: 1.2rem;"><i class="fas fa-box-open"></i> В магазине пока нет товаров.</p>')
    # ------------------------------------
    # --- НОВОЕ: Заменяем товары магазина в админ-панели ---
    if 'admin_shop_items' in context:
        admin_shop_items_html = ''
        for item in context['admin_shop_items']:
            # Формируем путь к изображению
            image_url = url_for('uploaded_file', filename=item.image_filename)
            # Форма удаления товара (только для админа)
            delete_form_html = f'''
            <form method="POST" action="/delete_shop_item/{item.id}" class="delete-form" onsubmit="return confirm('Вы уверены, что хотите удалить товар \'{item.name}\'? Это действие необратимо.');">
                <button type="submit" class="btn btn-danger btn-sm" style="padding: 8px 14px; font-size: 0.85rem; margin-top: 15px;">
                    <i class="fas fa-trash"></i> Удалить товар
                </button>
            </form>
            '''
            admin_shop_items_html += f'''
            <div class="event-card" style="border-left: 5px solid var(--accent);">
                <div style="display: flex; gap: 20px; align-items: flex-start; padding: 25px;">
                    <div style="min-width: 100px; height: 100px; overflow: hidden; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
                        <img src="{image_url}" alt="{item.name}" style="width: 100%; height: 100%; object-fit: cover;">
                    </div>
                    <div style="flex-grow: 1;">
                        <div class="event-title" style="font-size: 1.3rem; color: var(--dark); margin-bottom: 10px;">{item.name}</div>
                        <p style="font-size: 0.95rem; color: var(--gray); margin: 10px 0;">{item.description or 'Описание отсутствует'}</p>
                        <p style="font-size: 1.1rem; font-weight: 700; color: var(--primary); margin: 10px 0;"><i class="fas fa-coins"></i> Цена: {item.price:.1f} 🪙</p>
                        <p style="font-size: 0.85rem; color: var(--gray);"><i class="fas fa-calendar-plus"></i> Добавлено: {item.created_at.strftime('%d.%m.%Y %H:%M')}</p>
                        {delete_form_html}
                    </div>
                </div>
            </div>
            '''
        template = template.replace('<!-- SHOP_ITEMS_PLACEHOLDER -->', admin_shop_items_html)
    else:
        template = template.replace('<!-- SHOP_ITEMS_PLACEHOLDER -->', '<p style="text-align: center; padding: 30px; color: var(--gray);">В магазине пока нет товаров.</p>')
    # ------------------------------------
    # Заменяем посещения
    if 'attendances' in context:
        attendances_html = ''
        # Сортируем посещения по убыванию даты (новые первые)
        sorted_attendances = sorted(context['attendances'], key=lambda a: a.timestamp, reverse=True)
        for attendance in sorted_attendances:
            # Форматируем время
            registration_time = attendance.registration_time.strftime('%d.%m.%Y %H:%M:%S') if attendance.registration_time else 'Не зафиксировано'
            credited_time = attendance.credited_time.strftime('%d.%m.%Y %H:%M:%S') if attendance.credited_time else 'Не зачислено'
            attendances_html += f'''
            <div class="event-card">
                <div class="event-date">
                    <div class="event-day">{attendance.timestamp.strftime('%d')}</div>
                    <div class="event-month">{attendance.timestamp.strftime('%b')}</div>
                </div>
                <div class="event-content">
                    <div class="event-title">{attendance.event.title}</div>
                    <p>{attendance.event.description[:80]}{'...' if len(attendance.event.description) > 80 else ''}</p>
                    <div class="event-meta">
                        <div><i class="fas fa-calendar-check"></i> Регистрация: {registration_time}</div>
                        <div><i class="fas fa-clock"></i> Часы зачислены: {credited_time}</div>
                        <div><i class="fas fa-map-marker-alt"></i> {attendance.event.location}</div>
                    </div>
                </div>
            </div>
            '''
        template = template.replace('<!-- ATTENDANCES_PLACEHOLDER -->', attendances_html)
    # Заменяем кнопки регистрации/входа
    if not current_user.is_authenticated:
        register_login_html = '''
            <a href="/register" class="btn" style="font-size: 1.1rem; padding: 14px 24px; margin: 0 8px;">
                <i class="fas fa-user-plus"></i> Регистрация
            </a>
            <a href="/login" class="btn btn-outline" style="font-size: 1.1rem; padding: 14px 24px; margin: 0 8px;">
                <i class="fas fa-sign-in-alt"></i> Вход
            </a>
        '''
    else:
        register_login_html = '''
            <a href="/dashboard" class="btn" style="font-size: 1.1rem; padding: 14px 24px;">
                <i class="fas fa-arrow-right"></i> Личный кабинет
            </a>
        '''
    template = template.replace('<!-- REGISTER_LOGIN_PLACEHOLDER -->', register_login_html)
    # Вставляем контент в базовый шаблон
    result = base_template.replace('<!-- CONTENT_PLACEHOLDER -->', template)
    
    # Добавляем скрипт для генерации QR кода выхода только если админ авторизован
    if 'events' in context and current_user.is_authenticated and current_user.role == 'admin':
        result = result.replace('</body>', '''
        <script>
        function generateExitQR(eventId) {
            fetch('/generate_exit_qr/' + eventId)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('exit-qr-img-' + eventId).src = 'data:image/png;base64,' + data.qr_code;
                        document.getElementById('exit-qr-' + eventId).style.display = 'block';
                    } else {
                        alert('Ошибка генерации QR кода выхода');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Ошибка генерации QR кода выхода');
                });
        }
        </script>
        </body>''')
    
    return result
# Маршруты
@app.route('/')
def index():
    # Если пользователь авторизован, перенаправляем на dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    # Иначе перенаправляем на страницу входа
    return redirect(url_for('login'))

# --- УДАЛЕН МАРШРУТ /index ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.session.execute(db.select(User).filter_by(email=email)).scalar()
        if user and check_password_hash(user.password, password):
            login_user(user)
            # Проверяем, является ли пользователь админом
            if user.role == 'admin':
                resp = make_response(redirect(url_for('admin_panel')))
                resp.set_cookie('admin_session', 'authenticated', max_age=3600)  # 1 час
                return resp
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Неверный email или пароль', 'error')
    return render_template('login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        faculty = request.form.get('faculty')
        # --- НОВЫЕ ПОЛЯ ---
        phone = request.form.get('phone')
        group = request.form.get('group')
        # -----------------
        user = db.session.execute(db.select(User).filter_by(email=email)).scalar()
        if user:
            flash('Пользователь с таким email уже существует', 'error')
        else:
            new_user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                faculty=faculty,
                # --- НОВЫЕ ПОЛЯ ---
                phone=phone,
                group=group
                # -----------------
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Аккаунт успешно создан!', 'success')
            return redirect(url_for('login'))
    return render_template('register')

@app.route('/dashboard')
@login_required
def dashboard():
    # Получаем последние 5 событий
    events = db.session.execute(db.select(Event).order_by(Event.date.desc()).limit(5)).scalars().all()
    # Вычисляем процент выполнения
    progress_percent = min(100, round((current_user.total_hours / 300) * 100))
    # --- ДОБАВЛЕНО: Получаем баланс койнов ---
    coin_balance = current_user.coin_balance or 0.0
    # ----------------------------------------
    return render_template('dashboard',
                          username=current_user.username,
                          events=events,
                          progress_percent=progress_percent,
                          total_hours=current_user.total_hours,
                          # --- ДОБАВЛЕНО: Передаем баланс в шаблон ---
                          coin_balance=coin_balance)
                          # ----------------------------------------

@app.route('/profile')
@login_required
def profile():
    # Получаем историю посещений пользователя, отсортированную по убыванию даты
    attendances = db.session.execute(
        db.select(Attendance)
        .filter_by(user_id=current_user.id)
        .join(Event)
        .order_by(Attendance.timestamp.desc()) # Новые события первыми
    ).scalars().all()
    # Определяем роль текстом
    role_text = 'Администратор' if current_user.role == 'admin' else 'Организатор' if current_user.role == 'organizer' else 'Студент/Выпускник'
    return render_template('profile',
                          username=current_user.username,
                          email=current_user.email,
                          faculty=current_user.faculty,
                          phone=current_user.phone or 'Не указан',
                          group=current_user.group or 'Не указана',
                          role=role_text,
                          total_hours=current_user.total_hours,
                          progress_percent=min(100, round((current_user.total_hours / 300) * 100)),
                          coin_balance=current_user.coin_balance or 0.0,
                          attendances=attendances,
                          avatar_filename=current_user.avatar_filename,
                          bio=current_user.bio or '')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # Обновление данных профиля
        current_user.username = request.form.get('username')
        current_user.faculty = request.form.get('faculty')
        current_user.phone = request.form.get('phone')
        current_user.group = request.form.get('group')
        current_user.bio = request.form.get('bio')
        # Обработка загрузки аватара
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                # Генерируем уникальное имя файла
                unique_filename = f"avatar_{current_user.id}_{uuid.uuid4().hex}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                try:
                    # Открываем изображение
                    img = Image.open(file.stream)
                    # Конвертируем в RGB, если нужно (например, для PNG с прозрачностью)
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGB")
                    # Создаем маску для круглой обрезки
                    size = min(img.size)
                    mask = Image.new('L', (size, size), 0)
                    draw = ImageDraw.Draw(mask)
                    draw.ellipse((0, 0, size, size), fill=255)
                    # Обрезаем изображение до квадрата
                    left = (img.width - size) / 2
                    top = (img.height - size) / 2
                    right = (img.width + size) / 2
                    bottom = (img.height + size) / 2
                    img_cropped = img.crop((left, top, right, bottom))
                    # Применяем маску
                    output = Image.new("RGBA", (size, size))
                    output.paste(img_cropped, mask=mask)
                    # Сохраняем как PNG
                    output.save(filepath, format='PNG')
                    # Удаляем старый аватар, если он был
                    if current_user.avatar_filename:
                        old_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar_filename)
                        if os.path.exists(old_avatar_path):
                            os.remove(old_avatar_path)
                    # Обновляем имя файла в базе данных
                    current_user.avatar_filename = unique_filename
                except Exception as e:
                    flash(f'Ошибка при загрузке аватара: {str(e)}', 'error')
                    db.session.rollback()
                    return redirect('/settings')
        db.session.commit()
        flash('Профиль успешно обновлен!', 'success')
        return redirect('/profile')
    # Для GET-запроса отображаем форму
    return render_template('settings',
                          username=current_user.username,
                          faculty=current_user.faculty,
                          phone=current_user.phone or '',
                          group=current_user.group or '',
                          bio=current_user.bio or '',
                          avatar_filename=current_user.avatar_filename)

# --- НОВЫЙ МАРШРУТ: СЕРВИС ДЛЯ ОТОБРАЖЕНИЯ ЗАГРУЖЕННЫХ ФАЙЛОВ (АВАТАРОВ, ИЗОБРАЖЕНИЙ ТОВАРОВ) ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
# ------------------------------------------

@app.route('/events')
@login_required
def events():
    # Получаем все события
    all_events = db.session.execute(db.select(Event).order_by(Event.date.desc())).scalars().all()
    return render_template('events', events=all_events)

@app.route('/scan_qr')
@login_required
def scan_qr():
    return render_template('scan_qr')

# Обработка QR-кода через AJAX
@app.route('/process_qr', methods=['POST'])
@login_required
def process_qr():
    data = request.get_json()
    qr_data = data.get('qr_data', '')
    now = datetime.now()
    
    if qr_data.startswith('/event_registration_'):
        # Разбираем данные QR-кода
        try:
            # Ожидаем формат: /event_registration_<event_id>?uuid=<qr_uuid>
            path_part, query_part = qr_data.split('?', 1)
            event_id = int(path_part.split('_')[-1])
            params = dict(p.split('=') for p in query_part.split('&'))
            provided_uuid = params.get('uuid')
        except (ValueError, IndexError, KeyError):
            return jsonify({'success': False, 'message': 'Неверный формат QR-кода'})
        event = db.session.get(Event, event_id)
        if not event:
            return jsonify({'success': False, 'message': 'Событие не найдено'})
        # Проверяем UUID
        if event.qr_uuid != provided_uuid:
             return jsonify({'success': False, 'message': 'QR-код устарел или недействителен'})
        # Проверяем, началось ли событие
        if now < event.date:
            return jsonify({
                'success': False,
                'message': f'Событие ещё не началось. Оно начнётся {event.date.strftime("%d.%m.%Y в %H:%M")}'
            })
        # Проверяем, завершилось ли событие
        event_end_time = event.date + timedelta(hours=event.hours)
        if now > event_end_time:
            return jsonify({
                'success': False, 'message': f'Событие уже завершилось. Оно закончилось {event_end_time.strftime("%d.%m.%Y в %H:%M")}'})
        
        # Проверяем, есть ли уже запись о входе
        existing_entry = db.session.execute(
            db.select(EventEntry)
            .filter_by(user_id=current_user.id, event_id=event.id)
        ).scalar()
        
        if existing_entry and existing_entry.entry_time:
            return jsonify({
                'success': False,
                'message': 'Вы уже отметили вход на это событие'
            })
        
        # Создаем новую запись о входе
        if not existing_entry:
            entry = EventEntry(
                user_id=current_user.id,
                event_id=event.id,
                entry_time=now
            )
            db.session.add(entry)
        else:
            existing_entry.entry_time = now
        
        # Проверяем, зарегистрирован ли уже пользователь
        existing_attendance = db.session.execute(
            db.select(Attendance)
            .filter_by(user_id=current_user.id, event_id=event.id)
        ).scalar()
        
        if not existing_attendance:
            attendance = Attendance(
                user_id=current_user.id,
                event_id=event.id,
                registration_time=now,
                credited_time=now  # часы зачисляются сразу
            )
            db.session.add(attendance)
            current_user.total_hours += event.hours
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Вы успешно отметили вход на мероприятие "{event.title}". Часы зачислены: +{event.hours}',
        })
    
    elif qr_data.startswith('/event_exit_'):
        try:
            path_part, query_part = qr_data.split('?', 1)
            event_id = int(path_part.split('_')[-1])
            params = dict(p.split('=') for p in query_part.split('&'))
            provided_uuid = params.get('uuid')
        except (ValueError, IndexError, KeyError):
            return jsonify({'success': False, 'message': 'Неверный формат QR-кода выхода'})
        
        event = db.session.get(Event, event_id)
        if not event:
            return jsonify({'success': False, 'message': 'Событие не найдено'})
        
        # Проверяем UUID выхода
        if event.exit_qr_uuid != provided_uuid:
             return jsonify({'success': False, 'message': 'QR-код выхода устарел или недействителен'})
        
        # Ищем запись о входе
        entry = db.session.execute(
            db.select(EventEntry)
            .filter_by(user_id=current_user.id, event_id=event.id)
        ).scalar()
        
        if not entry or not entry.entry_time:
            return jsonify({
                'success': False,
                'message': 'Сначала необходимо отметить вход на мероприятие'
            })
        
        if entry.exit_time:
            return jsonify({
                'success': False,
                'message': 'Вы уже отметили выход с этого мероприятия'
            })
        
        # Отмечаем выход и вычисляем время
        entry.exit_time = now
        time_diff = now - entry.entry_time
        entry.total_minutes = int(time_diff.total_seconds() / 60)
        
        hours_spent = entry.total_minutes / 60
        coins_earned = hours_spent  # 1 коин за час
        entry.coins_earned = coins_earned
        current_user.coin_balance = (current_user.coin_balance or 0.0) + coins_earned
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Выход отмечен! Время участия: {entry.total_minutes} мин. Койны: +{coins_earned:.2f}',
            'coin_balance': current_user.coin_balance
        })
    
    else:
        return jsonify({'success': False, 'message': 'Неверный формат QR-кода'})

# --- МАРШРУТ ДЛЯ ГЕНЕРАЦИИ И СКАЧИВАНИЯ PDF ---
@app.route('/generate_certificate')
@login_required
def generate_certificate():
    """Маршрут для генерации и скачивания сертификата."""
    # Генерируем PDF
    pdf_buffer = generate_certificate_pdf(current_user)
    # Отправляем PDF файл пользователю
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"certificate_{current_user.username}.pdf",
        mimetype='application/pdf'
    )
# --------------------------------------------

# --- НОВЫЙ МАРШРУТ: СТРАНИЦА МАГАЗИНА ---
@app.route('/shop')
@login_required
def shop():
    # Получаем все товары из магазина
    shop_items = db.session.execute(db.select(ShopItem).order_by(ShopItem.created_at.desc())).scalars().all()
    coin_balance = current_user.coin_balance or 0.0
    return render_template('shop', shop_items=shop_items, coin_balance=coin_balance)

# --- НОВЫЙ МАРШРУТ: ДОБАВЛЕНИЕ ТОВАРА В МАГАЗИН (АДМИН) ---
@app.route('/admin_add_item', methods=['POST'])
def admin_add_item():
    # Проверяем, авторизован ли администратор
    if request.cookies.get('admin_session') != 'authenticated':
        flash('Доступ запрещен', 'error')
        return redirect('/adminl')
    name = request.form.get('name')
    description = request.form.get('description', '')
    price = float(request.form.get('price', 0))
    # Валидация цены
    if price < 1 or price > 100:
        flash('Цена должна быть от 1 до 100 койнов', 'error')
        return redirect('/admin_panel')
    # Проверка наличия файла
    if 'image' not in request.files:
        flash('Изображение не выбрано', 'error')
        return redirect('/admin_panel')
    file = request.files['image']
    if file.filename == '':
        flash('Изображение не выбрано', 'error')
        return redirect('/admin_panel')
    if file:
        filename = secure_filename(file.filename)
        # Генерируем уникальное имя файла
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        # Сохраняем файл временно
        file.save(filepath)
        try:
            # Открываем изображение и обрезаем до 1:1
            img = Image.open(filepath)
            min_size = min(img.size)
            left = (img.width - min_size) / 2
            top = (img.height - min_size) / 2
            right = (img.width + min_size) / 2
            bottom = (img.height + min_size) / 2
            img_cropped = img.crop((left, top, right, bottom))
            # Сохраняем обрезанное изображение, перезаписывая оригинал
            img_cropped.save(filepath)
            # Создаем запись в базе данных
            new_item = ShopItem(
                name=name,
                description=description,
                price=price,
                image_filename=unique_filename
            )
            db.session.add(new_item)
            db.session.commit()
            flash('Товар успешно добавлен в магазин!', 'success')
        except Exception as e:
            # В случае ошибки удаляем файл и откатываем транзакцию
            if os.path.exists(filepath):
                os.remove(filepath)
            db.session.rollback()
            flash(f'Ошибка при загрузке изображения: {str(e)}', 'error')
        return redirect('/admin_panel')
    else:
        flash('Ошибка при загрузке файла', 'error')
        return redirect('/admin_panel')
# ------------------------------------------

# --- НОВЫЙ МАРШРУТ: УДАЛЕНИЕ ТОВАРА ИЗ МАГАЗИНА (АДМИН) ---
@app.route('/delete_shop_item/<int:item_id>', methods=['POST'])
def delete_shop_item(item_id):
    # Проверяем, авторизован ли администратор
    if request.cookies.get('admin_session') != 'authenticated':
        flash('Доступ запрещен', 'error')
        return redirect('/adminl')
    item = db.session.get(ShopItem, item_id)
    if not item:
        flash('Товар не найден', 'error')
        return redirect('/admin_panel')
    # Удаляем файл изображения с сервера
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], item.image_filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    # Удаляем запись из базы данных
    db.session.delete(item)
    db.session.commit()
    flash(f'Товар "{item.name}" успешно удален из магазина!', 'success')
    return redirect('/admin_panel')
# ------------------------------------------

# Админ-панель
@app.route('/adminl', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Проверяем учетные данные администратора
        if username == 'Yernur@' and password == 'ernur140707':
            # Создаем сессию администратора
            resp = make_response(redirect('/admin_panel'))
            resp.set_cookie('admin_session', 'authenticated', max_age=3600)  # 1 час
            return resp
        else:
            flash('Неверный логин или пароль', 'error')
    return render_template('admin_login')

@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    # Проверяем, авторизован ли администратор
    if request.cookies.get('admin_session') != 'authenticated':
        return redirect('/adminl')
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        date_str = request.form.get('date')
        hours = int(request.form.get('hours'))
        location = request.form.get('location')
        # Преобразуем строку даты в объект datetime
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        # --- ИСПРАВЛЕНИЕ: Проверка на дубликат события перед созданием ---
        # Проверим, существует ли уже событие с такими же параметрами
        # Можно использовать более сложную логику, например, уникальность названия+даты+места
        # Для простоты проверим по названию и дате
        existing_event = db.session.execute(
            db.select(Event)
            .filter_by(title=title, date=date)
        ).scalar()
        if existing_event:
            flash(f'Событие с названием "{title}" и датой "{date_str}" уже существует!', 'error')
            # Получаем статистику и все события для повторного рендеринга
            total_users = db.session.execute(db.select(db.func.count(User.id))).scalar()
            total_events = db.session.execute(db.select(db.func.count(Event.id))).scalar()
            total_attendances = db.session.execute(db.select(db.func.count(Attendance.id))).scalar()
            all_events = db.session.execute(db.select(Event).order_by(Event.date.desc())).scalars().all()
            # --- ДОБАВЛЕНО: Получаем товары для админ-панели ---
            admin_shop_items = db.session.execute(db.select(ShopItem).order_by(ShopItem.created_at.desc())).scalars().all()
            # ------------------------------------------------
            return render_template('admin_panel',
                                  total_users=total_users,
                                  total_events=total_events,
                                  total_attendances=total_attendances,
                                  events=all_events,
                                  admin_shop_items=admin_shop_items)
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        # Создаем событие
        event = Event(
            title=title,
            description=description,
            date=date,
            hours=hours,
            location=location
        )
        db.session.add(event)
        db.session.flush()  # Получаем ID события
        # --- ГЕНЕРАЦИЯ UUID И QR-КОДА ПРИ СОЗДАНИИ ---
        # Генерируем UUID для нового события
        new_uuid = str(uuid.uuid4())
        event.qr_uuid = new_uuid
        registration_qr_data = f"/event_registration_{event.id}?uuid={new_uuid}"
        # QR-код для регистрации
        registration_qr = qrcode.QRCode(version=1, box_size=8, border=4) # Уменьшаем размер
        registration_qr.add_data(registration_qr_data)
        registration_qr.make(fit=True)
        registration_img = registration_qr.make_image(fill='black', back_color='white')
        registration_buffer = BytesIO()
        registration_img.save(registration_buffer, format='PNG')
        event.registration_qr_code = base64.b64encode(registration_buffer.getvalue()).decode()
        # ------------------------------------------------
        db.session.commit()
        flash('Событие успешно создано!', 'success')
    # Получаем статистику
    total_users = db.session.execute(db.select(db.func.count(User.id))).scalar()
    total_events = db.session.execute(db.select(db.func.count(Event.id))).scalar()
    total_attendances = db.session.execute(db.select(db.func.count(Attendance.id))).scalar()
    # Получаем все события
    all_events = db.session.execute(db.select(Event).order_by(Event.date.desc())).scalars().all()
    # --- ДОБАВЛЕНО: Получаем товары для админ-панели ---
    admin_shop_items = db.session.execute(db.select(ShopItem).order_by(ShopItem.created_at.desc())).scalars().all()
    # ------------------------------------------------
    return render_template('admin_panel',
                          total_users=total_users,
                          total_events=total_events,
                          total_attendances=total_attendances,
                          events=all_events,
                          admin_shop_items=admin_shop_items)

# Маршрут для удаления события
@app.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    # Проверяем, авторизован ли администратор
    if request.cookies.get('admin_session') != 'authenticated':
        flash('Доступ запрещен', 'error')
        return redirect('/adminl')
    event = db.session.get(Event, event_id)
    if not event:
        flash('Событие не найдено', 'error')
        return redirect('/admin_panel')
    # Удаляем все посещения, связанные с событием
    db.session.execute(db.delete(Attendance).where(Attendance.event_id == event_id))
    # Удаляем все записи о входе/выходе, связанные с событием
    db.session.execute(db.delete(EventEntry).where(EventEntry.event_id == event_id))
    # Удаляем само событие
    db.session.delete(event)
    db.session.commit()
    flash(f'Событие "{event.title}" успешно удалено!', 'success')
    return redirect('/admin_panel')

# --- МАРШРУТ ДЛЯ ГЕНЕРАЦИИ QR КОДА ВЫХОДА АДМИНОМ ---
@app.route('/generate_exit_qr/<int:event_id>')
@login_required
def generate_exit_qr(event_id):
    """Генерирует QR код для выхода с события (только для админов)."""
    if (request.cookies.get('admin_session') != 'authenticated' and 
        current_user.role != 'admin'):
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('events'))
    
    event = db.session.get(Event, event_id)
    if not event:
        flash('Событие не найдено!', 'error')
        return redirect(url_for('events'))
    
    # Генерируем новый UUID для QR кода выхода, если его нет
    if not event.exit_qr_uuid:
        event.exit_qr_uuid = str(uuid.uuid4())
        
        # Генерируем QR код для выхода
        exit_qr_data = f"/event_exit_{event_id}?uuid={event.exit_qr_uuid}"
        exit_qr = qrcode.QRCode(version=1, box_size=8, border=4)
        exit_qr.add_data(exit_qr_data)
        exit_qr.make(fit=True)
        exit_img = exit_qr.make_image(fill='black', back_color='white')
        exit_buffer = BytesIO()
        exit_img.save(exit_buffer, format='PNG')
        event.exit_qr_code = base64.b64encode(exit_buffer.getvalue()).decode()
        
        db.session.commit()
    
    # Возвращаем QR код в формате JSON
    return jsonify({
        'success': True,
        'qr_code': event.exit_qr_code
    })
# ------------------------------------------

@app.route('/logout')
@login_required
def logout():
    logout_user()
    # Удаляем админ-сессию, если она есть
    resp = make_response(redirect('/'))
    resp.set_cookie('admin_session', '', expires=0)
    return resp

# Маршрут для обработки QR-кода регистрации (теперь устаревший, но оставлен для совместимости)
# @app.route('/event_registration_<int:event_id>') # Удален, так как требует UUID в параметрах
# def event_registration(event_id):
#     # Логика перенесена в process_qr и проверяется по UUID
#     pass

# Фоновая задача для зачисления часов (без изменений)
def credit_hours():
    with app.app_context():
        # Получаем все записи, где время зачисления наступило, но часы еще не зачислены
        # Исправлено условие: credited_time <= now AND credited_time > registration_time
        # Это означает, что credited_time было установлено в будущее и это время наступило.
        now = datetime.now()
        attendances_to_credit = db.session.execute(
            db.select(Attendance)
            .filter(Attendance.credited_time <= now)
            .filter(Attendance.credited_time > Attendance.registration_time) # Проверяем, что часы еще не были зачислены (т.е. credited_time не было "обнулено")
        ).scalars().all()
        for attendance in attendances_to_credit:
            # Проверяем, не были ли часы уже зачислены (дублирующая проверка)
            # Важно: credited_time > registration_time означает, что часы еще не зачислены
            if attendance.credited_time <= now and attendance.credited_time > attendance.registration_time:
                # Добавляем часы пользователю
                user = db.session.get(User, attendance.user_id)
                if user:
                    user.total_hours += attendance.event.hours
                    # Обновляем credited_time, чтобы отметить, что часы зачислены
                    # Устанавливаем его равным registration_time, чтобы больше не обрабатывать
                    attendance.credited_time = attendance.registration_time
                    db.session.commit()

# Вызываем функцию зачисления часов при каждом запросе (для демонстрации)
# В реальном приложении используйте планировщик задач или фоновые задачи
@app.before_request
def before_request():
    credit_hours()

@app.route('/join_event/<int:event_id>')
@login_required
def join_event(event_id):
    """Присоединиться к событию кнопкой (вход)."""
    event = db.session.get(Event, event_id)
    if not event:
        flash('Событие не найдено!', 'error')
        return redirect(url_for('events'))
    
    # Проверяем, не началось ли событие
    if datetime.now() < event.date:
        flash('Событие еще не началось!', 'warning')
        return redirect(url_for('events'))
    
    # Проверяем, не завершилось ли событие
    event_end_time = event.date + timedelta(hours=event.hours)
    if datetime.now() > event_end_time:
        flash('Событие уже завершилось!', 'warning')
        return redirect(url_for('events'))

    # Проверяем, есть ли уже запись о входе без выхода
    existing_entry = db.session.execute(
        db.select(EventEntry)
        .filter_by(user_id=current_user.id, event_id=event_id, exit_time=None)
    ).scalar()
    
    if existing_entry:
        flash('Вы уже зарегистрированы на это событие!', 'warning')
        return redirect(url_for('events'))
    
    # Создаем новую запись о входе
    entry = EventEntry(
        user_id=current_user.id,
        event_id=event_id,
        entry_time=datetime.now()
    )
    db.session.add(entry)
    
    # Также создаем запись в старой таблице Attendance для совместимости
    attendance = Attendance(
        user_id=current_user.id,
        event_id=event_id,
        registration_time=datetime.now(),
        credited_time=datetime.now() + timedelta(seconds=5) # Зачисляем через 5 секунд
    )
    db.session.add(attendance)
    
    db.session.commit()
    flash(f'Вы успешно присоединились к событию "{event.title}"!', 'success')
    return redirect(url_for('events'))
# </CHANGE>

# --- ИЗМЕНЕНИЕ: Удалена первая дублирующая функция generate_exit_qr ---
# --- Оставлена только вторая, более полная версия ---
# </CHANGE>

@app.route('/event_exit_<int:event_id>')
@login_required
def event_exit(event_id):
    """Обрабатывает выход с события по QR коду."""
    uuid_param = request.args.get('uuid')
    event = db.session.get(Event, event_id)
    if not event:
        flash('Событие не найдено!', 'error')
        return redirect(url_for('events'))
    
    # Проверяем UUID
    if not uuid_param or uuid_param != event.exit_qr_uuid:
        flash('Недействительный или устаревший QR-код!', 'error')
        return redirect(url_for('events'))
    
    # Ищем запись о входе без выхода
    entry = db.session.execute(
        db.select(EventEntry)
        .filter_by(user_id=current_user.id, event_id=event_id, exit_time=None)
    ).scalar()
    
    if not entry:
        flash('Вы не зарегистрированы на это событие или уже вышли!', 'warning')
        return redirect(url_for('events'))
    
    # Записываем время выхода
    entry.exit_time = datetime.now()
    
    # Вычисляем время пребывания в минутах
    time_diff = entry.exit_time - entry.entry_time
    entry.total_minutes = int(time_diff.total_seconds() / 60)
    
    # Вычисляем койны: 1 час = 1 коин
    hours_spent = entry.total_minutes / 60
    entry.coins_earned = round(hours_spent, 2)
    
    # Добавляем койны пользователю
    current_user.coin_balance = (current_user.coin_balance or 0.0) + entry.coins_earned
    
    # Добавляем часы пользователю
    current_user.total_hours += int(hours_spent)
    
    db.session.commit()
    
    flash(f'Вы успешно вышли с события! Время пребывания: {entry.total_minutes} мин. Заработано коинов: {entry.coins_earned}', 'success')
    return redirect(url_for('events'))
# </CHANGE>

# --- ИНИЦИАЛИЗАЦИЯ И ЗАПУСК ПЛАНИРОВЩИКА ---
if __name__ == '__main__':
    # Инициализируем и запускаем планировщик
    init_scheduler()
    # Запускаем Flask-приложение
    app.run(debug=True, host='0.0.0.0', port = 5000)
# ------------------------------------------