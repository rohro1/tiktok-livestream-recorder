#!/bin/bash

# Render Deployment Script for TikTok Livestream Recorder
# This script prepares and deploys the app to Render

echo "🚀 TikTok Livestream Recorder - Deployment Script"
echo "================================================"

# 1. Create required directories
echo "📁 Creating directories..."
mkdir -p recordings
mkdir -p logs
mkdir -p templates

# 2. Ensure usernames.txt exists
if [ ! -f "usernames.txt" ]; then
    echo "📝 Creating usernames.txt..."
    cat > usernames.txt << EOF
# TikTok usernames to monitor (one per line, without @)
baba_king_officia1
mubarakdewan7
yeahitsme
justdoyoubro
liza.akter304
atif_live_
EOF
fi

# 3. Create simplified requirements.txt
echo "📦 Creating requirements.txt..."
cat > requirements.txt << EOF
Flask==3.0.0
gunicorn==21.2.0
yt-dlp>=2024.1.0
requests==2.31.0
python-dateutil==2.8.2
EOF

# 4. Create Procfile for Render
echo "⚙️ Creating Procfile..."
cat > Procfile << EOF
web: gunicorn main:app --bind 0.0.0.0:\$PORT --workers 1 --threads 2 --timeout 120
EOF

# 5. Create render.yaml
echo "🔧 Creating render.yaml..."
cat > render.yaml << EOF
services:
  - type: web
    name: tiktok-recorder
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn main:app --bind 0.0.0.0:\$PORT --workers 1 --threads 2 --timeout 120
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: SECRET_KEY
        generateValue: true
    healthCheckPath: /health
    autoDeploy: true
EOF

# 6. Create .gitignore
echo "🚫 Creating .gitignore..."
cat > .gitignore << EOF
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
recordings/*.mp4
logs/*.log
token.pickle
credentials.json
.env
.DS_Store
EOF

# 7. Initialize git if needed
if [ ! -d ".git" ]; then
    echo "📂 Initializing git repository..."
    git init
fi

# 8. Stage all files
echo "📤 Staging files for commit..."
git add -A

# 9. Commit changes
echo "💾 Committing changes..."
git commit -m "Deploy TikTok Livestream Recorder to Render" || true

# 10. Instructions
echo ""
echo "✅ Deployment preparation complete!"
echo ""
echo "📋 Next steps to deploy to Render:"
echo ""
echo "1. Push to GitHub (if not already done):"
echo "   git remote add origin YOUR_GITHUB_REPO_URL"
echo "   git push -u origin main"
echo ""
echo "2. Go to https://dashboard.render.com"
echo ""
echo "3. Click 'New +' → 'Web Service'"
echo ""
echo "4. Connect your GitHub repository"
echo ""
echo "5. Use these settings:"
echo "   - Name: tiktok-recorder"
echo "   - Environment: Python 3"
echo "   - Build Command: pip install -r requirements.txt"
echo "   - Start Command: gunicorn main:app --bind 0.0.0.0:\$PORT"
echo ""
echo "6. Click 'Create Web Service'"
echo ""
echo "7. Your app will be available at: https://tiktok-recorder.onrender.com"
echo ""
echo "📌 Important: The app will automatically start monitoring when deployed!"
echo ""