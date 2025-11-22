"""
Urban University Platform - Полная система управления студенческими мероприятиями
Версия 3.0 - С QR-кодами, аналитикой и управлением студентами

Новые возможности:
- Динамические QR-коды с автообновлением каждую минуту
- Увеличение QR-кода при клике
- Быстрое сканирование QR-кодов
- Страница аналитики для админа
- Полный список студентов с фильтрами
- Просмотр профилей студентов
"""

from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
import os
import time
import base64
from PIL import Image
import io
import random
import string
import qrcode

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

# =============== DATABASE INITIALIZATION ===============

def init_db():
    """Инициализация базы данных с улучшенной структурой"""
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT NOT NULL,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  faculty TEXT NOT NULL,
                  phone TEXT NOT NULL,
                  group_name TEXT NOT NULL,
                  hours INTEGER DEFAULT 0,
                  coins INTEGER DEFAULT 0,
                  first_login INTEGER DEFAULT 1,
                  avatar TEXT DEFAULT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Event creators table
    c.execute('''CREATE TABLE IF NOT EXISTS event_creators
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  description TEXT,
                  date TEXT NOT NULL,
                  start_time TEXT NOT NULL,
                  end_time TEXT NOT NULL,
                  location TEXT NOT NULL,
                  hours INTEGER NOT NULL,
                  creator_id INTEGER,
                  exit_qr TEXT,
                  qr_timestamp INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (creator_id) REFERENCES event_creators (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS scans
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  event_id INTEGER,
                  exit_time TIMESTAMP,
                  hours_earned INTEGER DEFAULT 0,
                  coins_earned INTEGER DEFAULT 0,
                  status TEXT DEFAULT 'completed',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id),
                  FOREIGN KEY (event_id) REFERENCES events (id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS shop_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  image_data TEXT NOT NULL,
                  price INTEGER NOT NULL,
                  description TEXT DEFAULT '',
                  quantity INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS purchases
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  item_id INTEGER,
                  code TEXT UNIQUE NOT NULL,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id),
                  FOREIGN KEY (item_id) REFERENCES shop_items (id))''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_time_based_qr(event_id):
    """Генерация 4-символьного QR-кода, который меняется каждую минуту"""
    current_minute = int(time.time() // 60)
    seed = f"{event_id}-exit-{current_minute}"
    hash_obj = hashlib.md5(seed.encode())
    code = hash_obj.hexdigest()[:4].upper()
    return code

def generate_purchase_code():
    """Генерация уникального 6-символьного кода для покупки"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        c.execute('SELECT id FROM purchases WHERE code = ?', (code,))
        if not c.fetchone():
            conn.close()
            return code
        conn.close()

def generate_qr_image(data):
    """Генерация QR-кода в виде base64 изображения"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    image_data = base64.b64encode(buffer.read()).decode('utf-8')
    return f'data:image/png;base64,{image_data}'

# =============== ENHANCED MODERN UI STYLES ===============

MODERN_STYLES = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
    
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
    
    :root {
        --primary: #6366f1;
        --primary-dark: #4f46e5;
        --primary-light: #818cf8;
        --secondary: #8b5cf6;
        --accent: #ec4899;
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
        --dark: #1e293b;
        --light: #f8fafc;
        --gray: #64748b;
        --border: #e2e8f0;
        --shadow: rgba(0, 0, 0, 0.1);
        --shadow-lg: rgba(0, 0, 0, 0.15);
    }
    
    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
        background-attachment: fixed;
        min-height: 100vh;
        padding: 15px;
        line-height: 1.6;
        color: var(--dark);
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    
    .container {
        max-width: 1400px;
        margin: 0 auto;
        animation: fadeIn 0.5s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes slideIn {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes scaleIn {
        from { opacity: 0; transform: scale(0.9); }
        to { opacity: 1; transform: scale(1); }
    }
    
    .card {
        background: rgba(255, 255, 255, 0.98);
        border-radius: 24px;
        padding: 35px;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(20px);
        margin-bottom: 25px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        animation: scaleIn 0.4s ease-out;
    }
    
    .card:hover {
        transform: translateY(-5px);
        box-shadow: 0 30px 60px -15px rgba(0, 0, 0, 0.3);
    }
    
    .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 35px;
        flex-wrap: wrap;
        gap: 20px;
        animation: slideIn 0.5s ease-out;
    }
    
    h1 {
        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: clamp(2rem, 5vw, 3rem);
        font-weight: 800;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }
    
    h2 {
        color: var(--primary);
        font-size: clamp(1.5rem, 3vw, 2rem);
        font-weight: 700;
        margin-bottom: 25px;
        letter-spacing: -0.01em;
    }
    
    h3 {
        color: var(--dark);
        font-size: clamp(1.2rem, 2.5vw, 1.5rem);
        font-weight: 600;
        margin-bottom: 15px;
    }
    
    .btn {
        padding: 14px 32px;
        border: none;
        border-radius: 12px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        position: relative;
        overflow: hidden;
        white-space: nowrap;
    }
    
    .btn::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: translate(-50%, -50%);
        transition: width 0.6s, height 0.6s;
    }
    
    .btn:hover::before {
        width: 300px;
        height: 300px;
    }
    
    .btn > * {
        position: relative;
        z-index: 1;
    }
    
    .btn-primary {
        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
        color: white;
        box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.4);
    }
    
    .btn-primary:hover {
        transform: translateY(-3px);
        box-shadow: 0 15px 35px -5px rgba(99, 102, 241, 0.5);
    }
    
    .btn-primary:active {
        transform: translateY(-1px);
    }
    
    .btn-secondary {
        background: var(--light);
        color: var(--dark);
        border: 2px solid var(--border);
    }
    
    .btn-secondary:hover {
        background: white;
        border-color: var(--primary);
        color: var(--primary);
        transform: translateY(-2px);
    }
    
    .btn-danger {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: white;
        box-shadow: 0 10px 25px -5px rgba(239, 68, 68, 0.4);
    }
    
    .btn-danger:hover {
        transform: translateY(-3px);
        box-shadow: 0 15px 35px -5px rgba(239, 68, 68, 0.5);
    }
    
    .btn-success {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.4);
    }
    
    .btn-success:hover {
        transform: translateY(-3px);
        box-shadow: 0 15px 35px -5px rgba(16, 185, 129, 0.5);
    }
    
    input, select, textarea {
        width: 100%;
        padding: 16px 20px;
        border: 2px solid var(--border);
        border-radius: 12px;
        font-size: 16px;
        font-family: inherit;
        margin-bottom: 18px;
        transition: all 0.3s ease;
        background: white;
    }
    
    input:focus, select:focus, textarea:focus {
        outline: none;
        border-color: var(--primary);
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
        transform: translateY(-2px);
    }
    
    input::placeholder {
        color: var(--gray);
    }
    
    label {
        display: block;
        font-weight: 600;
        margin-bottom: 10px;
        color: var(--dark);
        font-size: 15px;
    }
    
    .alert {
        padding: 18px 24px;
        border-radius: 12px;
        margin-bottom: 25px;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 12px;
        animation: slideIn 0.4s ease-out;
    }
    
    .alert::before {
        font-size: 24px;
    }
    
    .alert-success {
        background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
        color: #065f46;
        border: 2px solid #6ee7b7;
    }
    
    .alert-success::before {
        content: '✅';
    }
    
    .alert-error {
        background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
        color: #991b1b;
        border: 2px solid #fca5a5;
    }
    
    .alert-error::before {
        content: '❌';
    }
    
    .grid {
        display: grid;
        gap: 25px;
    }
    
    .grid-2 {
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
    }
    
    .grid-3 {
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
    }
    
    .grid-4 {
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
    }
    
    .stat-card {
        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
        color: white;
        padding: 30px;
        border-radius: 20px;
        text-align: center;
        box-shadow: 0 20px 40px -10px rgba(99, 102, 241, 0.4);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .stat-card::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        animation: rotate 20s linear infinite;
    }
    
    @keyframes rotate {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    
    .stat-card:hover {
        transform: translateY(-8px) scale(1.02);
        box-shadow: 0 25px 50px -10px rgba(99, 102, 241, 0.5);
    }
    
    .stat-number {
        font-size: clamp(2.5rem, 6vw, 4rem);
        font-weight: 800;
        margin: 15px 0;
        position: relative;
        z-index: 1;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }
    
    .stat-label {
        font-size: clamp(1rem, 2vw, 1.3rem);
        opacity: 0.95;
        font-weight: 600;
        position: relative;
        z-index: 1;
    }
    
    table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin-top: 25px;
        overflow: hidden;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px var(--shadow);
    }
    
    th, td {
        padding: 18px 20px;
        text-align: left;
        border-bottom: 1px solid var(--border);
    }
    
    th {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        font-weight: 700;
        color: var(--primary);
        text-transform: uppercase;
        font-size: 13px;
        letter-spacing: 0.05em;
        cursor: pointer;
        user-select: none;
        position: sticky;
        top: 0;
        z-index: 10;
    }
    
    th:hover {
        background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
    }
    
    tbody tr {
        transition: all 0.2s ease;
        background: white;
    }
    
    tbody tr:hover {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        transform: scale(1.01);
        box-shadow: 0 4px 12px -2px var(--shadow);
    }
    
    tbody tr:last-child td {
        border-bottom: none;
    }
    
    /* QR Code Styles */
    .qr-container {
        text-align: center;
        padding: 30px;
        background: white;
        border-radius: 20px;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 10px 30px -5px var(--shadow);
    }
    
    .qr-container:hover {
        transform: scale(1.05);
        box-shadow: 0 20px 40px -5px var(--shadow-lg);
    }
    
    .qr-code-img {
        max-width: 350px;
        width: 100%;
        height: auto;
        border-radius: 15px;
        box-shadow: 0 8px 20px -5px var(--shadow);
    }
    
    .modal {
        display: none;
        position: fixed;
        z-index: 9999;
        left: 0;
        top: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.85);
        backdrop-filter: blur(10px);
        justify-content: center;
        align-items: center;
        animation: fadeIn 0.3s ease;
    }
    
    .modal.active {
        display: flex;
    }
    
    .modal-content {
        background: white;
        padding: 40px;
        border-radius: 24px;
        max-width: 90%;
        max-height: 90%;
        position: relative;
        animation: scaleIn 0.3s ease-out;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }
    
    .modal-close {
        position: absolute;
        top: 15px;
        right: 25px;
        font-size: 36px;
        cursor: pointer;
        color: var(--gray);
        transition: all 0.2s ease;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
    }
    
    .modal-close:hover {
        color: var(--danger);
        background: var(--light);
        transform: rotate(90deg);
    }
    
    .modal-qr {
        max-width: 700px;
        width: 100%;
    }
    
    /* Filter Styles */
    .filter-bar {
        display: flex;
        gap: 18px;
        margin-bottom: 25px;
        flex-wrap: wrap;
    }
    
    .filter-bar input,
    .filter-bar select {
        flex: 1;
        min-width: 220px;
        margin-bottom: 0;
    }
    
    .student-row {
        cursor: pointer;
    }
    
    .badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    
    .badge-success {
        background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
        color: #065f46;
    }
    
    .badge-warning {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        color: #92400e;
    }
    
    .badge-info {
        background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
        color: #1e40af;
    }
    
    .progress-bar {
        width: 100%;
        height: 35px;
        background: var(--light);
        border-radius: 20px;
        overflow: hidden;
        margin: 15px 0;
        box-shadow: inset 0 2px 4px var(--shadow);
    }
    
    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: 700;
        font-size: 15px;
        transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 2px 10px rgba(99, 102, 241, 0.4);
    }
    
    .chart-container {
        background: white;
        padding: 25px;
        border-radius: 20px;
        margin: 25px 0;
        box-shadow: 0 4px 6px -1px var(--shadow);
    }
    
    /* Responsive Design */
    @media (max-width: 768px) {
        body {
            padding: 10px;
        }
        
        .card {
            padding: 25px 20px;
            border-radius: 20px;
        }
        
        .header {
            flex-direction: column;
            align-items: flex-start;
        }
        
        h1 {
            font-size: 2rem;
        }
        
        .btn {
            width: 100%;
            padding: 16px 24px;
        }
        
        .grid-2, .grid-3, .grid-4 {
            grid-template-columns: 1fr;
        }
        
        table {
            font-size: 14px;
        }
        
        th, td {
            padding: 12px 10px;
        }
        
        .stat-number {
            font-size: 3rem;
        }
        
        .filter-bar {
            flex-direction: column;
        }
        
        .filter-bar input,
        .filter-bar select {
            width: 100%;
            min-width: 100%;
        }
    }
    
    @media (max-width: 480px) {
        .modal-content {
            padding: 25px;
            max-width: 95%;
        }
        
        .qr-code-img {
            max-width: 250px;
        }
    }
    
    /* Loading Animation */
    .loading {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(255, 255, 255, 0.3);
        border-radius: 50%;
        border-top-color: white;
        animation: spin 0.8s linear infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    /* Smooth Scrollbar */
    ::-webkit-scrollbar {
        width: 12px;
        height: 12px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--light);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
        border-radius: 10px;
        border: 2px solid var(--light);
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(135deg, var(--primary-dark) 0%, var(--secondary) 100%);
    }
    
    /* Link Styles */
    a {
        color: var(--primary);
        text-decoration: none;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    a:hover {
        color: var(--secondary);
        text-decoration: underline;
    }
    
    /* Form Styles */
    form {
        animation: fadeIn 0.5s ease-out;
    }
    
    /* Utility Classes */
    .text-center {
        text-align: center;
    }
    
    .mt-1 { margin-top: 10px; }
    .mt-2 { margin-top: 20px; }
    .mt-3 { margin-top: 30px; }
    .mb-1 { margin-bottom: 10px; }
    .mb-2 { margin-bottom: 20px; }
    .mb-3 { margin-bottom: 30px; }
    
    .p-1 { padding: 10px; }
    .p-2 { padding: 20px; }
    .p-3 { padding: 30px; }
</style>
"""

# =============== ENHANCED TEMPLATES ===============

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Вход</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА: CSS CUSTOM PROPERTIES === */
        :root {
            /* Цвета из ТЗ */
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --accent-yellow: #FFB030;
            --accent-violet: #50318F;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            /* Типографика (ТЗ: шкала Montserrat) */
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            /* Сетка (8px-based) */
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 520px;
            margin: 60px auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .logo-header {
            text-align: center;
            margin-bottom: var(--space-4);
        }
        .logo-header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            letter-spacing: -0.5px;
            color: var(--primary-black);
            margin-bottom: var(--space-1);
        }
        .logo-header .tagline {
            font-size: var(--body-size);
            font-weight: var(--body-weight);
            color: var(--dark-grey);
            margin-bottom: var(--space-1);
        }
        .logo-header .power {
            font-size: var(--h2-size);
            font-weight: var(--h2-weight);
            color: var(--primary-red);
            letter-spacing: 1px;
        }
        .illustration {
            text-align: center;
            margin: var(--space-4) 0;
        }
        .illustration i {
            font-size: 64px;
            color: var(--primary-red);
        }
        .alert {
            padding: var(--space-2);
            border-radius: 8px;
            margin-bottom: var(--space-3);
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
            background: #fee;
            border-left: 4px solid var(--primary-red);
            color: var(--primary-black);
        }
        label {
            display: block;
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
            margin-bottom: var(--space-1);
            color: var(--primary-black);
        }
        input {
            width: 100%;
            padding: var(--space-2);
            border: 1px solid var(--light-grey);
            border-radius: 8px;
            font-family: inherit;
            font-size: var(--body-size);
            margin-bottom: var(--space-3);
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: var(--primary-red);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        .btn {
            width: 100%;
            padding: var(--space-2) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
        }
        .btn-primary {
            background: var(--primary-red);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
        }
        .divider {
            margin: var(--space-4) 0;
            padding-top: var(--space-3);
            border-top: 1px solid var(--light-grey);
            text-align: center;
        }
        .divider p {
            color: var(--grey);
            font-size: var(--body-size);
            margin-bottom: var(--space-2);
        }
        .btn-secondary {
            background: var(--card-bg);
            color: var(--primary-black);
            border: 1px solid var(--light-grey);
        }
        .btn-secondary:hover {
            background: #f5f5f5;
            border-color: var(--grey);
        }
        .link {
            display: block;
            text-align: center;
            margin-top: var(--space-2);
            font-size: var(--body-size);
            color: var(--dark-grey);
            text-decoration: none;
        }
        .link:hover {
            color: var(--primary-red);
            text-decoration: underline;
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            .logo-header h1 {
                font-size: 24px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo-header">
                <h1>URBAN COLLEGE</h1>
                <div class="tagline">Платформа студенческих мероприятий</div>
                <div class="power">МЕСТО СИЛЫ</div>
            </div>
            <div class="illustration">
                <i class='bx bx-graduation-cap'></i>
            </div>

            {% if error %}
            <div class="alert">{{ error }}</div>
            {% endif %}

            <form method="POST">
                <label>Username</label>
                <input type="text" name="username" placeholder="Введите ваш username" required autofocus>

                <label>Пароль</label>
                <input type="password" name="password" placeholder="••••••••" required>

                <button type="submit" class="btn btn-primary">
                    <i class='bx bx-log-in-circle'></i>
                    Войти в систему
                </button>
            </form>

            <div class="divider">
                <p>Нет аккаунта?</p>
                <a href="/register" class="btn btn-secondary">
                    <i class='bx bx-user-plus'></i>
                    Зарегистрироваться
                </a>
            </div>

            <a href="/creator/login" class="link">
                <i class='bx bx-user-voice'></i>
                Вход для организаторов мероприятий
            </a>
        </div>
    </div>
</body>
</html>
"""

REGISTER_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Регистрация</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА: CSS CUSTOM PROPERTIES === */
        :root {
            /* Цвета из ТЗ */
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --accent-yellow: #FFB030;
            --accent-violet: #50318F;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            /* Типографика (ТЗ: шкала Montserrat) */
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            /* Сетка (8px-based) */
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 650px;
            margin: 40px auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .logo-header {
            text-align: center;
            margin-bottom: var(--space-4);
        }
        .logo-header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            letter-spacing: -0.5px;
            color: var(--primary-black);
            margin-bottom: var(--space-1);
        }
        .logo-header .tagline {
            font-size: var(--body-size);
            font-weight: var(--body-weight);
            color: var(--dark-grey);
            margin-bottom: var(--space-1);
        }
        .logo-header .power {
            font-size: var(--h2-size);
            font-weight: var(--h2-weight);
            color: var(--primary-red);
            letter-spacing: 1px;
        }
        .illustration {
            text-align: center;
            margin: var(--space-4) 0;
        }
        .illustration i {
            font-size: 64px;
            color: var(--primary-red);
        }
        .alert {
            padding: var(--space-2);
            border-radius: 8px;
            margin-bottom: var(--space-3);
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
            background: #fee;
            border-left: 4px solid var(--primary-red);
            color: var(--primary-black);
        }
        label {
            display: block;
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
            margin-bottom: var(--space-1);
            color: var(--primary-black);
        }
        input {
            width: 100%;
            padding: var(--space-2);
            border: 1px solid var(--light-grey);
            border-radius: 8px;
            font-family: inherit;
            font-size: var(--body-size);
            margin-bottom: var(--space-3);
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: var(--primary-red);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        .btn {
            width: 100%;
            padding: var(--space-2) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
        }
        .btn-primary {
            background: var(--primary-red);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
        }
        .grid {
            display: grid;
            gap: var(--space-2);
            margin-bottom: var(--space-2);
        }
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        }
        @media (max-width: 580px) {
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }
        .divider {
            margin-top: var(--space-4);
            padding-top: var(--space-3);
            border-top: 1px solid var(--light-grey);
            text-align: center;
        }
        .divider a {
            color: var(--dark-grey);
            text-decoration: none;
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
            transition: color 0.2s;
        }
        .divider a:hover {
            color: var(--primary-red);
            text-decoration: underline;
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            .logo-header h1 {
                font-size: 24px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo-header">
                <h1>URBAN COLLEGE</h1>
                <div class="tagline">Создайте аккаунт для участия в мероприятиях</div>
                <div class="power">МЕСТО СИЛЫ</div>
            </div>
            <div class="illustration">
                <i class='bx bx-user-plus'></i>
            </div>

            {% if error %}
            <div class="alert">{{ error }}</div>
            {% endif %}

            <form method="POST">
                <div class="grid grid-2">
                    <div>
                        <label>Полное имя</label>
                        <input type="text" name="full_name" placeholder="Иванов Иван Иванович" required>
                    </div>
                    <div>
                        <label>Username</label>
                        <input type="text" name="username" placeholder="ivan_ivanov" required>
                    </div>
                </div>

                <label>Пароль</label>
                <input type="password" name="password" placeholder="••••••••" required minlength="6">

                <div class="grid grid-2">
                    <div>
                        <label>Факультет</label>
                        <input type="text" name="faculty" placeholder="Например: ИТ" required>
                    </div>
                    <div>
                        <label>Группа</label>
                        <input type="text" name="group_name" placeholder="Например: ИТ-21" required>
                    </div>
                </div>

                <label>Телефон</label>
                <input type="tel" name="phone" placeholder="+7 (___) ___-__-__" required>

                <button type="submit" class="btn btn-primary">
                    <i class='bx bx-chevron-right'></i>
                    Создать аккаунт
                </button>
            </form>

            <div class="divider">
                <a href="/login">
                    <i class='bx bx-log-in-circle'></i>
                    Уже есть аккаунт? Войти
                </a>
            </div>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Панель студента</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА: CSS CUSTOM PROPERTIES (ТОЧНО ПО ТЗ) === */
        :root {
            /* Цвета */
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --accent-yellow: #FFB030;
            --accent-violet: #50318F;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            /* Типографика */
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            /* Сетка (8px-based) */
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-4);
        }
        .header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            letter-spacing: -0.5px;
            color: var(--primary-black);
            margin: 0;
        }
        .header p {
            color: var(--dark-grey);
            font-size: var(--body-size);
            margin-top: var(--space-1);
        }
        .stat-card {
            background: var(--card-bg);
            border: 2px solid var(--primary-red);
            border-radius: 12px;
            padding: var(--space-3);
            text-align: center;
            box-shadow: 0 4px 12px rgba(225, 37, 83, 0.1);
        }
        .stat-card.green {
            border-color: var(--accent-green);
            box-shadow: 0 4px 12px rgba(39, 163, 138, 0.1);
        }
        .stat-label {
            font-size: var(--body-size);
            font-weight: var(--body-weight);
            color: var(--dark-grey);
            letter-spacing: 0.5px;
            margin-bottom: var(--space-1);
        }
        .stat-number {
            font-size: clamp(2.5rem, 5vw, 3.5rem);
            font-weight: var(--h1-weight);
            margin: var(--space-2) 0;
        }
        .stat-card:not(.green) .stat-number {
            color: var(--primary-red);
        }
        .stat-card.green .stat-number {
            color: var(--accent-green);
        }
        .note {
            font-size: 13px;
            color: var(--grey);
            margin-top: var(--space-1);
        }
        .actions-header {
            font-size: var(--h2-size);
            font-weight: var(--h2-weight);
            margin: var(--space-5) 0 var(--space-3);
            color: var(--primary-black);
        }
        .grid {
            display: grid;
            gap: var(--space-3);
        }
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }
        .grid-3 {
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        }
        .btn {
            width: 100%;
            padding: var(--space-2) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            cursor: pointer;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
            text-decoration: none;
            position: relative;
            overflow: hidden;
        }
        /* === ФИКС: ПОСТОЯННЫЕ ЦВЕТНЫЕ ФОНЫ ДЛЯ 3 ОСНОВНЫХ КНОПОК === */
        .btn-primary {
            background: var(--primary-red);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(225, 37, 83, 0.2);
        }
        .btn-green {
            background: var(--accent-green);
            color: white;
        }
        .btn-green:hover {
            background: #1f8a70;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(39, 163, 138, 0.2);
        }
        .btn-purple {
            background: linear-gradient(135deg, var(--accent-violet) 0%, var(--accent-green) 100%);
            color: white;
        }
        .btn-purple:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(80, 49, 143, 0.2);
        }
        /* Второстепенные кнопки — outline */
        .btn-outline {
            background: var(--card-bg);
            color: var(--primary-black);
            border: 1px solid var(--light-grey);
        }
        .btn-outline:hover {
            background: #fafafa;
            border-color: var(--grey);
        }
        .btn-icon {
            font-size: 32px;
            margin: 0;
            line-height: 1;
        }
        .btn-label {
            font-size: 16px;
            font-weight: var(--h2-weight);
            margin: 0;
        }
        .btn-desc {
            font-size: 12px;
            font-weight: var(--body-weight);
            opacity: 0.9;
            margin: 0;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .stat-number {
                font-size: 2.8rem;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            .grid-3 {
                grid-template-columns: 1fr;
            }
            .btn-icon {
                font-size: 28px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>👋 Привет, {{ user_name }}!</h1>
                    <p>Добро пожаловать в вашу панель управления</p>
                </div>
                <form method="POST" action="/logout" style="margin: 0;">
                    <button type="submit" class="btn btn-outline" style="width: auto; padding: var(--space-1) var(--space-3);">
                        <i class='bx bx-log-out'></i>
                        Выйти
                    </button>
                </form>
            </div>

            <div class="grid grid-2 mb-3">
                <div class="stat-card">
                    <div class="stat-label">⏱️ Накоплено часов</div>
                    <div class="stat-number">{{ hours }}</div>
                    <div class="note">Продолжайте участвовать!</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-label">🪙 Баланс койнов</div>
                    <div class="stat-number">{{ coins }}</div>
                    <div class="note">Тратьте в магазине</div>
                </div>
            </div>

            <h2 class="actions-header">🚀 Быстрые действия</h2>
            <div class="grid grid-3">
                <a href="/scan" class="btn btn-primary">
                    <i class='bx bx-mobile' style="font-size: 36px;"></i>
                    <div class="btn-label">Сканировать QR</div>
                    <div class="btn-desc">Отметить посещение</div>
                </a>
                <a href="/events" class="btn btn-green">
                    <i class='bx bx-calendar' style="font-size: 36px;"></i>
                    <div class="btn-label">Мероприятия</div>
                    <div class="btn-desc">Список событий</div>
                </a>
                <a href="/shop" class="btn btn-purple">
                    <i class='bx bx-store' style="font-size: 36px;"></i>
                    <div class="btn-label">Магазин</div>
                    <div class="btn-desc">Потратить койны</div>
                </a>
                <a href="/history" class="btn btn-outline">
                    <i class='bx bx-history' style="font-size: 32px;"></i>
                    <div class="btn-label">История</div>
                </a>
                <a href="/profile" class="btn btn-outline">
                    <i class='bx bx-user' style="font-size: 32px;"></i>
                    <div class="btn-label">Профиль</div>
                </a>
                {% if show_certificate %}
                <a href="/certificate" class="btn btn-outline">
                    <i class='bx bx-award' style="font-size: 32px;"></i>
                    <div class="btn-label">Сертификат</div>
                </a>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

SCAN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Сканировать QR</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА === */
        :root {
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', system-ui, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 700px;
            margin: 40px auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-4);
        }
        .header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            color: var(--primary-black);
            margin: 0;
        }
        .alert {
            padding: var(--space-2);
            border-radius: 8px;
            margin-bottom: var(--space-3);
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
        }
        .alert-success {
            background: #d1fae5;
            color: #065f46;
            border-left: 4px solid var(--accent-green);
        }
        .alert-error {
            background: #fee;
            color: #991b1b;
            border-left: 4px solid var(--primary-red);
        }
        .illustration {
            text-align: center;
            margin: var(--space-4) 0;
        }
        .illustration i {
            font-size: 64px;
            color: var(--primary-red);
        }
        .camera-container {
            margin-bottom: var(--space-4);
        }
        .btn {
            width: 100%;
            padding: var(--space-2) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
        }
        .btn-success {
            background: var(--accent-green);
            color: white;
        }
        .btn-success:hover {
            background: #1f8a70;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(39, 163, 138, 0.2);
        }
        .btn-danger {
            background: var(--primary-red);
            color: white;
        }
        .btn-danger:hover {
            background: #c91f47;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(225, 37, 83, 0.2);
        }
        #qr-video {
            width: 100%;
            border-radius: 8px;
            margin-top: var(--space-3);
            display: none;
            box-shadow: 0 4px 8px rgba(0,0,0,0.08);
        }
        .separator {
            text-align: center;
            margin: var(--space-4) 0;
            color: var(--grey);
            font-weight: var(--btn-weight);
            position: relative;
            padding: 0 var(--space-3);
        }
        .separator::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: var(--light-grey);
            z-index: 0;
        }
        .separator span {
            background: var(--card-bg);
            position: relative;
            z-index: 1;
            padding: 0 var(--space-2);
        }
        label {
            display: block;
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
            margin-bottom: var(--space-1);
            color: var(--primary-black);
        }
        input[name="qr_code"] {
            width: 100%;
            padding: var(--space-2) var(--space-3);
            border: 1px solid var(--light-grey);
            border-radius: 8px;
            font-size: 28px;
            font-family: inherit;
            text-align: center;
            letter-spacing: 8px;
            font-weight: var(--h2-weight);
            text-transform: uppercase;
            margin-bottom: var(--space-3);
            transition: border-color 0.2s;
        }
        input[name="qr_code"]:focus {
            outline: none;
            border-color: var(--primary-red);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        .btn-primary {
            background: var(--primary-red);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(225, 37, 83, 0.2);
        }
        .info-card {
            background: var(--card-bg);
            border: 1px solid var(--light-grey);
            border-radius: 12px;
            padding: var(--space-3);
            margin-top: var(--space-4);
        }
        .info-card h3 {
            font-size: var(--h2-size);
            font-weight: var(--h2-weight);
            color: var(--primary-red);
            display: flex;
            align-items: center;
            gap: var(--space-2);
            margin-bottom: var(--space-2);
        }
        .info-card ol {
            padding-left: var(--space-4);
            line-height: 2.0;
        }
        .info-card li {
            margin-bottom: var(--space-2);
            font-weight: var(--body-weight);
        }
        .info-card li strong {
            color: var(--primary-red);
            font-weight: var(--h2-weight);
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            input[name="qr_code"] {
                font-size: 24px;
                letter-spacing: 6px;
                padding: var(--space-2);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>📱 Сканировать QR-код</h1>
                <a href="/dashboard" class="btn" style="background: var(--card-bg); border: 1px solid var(--light-grey); color: var(--primary-black);">
                    <i class='bx bx-arrow-back'></i>
                    Назад
                </a>
            </div>

            {% if success %}
            <div class="alert alert-success">
                <i class='bx bx-check-circle'></i>
                {{ success }}
            </div>
            {% endif %}
            {% if error %}
            <div class="alert alert-error">
                <i class='bx bx-error-circle'></i>
                {{ error }}
            </div>
            {% endif %}

            <div class="illustration">
                <i class='bx bx-mobile'></i>
            </div>

            <div class="camera-container">
                <button id="start-camera" class="btn btn-success">
                    <i class='bx bx-qrcode-scan'></i>
                    Открыть камеру для сканирования
                </button>
                <video id="qr-video" playsinline></video>
                <canvas id="qr-canvas" style="display: none;"></canvas>
            </div>

            <div class="separator">
                <span>или</span>
            </div>

            <form method="POST">
                <label>Введите 4-символьный код</label>
                <input type="text" name="qr_code" placeholder="A1B2" maxlength="4" required>
                <button type="submit" class="btn btn-primary">
                    <i class='bx bx-barcode-reader'></i>
                    Подтвердить выход с мероприятия
                </button>
            </form>

            <div class="info-card">
                <h3>
                    <i class='bx bx-info-circle'></i>
                    Как это работает?
                </h3>
                <ol>
                    <li><strong>Посетите мероприятие</strong> и участвуйте в нем</li>
                    <li><strong>В конце получите QR-код</strong> от организатора</li>
                    <li><strong>Отсканируйте камерой</strong> или введите 4-символьный код</li>
                    <li><strong>Получите часы и койны</strong> автоматически на ваш счёт!</li>
                </ol>
            </div>
        </div>
    </div>

    <script src="https://unpkg.com/jsqr@1.4.0/dist/jsQR.js"></script>
    <script>
        const video = document.getElementById('qr-video');
        const canvas = document.getElementById('qr-canvas');
        const startBtn = document.getElementById('start-camera');
        const ctx = canvas.getContext('2d');
        let scanning = false;

        startBtn.addEventListener('click', async () => {
            if (!scanning) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        video: { facingMode: 'environment' } 
                    });
                    video.srcObject = stream;
                    video.play();
                    video.style.display = 'block';
                    startBtn.innerHTML = '<i class="bx bx-stop-circle"></i> Остановить сканирование';
                    startBtn.classList.remove('btn-success');
                    startBtn.classList.add('btn-danger');
                    scanning = true;
                    requestAnimationFrame(tick);
                } catch (err) {
                    alert('Ошибка доступа к камере: ' + (err.message || 'разрешение не дано'));
                }
            } else {
                const stream = video.srcObject;
                const tracks = stream.getTracks();
                tracks.forEach(track => track.stop());
                video.style.display = 'none';
                startBtn.innerHTML = '<i class="bx bx-qrcode-scan"></i> Открыть камеру для сканирования';
                startBtn.classList.remove('btn-danger');
                startBtn.classList.add('btn-success');
                scanning = false;
            }
        });

        function tick() {
            if (!scanning) return;
            if (video.readyState === video.HAVE_ENOUGH_DATA) {
                canvas.height = video.videoHeight;
                canvas.width = video.videoWidth;
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                const code = jsQR(imageData.data, imageData.width, imageData.height);
                if (code) {
                    const qrData = code.data;
                    if (qrData.length >= 4) {
                        const extractedCode = qrData.slice(-4).toUpperCase();
                        document.querySelector('input[name="qr_code"]').value = extractedCode;
                        const stream = video.srcObject;
                        const tracks = stream.getTracks();
                        tracks.forEach(track => track.stop());
                        video.style.display = 'none';
                        scanning = false;
                        document.querySelector('form').submit();
                    }
                }
            }
            requestAnimationFrame(tick);
        }
    </script>
</body>
</html>
"""

EVENTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Мероприятия</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА === */
        :root {
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', system-ui, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-4);
        }
        .header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            color: var(--primary-black);
            margin: 0;
        }
        .header p {
            color: var(--dark-grey);
            font-size: var(--body-size);
            margin-top: var(--space-1);
        }
        .empty-state {
            text-align: center;
            padding: var(--space-5) var(--space-2);
        }
        .empty-state i {
            font-size: 64px;
            color: var(--primary-red);
            margin-bottom: var(--space-3);
            opacity: 0.5;
        }
        .empty-state p {
            color: var(--dark-grey);
            font-size: var(--body-size);
        }
        .event-card {
            background: var(--card-bg);
            border: 2px solid var(--primary-red);
            border-radius: 12px;
            padding: var(--space-3);
            margin-bottom: var(--space-3);
            box-shadow: 0 4px 12px rgba(225, 37, 83, 0.1);
            transition: all 0.2s ease;
        }
        .event-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 16px rgba(225, 37, 83, 0.15);
        }
        .event-card h2 {
            font-size: var(--h2-size);
            font-weight: var(--h2-weight);
            color: var(--primary-red);
            margin-bottom: var(--space-2);
            line-height: 1.3;
        }
        .event-card .desc {
            color: var(--dark-grey);
            margin-bottom: var(--space-3);
            line-height: 1.6;
        }
        .event-meta {
            display: grid;
            gap: var(--space-2);
            margin-bottom: var(--space-3);
        }
        .meta-item {
            display: flex;
            align-items: flex-start;
            gap: var(--space-2);
            padding: var(--space-2);
            background: var(--light-grey);
            border-radius: 8px;
            font-weight: var(--body-weight);
        }
        .meta-item i {
            font-size: 20px;
            min-width: 24px;
            text-align: center;
        }
        .meta-item.green {
            border-left: 4px solid var(--accent-green);
            background: #f0fdfa;
        }
        .meta-item.green i {
            color: var(--accent-green);
        }
        .meta-item i {
            color: var(--primary-red);
        }
        .reward {
            display: flex;
            align-items: center;
            gap: var(--space-1);
            background: #f0fdfa;
            border: 2px solid var(--accent-green);
            border-radius: 8px;
            padding: var(--space-2);
            font-weight: var(--h2-weight);
            color: var(--accent-green);
        }
        .btn {
            width: auto;
            padding: var(--space-1) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            color: var(--primary-black);
            background: var(--card-bg);
            border: 1px solid var(--light-grey);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
        }
        .btn:hover {
            border-color: var(--primary-red);
            color: var(--primary-red);
            background: #fff9f9;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            .event-meta {
                gap: var(--space-1);
            }
            .meta-item {
                padding: var(--space-1);
                font-size: 14px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>📅 Мероприятия</h1>
                    <p>Список всех доступных мероприятий</p>
                </div>
                <a href="/dashboard" class="btn">
                    <i class='bx bx-arrow-back'></i>
                    Назад
                </a>
            </div>

            {% if events %}
                {% for event in events %}
                <div class="event-card">
                    <h2>{{ event[1] }}</h2>
                    {% if event[2] %}
                    <p class="desc">{{ event[2] }}</p>
                    {% endif %}
                    <div class="event-meta">
                        <div class="meta-item">
                            <i class='bx bx-calendar'></i>
                            <span>{{ event[3] }}</span>
                        </div>
                        <div class="meta-item">
                            <i class='bx bx-time'></i>
                            <span>{{ event[4] }} – {{ event[5] }}</span>
                        </div>
                        <div class="meta-item">
                            <i class='bx bx-map'></i>
                            <span>{{ event[7] }}</span>
                        </div>
                        <div class="meta-item green">
                            <i class='bx bx-hourglass'></i>
                            <span>{{ event[6] }} часов</span>
                        </div>
                    </div>
                </div>
                {% endfor %}
            {% else %}
            <div class="empty-state">
                <i class='bx bx-calendar-x'></i>
                <p>Пока нет доступных мероприятий</p>
                <p style="font-size: 14px; margin-top: var(--space-2);">Следите за обновлениями!</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

HISTORY_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — История посещений</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА === */
        :root {
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', system-ui, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-4);
        }
        .header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            color: var(--primary-black);
            margin: 0;
        }
        .header p {
            color: var(--dark-grey);
            font-size: var(--body-size);
            margin-top: var(--space-1);
        }
        .empty-state {
            text-align: center;
            padding: var(--space-5) var(--space-2);
        }
        .empty-state i {
            font-size: 64px;
            color: var(--primary-red);
            margin-bottom: var(--space-3);
            opacity: 0.5;
        }
        .empty-state p {
            color: var(--dark-grey);
            font-size: var(--body-size);
        }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin-top: var(--space-3);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        }
        th, td {
            padding: var(--space-2) var(--space-3);
            text-align: left;
            border-bottom: 1px solid var(--light-grey);
        }
        th {
            background: var(--card-bg);
            font-weight: var(--h2-weight);
            font-size: 13px;
            color: var(--primary-red);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            position: sticky;
            top: 0;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        tbody tr:hover {
            background: #fafafa;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            padding: var(--space-1) var(--space-2);
            border-radius: 20px;
            font-size: 13px;
            font-weight: var(--h2-weight);
            letter-spacing: 0.02em;
        }
        .badge-info {
            background: #fee;
            color: var(--primary-red);
            border: 1px solid var(--primary-red);
        }
        .badge-warning {
            background: #f0fdfa;
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
        }
        .btn {
            width: auto;
            padding: var(--space-1) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            color: var(--primary-black);
            background: var(--card-bg);
            border: 1px solid var(--light-grey);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
        }
        .btn:hover {
            border-color: var(--primary-red);
            color: var(--primary-red);
            background: #fff9f9;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            table {
                font-size: 14px;
            }
            th, td {
                padding: var(--space-1) var(--space-2);
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            table {
                display: block;
                overflow-x: auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>📊 История посещений</h1>
                    <p>Все ваши посещенные мероприятия</p>
                </div>
                <a href="/dashboard" class="btn">
                    <i class='bx bx-arrow-back'></i>
                    Назад
                </a>
            </div>

            {% if scans %}
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Мероприятие</th>
                            <th>Дата выхода</th>
                            <th>Часы</th>
                            <th>Койны</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for scan in scans %}
                        <tr>
                            <td><strong>{{ scan[0] }}</strong></td>
                            <td>{{ scan[1] }}</td>
                            <td><span class="badge badge-info"><i class='bx bx-hourglass'></i> {{ scan[2] }} ч</span></td>
                            <td><span class="badge badge-warning"><i class='bx bx-coin-stack'></i> 🪙 {{ scan[3] }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">
                <i class='bx bx-history'></i>
                <p>История посещений пуста</p>
                <p style="font-size: 14px; margin-top: var(--space-2);">Начните посещать мероприятия!</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

SHOP_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Магазин</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА === */
        :root {
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', system-ui, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-4);
        }
        .header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            color: var(--primary-black);
            margin: 0;
        }
        .header p {
            color: var(--dark-grey);
            font-size: var(--body-size);
            margin-top: var(--space-1);
        }
        .balance {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--card-bg);
            border: 2px solid var(--accent-green);
            border-radius: 12px;
            padding: var(--space-2) var(--space-3);
            font-weight: var(--h2-weight);
            color: var(--accent-green);
            box-shadow: 0 4px 8px rgba(39, 163, 138, 0.1);
        }
        .balance i {
            font-size: 24px;
        }
        .alert {
            padding: var(--space-2);
            border-radius: 8px;
            margin-bottom: var(--space-3);
            font-weight: var(--btn-weight);
            font-size: var(--body-size);
        }
        .alert-success {
            background: #d1fae5;
            color: #065f46;
            border-left: 4px solid var(--accent-green);
        }
        .alert-error {
            background: #fee;
            color: #991b1b;
            border-left: 4px solid var(--primary-red);
        }
        .code-block {
            margin-top: var(--space-2);
            padding: var(--space-2);
            background: var(--card-bg);
            border: 2px dashed var(--accent-green);
            border-radius: 8px;
        }
        .code-block strong {
            font-size: 18px;
            color: var(--accent-green);
            display: block;
            font-weight: var(--h2-weight);
        }
        .code-block p {
            margin-top: var(--space-1);
            color: var(--dark-grey);
            font-size: var(--body-size);
        }
        .empty-state {
            text-align: center;
            padding: var(--space-5) var(--space-2);
        }
        .empty-state i {
            font-size: 64px;
            color: var(--primary-red);
            margin-bottom: var(--space-3);
            opacity: 0.5;
        }
        .empty-state p {
            color: var(--dark-grey);
            font-size: var(--body-size);
        }
        .item-card {
            background: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 8px rgba(0,0,0,0.08);
            border: 1px solid var(--light-grey);
            transition: all 0.2s ease;
        }
        .item-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.12);
        }
        .item-image {
            width: 100%;
            height: 200px;
            object-fit: cover;
            display: block;
        }
        .item-content {
            padding: var(--space-3);
        }
        .item-name {
            font-weight: var(--h2-weight);
            font-size: 1.25rem;
            color: var(--primary-red);
            margin-bottom: var(--space-2);
        }
        .item-desc {
            color: var(--dark-grey);
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: var(--space-2);
        }
        .item-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: var(--space-2);
            padding-top: var(--space-2);
            border-top: 1px solid var(--light-grey);
        }
        .item-price {
            font-weight: var(--h2-weight);
            font-size: 1.2rem;
            color: var(--accent-green);
        }
        .item-stock {
            font-size: 13px;
            font-weight: var(--body-weight);
            color: var(--grey);
        }
        .item-stock.in-stock {
            color: var(--accent-green);
        }
        .btn {
            width: 100%;
            padding: var(--space-2);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            cursor: pointer;
            text-align: center;
            transition: all 0.2s ease;
        }
        .btn-primary {
            background: var(--primary-red);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(225, 37, 83, 0.2);
        }
        .btn-disabled {
            background: var(--light-grey);
            color: var(--grey);
            cursor: not-allowed;
            opacity: 0.8;
        }
        .grid {
            display: grid;
            gap: var(--space-3);
        }
        .grid-3 {
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .balance {
                justify-content: center;
                width: 100%;
            }
        }
        @media (max-width: 480px) {
            .grid-3 {
                grid-template-columns: 1fr;
            }
            .item-image {
                height: 180px;
            }
            .card {
                padding: var(--space-3);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>🛍️ Магазин</h1>
                    <p>Обменяйте койны на призы</p>
                </div>
                <div style="display: flex; align-items: center; gap: var(--space-2);">
                    <div class="balance">
                        <i class='bx bx-coin-stack'></i>
                        <span>🪙 {{ user_coins }}</span>
                    </div>
                    <a href="/dashboard" class="btn" style="background: var(--card-bg); border: 1px solid var(--light-grey); color: var(--primary-black); width: auto; padding: var(--space-1) var(--space-3);">
                        <i class='bx bx-arrow-back'></i>
                        Назад
                    </a>
                </div>
            </div>

            {% if success %}
            <div class="alert alert-success">
                <i class='bx bx-check-circle'></i>
                {{ success }}
                {% if purchase_code %}
                <div class="code-block">
                    <strong><i class='bx bx-barcode'></i> {{ purchase_code }}</strong>
                    <p>Покажите этот код администратору для получения товара</p>
                </div>
                {% endif %}
            </div>
            {% endif %}
            {% if error %}
            <div class="alert alert-error">
                <i class='bx bx-x-circle'></i>
                {{ error }}
            </div>
            {% endif %}

            {% if items %}
            <div class="grid grid-3">
                {% for item in items %}
                <div class="item-card">
                    <img src="{{ item[2] }}" class="item-image" alt="{{ item[1] }}">
                    <div class="item-content">
                        <div class="item-name">{{ item[1] }}</div>
                        <p class="item-desc">{{ item[4] }}</p>
                        <div class="item-footer">
                            <div class="item-price">🪙 {{ item[3] }}</div>
                            <div class="item-stock {% if item[5] > 0 %}in-stock{% endif %}">
                                {% if item[5] > 0 %}
                                <i class='bx bx-check-circle'></i> {{ item[5] }}
                                {% else %}
                                <i class='bx bx-x-circle'></i> Нет
                                {% endif %}
                            </div>
                        </div>
                        {% if item[5] > 0 %}
                        <form method="POST" action="/shop/buy/{{ item[0] }}" style="margin-top: var(--space-2);">
                            <button type="submit" class="btn btn-primary">Купить сейчас</button>
                        </form>
                        {% else %}
                        <button class="btn btn-disabled" disabled>Нет в наличии</button>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <i class='bx bx-store-alt'></i>
                <p>Магазин временно пуст</p>
                <p style="font-size: 14px; margin-top: var(--space-2);">Скоро появятся новые товары!</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Мой профиль</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА === */
        :root {
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', system-ui, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: var(--space-4);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: var(--space-3);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--space-2);
            margin-bottom: var(--space-3);
        }
        .header h1 {
            font-size: var(--h1-size);
            font-weight: var(--h1-weight);
            color: var(--primary-black);
            margin: 0;
        }
        .avatar-section {
            text-align: center;
            margin: var(--space-4) 0;
        }
        .avatar-container {
            position: relative;
            display: inline-block;
        }
        .avatar {
            width: 160px;
            height: 160px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid var(--primary-red);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .avatar-status {
            position: absolute;
            bottom: 4px;
            right: 4px;
            width: 24px;
            height: 24px;
            background: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        .avatar-form {
            display: flex;
            justify-content: center;
            gap: var(--space-2);
            flex-wrap: wrap;
            margin-top: var(--space-3);
        }
        .btn {
            padding: var(--space-1) var(--space-3);
            border: none;
            border-radius: 8px;
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            transition: all 0.2s ease;
        }
        .btn-primary {
            background: var(--primary-red);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(225, 37, 83, 0.2);
        }
        .btn-success {
            background: var(--accent-green);
            color: white;
        }
        .btn-success:hover {
            background: #1f8a70;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(39, 163, 138, 0.2);
        }
        .info-card,
        .stats-card,
        .purchases-card {
            background: var(--card-bg);
            border: 1px solid var(--light-grey);
            border-radius: 12px;
            padding: var(--space-4);
            margin-top: var(--space-3);
        }
        .section-title {
            font-size: var(--h2-size);
            font-weight: var(--h2-weight);
            color: var(--primary-red);
            margin-bottom: var(--space-3);
            display: flex;
            align-items: center;
            gap: var(--space-2);
        }
        .info-grid {
            display: grid;
            gap: var(--space-3);
        }
        .info-item {
            padding: var(--space-2);
            background: var(--light-grey);
            border-radius: 8px;
        }
        .info-label {
            font-size: 13px;
            color: var(--dark-grey);
            margin-bottom: var(--space-1);
            font-weight: var(--btn-weight);
        }
        .info-value {
            font-size: 17px;
            font-weight: var(--h2-weight);
            color: var(--primary-black);
        }
        .stats-grid {
            display: grid;
            gap: var(--space-3);
        }
        .stat-box {
            padding: var(--space-3);
            border-radius: 12px;
            text-align: center;
            background: var(--light-grey);
        }
        .stat-box.hours {
            border: 2px solid var(--primary-red);
            background: #fee;
        }
        .stat-box.coins {
            border: 2px solid var(--accent-green);
            background: #f0fdfa;
        }
        .stat-label {
            font-size: 13px;
            color: var(--dark-grey);
            margin-bottom: var(--space-1);
            font-weight: var(--btn-weight);
        }
        .stat-value {
            font-size: 2.5rem;
            font-weight: var(--h1-weight);
            margin: var(--space-2) 0;
        }
        .stat-box.hours .stat-value {
            color: var(--primary-red);
        }
        .stat-box.coins .stat-value {
            color: var(--accent-green);
        }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin-top: var(--space-3);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        th, td {
            padding: var(--space-2) var(--space-3);
            text-align: left;
            border-bottom: 1px solid var(--light-grey);
        }
        th {
            background: var(--card-bg);
            font-weight: var(--h2-weight);
            font-size: 13px;
            color: var(--primary-red);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        .code-badge {
            font-weight: var(--h2-weight);
            font-size: 16px;
            letter-spacing: 2px;
            background: var(--light-grey);
            color: var(--primary-red);
            padding: var(--space-1) var(--space-2);
            border-radius: 8px;
            display: inline-block;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: var(--space-3);
            }
            .avatar-form {
                flex-direction: column;
                align-items: center;
            }
            .btn {
                width: 100%;
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>👤 Мой профиль</h1>
                <a href="/dashboard" class="btn" style="background: var(--card-bg); border: 1px solid var(--light-grey);">
                    <i class='bx bx-arrow-back'></i>
                    Назад
                </a>
            </div>

            <div class="avatar-section">
                <div class="avatar-container">
                    <img src="{{ avatar_url }}" class="avatar" alt="Аватар">
                    <div class="avatar-status"></div>
                </div>
                <form method="POST" action="/profile/update-avatar" enctype="multipart/form-data" class="avatar-form">
                    <input type="file" name="avatar" accept="image/*" style="display: none;" id="avatar-input">
                    <label for="avatar-input" class="btn btn-primary" style="cursor: pointer;">
                        <i class='bx bx-camera'></i>
                        Изменить фото
                    </label>
                    <button type="submit" class="btn btn-success">
                        <i class='bx bx-save'></i>
                        Сохранить
                    </button>
                </form>
            </div>

            <div class="grid grid-2" style="display: grid; gap: var(--space-3);">
                <div class="info-card">
                    <h2 class="section-title"><i class='bx bx-user-detail'></i> Личная информация</h2>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">Полное имя</div>
                            <div class="info-value">{{ full_name }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Username</div>
                            <div class="info-value">{{ username }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Факультет</div>
                            <div class="info-value">{{ faculty }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Группа</div>
                            <div class="info-value">{{ group_name }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Телефон</div>
                            <div class="info-value">{{ phone }}</div>
                        </div>
                    </div>
                </div>
                <div class="stats-card">
                    <h2 class="section-title"><i class='bx bx-stats'></i> Статистика</h2>
                    <div class="stats-grid">
                        <div class="stat-box hours">
                            <div class="stat-label">⏱️ Накоплено часов</div>
                            <div class="stat-value">{{ hours }}</div>
                        </div>
                        <div class="stat-box coins">
                            <div class="stat-label">🪙 Баланс койнов</div>
                            <div class="stat-value">{{ coins }}</div>
                        </div>
                    </div>
                </div>
            </div>

            {% if pending_purchases %}
            <div class="purchases-card">
                <h2 class="section-title"><i class='bx bx-cart-download'></i> Мои покупки (ожидают выдачи)</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Товар</th>
                                <th>Код для получения</th>
                                <th>Дата покупки</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for purchase in pending_purchases %}
                            <tr>
                                <td><strong>{{ purchase[1] }}</strong></td>
                                <td><span class="code-badge">{{ purchase[2] }}</span></td>
                                <td>{{ purchase[3] }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

CERTIFICATE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Сертификат</title>
    <!-- ШРИФТ -->
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <!-- ИКОНКИ -->
    <link href="https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        /* === ДИЗАЙН-СИСТЕМА === */
        :root {
            --primary-red: #E12553;
            --primary-black: #292929;
            --dark-grey: #938E8D;
            --grey: #B1ACA9;
            --light-grey: #D7D9D3;
            --accent-green: #27A38A;
            --bg-light: #F9F9FB;
            --card-bg: #FFFFFF;
            --h1-size: 28px;
            --h1-weight: 900;
            --h2-size: 20px;
            --h2-weight: 900;
            --body-size: 15px;
            --body-weight: 300;
            --btn-size: 14px;
            --btn-weight: 700;
            --space-1: 8px;
            --space-2: 16px;
            --space-3: 24px;
            --space-4: 32px;
            --space-5: 40px;
        }
        body {
            font-family: 'Montserrat', system-ui, sans-serif;
            background-color: var(--bg-light);
            color: var(--primary-black);
            line-height: 1.6;
            padding: var(--space-2);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            max-width: 900px;
            margin: 40px auto;
            width: 100%;
        }
        .certificate {
            background: var(--card-bg);
            border: 3px solid var(--primary-red);
            border-radius: 30px;
            padding: var(--space-5);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            position: relative;
            overflow: hidden;
            text-align: center;
            font-feature-settings: "liga" 1;
        }
        /* Водяной знак "МЕСТО СИЛЫ" — как в Handbook */
        .power-watermark {
            position: absolute;
            top: 50%;
            right: 40px;
            transform: rotate(90deg) translateX(50%);
            font-weight: var(--h1-weight);
            font-size: 20px;
            color: var(--primary-red);
            opacity: 0.08;
            pointer-events: none;
            letter-spacing: 3px;
            white-space: nowrap;
        }
        .logo {
            font-weight: var(--h1-weight);
            font-size: var(--h1-size);
            color: var(--primary-red);
            margin-bottom: var(--space-1);
            letter-spacing: -0.5px;
        }
        .tagline {
            font-weight: var(--body-weight);
            font-size: 16px;
            color: var(--grey);
            margin-bottom: var(--space-4);
            letter-spacing: 1px;
        }
        .document-type {
            font-weight: var(--h2-weight);
            font-size: 24px;
            color: var(--primary-black);
            margin: var(--space-3) 0 var(--space-4);
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        .intro {
            font-weight: var(--body-weight);
            font-size: var(--body-size);
            color: var(--primary-black);
            margin-bottom: var(--space-3);
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }
        .recipient {
            font-weight: var(--h1-weight);
            font-size: 36px;
            color: var(--primary-red);
            margin: var(--space-4) 0;
            letter-spacing: -0.5px;
            line-height: 1.2;
        }
        .statement {
            font-weight: var(--body-weight);
            font-size: var(--body-size);
            color: var(--primary-black);
            margin: var(--space-3) 0 var(--space-4);
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }
        .details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: var(--space-3);
            margin: var(--space-4) 0;
        }
        .detail-item {
            padding: var(--space-2);
            border-top: 2px solid var(--light-grey);
            border-bottom: 2px solid var(--light-grey);
        }
        .detail-label {
            font-weight: var(--btn-weight);
            font-size: 14px;
            color: var(--dark-grey);
            margin-bottom: var(--space-1);
            letter-spacing: 0.5px;
        }
        .detail-value {
            font-weight: var(--h2-weight);
            font-size: 22px;
            color: var(--primary-black);
        }
        .faculty .detail-value { color: var(--primary-red); }
        .group .detail-value { color: var(--accent-green); }
        .date-line {
            margin-top: var(--space-4);
            font-weight: var(--body-weight);
            color: var(--primary-black);
            font-size: 15px;
        }
        .btn {
            display: inline-block;
            margin-top: var(--space-4);
            padding: var(--space-2) var(--space-4);
            border: 2px solid var(--primary-red);
            border-radius: 12px;
            background: var(--card-bg);
            color: var(--primary-red);
            font-family: inherit;
            font-weight: var(--btn-weight);
            font-size: var(--btn-size);
            text-decoration: none;
            transition: all 0.2s ease;
        }
        .btn:hover {
            background: var(--primary-red);
            color: white;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(225, 37, 83, 0.2);
        }
        @media print {
            body {
                padding: 0;
                background: white;
            }
            .btn {
                display: none;
            }
            .container {
                margin: 0;
            }
        }
        @media (max-width: 600px) {
            .certificate {
                padding: var(--space-4);
                border-radius: 20px;
            }
            .recipient {
                font-size: 30px;
            }
            .details {
                gap: var(--space-2);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="certificate">
            <div class="power-watermark">МЕСТО СИЛЫ</div>
            <div class="logo">URBAN COLLEGE</div>
            <div class="tagline">Платформа студенческих мероприятий</div>
            <div class="document-type">Сертификат участника</div>
            <div class="intro">Настоящий сертификат подтверждает, что</div>
            <div class="recipient">{{ full_name }}</div>
            <div class="statement">является активным участником образовательного сообщества Urban College</div>
            <div class="details">
                <div class="detail-item faculty">
                    <div class="detail-label">ФАКУЛЬТЕТ</div>
                    <div class="detail-value">{{ faculty }}</div>
                </div>
                <div class="detail-item group">
                    <div class="detail-label">ГРУППА</div>
                    <div class="detail-value">{{ group_name }}</div>
                </div>
            </div>
            <div class="date-line">Дата выдачи: {{ date }}</div>
        </div>
        <a href="/dashboard" class="btn">
            <i class='bx bx-arrow-back'></i>
            Вернуться на главную
        </a>
    </div>
</body>
</html>
"""

CREATOR_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Вход для организаторов</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            max-width: 520px;
            margin: 60px auto;
            width: 100%;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 10px 30px -5px rgba(41, 41, 41, 0.1);
            border: 1px solid var(--gray-light);
        }
        .logo-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo-header h1 {
            font-weight: 900;
            font-size: clamp(2rem, 6vw, 2.6rem);
            color: var(--dark);
            margin-bottom: 8px;
        }
        .logo-header .tagline {
            font-weight: 300;
            font-size: clamp(1rem, 3.5vw, 1.15rem);
            color: var(--gray-dark);
        }
        .logo-header .power {
            font-weight: 900;
            font-size: clamp(1.1rem, 4vw, 1.25rem);
            color: var(--primary);
            letter-spacing: 1px;
            margin-top: 6px;
        }
        .illustration {
            text-align: center;
            margin: 25px 0 30px;
        }
        .illustration div {
            font-size: clamp(4rem, 10vw, 5.5rem);
            margin-bottom: 12px;
        }
        .alert {
            background: #fee;
            color: var(--dark);
            padding: 14px;
            border-radius: 12px;
            margin-bottom: 25px;
            border-left: 4px solid var(--primary);
            font-weight: 600;
        }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--dark);
            font-size: 15px;
        }
        input {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 12px;
            font-size: 16px;
            font-family: inherit;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        .btn {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 17px;
            cursor: pointer;
            font-family: inherit;
            transition: background 0.2s, transform 0.15s;
        }
        .btn-primary {
            background: var(--primary);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
        }
        .divider {
            margin-top: 30px;
            padding-top: 25px;
            border-top: 1px solid var(--gray-light);
            text-align: center;
        }
        .back-link {
            display: inline-block;
            color: var(--gray-dark);
            text-decoration: none;
            font-size: 15px;
            transition: color 0.2s;
        }
        .back-link:hover {
            color: var(--primary);
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo-header">
                <h1>URBAN COLLEGE</h1>
                <div class="tagline">Панель организаторов мероприятий</div>
                <div class="power">МЕСТО СИЛЫ</div>
            </div>
            <div class="illustration">
                <div>🎪</div>
            </div>

            {% if error %}
            <div class="alert">{{ error }}</div>
            {% endif %}

            <form method="POST">
                <label>Username организатора</label>
                <input type="text" name="username" placeholder="Введите username" required autofocus>
                <label>Пароль</label>
                <input type="password" name="password" placeholder="••••••••" required>
                <button type="submit" class="btn btn-primary">Войти в панель организатора</button>
            </form>

            <div class="divider">
                <a href="/login" class="back-link">← Вход для студентов</a>
            </div>
        </div>
    </div>
</body>
</html>
"""

CREATOR_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Панель организатора</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 32px 24px;
            box-shadow: 0 8px 24px rgba(41, 41, 41, 0.08);
            border: 1px solid var(--gray-light);
            margin-bottom: 28px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 35px;
        }
        .header h1 {
            font-weight: 900;
            font-size: clamp(1.8rem, 5vw, 2.4rem);
            letter-spacing: -0.5px;
            color: var(--dark);
            margin: 0;
        }
        .header p {
            color: var(--gray-dark);
            font-size: clamp(1rem, 3.5vw, 1.1rem);
            margin-top: 6px;
        }
        .alert {
            padding: 18px;
            border-radius: 12px;
            margin-bottom: 25px;
            font-weight: 600;
            background: #d1fae5;
            border-left: 4px solid var(--secondary);
            color: #065f46;
        }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--dark);
            font-size: 15px;
        }
        input, textarea, select {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 12px;
            font-size: 16px;
            font-family: inherit;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        .grid {
            display: grid;
            gap: 20px;
        }
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        }
        .grid-3 {
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        }
        @media (max-width: 768px) {
            .grid-3 {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        @media (max-width: 480px) {
            .grid-3 {
                grid-template-columns: 1fr;
            }
        }
        .btn {
            width: auto;
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-family: inherit;
            font-weight: 600;
            font-size: 15px;
            color: var(--white);
            background: var(--primary);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }
        .btn:hover {
            background: #c91f47;
            transform: translateY(-2px);
        }
        .btn-secondary {
            background: var(--white);
            color: var(--dark);
            border: 1px solid var(--border);
        }
        .btn-secondary:hover {
            border-color: var(--gray);
            background: var(--gray-light);
        }
        .event-card {
            background: var(--white);
            border: 2px solid var(--primary);
            border-radius: 20px;
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: 0 6px 15px -4px rgba(225, 37, 83, 0.15);
            transition: all 0.2s ease;
        }
        .event-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 25px -4px rgba(225, 37, 83, 0.25);
        }
        .event-card h3 {
            font-weight: 800;
            font-size: 1.4rem;
            color: var(--primary);
            margin-bottom: 15px;
        }
        .event-card p {
            color: var(--gray-dark);
            margin-bottom: 20px;
            line-height: 1.6;
        }
        .event-meta {
            display: grid;
            gap: 12px;
            margin-bottom: 25px;
        }
        .meta-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px;
            background: var(--gray-light);
            border-radius: 12px;
            font-weight: 600;
        }
        .meta-item.hours {
            border-left: 4px solid var(--secondary);
            background: #f0fdfa;
        }
        .meta-item.hours strong {
            color: var(--secondary);
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            background: var(--gray-light);
            border-radius: 20px;
        }
        .empty-state div {
            font-size: clamp(4rem, 10vw, 6rem);
            margin-bottom: 20px;
            opacity: 0.5;
        }
        .empty-state p {
            color: var(--gray-dark);
            font-size: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>🎪 Панель организатора</h1>
                    <p>Создание и управление мероприятиями</p>
                </div>
                <a href="/creator/logout" class="btn btn-secondary">Выйти</a>
            </div>

            {% if success %}
            <div class="alert">{{ success }}</div>
            {% endif %}

            <div class="card">
                <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 25px;">➕ Создать новое мероприятие</h2>
                <form method="POST" action="/creator/create-event">
                    <label>Название мероприятия</label>
                    <input type="text" name="name" placeholder="Например: Хакатон 2025" required>

                    <label>Описание</label>
                    <textarea name="description" placeholder="Краткое описание мероприятия..." rows="3"></textarea>

                    <label>Дата проведения</label>
                    <div class="grid grid-3">
                        <input type="number" name="day" placeholder="День (1-31)" min="1" max="31" required>
                        <input type="number" name="month" placeholder="Месяц (1-12)" min="1" max="12" required>
                        <input type="number" name="year" placeholder="Год" min="2025" value="2025" required>
                    </div>

                    <label>Время проведения</label>
                    <div class="grid grid-2">
                        <div>
                            <label style="font-size: 13px; color: var(--gray-dark);">Начало</label>
                            <input type="time" name="start_time" value="09:00" required>
                        </div>
                        <div>
                            <label style="font-size: 13px; color: var(--gray-dark);">Конец</label>
                            <input type="time" name="end_time" value="18:00" required>
                        </div>
                    </div>

                    <label>Место проведения</label>
                    <input type="text" name="location" placeholder="Например: Главный корпус, ауд. 101" required>

                    <label>Количество часов (награда)</label>
                    <input type="number" name="hours" placeholder="Например: 3" min="1" max="24" required>

                    <button type="submit" class="btn" style="width: 100%; padding: 16px; font-size: 17px;">
                        ✓ Создать мероприятие
                    </button>
                </form>
            </div>

            <h2 style="font-weight: 800; font-size: 1.8rem; margin: 40px 0 25px;">📋 Мои мероприятия</h2>

            {% if events %}
            <div class="grid grid-2">
                {% for event in events %}
                <div class="event-card">
                    <h3>{{ event[1] }}</h3>
                    <p>{{ event[2] }}</p>
                    <div class="event-meta">
                        <div class="meta-item">
                            <span>📅</span>
                            <span>{{ event[3] }}</span>
                        </div>
                        <div class="meta-item">
                            <span>⏰</span>
                            <span>{{ event[4] }} – {{ event[5] }}</span>
                        </div>
                        <div class="meta-item">
                            <span>📍</span>
                            <span>{{ event[6] }}</span>
                        </div>
                        <div class="meta-item hours">
                            <strong>⏱️</strong>
                            <strong>{{ event[7] }} часов</strong>
                        </div>
                    </div>
                    <a href="/creator/event/{{ event[0] }}" class="btn" style="width: 100%;">
                        Открыть мероприятие →
                    </a>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <div>📋</div>
                <p>У вас пока нет мероприятий</p>
                <p style="font-size: 14px; margin-top: 10px;">Создайте первое мероприятие выше!</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

EVENT_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Мероприятие</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 32px 24px;
            box-shadow: 0 8px 24px rgba(41, 41, 41, 0.08);
            border: 1px solid var(--gray-light);
            margin-bottom: 28px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 35px;
        }
        .header h1 {
            font-weight: 900;
            font-size: clamp(1.8rem, 5vw, 2.4rem);
            letter-spacing: -0.5px;
            color: var(--dark);
            margin: 0;
        }
        .header p {
            color: var(--gray-dark);
            font-size: clamp(1rem, 3.5vw, 1.1rem);
            margin-top: 6px;
        }
        .stat-card {
            background: var(--white);
            border: 2px solid var(--primary);
            border-radius: 20px;
            padding: 24px;
            text-align: center;
            box-shadow: 0 6px 15px -4px rgba(225, 37, 83, 0.15);
        }
        .stat-card.green {
            border-color: var(--secondary);
            box-shadow: 0 6px 15px -4px rgba(39, 163, 138, 0.15);
        }
        .stat-label {
            font-weight: 300;
            font-size: 14px;
            color: var(--gray-dark);
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }
        .stat-value {
            font-weight: 800;
            font-size: clamp(1.4rem, 4vw, 1.8rem);
            color: var(--primary);
        }
        .stat-card.green .stat-value {
            color: var(--secondary);
        }
        .qr-section {
            background: var(--white);
            border: 2px solid var(--primary);
            border-radius: 20px;
            padding: 30px;
            text-align: center;
            margin-top: 25px;
            cursor: pointer;
            box-shadow: 0 8px 20px -5px rgba(225, 37, 83, 0.15);
            transition: all 0.2s ease;
        }
        .qr-section:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 25px -5px rgba(225, 37, 83, 0.25);
        }
        .qr-code-img {
            max-width: 300px;
            width: 100%;
            height: auto;
            border-radius: 12px;
            margin: 20px auto;
            display: block;
            box-shadow: 0 4px 12px -2px rgba(0,0,0,0.1);
        }
        .exit-code {
            font-weight: 900;
            font-size: clamp(2.5rem, 6vw, 3.5rem);
            color: var(--primary);
            letter-spacing: 12px;
            margin: 20px 0;
            text-shadow: 0 2px 6px rgba(0,0,0,0.05);
        }
        .countdown {
            background: var(--gray-light);
            padding: 12px 20px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 18px;
            display: inline-block;
            margin-top: 15px;
        }
        .qr-hint {
            font-size: 14px;
            color: var(--gray-dark);
            margin-top: 12px;
        }
        .participants-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 40px 0 25px;
        }
        .participants-header h2 {
            font-weight: 800;
            font-size: clamp(1.6rem, 4.5vw, 2rem);
            color: var(--dark);
        }
        .participants-count {
            background: var(--primary);
            color: white;
            padding: 8px 18px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 16px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 16px 18px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            font-size: 13px;
            color: var(--dark);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        .badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            background: #f0fdfa;
            color: var(--secondary);
            border: 1px solid var(--secondary);
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            background: var(--gray-light);
            border-radius: 20px;
        }
        .empty-state div {
            font-size: clamp(4rem, 10vw, 6rem);
            margin-bottom: 20px;
            opacity: 0.5;
        }
        .empty-state p {
            color: var(--gray-dark);
            font-size: 16px;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-family: inherit;
            font-weight: 600;
            font-size: 15px;
            color: var(--dark);
            background: var(--white);
            border: 1px solid var(--border);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }
        .btn:hover {
            border-color: var(--primary);
            color: var(--primary);
            background: #fff9f9;
        }
        .modal {
            display: none;
            position: fixed;
            z-index: 9999;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(10px);
            justify-content: center;
            align-items: center;
        }
        .modal.active {
            display: flex;
        }
        .modal-content {
            background: white;
            padding: 40px;
            border-radius: 24px;
            max-width: 90%;
            max-height: 90%;
            position: relative;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .modal-close {
            position: absolute;
            top: 15px;
            right: 25px;
            font-size: 36px;
            cursor: pointer;
            color: var(--gray-dark);
        }
        .modal-close:hover {
            color: var(--primary);
        }
        .modal-qr {
            max-width: 600px;
            width: 100%;
        }
        .modal-code {
            font-weight: 900;
            font-size: 5rem;
            color: var(--primary);
            letter-spacing: 20px;
            margin: 30px 0;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .grid {
                grid-template-columns: 1fr;
            }
            .qr-section {
                padding: 25px 20px;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: 28px 20px;
            }
            .exit-code {
                font-size: 2.8rem;
                letter-spacing: 8px;
            }
            .modal-code {
                font-size: 3.5rem;
                letter-spacing: 12px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>{{ event_name }}</h1>
                    <p>Детали мероприятия</p>
                </div>
                <a href="{{ back_url }}" class="btn">← Назад</a>
            </div>

            <div class="grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin-bottom: 30px;">
                <div class="stat-card">
                    <div class="stat-label">📅 Дата</div>
                    <div class="stat-value">{{ date }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">⏰ Время</div>
                    <div class="stat-value">{{ start_time }} – {{ end_time }}</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-label">📍 Место</div>
                    <div class="stat-value">{{ location }}</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-label">⏱️ Часы</div>
                    <div class="stat-value">{{ hours }} ч</div>
                </div>
            </div>

            <div class="qr-section" onclick="openQRModal()">
                <h2 style="font-weight: 800; color: var(--primary);">📱 QR-код для выхода</h2>
                <p style="color: var(--gray-dark); margin-bottom: 20px;">Покажите этот код студентам в конце мероприятия</p>
                <img id="qr-image" src="{{ qr_image }}" class="qr-code-img" alt="QR Code">
                <div class="exit-code">{{ exit_code }}</div>
                <div class="countdown">Обновление через <span id="countdown">60</span> сек</div>
                <p class="qr-hint">💡 Нажмите для увеличения</p>
            </div>

            <div class="participants-header">
                <h2>👥 Участники</h2>
                <div class="participants-count">{{ registered_count }} чел.</div>
            </div>

            {% if registered_students %}
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Имя студента</th>
                            <th>Факультет</th>
                            <th>Группа</th>
                            <th>Статус</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for student in registered_students %}
                        <tr>
                            <td><strong>{{ student[0] }}</strong></td>
                            <td>{{ student[1] }}</td>
                            <td>{{ student[2] }}</td>
                            <td><span class="badge">✓ Завершено</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">
                <div>👥</div>
                <p>Пока нет участников</p>
                <p style="font-size: 14px; margin-top: 10px;">Студенты появятся после сканирования QR-кода</p>
            </div>
            {% endif %}
        </div>
    </div>

    <!-- QR Modal -->
    <div id="qr-modal" class="modal" onclick="closeQRModal()">
        <div class="modal-content" onclick="event.stopPropagation()">
            <span class="modal-close" onclick="closeQRModal()">&times;</span>
            <h2 style="font-weight: 800; color: var(--primary); text-align: center; margin-bottom: 25px;">QR-код для сканирования</h2>
            <img id="modal-qr-image" src="{{ qr_image }}" class="modal-qr" alt="QR Code">
            <div class="modal-code">{{ exit_code }}</div>
        </div>
    </div>

    <script>
        let countdown = 10
        const eventId = {{ event_id }};
        function openQRModal() {
            document.getElementById('qr-modal').classList.add('active');
        }
        function closeQRModal() {
            document.getElementById('qr-modal').classList.remove('active');
        }
        function updateQR() {
            fetch(`/api/refresh-qr/${eventId}`)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('qr-image').src = data.qr_image + '?t=' + Date.now();
                    document.getElementById('modal-qr-image').src = data.qr_image + '?t=' + Date.now();
                    document.querySelector('.exit-code').textContent = data.exit_code;
                    document.querySelector('.modal-code').textContent = data.exit_code;
                    countdown = 10
                });
        }
        setInterval(() => {
            countdown--;
            document.getElementById('countdown').textContent = countdown;
            if (countdown <= 0) {
                updateQR();
            }
        }, 1000);
    </script>
</body>
</html>
"""

ADMIN_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Админ-панель</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            max-width: 520px;
            margin: 60px auto;
            width: 100%;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 10px 30px -5px rgba(41, 41, 41, 0.1);
            border: 1px solid var(--gray-light);
        }
        .logo-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo-header h1 {
            font-weight: 900;
            font-size: clamp(2rem, 6vw, 2.6rem);
            color: var(--dark);
            margin-bottom: 8px;
        }
        .logo-header .tagline {
            font-weight: 300;
            font-size: clamp(1rem, 3.5vw, 1.15rem);
            color: var(--gray-dark);
        }
        .logo-header .power {
            font-weight: 900;
            font-size: clamp(1.1rem, 4vw, 1.25rem);
            color: var(--primary);
            letter-spacing: 1px;
            margin-top: 6px;
        }
        .illustration {
            text-align: center;
            margin: 25px 0 30px;
        }
        .illustration div {
            font-size: clamp(4rem, 10vw, 5.5rem);
            margin-bottom: 12px;
        }
        .alert {
            background: #fee;
            color: var(--dark);
            padding: 14px;
            border-radius: 12px;
            margin-bottom: 25px;
            border-left: 4px solid var(--primary);
            font-weight: 600;
        }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--dark);
            font-size: 15px;
        }
        input {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 12px;
            font-size: 16px;
            font-family: inherit;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        .btn {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 17px;
            cursor: pointer;
            font-family: inherit;
            transition: background 0.2s, transform 0.15s;
        }
        .btn-primary {
            background: var(--primary);
            color: white;
        }
        .btn-primary:hover {
            background: #c91f47;
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo-header">
                <h1>URBAN COLLEGE</h1>
                <div class="tagline">Вход в админ-панель</div>
                <div class="power">МЕСТО СИЛЫ</div>
            </div>
            <div class="illustration">
                <div>🔐</div>
            </div>

            {% if error %}
            <div class="alert">{{ error }}</div>
            {% endif %}

            <form method="POST">
                <label>Username администратора</label>
                <input type="text" name="username" placeholder="Введите username" required autofocus>
                <label>Пароль</label>
                <input type="password" name="password" placeholder="••••••••" required>
                <button type="submit" class="btn btn-primary">Войти в админ-панель</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

ADMIN_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Админ-панель</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 32px 24px;
            box-shadow: 0 8px 24px rgba(41, 41, 41, 0.08);
            border: 1px solid var(--gray-light);
            margin-bottom: 28px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 35px;
        }
        .header h1 {
            font-weight: 900;
            font-size: clamp(1.8rem, 5vw, 2.4rem);
            letter-spacing: -0.5px;
            color: var(--dark);
            margin: 0;
        }
        .header p {
            color: var(--gray-dark);
            font-size: clamp(1rem, 3.5vw, 1.1rem);
            margin-top: 8px;
        }
        .alert {
            padding: 18px;
            border-radius: 12px;
            margin-bottom: 25px;
            font-weight: 600;
            background: #d1fae5;
            border-left: 4px solid var(--secondary);
            color: #065f46;
        }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--dark);
            font-size: 15px;
        }
        input, textarea, select {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 12px;
            font-size: 16px;
            font-family: inherit;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        input[type="file"] {
            padding: 10px;
        }
        .grid {
            display: grid;
            gap: 25px;
        }
        .grid-3 {
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }
        @media (max-width: 768px) {
            .grid-3 {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        @media (max-width: 480px) {
            .grid-3 {
                grid-template-columns: 1fr;
            }
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
        }
        .btn {
            width: auto;
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-family: inherit;
            font-weight: 600;
            font-size: 15px;
            color: var(--white);
            background: var(--primary);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }
        .btn:hover {
            background: #c91f47;
            transform: translateY(-2px);
        }
        .btn-green {
            background: var(--secondary);
        }
        .btn-green:hover {
            background: #1f8a70;
        }
        .btn-purple {
            background: linear-gradient(135deg, #50318F 0%, #27A38A 100%);
        }
        .btn-outline {
            background: var(--white);
            color: var(--dark);
            border: 1px solid var(--border);
        }
        .btn-outline:hover {
            background: var(--gray-light);
        }
        .btn-group {
            display: flex;
            gap: 8px;
        }
        .badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
        .badge-yellow {
            background: var(--white);
            color: var(--primary);
            border: 2px solid var(--primary);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 16px 18px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            font-size: 13px;
            color: var(--dark);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        tbody tr:hover {
            background: var(--gray-light);
        }
        .item-card {
            background: var(--white);
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 6px 15px -4px rgba(0,0,0,0.08);
            border: 1px solid var(--border);
        }
        .item-img {
            width: 100%;
            height: 160px;
            object-fit: cover;
        }
        .item-content {
            padding: 20px;
        }
        .item-name {
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 8px;
        }
        .item-desc {
            font-size: 14px;
            color: var(--gray-dark);
            margin-bottom: 15px;
        }
        .item-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .item-price {
            font-weight: 700;
            color: var(--secondary);
        }
        .item-qty {
            font-size: 13px;
            color: var(--gray);
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            background: var(--gray-light);
            border-radius: 20px;
        }
        .empty-state div {
            font-size: clamp(4rem, 10vw, 6rem);
            margin-bottom: 20px;
            opacity: 0.5;
        }
        .empty-state p {
            color: var(--gray-dark);
            font-size: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>🔐 Админ-панель</h1>
                    <p>Управление платформой URBAN COLLEGE</p>
                </div>
                <a href="/admin/logout" class="btn btn-outline">Выйти</a>
            </div>

            {% if success %}
            <div class="alert">{{ success }}</div>
            {% endif %}

            <!-- Navigation Quick Actions -->
            <div class="grid grid-3" style="margin-bottom: 35px;">
                <a href="/admin/analytics" class="btn">
                    <span>📊</span> Аналитика
                </a>
                <a href="/admin/students" class="btn btn-green">
                    <span>👥</span> Студенты
                </a>
                <a href="/admin/dashboard" class="btn btn-purple">
                    <span>🛠️</span> Управление
                </a>
            </div>

            <div class="grid grid-2" style="margin-bottom: 40px;">
                <!-- Create Creator -->
                <div class="card">
                    <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 20px;">➕ Создать организатора</h2>
                    <form method="POST" action="/admin/create-creator">
                        <label>Username</label>
                        <input type="text" name="username" placeholder="ivan_event" required>
                        <label>Пароль</label>
                        <input type="password" name="password" placeholder="••••••••" required>
                        <button type="submit" class="btn" style="width: 100%;">Создать</button>
                    </form>
                </div>

                <!-- Add Shop Item -->
                <div class="card">
                    <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 20px;">🛍️ Добавить товар</h2>
                    <form method="POST" action="/admin/add-shop-item" enctype="multipart/form-data">
                        <label>Название товара</label>
                        <input type="text" name="name" placeholder="Футболка Urban" required>
                        <label>Описание</label>
                        <textarea name="description" placeholder="Краткое описание..." rows="2"></textarea>
                        <div class="grid" style="grid-template-columns: 1fr 1fr; gap: 15px;">
                            <div>
                                <label>Цена (койны)</label>
                                <input type="number" name="price" placeholder="100" min="1" required>
                            </div>
                            <div>
                                <label>Количество</label>
                                <input type="number" name="quantity" placeholder="10" min="0" required>
                            </div>
                        </div>
                        <label>Изображение</label>
                        <input type="file" name="image" accept="image/*" required>
                        <button type="submit" class="btn btn-green" style="width: 100%; margin-top: 10px;">Добавить</button>
                    </form>
                </div>
            </div>

            <!-- Pending Orders -->
            <h2 style="font-weight: 800; font-size: 1.8rem; margin: 40px 0 25px;">
                📦 Ожидающие заказы
                {% if pending_count > 0 %}
                <span class="badge badge-yellow">{{ pending_count }}</span>
                {% endif %}
            </h2>
            {% if pending_purchases %}
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Товар</th>
                            <th>Код</th>
                            <th>Студент</th>
                            <th>Телефон</th>
                            <th>Дата</th>
                            <th>Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for purchase in pending_purchases %}
                        <tr>
                            <td><strong>{{ purchase[1] }}</strong></td>
                            <td><span class="badge badge-yellow">{{ purchase[2] }}</span></td>
                            <td>{{ purchase[3] }}</td>
                            <td>{{ purchase[4] }}</td>
                            <td>{{ purchase[5] }}</td>
                            <td class="btn-group">
                                <form method="POST" action="/admin/complete-order/{{ purchase[0] }}">
                                    <button type="submit" class="btn btn-green" style="padding: 8px 14px; font-size: 13px;">✓ Выдано</button>
                                </form>
                                <form method="POST" action="/admin/cancel-order/{{ purchase[0] }}">
                                    <button type="submit" class="btn" style="padding: 8px 14px; font-size: 13px; background: #ef4444;">✗ Отменить</button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">
                <div>📦</div>
                <p>Нет ожидающих заказов</p>
            </div>
            {% endif %}

            <!-- Shop Items -->
            <h2 style="font-weight: 800; font-size: 1.8rem; margin: 50px 0 25px;">🛍️ Товары в магазине</h2>
            {% if shop_items %}
            <div class="grid grid-3">
                {% for item in shop_items %}
                <div class="item-card">
                    <img src="{{ item[2] }}" class="item-img" alt="{{ item[1] }}">
                    <div class="item-content">
                        <div class="item-name">{{ item[1] }}</div>
                        <p class="item-desc">{{ item[4] }}</p>
                        <div class="item-footer">
                            <div class="item-price">🪙 {{ item[3] }}</div>
                            <div class="item-qty">В наличии: {{ item[5] }}</div>
                        </div>
                        <form method="POST" action="/admin/delete-shop-item/{{ item[0] }}" style="margin-top: 18px;">
                            <button type="submit" class="btn" style="width: 100%; padding: 10px; background: #ef4444;">Удалить</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <div>🛍️</div>
                <p>Магазин пуст</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

ANALYTICS_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Аналитика</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 32px 24px;
            box-shadow: 0 8px 24px rgba(41, 41, 41, 0.08);
            border: 1px solid var(--gray-light);
            margin-bottom: 28px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 35px;
        }
        .header h1 {
            font-weight: 900;
            font-size: clamp(1.8rem, 5vw, 2.4rem);
            letter-spacing: -0.5px;
            color: var(--dark);
            margin: 0;
        }
        .header p {
            color: var(--gray-dark);
            font-size: clamp(1rem, 3.5vw, 1.1rem);
            margin-top: 8px;
        }
        .stat-card {
            background: var(--white);
            border: 2px solid var(--primary);
            border-radius: 20px;
            padding: 30px 20px;
            text-align: center;
            box-shadow: 0 6px 15px -4px rgba(225, 37, 83, 0.15);
        }
        .stat-card:nth-child(2) {
            border-color: var(--gray-dark);
        }
        .stat-card:nth-child(3) {
            border-color: var(--secondary);
        }
        .stat-card:nth-child(4) {
            border-color: var(--secondary);
        }
        .stat-label {
            font-weight: 300;
            font-size: clamp(1rem, 3vw, 1.2rem);
            color: var(--gray-dark);
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }
        .stat-number {
            font-weight: 900;
            font-size: clamp(2.5rem, 6vw, 3.5rem);
            color: var(--primary);
            margin: 15px 0;
        }
        .stat-card:nth-child(2) .stat-number {
            color: var(--gray-dark);
        }
        .stat-card:nth-child(3) .stat-number,
        .stat-card:nth-child(4) .stat-number {
            color: var(--secondary);
        }
        .progress-card {
            background: var(--white);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 30px;
        }
        .progress-title {
            font-weight: 800;
            font-size: 1.6rem;
            color: var(--primary);
            margin-bottom: 20px;
        }
        .progress-bar {
            width: 100%;
            height: 36px;
            background: var(--gray-light);
            border-radius: 18px;
            overflow: hidden;
            margin: 20px 0;
        }
        .progress-fill {
            height: 100%;
            background: var(--primary);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 800;
            font-size: 16px;
        }
        .progress-text {
            text-align: center;
            font-size: 17px;
            font-weight: 600;
            color: var(--dark);
            margin-top: 10px;
        }
        .economy-card {
            background: var(--white);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 30px;
        }
        .economy-title {
            font-weight: 800;
            font-size: 1.6rem;
            color: var(--primary);
            margin-bottom: 20px;
        }
        .economy-grid {
            display: grid;
            gap: 18px;
        }
        .eco-item {
            display: flex;
            justify-content: space-between;
            padding: 14px;
            background: var(--gray-light);
            border-radius: 12px;
            font-weight: 600;
        }
        .eco-label {
            color: var(--gray-dark);
        }
        .eco-value {
            font-weight: 800;
        }
        .eco-value.issued { color: var(--primary); }
        .eco-value.spent { color: #ef4444; }
        .eco-value.circ { color: var(--secondary); }
        .eco-value.avg { color: var(--dark); }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 16px 18px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            font-size: 13px;
            color: var(--dark);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        .badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }
        .badge-info {
            background: var(--gray-light);
            color: var(--primary);
        }
        .badge-warning {
            background: #f0fdfa;
            color: var(--secondary);
            border: 1px solid var(--secondary);
        }
        .badge-success {
            background: #f0fdfa;
            color: var(--secondary);
        }
        .grid {
            display: grid;
            gap: 25px;
        }
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }
        .grid-4 {
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-family: inherit;
            font-weight: 600;
            font-size: 15px;
            color: var(--dark);
            background: var(--white);
            border: 1px solid var(--border);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }
        .btn:hover {
            border-color: var(--primary);
            color: var(--primary);
            background: #fff9f9;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .grid-2, .grid-4 {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: 24px 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>📊 Аналитика платформы</h1>
                    <p>Общая статистика и отчёты</p>
                </div>
                <a href="/admin/dashboard" class="btn">← Назад</a>
            </div>

            <div class="grid grid-4 mb-3">
                <div class="stat-card">
                    <div class="stat-label">👥 Студентов</div>
                    <div class="stat-number">{{ total_students }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">📅 Мероприятий</div>
                    <div class="stat-number">{{ total_events }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">✅ Посещений</div>
                    <div class="stat-number">{{ total_scans }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">🛍️ Покупок</div>
                    <div class="stat-number">{{ total_purchases }}</div>
                </div>
            </div>

            <div class="grid grid-2 mb-3">
                <div class="progress-card">
                    <h3 class="progress-title">📈 Активность студентов</h3>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {{ activity_percent }}%;">
                            {{ activity_percent }}%
                        </div>
                    </div>
                    <div class="progress-text">
                        {{ active_students }} из {{ total_students }} студентов активны
                    </div>
                </div>
                <div class="economy-card">
                    <h3 class="economy-title">💰 Экономика койнов</h3>
                    <div class="economy-grid">
                        <div class="eco-item">
                            <span class="eco-label">Выдано:</span>
                            <span class="eco-value issued">🪙 {{ total_coins_issued }}</span>
                        </div>
                        <div class="eco-item">
                            <span class="eco-label">Потрачено:</span>
                            <span class="eco-value spent">🪙 {{ total_coins_spent }}</span>
                        </div>
                        <div class="eco-item">
                            <span class="eco-label">В обороте:</span>
                            <span class="eco-value circ">🪙 {{ total_coins_circulation }}</span>
                        </div>
                        <div class="eco-item">
                            <span class="eco-label">Средний баланс:</span>
                            <span class="eco-value avg">🪙 {{ avg_coins }}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card" style="margin-top: 30px;">
                <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 25px;">🏆 Топ-10 активных студентов</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Место</th>
                                <th>Студент</th>
                                <th>Факультет</th>
                                <th>Часы</th>
                                <th>Койны</th>
                                <th>Посещений</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for i, student in enumerate(top_students, 1) %}
                            <tr>
                                <td style="font-size: 22px;">
                                    {% if i == 1 %}🥇
                                    {% elif i == 2 %}🥈
                                    {% elif i == 3 %}🥉
                                    {% else %}<strong>{{ i }}</strong>
                                    {% endif %}
                                </td>
                                <td><strong>{{ student[1] }}</strong></td>
                                <td>{{ student[2] }}</td>
                                <td><span class="badge badge-info">{{ student[3] }} ч</span></td>
                                <td><span class="badge badge-warning">🪙 {{ student[4] }}</span></td>
                                <td><span class="badge badge-success">{{ student[5] }}</span></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card" style="margin-top: 30px;">
                <h2 style="font-weight: 800; font-size: 1.8rem; margin-bottom: 25px;">📅 Популярные мероприятия</h2>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Мероприятие</th>
                                <th>Дата</th>
                                <th>Участников</th>
                                <th>Часов выдано</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for event in popular_events %}
                            <tr>
                                <td><strong>{{ event[0] }}</strong></td>
                                <td>{{ event[1] }}</td>
                                <td><span class="badge badge-success">{{ event[2] }} чел.</span></td>
                                <td><span class="badge badge-info">{{ event[3] }} ч</span></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

STUDENTS_LIST_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Список студентов</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 32px 24px;
            box-shadow: 0 8px 24px rgba(41, 41, 41, 0.08);
            border: 1px solid var(--gray-light);
            margin-bottom: 28px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 35px;
        }
        .header h1 {
            font-weight: 900;
            font-size: clamp(1.8rem, 5vw, 2.4rem);
            letter-spacing: -0.5px;
            color: var(--dark);
            margin: 0;
        }
        .header p {
            color: var(--gray-dark);
            font-size: clamp(1rem, 3.5vw, 1.1rem);
            margin-top: 8px;
        }
        .filter-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        input, select {
            width: 100%;
            padding: 14px 16px;
            border: 1px solid var(--border);
            border-radius: 12px;
            font-size: 16px;
            font-family: inherit;
            transition: border-color 0.2s;
        }
        input:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(225, 37, 83, 0.1);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 16px 18px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            font-size: 13px;
            color: var(--dark);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
            position: sticky;
            top: 0;
        }
        th:hover {
            color: var(--primary);
        }
        tbody tr {
            transition: all 0.15s ease;
            cursor: pointer;
        }
        tbody tr:hover {
            background: var(--gray-light);
            transform: translateY(-1px);
        }
        .badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }
        .badge-success {
            background: #f0fdfa;
            color: var(--secondary);
            border: 1px solid var(--secondary);
        }
        .badge-warning {
            background: var(--gray-light);
            color: var(--primary);
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-family: inherit;
            font-weight: 600;
            font-size: 15px;
            color: var(--dark);
            background: var(--white);
            border: 1px solid var(--border);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }
        .btn:hover {
            border-color: var(--primary);
            color: var(--primary);
            background: #fff9f9;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .filter-bar {
                grid-template-columns: 1fr;
            }
            table {
                font-size: 14px;
            }
            th, td {
                padding: 12px 10px;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: 24px 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>👥 Список студентов</h1>
                    <p>Всего: {{ total_students }} студентов</p>
                </div>
                <a href="/admin/dashboard" class="btn">← Назад</a>
            </div>

            <div class="filter-bar">
                <input type="text" id="search-name" placeholder="🔍 Поиск по имени..." onkeyup="filterStudents()">
                <select id="filter-faculty" onchange="filterStudents()">
                    <option value="">Все факультеты</option>
                    {% for faculty in faculties %}
                    <option value="{{ faculty }}">{{ faculty }}</option>
                    {% endfor %}
                </select>
                <select id="filter-group" onchange="filterStudents()">
                    <option value="">Все группы</option>
                    {% for group in groups %}
                    <option value="{{ group }}">{{ group }}</option>
                    {% endfor %}
                </select>
            </div>

            <div style="overflow-x: auto;">
                <table id="students-table">
                    <thead>
                        <tr>
                            <th onclick="sortTable(0)">ID ↕</th>
                            <th onclick="sortTable(1)">Имя ↕</th>
                            <th onclick="sortTable(2)">Username ↕</th>
                            <th onclick="sortTable(3)">Факультет ↕</th>
                            <th onclick="sortTable(4)">Группа ↕</th>
                            <th onclick="sortTable(5)">Часы ↕</th>
                            <th onclick="sortTable(6)">Койны ↕</th>
                            <th>Статус</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for student in students %}
                        <tr class="student-row" onclick="window.location.href='/admin/student/{{ student[0] }}'"
                            data-name="{{ student[1].lower() }}"
                            data-faculty="{{ student[3] }}"
                            data-group="{{ student[4] }}">
                            <td><strong>{{ student[0] }}</strong></td>
                            <td><strong style="color: var(--primary);">{{ student[1] }}</strong></td>
                            <td>{{ student[2] }}</td>
                            <td>{{ student[3] }}</td>
                            <td>{{ student[4] }}</td>
                            <td><span class="badge badge-success">{{ student[5] }} ч</span></td>
                            <td><span class="badge badge-warning">🪙 {{ student[6] }}</span></td>
                            <td>
                                {% if student[7] > 0 %}
                                <span class="badge badge-success">✓ Активен</span>
                                {% else %}
                                <span class="badge badge-warning">⚠ Новый</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function filterStudents() {
            const searchName = document.getElementById('search-name').value.toLowerCase();
            const filterFaculty = document.getElementById('filter-faculty').value;
            const filterGroup = document.getElementById('filter-group').value;
            const rows = document.querySelectorAll('.student-row');
            rows.forEach(row => {
                const name = row.getAttribute('data-name');
                const faculty = row.getAttribute('data-faculty');
                const group = row.getAttribute('data-group');
                const matchName = name.includes(searchName);
                const matchFaculty = !filterFaculty || faculty === filterFaculty;
                const matchGroup = !filterGroup || group === filterGroup;
                if (matchName && matchFaculty && matchGroup) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }
        function sortTable(columnIndex) {
            const table = document.getElementById('students-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            rows.sort((a, b) => {
                const aValue = a.cells[columnIndex].textContent.trim();
                const bValue = b.cells[columnIndex].textContent.trim();
                const aNum = parseFloat(aValue.replace(/[^0-9.-]/g, ''));
                const bNum = parseFloat(bValue.replace(/[^0-9.-]/g, ''));
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return bNum - aNum;
                }
                return aValue.localeCompare(bValue);
            });
            rows.forEach(row => tbody.appendChild(row));
        }
    </script>
</body>
</html>
"""

STUDENT_PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URBAN COLLEGE — Профиль студента</title>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        :root {
            --primary: #E12553;
            --secondary: #27A38A;
            --dark: #292929;
            --gray-dark: #938E8D;
            --gray: #B1ACA9;
            --gray-light: #D7D9D3;
            --white: #FFFFFF;
            --border: #D7D9D3;
        }
        body {
            font-family: 'Manrope', system-ui, sans-serif;
            background-color: var(--white);
            color: var(--dark);
            line-height: 1.5;
            padding: 16px;
            min-height: 100vh;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
        }
        .card {
            background: var(--white);
            border-radius: 20px;
            padding: 32px 24px;
            box-shadow: 0 8px 24px rgba(41, 41, 41, 0.08);
            border: 1px solid var(--gray-light);
            margin-bottom: 28px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 35px;
        }
        .header h1 {
            font-weight: 900;
            font-size: clamp(1.8rem, 5vw, 2.4rem);
            letter-spacing: -0.5px;
            color: var(--dark);
            margin: 0;
        }
        .avatar-section {
            text-align: center;
            margin: 30px 0;
        }
        .avatar {
            width: 160px;
            height: 160px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid var(--primary);
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1);
            margin: 0 auto;
        }
        .student-name {
            font-weight: 800;
            font-size: clamp(1.6rem, 4.5vw, 2rem);
            color: var(--primary);
            margin-top: 20px;
        }
        .student-username {
            color: var(--gray-dark);
            font-size: 16px;
            margin-top: 8px;
        }
        .stat-card {
            background: var(--white);
            border: 2px solid var(--primary);
            border-radius: 20px;
            padding: 24px;
            text-align: center;
            box-shadow: 0 6px 15px -4px rgba(225, 37, 83, 0.15);
        }
        .stat-card:nth-child(2) {
            border-color: var(--secondary);
        }
        .stat-card:nth-child(3) {
            border-color: var(--gray-dark);
        }
        .stat-card:nth-child(4) {
            border-color: var(--secondary);
        }
        .stat-label {
            font-weight: 300;
            font-size: 14px;
            color: var(--gray-dark);
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }
        .stat-number {
            font-weight: 800;
            font-size: clamp(2rem, 5vw, 2.8rem);
            margin: 15px 0;
        }
        .stat-card:nth-child(1) .stat-number { color: var(--primary); }
        .stat-card:nth-child(2) .stat-number { color: var(--secondary); }
        .stat-card:nth-child(3) .stat-number { color: var(--gray-dark); }
        .stat-card:nth-child(4) .stat-number { color: var(--secondary); }
        .info-card {
            background: var(--white);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 28px;
        }
        .info-title {
            font-weight: 800;
            font-size: 1.6rem;
            color: var(--primary);
            margin-bottom: 20px;
        }
        .info-grid {
            display: grid;
            gap: 16px;
        }
        .info-item {
            padding: 14px;
            background: var(--gray-light);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
        }
        .info-label {
            font-size: 13px;
            color: var(--gray-dark);
            margin-bottom: 6px;
            font-weight: 600;
        }
        .info-value {
            font-size: 17px;
            font-weight: 700;
            color: var(--dark);
        }
        .economy-item {
            padding: 15px;
            background: var(--gray-light);
            border-radius: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .economy-value.positive {
            color: var(--secondary);
            font-weight: 800;
        }
        .economy-value.negative {
            color: var(--primary);
            font-weight: 800;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 16px 18px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            font-size: 13px;
            color: var(--dark);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        .badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }
        .badge-success {
            background: #f0fdfa;
            color: var(--secondary);
            border: 1px solid var(--secondary);
        }
        .badge-warning {
            background: var(--gray-light);
            color: var(--primary);
        }
        .grid {
            display: grid;
            gap: 25px;
        }
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }
        .grid-4 {
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-family: inherit;
            font-weight: 600;
            font-size: 15px;
            color: var(--dark);
            background: var(--white);
            border: 1px solid var(--border);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }
        .btn:hover {
            border-color: var(--primary);
            color: var(--primary);
            background: #fff9f9;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }
            .grid-2, .grid-4 {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 480px) {
            .card {
                padding: 24px 20px;
            }
            .stat-number {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>👤 Профиль студента</h1>
                <a href="/admin/students" class="btn">← Назад</a>
            </div>

            <div class="avatar-section">
                <img src="{{ avatar_url }}" class="avatar" alt="Аватар">
                <div class="student-name">{{ student[1] }}</div>
                <div class="student-username">@{{ student[2] }}</div>
            </div>

            <div class="grid grid-4 mb-3">
                <div class="stat-card">
                    <div class="stat-label">⏱️ Часы</div>
                    <div class="stat-number">{{ student[6] }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">🪙 Койны</div>
                    <div class="stat-number">{{ student[7] }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">📅 Посещений</div>
                    <div class="stat-number">{{ total_events }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">🛍️ Покупок</div>
                    <div class="stat-number">{{ total_purchases }}</div>
                </div>
            </div>

            <div class="grid grid-2 mb-3">
                <div class="info-card">
                    <h3 class="info-title">📋 Информация</h3>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">Факультет</div>
                            <div class="info-value">{{ student[3] }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Группа</div>
                            <div class="info-value">{{ student[4] }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Телефон</div>
                            <div class="info-value">{{ student[5] }}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Дата регистрации</div>
                            <div class="info-value">{{ student[8] }}</div>
                        </div>
                    </div>
                </div>
                <div class="info-card">
                    <h3 class="info-title">💰 Экономика</h3>
                    <div class="info-grid">
                        <div class="economy-item">
                            <span>Койнов потрачено:</span>
                            <span class="economy-value negative">🪙 {{ coins_spent }}</span>
                        </div>
                        <div class="economy-item">
                            <span>Текущий баланс:</span>
                            <span class="economy-value positive">🪙 {{ student[7] }}</span>
                        </div>
                    </div>
                </div>
            </div>

            {% if scans %}
            <div class="card">
                <h3 style="font-weight: 800; font-size: 1.6rem; color: var(--primary); margin-bottom: 20px;">📊 История посещений</h3>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Мероприятие</th>
                                <th>Дата</th>
                                <th>Часы</th>
                                <th>Койны</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for scan in scans %}
                            <tr>
                                <td><strong>{{ scan[0] }}</strong></td>
                                <td>{{ scan[1] }}</td>
                                <td><span class="badge badge-warning">{{ scan[2] }} ч</span></td>
                                <td><span class="badge badge-success">🪙 {{ scan[3] }}</span></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endif %}

            {% if purchases %}
            <div class="card">
                <h3 style="font-weight: 800; font-size: 1.6rem; color: var(--primary); margin-bottom: 20px;">🛍️ История покупок</h3>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Товар</th>
                                <th>Код</th>
                                <th>Статус</th>
                                <th>Дата</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for purchase in purchases %}
                            <tr>
                                <td><strong>{{ purchase[0] }}</strong></td>
                                <td><span style="font-weight: 800; color: var(--primary); font-size: 16px;">{{ purchase[1] }}</span></td>
                                <td>
                                    {% if purchase[2] == 'pending' %}
                                    <span class="badge badge-warning">⏳ Ожидает</span>
                                    {% else %}
                                    <span class="badge badge-success">✓ Выдано</span>
                                    {% endif %}
                                </td>
                                <td>{{ purchase[3] }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""
# =============== ROUTES ===============

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    elif 'creator_id' in session:
        return redirect(url_for('creator_dashboard'))
    elif 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        
        hashed_password = hash_password(password)
        c.execute('SELECT id, full_name, first_login FROM users WHERE username = ? AND password = ?',
                  (username, hashed_password))
        user = c.fetchone()
        
        if user:
            session['user_id'] = user[0]
            session['username'] = username
            session['full_name'] = user[1]
            
            if user[2] == 1:
                c.execute('UPDATE users SET first_login = 0 WHERE id = ?', (user[0],))
                conn.commit()
                conn.close()
                return redirect(url_for('certificate'))
            
            conn.close()
            return redirect(url_for('dashboard'))
        
        conn.close()
        return render_template_string(LOGIN_TEMPLATE, error='❌ Неверный логин или пароль')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        password = request.form['password']
        faculty = request.form['faculty']
        phone = request.form['phone']
        group_name = request.form['group_name']
        
        hashed_password = hash_password(password)
        
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        
        try:
            c.execute('''INSERT INTO users (full_name, username, password, faculty, phone, group_name, first_login)
                        VALUES (?, ?, ?, ?, ?, ?, 1)''',
                     (full_name, username, hashed_password, faculty, phone, group_name))
            conn.commit()
            
            user_id = c.lastrowid
            session['user_id'] = user_id
            session['username'] = username
            session['full_name'] = full_name
            
            conn.close()
            return redirect(url_for('certificate'))
        except sqlite3.IntegrityError:
            conn.close()
            return render_template_string(REGISTER_TEMPLATE, 
                                        error='❌ Этот username уже занят. Выберите другой.')
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('SELECT coins, hours, full_name, avatar FROM users WHERE id = ?', (session['user_id'],))
    user_data = c.fetchone()
    conn.close()
    
    if not user_data:
        return redirect(url_for('login'))
    
    avatar_url = user_data[3] if user_data[3] else 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="%23667eea"/><text x="50" y="50" font-size="40" fill="white" text-anchor="middle" dominant-baseline="central">👤</text></svg>'
    
    show_certificate = True if user_data and int(user_data[1]) > 0 else False
    
    return render_template_string(DASHBOARD_TEMPLATE,
                                 user_name=session['full_name'].split()[0] if session.get('full_name') else 'User',
                                 hours=user_data[1] if user_data else 0,
                                 coins=user_data[0] if user_data else 0,
                                 avatar_url=avatar_url,
                                 show_certificate=show_certificate)

@app.route('/certificate')
def certificate():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('SELECT full_name, faculty, group_name, created_at FROM users WHERE id = ?', (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    if not user:
        return redirect(url_for('login'))
    
    date = datetime.strptime(user[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
    
    return render_template_string(CERTIFICATE_TEMPLATE,
                                 full_name=user[0],
                                 faculty=user[1],
                                 group_name=user[2],
                                 date=date)

@app.route('/scan', methods=['GET', 'POST'])
def scan():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        qr_code = request.form.get('qr_code', '').strip().upper()
        
        if not qr_code or len(qr_code) != 4:
            return render_template_string(SCAN_TEMPLATE, error='❌ Неверный формат кода')
        
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        
        current_minute = int(time.time() // 60)
        c.execute('SELECT id, name, hours, date, start_time, end_time FROM events')
        events = c.fetchall()
        
        found_event = None
        
        for event in events:
            event_id = event[0]
            for minute_offset in [0, -1]:
                test_minute = current_minute + minute_offset
                
                exit_seed = f"{event_id}-exit-{test_minute}"
                exit_hash = hashlib.md5(exit_seed.encode()).hexdigest()[:4].upper()
                
                if exit_hash == qr_code:
                    found_event = event
                    break
            
            if found_event:
                break
        
        if not found_event:
            conn.close()
            return render_template_string(SCAN_TEMPLATE, error='❌ QR-код не найден или истек')
        
        event_id, event_name, event_hours, event_date, start_time, end_time = found_event
        user_id = session['user_id']
        
        c.execute('SELECT id FROM scans WHERE user_id = ? AND event_id = ?', 
                 (user_id, event_id))
        existing = c.fetchone()
        
        if existing:
            conn.close()
            return render_template_string(SCAN_TEMPLATE, 
                                        error=f'⚠️ Вы уже отметили выход с "{event_name}"')
        
        coins_to_add = event_hours
        
        c.execute('''INSERT INTO scans (user_id, event_id, exit_time, hours_earned, coins_earned, status) 
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (user_id, event_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                  event_hours, coins_to_add, 'completed'))
        
        c.execute('UPDATE users SET hours = hours + ?, coins = coins + ? WHERE id = ?',
                 (event_hours, coins_to_add, user_id))
        
        conn.commit()
        conn.close()
        
        return render_template_string(SCAN_TEMPLATE, 
                                    success=f'✅ Успешно! Вы получили {event_hours} часов и {coins_to_add} койнов за "{event_name}"')
    
    return render_template_string(SCAN_TEMPLATE)

@app.route('/events')
def events():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('SELECT id, name, description, date, start_time, end_time, hours, location FROM events ORDER BY date DESC')
    events_list = c.fetchall()
    conn.close()
    
    return render_template_string(EVENTS_TEMPLATE, events=events_list)

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('''SELECT e.name, s.exit_time, s.hours_earned, s.coins_earned
                 FROM scans s
                 JOIN events e ON s.event_id = e.id
                 WHERE s.user_id = ?
                 ORDER BY s.exit_time DESC''', (session['user_id'],))
    scans = c.fetchall()
    conn.close()
    
    return render_template_string(HISTORY_TEMPLATE, scans=scans)

@app.route('/shop')
def shop():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    c.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],))
    user_coins = c.fetchone()[0]
    
    c.execute('SELECT id, name, image_data, price, description, quantity FROM shop_items ORDER BY created_at DESC')
    items = c.fetchall()
    
    conn.close()
    
    success = request.args.get('success')
    error = request.args.get('error')
    purchase_code = request.args.get('code')
    
    return render_template_string(SHOP_TEMPLATE, 
                                 items=items, 
                                 user_coins=user_coins,
                                 success=success,
                                 error=error,
                                 purchase_code=purchase_code)

@app.route('/shop/buy/<int:item_id>', methods=['POST'])
def buy_item(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    c.execute('SELECT coins FROM users WHERE id = ?', (session['user_id'],))
    user_coins = c.fetchone()[0]
    
    c.execute('SELECT name, price, quantity FROM shop_items WHERE id = ?', (item_id,))
    item = c.fetchone()
    
    if not item:
        conn.close()
        return redirect(url_for('shop', error='Товар не найден'))
    
    item_name, item_price, item_quantity = item
    
    if item_quantity <= 0:
        conn.close()
        return redirect(url_for('shop', error='Товар закончился'))
    
    if user_coins < item_price:
        conn.close()
        return redirect(url_for('shop', error='Недостаточно койнов'))
    
    purchase_code = generate_purchase_code()
    
    c.execute('UPDATE users SET coins = coins - ? WHERE id = ?', (item_price, session['user_id']))
    c.execute('UPDATE shop_items SET quantity = quantity - 1 WHERE id = ?', (item_id,))
    c.execute('INSERT INTO purchases (user_id, item_id, code, status) VALUES (?, ?, ?, ?)',
             (session['user_id'], item_id, purchase_code, 'pending'))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('shop', success=f'✅ Товар "{item_name}" куплен!', code=purchase_code))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('SELECT full_name, username, faculty, group_name, phone, hours, coins, avatar FROM users WHERE id = ?', 
              (session['user_id'],))
    user = c.fetchone()
    
    c.execute('''SELECT p.id, si.name, p.code, p.created_at
                 FROM purchases p
                 JOIN shop_items si ON p.item_id = si.id
                 WHERE p.user_id = ? AND p.status = 'pending'
                 ORDER BY p.created_at DESC''', (session['user_id'],))
    pending_purchases = c.fetchall()
    
    conn.close()
    
    if not user:
        return redirect(url_for('login'))
    
    avatar_url = user[7] if user[7] else 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="%23667eea"/><text x="50" y="50" font-size="40" fill="white" text-anchor="middle" dominant-baseline="central">👤</text></svg>'
    
    return render_template_string(PROFILE_TEMPLATE,
                                 full_name=user[0],
                                 username=user[1],
                                 faculty=user[2],
                                 group_name=user[3],
                                 phone=user[4],
                                 hours=user[5],
                                 coins=user[6],
                                 avatar_url=avatar_url,
                                 pending_purchases=pending_purchases)

@app.route('/profile/update-avatar', methods=['POST'])
def update_avatar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'avatar' not in request.files:
        return redirect(url_for('profile'))
    
    file = request.files['avatar']
    if file.filename == '':
        return redirect(url_for('profile'))
    
    try:
        image = Image.open(file.stream)
        image = image.convert('RGB')
        image.thumbnail((300, 300))
        
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
        
        image_data = base64.b64encode(buffer.read()).decode('utf-8')
        avatar_url = f'data:image/jpeg;base64,{image_data}'
        
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        c.execute('UPDATE users SET avatar = ? WHERE id = ?', (avatar_url, session['user_id']))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating avatar: {e}")
    
    return redirect(url_for('profile'))

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# =============== CREATOR ROUTES ===============

@app.route('/creator/login', methods=['GET', 'POST'])
def creator_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = hash_password(password)
        
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        c.execute('SELECT id FROM event_creators WHERE username = ? AND password = ?',
                  (username, hashed_password))
        creator = c.fetchone()
        conn.close()
        
        if creator:
            session['creator_id'] = creator[0]
            return redirect(url_for('creator_dashboard'))
        else:
            return render_template_string(CREATOR_LOGIN_TEMPLATE, error='❌ Неверный логин или пароль')
    
    return render_template_string(CREATOR_LOGIN_TEMPLATE)

@app.route('/creator/dashboard')
def creator_dashboard():
    if 'creator_id' not in session:
        return redirect(url_for('creator_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('SELECT id, name, description, date, start_time, end_time, location, hours FROM events WHERE creator_id = ? ORDER BY created_at DESC',
              (session['creator_id'],))
    events = c.fetchall()
    conn.close()
    
    return render_template_string(CREATOR_DASHBOARD_TEMPLATE, events=events, success=request.args.get('success'))

@app.route('/creator/create-event', methods=['POST'])
def create_event():
    if 'creator_id' not in session:
        return redirect(url_for('creator_login'))
    
    name = request.form['name']
    description = request.form['description']
    day = request.form['day']
    month = request.form['month']
    year = request.form['year']
    hours = int(request.form['hours'])
    location = request.form['location']
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    
    event_date = f"{day.zfill(2)}.{month.zfill(2)}.{year}"
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('''INSERT INTO events (name, description, date, start_time, end_time, location, hours, creator_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (name, description, event_date, start_time, end_time, location, hours, session['creator_id']))
    conn.commit()
    conn.close()
    
    return redirect(url_for('creator_dashboard', success=f'✅ Мероприятие "{name}" создано!'))

@app.route('/creator/event/<int:event_id>')
def creator_event_detail(event_id):
    if 'creator_id' not in session:
        return redirect(url_for('creator_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('SELECT name, description, date, start_time, end_time, location, hours FROM events WHERE id = ? AND creator_id = ?', 
              (event_id, session['creator_id']))
    event = c.fetchone()
    
    c.execute('''
        SELECT u.full_name, u.faculty, u.group_name
        FROM scans s
        JOIN users u ON s.user_id = u.id
        WHERE s.event_id = ?
        ORDER BY s.created_at DESC
    ''', (event_id,))
    registered_students = c.fetchall()
    
    conn.close()
    
    if not event:
        return "Event not found", 404
    
    exit_code = generate_time_based_qr(event_id)
    qr_image = generate_qr_image(exit_code)
    
    return render_template_string(EVENT_DETAIL_TEMPLATE,
                                 event_id=event_id,
                                 event_name=event[0],
                                 description=event[1],
                                 date=event[2],
                                 start_time=event[3],
                                 end_time=event[4],
                                 location=event[5],
                                 hours=event[6],
                                 exit_code=exit_code,
                                 qr_image=qr_image,
                                 registered_students=registered_students,
                                 registered_count=len(registered_students),
                                 completed_count=len(registered_students),
                                 back_url='/creator/dashboard')

@app.route('/creator/logout')
def creator_logout():
    session.pop('creator_id', None)
    return redirect(url_for('creator_login'))

# =============== ADMIN ROUTES ===============

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        ADMIN_USERNAME = 'yernur@'
        ADMIN_PASSWORD = 'ernur140707'
        
        is_valid = (
            (username == ADMIN_USERNAME and password == ADMIN_PASSWORD) or
            (username == 'admin' and password == 'admin123')
        )
        
        if is_valid:
            session.clear()
            session['admin'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template_string(ADMIN_LOGIN_TEMPLATE, error='❌ Неверный логин или пароль')
    
    return render_template_string(ADMIN_LOGIN_TEMPLATE)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    c.execute('SELECT id, name, image_data, price, description, quantity FROM shop_items ORDER BY created_at DESC')
    shop_items = c.fetchall()
    
    c.execute('''SELECT p.id, si.name, p.code, u.full_name, u.phone, p.created_at
                 FROM purchases p
                 JOIN shop_items si ON p.item_id = si.id
                 JOIN users u ON p.user_id = u.id
                 WHERE p.status = 'pending'
                 ORDER BY p.created_at DESC''')
    pending_purchases = c.fetchall()
    
    conn.close()
    
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE,
                                 shop_items=shop_items,
                                 pending_purchases=pending_purchases,
                                 pending_count=len(pending_purchases),
                                 success=request.args.get('success'))

@app.route('/admin/create-creator', methods=['POST'])
def create_creator():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    username = request.form['username']
    password = request.form['password']
    hashed_password = hash_password(password)
    
    try:
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        c.execute('INSERT INTO event_creators (username, password) VALUES (?, ?)',
                  (username, hashed_password))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard', success=f'✅ Создатель "{username}" добавлен!'))
    except sqlite3.IntegrityError:
        return redirect(url_for('admin_dashboard', success='❌ Этот логин уже занят'))

@app.route('/admin/add-shop-item', methods=['POST'])
def add_shop_item():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    name = request.form['name']
    description = request.form.get('description', '')
    price = int(request.form['price'])
    quantity = int(request.form['quantity'])
    
    if 'image' not in request.files:
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['image']
    if file.filename == '':
        return redirect(url_for('admin_dashboard'))
    
    try:
        image = Image.open(file.stream)
        image = image.convert('RGB')
        image.thumbnail((800, 800))
        
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
        
        image_data = base64.b64encode(buffer.read()).decode('utf-8')
        image_url = f'data:image/jpeg;base64,{image_data}'
        
        conn = sqlite3.connect('urban_community.db')
        c = conn.cursor()
        c.execute('INSERT INTO shop_items (name, image_data, price, description, quantity) VALUES (?, ?, ?, ?, ?)',
                 (name, image_url, price, description, quantity))
        conn.commit()
        conn.close()
        
        return redirect(url_for('admin_dashboard', success=f'✅ Товар "{name}" добавлен!'))
    except Exception as e:
        print(f"Error adding shop item: {e}")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-shop-item/<int:item_id>', methods=['POST'])
def delete_shop_item(item_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('DELETE FROM shop_items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_dashboard', success='✅ Товар удален!'))

@app.route('/admin/complete-order/<int:purchase_id>', methods=['POST'])
def complete_order(purchase_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    c.execute('UPDATE purchases SET status = ? WHERE id = ?', ('completed', purchase_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_dashboard', success='✅ Заказ выполнен!'))

@app.route('/admin/cancel-order/<int:purchase_id>', methods=['POST'])
def cancel_order(purchase_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    c.execute('SELECT user_id, item_id FROM purchases WHERE id = ?', (purchase_id,))
    purchase = c.fetchone()
    
    if purchase:
        user_id, item_id = purchase
        
        c.execute('SELECT price FROM shop_items WHERE id = ?', (item_id,))
        price = c.fetchone()[0]
        
        c.execute('UPDATE users SET coins = coins + ? WHERE id = ?', (price, user_id))
        c.execute('UPDATE shop_items SET quantity = quantity + 1 WHERE id = ?', (item_id,))
        c.execute('DELETE FROM purchases WHERE id = ?', (purchase_id,))
        
        conn.commit()
    
    conn.close()
    
    return redirect(url_for('admin_dashboard', success='✅ Заказ отменен, койны возвращены!'))

@app.route('/admin/analytics')
def admin_analytics():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    # Total statistics
    c.execute('SELECT COUNT(*) FROM users')
    total_students = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM events')
    total_events = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM scans')
    total_scans = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM purchases')
    total_purchases = c.fetchone()[0]
    
    # Active students (who have at least 1 scan)
    c.execute('SELECT COUNT(DISTINCT user_id) FROM scans')
    active_students = c.fetchone()[0]
    
    activity_percent = int((active_students / total_students * 100)) if total_students > 0 else 0
    
    # Coins statistics
    c.execute('SELECT SUM(coins_earned) FROM scans')
    total_coins_issued = c.fetchone()[0] or 0
    
    c.execute('SELECT SUM(si.price) FROM purchases p JOIN shop_items si ON p.item_id = si.id')
    total_coins_spent = c.fetchone()[0] or 0
    
    c.execute('SELECT SUM(coins) FROM users')
    total_coins_circulation = c.fetchone()[0] or 0
    
    c.execute('SELECT AVG(coins) FROM users')
    avg_coins = int(c.fetchone()[0] or 0)
    
    # Top 10 students
    c.execute('''SELECT u.id, u.full_name, u.faculty, u.hours, u.coins, COUNT(s.id) as scan_count
                 FROM users u
                 LEFT JOIN scans s ON u.id = s.user_id
                 GROUP BY u.id
                 ORDER BY u.hours DESC, u.coins DESC
                 LIMIT 10''')
    top_students = c.fetchall()
    
    # Popular events
    c.execute('''SELECT e.name, e.date, COUNT(s.id) as participants, SUM(s.hours_earned) as total_hours
                 FROM events e
                 LEFT JOIN scans s ON e.id = s.event_id
                 GROUP BY e.id
                 ORDER BY participants DESC
                 LIMIT 10''')
    popular_events = c.fetchall()
    
    conn.close()
    
    return render_template_string(ANALYTICS_TEMPLATE,
                                 total_students=total_students,
                                 total_events=total_events,
                                 total_scans=total_scans,
                                 total_purchases=total_purchases,
                                 active_students=active_students,
                                 activity_percent=activity_percent,
                                 total_coins_issued=total_coins_issued,
                                 total_coins_spent=total_coins_spent,
                                 total_coins_circulation=total_coins_circulation,
                                 avg_coins=avg_coins,
                                 top_students=top_students,
                                 popular_events=popular_events,
                                 enumerate=enumerate)

@app.route('/admin/students')
def admin_students():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    c.execute('''SELECT u.id, u.full_name, u.username, u.faculty, u.group_name, u.hours, u.coins, 
                 COUNT(s.id) as scan_count
                 FROM users u
                 LEFT JOIN scans s ON u.id = s.user_id
                 GROUP BY u.id
                 ORDER BY u.full_name''')
    students = c.fetchall()
    
    c.execute('SELECT DISTINCT faculty FROM users ORDER BY faculty')
    faculties = [row[0] for row in c.fetchall()]
    
    c.execute('SELECT DISTINCT group_name FROM users ORDER BY group_name')
    groups = [row[0] for row in c.fetchall()]
    
    conn.close()
    
    return render_template_string(STUDENTS_LIST_TEMPLATE,
                                 students=students,
                                 total_students=len(students),
                                 faculties=faculties,
                                 groups=groups)

@app.route('/admin/student/<int:student_id>')
def admin_student_profile(student_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('urban_community.db')
    c = conn.cursor()
    
    c.execute('SELECT id, full_name, username, faculty, group_name, phone, hours, coins, created_at, avatar FROM users WHERE id = ?', 
              (student_id,))
    student = c.fetchone()
    
    if not student:
        conn.close()
        return "Student not found", 404
    
    c.execute('''SELECT e.name, s.exit_time, s.hours_earned, s.coins_earned
                 FROM scans s
                 JOIN events e ON s.event_id = e.id
                 WHERE s.user_id = ?
                 ORDER BY s.exit_time DESC''', (student_id,))
    scans = c.fetchall()
    
    c.execute('''SELECT si.name, p.code, p.status, p.created_at
                 FROM purchases p
                 JOIN shop_items si ON p.item_id = si.id
                 WHERE p.user_id = ?
                 ORDER BY p.created_at DESC''', (student_id,))
    purchases = c.fetchall()
    
    c.execute('SELECT COUNT(*) FROM scans WHERE user_id = ?', (student_id,))
    total_events = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM purchases WHERE user_id = ?', (student_id,))
    total_purchases = c.fetchone()[0]
    
    c.execute('SELECT SUM(si.price) FROM purchases p JOIN shop_items si ON p.item_id = si.id WHERE p.user_id = ?', (student_id,))
    coins_spent = c.fetchone()[0] or 0
    
    conn.close()
    
    avatar_url = student[9] if student[9] else 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="%23667eea"/><text x="50" y="50" font-size="40" fill="white" text-anchor="middle" dominant-baseline="central">👤</text></svg>'
    
    return render_template_string(STUDENT_PROFILE_TEMPLATE,
                                 student=student,
                                 avatar_url=avatar_url,
                                 scans=scans,
                                 purchases=purchases,
                                 total_events=total_events,
                                 total_purchases=total_purchases,
                                 coins_spent=coins_spent)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

# =============== API ROUTES ===============

@app.route('/api/refresh-qr/<int:event_id>')
def refresh_qr(event_id):
    exit_code = generate_time_based_qr(event_id)
    qr_image = generate_qr_image(exit_code)
    return jsonify({
        'exit_code': exit_code,
        'qr_image': qr_image
    })

# =============== MAIN ===============

if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("🎓 Urban collage Platform")
    print("   Админ: yernur@ / ernur140707")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)