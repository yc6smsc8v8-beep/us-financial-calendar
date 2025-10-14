# US Economic + Earnings Calendar - Render Deployment

## 1. Create GitHub Repo
Follow steps in Render instructions. Use files in this folder.

## 2. Initialize Git repo
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/us-financial-calendar.git
git branch -M main
git push -u origin main

## 3. Deploy to Render
- Go to https://render.com → New → Web Service → Connect GitHub
- Select your repo
- Build & Start commands detected automatically via Dockerfile
- Access feed at: https://<your-service>.onrender.com/us_financial_calendar.ics
- Subscribe in Outlook or other calendar apps from this URL