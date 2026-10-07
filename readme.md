# 🎬 Movie Agent

Automated Python agent that scrapes movie websites, uploads posters to
Google Drive, and fills your admin panel — controlled from Firebase.

## Features
- 🤖 Automated scraping
- 🖼️ Memory-only poster upload
- 🔥 Firebase integration
- 🎛️ Admin panel control
- 🕵️ Human-like behaviour
- 📊 Rate limiting
- 📝 Rotating logs

## Setup

1. Install dependencies:
   `pip install -r requirements.txt`

2. Configure:
   `cp .env.example .env` and fill values

3. Add credentials:
   - `credentials.json` (Google Cloud)
   - `serviceAccountKey.json` (Firebase)

4. Run:
   `python agent.py`

## Deploy to Render

1. Push to GitHub
2. Create Background Worker on Render
3. Add Secret Files
4. Deploy

## Legal

For educational purposes only.

## License

MIT