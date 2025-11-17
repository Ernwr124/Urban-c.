# Multilingual Setup Guide

HR Agent now supports **three languages**: English, Russian (Русский), and Kazakh (Қазақша)!

## Features

### 1. **Full UI Translation**
- All buttons, labels, and text are translated
- Navigation menu in your language
- Forms and error messages localized

### 2. **AI Analysis in Your Language**
- Resume analysis results in your preferred language
- Recommendations and feedback in your language
- All pros/cons and skills analysis translated

### 3. **Easy Language Switching**
- Language selector in the navigation bar
- Click on current language (e.g., "English ▾")
- Select from: English / Русский / Қазақша
- Changes apply immediately

## How to Change Language

1. **Log in** to your HR Agent account
2. Look for the **language selector** in the top navigation bar (next to your name)
3. **Click** on the current language (e.g., "English ▾")
4. **Select** your preferred language from the dropdown
5. The page will **reload** with your selected language

## Supported Languages

### English
- Default language
- Full feature support
- AI analysis in English

### Русский (Russian)
- Полная поддержка интерфейса
- ИИ-анализ на русском языке
- Все функции переведены

### Қазақша (Kazakh)
- Толық интерфейс қолдауы
- AI талдауы қазақ тілінде
- Барлық функциялар аударылған

## Technical Details

### Database Schema
The `users` table now includes a `language` field:
- Default: `'en'` (English)
- Options: `'en'`, `'ru'`, `'kk'`

### AI Integration
The Ollama AI model (gpt-oss:20b-cloud) receives language instructions:
- English: "Respond in English. Provide all analysis..."
- Russian: "Отвечай на русском языке. Все тексты..."
- Kazakh: "Қазақ тілінде жауап беріңіз. Барлық мәтіндер..."

## Important Notes

### First Time Setup
If you're upgrading from an older version:

1. **Delete the old database**:
   ```bash
   rm hr_agent.db
   ```

2. **Restart the application**:
   ```bash
   python3 hr_platform.py
   ```

3. The new database will be created with the `language` field

### Default Language
- New users: English
- Existing users (after upgrade): English (until they change it)

## Translation Coverage

### Fully Translated Pages
- ✅ Landing page
- ✅ Login & Register
- ✅ Dashboard
- ✅ Profile page
- ✅ Edit Profile
- ✅ Resume Upload
- ✅ Analyze (Job Matching)
- ✅ Results page
- ✅ AI Analysis output
- ✅ Navigation menu
- ✅ Buttons and forms

### AI Output Translation
All AI-generated content is translated:
- Match score explanations
- Strengths (Pros)
- Areas to address (Cons)
- Skills analysis
- Experience match analysis
- Education match analysis
- Recommendations

## FAQ

**Q: Will my existing analyses be translated?**  
A: No, existing analyses remain in the language they were created in. Only new analyses will use your selected language.

**Q: Can I use different languages for different analyses?**  
A: Yes! The language used for analysis is based on your current language setting at the time of analysis.

**Q: Does the language affect the AI model?**  
A: The AI model (gpt-oss:20b-cloud) is instructed to respond in your selected language, providing natural and accurate translations.

**Q: Can I contribute translations?**  
A: Yes! The translations are stored in the `TRANSLATIONS` dictionary in `hr_platform.py`. Feel free to improve them or add new languages.

## Contributing Translations

If you'd like to improve translations or add a new language:

1. Find the `TRANSLATIONS` dictionary in `hr_platform.py`
2. Add or modify translation strings
3. For new languages, add a new language code (e.g., `"fr"` for French)
4. Update the language selector in `get_base_html()` function
5. Test thoroughly!

Example translation structure:
```python
TRANSLATIONS = {
    "en": {
        "key": "English text"
    },
    "ru": {
        "key": "Русский текст"
    },
    "kk": {
        "key": "Қазақ мәтіні"
    }
}
```

---

**Enjoy HR Agent in your language! 🌍**
Наслаждайтесь HR Agent на вашем языке! 🌍  
HR Agent-ті өз тіліңізде пайдаланыңыз! 🌍
