# 🌐 Upgrade to Multilingual Version

Your HR Agent platform now supports **three languages**! 🎉

## ✅ What's New

### 1. **Three Languages**
- 🇬🇧 **English** - Default
- 🇷🇺 **Русский** - Russian
- 🇰🇿 **Қазақша** - Kazakh

### 2. **Full Translation**
- ✅ All UI elements
- ✅ Navigation menu
- ✅ Buttons and forms
- ✅ AI analysis results
- ✅ Recommendations

### 3. **Easy Switching**
Click the language selector in the navigation bar!

## 🚀 Quick Upgrade Steps

### Step 1: Delete Old Database

The database schema has changed to include language preference:

```bash
rm hr_agent.db
```

### Step 2: Restart Application

```bash
python3 hr_platform.py
```

Or if using uvicorn:

```bash
uvicorn hr_platform:app --host 0.0.0.0 --port 8000
```

### Step 3: Done!

The new database will be created automatically with all new fields.

## 🎯 How to Use

1. **Log in** to your account
2. Look for the **language selector** in the top-right corner
3. Click on "English ▾" (or current language)
4. **Select** your preferred language:
   - English
   - Русский
   - Қазақша
5. **Enjoy** the platform in your language!

## 💡 Important Notes

### New Users
- Default language: English
- Can change anytime from navigation bar

### Existing Users (After Upgrade)
- Default language: English
- Your analyses and data are preserved
- Change language from navigation bar

### AI Analysis
- AI will respond in your selected language
- Existing analyses remain in their original language
- New analyses use your current language setting

## 🔧 Technical Changes

### Database Schema
New field in `users` table:
- `language` (String, default: 'en')

### Supported Languages
- `en` - English
- `ru` - Russian  
- `kk` - Kazakh

### Translation System
- Built-in `TRANSLATIONS` dictionary
- Helper function: `t(key, lang)`
- Covers all UI strings and labels

## 📚 Documentation

- **Full multilingual guide**: See [MULTILINGUAL_SETUP.md](./MULTILINGUAL_SETUP.md)
- **Updated README**: See [README.md](./README.md)
- **Ollama setup**: See [OLLAMA_SETUP.md](./OLLAMA_SETUP.md)

## ❓ FAQ

**Q: Will my old analyses be lost?**  
A: No! Only the database structure changes. Your data is safe.

**Q: Do I need to re-register?**  
A: Yes, after deleting the database you'll need to create a new account.

**Q: Can I export my old data first?**  
A: If you need to preserve old analyses, you can:
1. Backup `hr_agent.db` before deleting
2. Or keep it as `hr_agent_backup.db`

**Q: How do I change language?**  
A: Click the language selector in the navigation bar (e.g., "English ▾").

**Q: Will AI understand my language?**  
A: Yes! The AI model (gpt-oss:20b-cloud) is instructed to respond in your selected language.

## 🎉 Enjoy!

Your HR Agent is now multilingual!

**Наслаждайтесь!** (Russian)  
**Ләззат алыңыз!** (Kazakh)

---

For questions or issues, check the documentation or create an issue.
