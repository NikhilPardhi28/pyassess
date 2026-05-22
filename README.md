# PyAssess Pro – Python Developer Test System
### Complete setup, running, and hosting guide

---

## 📁 Project Structure
```
pytest/
├── app.py                  # Flask backend (all routes)
├── requirements.txt        # Dependencies
├── Procfile                # For Render/Railway deployment
├── data/
│   ├── questions.json      # All 60 questions
│   ├── results.json        # Auto-created on first submission
│   └── sessions.json       # Auto-created on first session
└── templates/
    ├── base.html           # Shared styles
    ├── index.html          # Landing page
    ├── test.html           # Candidate test page (camera + mic)
    ├── completed.html      # After submission
    ├── error.html          # Error/invalid link
    ├── admin_login.html    # Admin login
    ├── admin_dashboard.html # Admin panel
    └── admin_result.html   # Per-candidate result + code review
```

---

## 🚀 Running Locally

### Step 1 – Install Python (3.10+)
Download from https://python.org if not installed.

### Step 2 – Install dependencies
```bash
cd pytest
pip install -r requirements.txt
```

### Step 3 – Run the server
```bash
python app.py
```
Open: **http://localhost:5000**

### Step 4 – Admin Login
Go to: http://localhost:5000/admin/login
- Username: `admin`
- Password: `Admin@PyTest2024`

> ⚠️ Change the password in app.py (ADMIN_PASS_HASH) before going live!

### Step 5 – Send a test link
1. Log into admin panel
2. Enter candidate name + email → click "Generate Test Link"
3. Copy the link and send it to the candidate via email/WhatsApp

---

## 🌐 Hosting Online (Free – Render.com)

### Option A: Render (Recommended – Free tier)

1. **Create account** at https://render.com

2. **Push your project to GitHub:**
```bash
cd pytest
git init
git add .
git commit -m "Initial commit"
# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/pyassess.git
git push -u origin main
```

3. **On Render:**
   - Click "New Web Service"
   - Connect your GitHub repo
   - Set:
     - Build Command: `pip install -r requirements.txt`
     - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
   - Click Deploy

4. **Your URL** will be: `https://pyassess-xxxx.onrender.com`

5. **⚠️ Important for Render free tier:**
   - Data (results.json, sessions.json) is **not persistent** between restarts.
   - To persist data, use a free **PocketBase** or **Supabase** DB (or upgrade to Render paid).
   - OR use Railway (see below) which has a persistent disk option.

---

### Option B: Railway.app (Easy + Persistent)

1. Go to https://railway.app
2. Click "New Project" → "Deploy from GitHub"
3. Connect repo → Railway auto-detects Python
4. Add a **Volume** (under Settings) mounted at `/app/data` for persistent storage
5. Set environment variable: `PORT=8080`
6. Deploy! Your URL appears in the Railway dashboard.

---

### Option C: VPS (DigitalOcean / Hostinger / AWS EC2)

```bash
# SSH into your server
ssh user@your-server-ip

# Install Python & pip
sudo apt update && sudo apt install python3-pip nginx -y

# Clone/upload your project
git clone https://github.com/YOUR_USERNAME/pyassess.git
cd pyassess

# Install deps
pip3 install -r requirements.txt

# Run with gunicorn (background)
gunicorn app:app --bind 127.0.0.1:5000 --workers 2 --daemon

# Set up Nginx reverse proxy
sudo nano /etc/nginx/sites-available/pyassess
```
Paste this Nginx config:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/pyassess /etc/nginx/sites-enabled/
sudo systemctl restart nginx

# Add SSL (free with Let's Encrypt)
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

---

## 🔒 Security Checklist Before Going Live

- [ ] Change `app.secret_key` in app.py to a random 32+ char string
- [ ] Change admin password: update `ADMIN_PASS_HASH` in app.py
  ```python
  import hashlib
  print(hashlib.sha256("YourNewPassword".encode()).hexdigest())
  # Copy the output and replace ADMIN_PASS_HASH
  ```
- [ ] Use HTTPS (required for camera/mic access in browsers!)
- [ ] Restrict admin route with IP allowlist if on VPS

---

## 📊 Test Details

| Category     | Count | Points |
|-------------|-------|--------|
| Very Easy   | 3     | 3      |
| Easy        | 22    | 22     |
| Medium      | 20    | 20     |
| Extreme     | 10    | 10     |
| Coding      | 5     | 5      |
| **Total**   | **60**| **60** |

- MCQ: Auto-graded instantly
- Coding: Admin reviews manually in the result page
- **Final score**: MCQ score + admin-assigned code scores (max 65)

---

## 🎥 Proctoring Features

| Feature | Behavior |
|---------|----------|
| Camera | Required on test start; preview shown in top bar |
| Microphone | Required; continuously monitored |
| **Voice/Noise Detection** | **Single noise above threshold → instant auto-eject** |
| Tab Switch | Logged as proctoring event (shown to admin) |
| Copy/Paste | Logged as proctoring event |
| Fullscreen Exit | Logged as proctoring event |

All events are visible to admin in the result detail page.

---

## 📧 Sending Test Links

After generating a link in the admin panel, you can send it via:
- **Email** (copy-paste the link)
- **WhatsApp/Telegram**
- Use any email service like Gmail, or automate with SMTP

The link is unique per candidate and expires once used (test completed/ejected).

---

## ❓ FAQ

**Q: Can the candidate retake the test?**
Delete their session in the admin panel and generate a new link.

**Q: What if the candidate has no camera/mic?**
They'll see denied status in the bar, and the event is logged. You can choose to reject or allow.

**Q: Where is data stored?**
Locally in `data/results.json` and `data/sessions.json`. Back these up regularly.

**Q: Can I add/edit questions?**
Yes — edit `data/questions.json` directly. Follow the existing format.
