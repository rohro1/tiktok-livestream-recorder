#!/bin/bash

# TikTok Livestream Recorder Setup Script
# For Render free tier deployment

echo "🚀 Setting up TikTok Livestream Recorder..."

# Create required directories
echo "📁 Creating directories..."
mkdir -p recordings
mkdir -p logs
mkdir -p src/core
mkdir -p src/utils
mkdir -p templates

# Create empty usernames.txt if it doesn't exist
if [ ! -f "usernames.txt" ]; then
    echo "📝 Creating usernames.txt..."
    cat > usernames.txt << EOF
# Add TikTok usernames here (one per line, without @)
# Example:
# username1
# username2
EOF
fi

# Set permissions
echo "🔐 Setting permissions..."
chmod +x setup_project.sh
chmod 755 recordings
chmod 755 logs

# Check for required files
echo "🔍 Checking required files..."

if [ ! -f "credentials.json" ]; then
    echo "⚠️  WARNING: credentials.json not found"
    echo "   Please add your Google OAuth credentials to continue"
fi

if [ ! -f "requirements.txt" ]; then
    echo "❌ ERROR: requirements.txt not found"
    exit 1
fi

# Install dependencies (for local development)
if command -v python3 &> /dev/null; then
    echo "📦 Installing Python dependencies..."
    python3 -m pip install -r requirements.txt
else
    echo "⚠️  Python3 not found, skipping dependency installation"
fi

# Check for ffmpeg (required for recording)
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  WARNING: ffmpeg not found"
    echo "   FFmpeg is required for video recording"
    echo "   On Ubuntu/Debian: sudo apt-get install ffmpeg"
    echo "   On macOS: brew install ffmpeg"
    echo "   On Render: FFmpeg is pre-installed"
fi

# Create a sample environment file
if [ ! -f ".env.example" ]; then
    echo "📄 Creating .env.example..."
    cat > .env.example << EOF
# Google OAuth Configuration
GOOGLE_CREDENTIALS_JSON={"web":{"client_id":"your-client-id"...}}
OAUTH_REDIRECT_URI=https://your-app-name.onrender.com/auth/callback

# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_ENV=production

# Optional: Logging Level
LOG_LEVEL=INFO
EOF
fi

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Add your Google OAuth credentials to credentials.json"
echo "   2. Add TikTok usernames to usernames.txt"
echo "   3. Deploy to Render with the provided configuration"
echo "   4. Set up environment variables in Render dashboard"
echo "   5. Authorize Google Drive access through the web interface"
echo ""
echo "🔗 For deployment help, see README.md"