# Lnkedin Job Application Bot 🤖

Automate job applications on Lnkedin with AI-powered responses and Telegram integration for dynamic answering.  
This bot leverages Selenium stealth technology, OpenAI GPT answering, and Telegram real-time prompts to fill out Easy Apply forms hands-free!

---

## ✨ Features

- **Lnkedin Easy Apply Automation** (multiple roles, locations, and pages)
- **Auto-Fill Open-Ended Questions** using OpenAI GPT and an answer cache
- **Telegram Bot Integration** for manual human-assisted answering if needed
- **Answer Memory Bank** (caches answers to reuse on future applications)
- **Cookie-Based Authentication** (secure login using `li_at` and `JSESSIONID`)
- **Stealth Selenium Browser** (undetectable by Lnkedin anti-bot measures)
- **Multi-Page Support** (auto-scrolls through multiple pages of job results)
- **Error Recovery** (handles CAPTCHA detection, click errors, timeouts)

---

## 🚀 Requirements

- Python 3.8+
- Google Chrome (latest)
- ChromeDriver (automatically managed)
- A Lnkedin account (with `li_at` cookie)
- A Telegram bot token and chat ID
- An OpenAI API key

---

## 🛠 Installation

```bash
git clone https://github.com/YOUR_USERNAME/lnkedin-job-application-bot.git
cd lnkedin-job-application-bot
python -m venv venv
source venv/bin/activate   # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
```

---

## ⚙️ Setup

1. **Create `.env` file** (copy from example):

```bash
cp .env.example .env
```

2. **Fill in your `.env` values**:

```dotenv
LINKEDIN_LI_AT=your_li_at_cookie
LINKEDIN_JSESSIONID=your_jsessionid_cookie
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
OPENAI_API_KEY=your_openai_key
```

3. **Update `BASE_URLS` inside `job_application_bot.py`** with your Lnkedin job search links.

Example:

```python
BASE_URLS = [
    "https://www.lnkedin.com/jobs/search/?keywords=cloud%20engineer&location=Remote",
    "https://www.lnkedin.com/jobs/search/?keywords=cybersecurity%20analyst&location=United%20States"
]
```

---

## 🧠 How It Works

- **Login** using Lnkedin cookies (`li_at`, `JSESSIONID`).
- **Find jobs** matching the keywords and locations from your URLs.
- **Auto-click** \"Easy Apply\" and **fill forms**:
  - If an answer is known, it autofills.
  - If unknown, it sends a **Telegram prompt** to you for real-time answering.
  - Answers are **saved permanently** to an `answer_bank.json` for future reuse.
- **Submit the application** and move to the next job!

---

## 📈 Running the Bot

```bash
python job_application_bot.py
```

It will run **forever** and **re-check every 2 hours** automatically.

> **Tip:** Run inside `screen` or `tmux` if using a server or VPS.

---

## 📂 Project Structure

```
lnkedin-job-application-bot/
├── assets/
│   └── (Your Resume, if needed)
├── templates/
│   └── (Optional Cover Letters)
├── answer_bank.json
├── .env
├── job_application_bot.py
├── requirements.txt
└── README.md
```

---

## 🛡️ Important Notes

- **ChromeDriver is automatically managed** — no need to download manually.
- **Telegram Bot** must have "privacy mode disabled" to receive replies properly.
- **Do not abuse Lnkedin** — applications are throttled reasonably with random sleeps.
- **For best stealth:** Run the bot on a residential IP or your home network.

---

## 🤝 Contributing

Pull requests are welcome. Open an issue first to discuss a new feature or fix!

---

## 🪪 License

This project is licensed under the [MIT License](LICENSE).
