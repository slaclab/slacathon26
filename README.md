# SLACATHON'26 DEMO - AI optimization platform for accelerators

Framework for hosting AI optimization hackathons (e.g. beam physics challenges).

Supports **pluggable tasks** via the `tasks/` directory. Switch the active task with the `ACTIVE_TASK` environment variable (defaults to `beamline`).

- Discover input schema at `GET /task`
- Dynamic validation and storage using Pydantic models per task
- Example tasks: Beamline Guru (default), with stubs for FEL / MARS

See the live site and GPOptimizer client for usage examples.

## Installation

### 1. Clone
```bash
git clone https://github.com/balticfish/slacathon26.git
cd slacathon26
```

### 2. Virtualenv
```bash
python -m venv venv
source venv/bin/activate
pip install numpy scipy fastapi uvicorn gunicorn
```

### 3. Configuration
```bash
cp .env.example .env
# Edit .env and set SLACATHON_API_KEYS (comma or space separated)
```

### 4. Run
```bash
./start.sh
```

Or for development:
```bash
source venv/bin/activate
uvicorn main:app --reload
```

**Note:** `start.sh` hard-codes the venv path for the current deployment. Edit it or use your own activation for other environments. Set `ACTIVE_TASK` to switch challenge logic (see `tasks/`).

## Registering as a System Service (Linux with systemd)

To run the FastAPI app as a background service on a Linux system using systemd:

### 1. Create a service file

Create `/etc/systemd/system/myfastapi.service`:
```ini
[Unit]
Description=FastAPI application
Wants=nss-user-lookup.target
After=nss-user-lookup.target

[Service]
User=alex
Group=www-data
WorkingDirectory=/home/alex/backend
Environment="PATH=/home/alex/backend/venv/bin"
ExecStart=/home/alex/backend/start.sh
Restart=always

[Install]
WantedBy=multi-user.target
```

**Note:** Replace `/home/alex` with your actual path. Adjust `User`, `Group`, and port as needed.

### 2. Reload systemd
```bash
sudo systemctl daemon-reload
```

### 3. Service Management Commands

**Starting the Service:**
```bash
sudo systemctl start myfastapi
```

**Checking Status:**
```bash
sudo systemctl status myfastapi
```

**Stopping the Service:**
```bash
sudo systemctl stop myfastapi
```

**Enabling on Boot:**
```bash
sudo systemctl enable myfastapi
```

**Restarting the Service:**
```bash
sudo systemctl restart myfastapi
```

**Viewing Logs:**
```bash
sudo journalctl -u myfastapi -f
```

## Nginx Reverse Proxy Setup

### 1. Install Nginx
```bash
sudo apt update
sudo apt install nginx
```

### 2. Create Nginx Configuration

Create a new site configuration file `/etc/nginx/sites-available/slacathon`:
```nginx
server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain or IP

    # Redirect HTTP to HTTPS (optional, after SSL setup)
    # return 301 https://$server_name$request_uri;

    # Main application at /slacathon26
    location /slacathon26/ {
        proxy_pass http://127.0.0.1:8000/slacathon26/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Optional: Serve static files directly
    location /static/ {
        alias /home/alex/backend/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Optional: Health check endpoint
    location /slacathon26/health {
        proxy_pass http://127.0.0.1:8000/slacathon26/health;
        access_log off;
    }
}
```

### 3. Enable the Site
```bash
# Create symbolic link to sites-enabled
sudo ln -s /etc/nginx/sites-available/slacathon /etc/nginx/sites-enabled/

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

### 4. Configure Firewall (if using UFW)
```bash
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

### 5. SSL/HTTPS Setup with Let's Encrypt (Recommended)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain and install certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is set up automatically
# Test renewal with:
sudo certbot renew --dry-run
```

### 6. Advanced Nginx Configuration (Optional)

For production environments, add these optimizations to your Nginx config:
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificates (managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL optimization
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    
    location /slacathon26/ {
        limit_req zone=api_limit burst=20 nodelay;
        
        proxy_pass http://127.0.0.1:8000/slacathon26/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;
    }

    # Logging
    access_log /var/log/nginx/slacathon_access.log;
    error_log /var/log/nginx/slacathon_error.log;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### 7. Nginx Troubleshooting

**Check Nginx status:**
```bash
sudo systemctl status nginx
```

**View error logs:**
```bash
sudo tail -f /var/log/nginx/error.log
```

**View access logs:**
```bash
sudo tail -f /var/log/nginx/access.log
```

**Test configuration:**
```bash
sudo nginx -t
```

**Reload configuration (without downtime):**
```bash
sudo systemctl reload nginx
```

## Project Structure

```
backend/
├── main.py                 # FastAPI app (root_path=/slacathon26)
├── middleware.py           # Auth, quotas, jobs, leaderboard logic
├── task_loader.py          # Loads active task from tasks/ dir
├── tasks/
│   ├── base.py             # TaskInput, TaskResult, Task protocol
│   ├── beamline.py         # Default task (RTFB beam optimization)
│   └── __init__.py
├── GPOptimizer.py          # Gaussian Process optimizer client
├── optimize_usage.py       # Example optimization script (with patching)
├── usage.py                # Simple validation client example
├── start.sh                # Launcher (activates venv + gunicorn)
├── .env.example
├── fort.1                  # Physics data file (for beamline task)
├── index.html              # Landing / hero page
├── leaderboard.html        # Leaderboard UI (dynamic via /task)
├── team.html
├── .gitignore
└── README.md
```

**Key changes from legacy structure:**
- `models.py` and `logic.py` removed (dead code cleaned)
- New `task_loader.py` + `tasks/` package for pluggable challenges
- All static HTML served from root
- No top-level `app/` directory (the repo now uses a flat `backend/` layout)

## Development

```bash
# Recommended: use the provided start.sh (or manually)
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Production

Use the included launcher (recommended):

```bash
./start.sh
```

It activates the venv and runs:
```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 1 --timeout 300 \
  --bind 127.0.0.1:8888 main:app
```

To switch tasks (pluggable system):

```bash
export ACTIVE_TASK=beamline   # or fel, mars, etc.
./start.sh
```

See `GET /task` for the current task's input schema, labels, and bounds.

## Accessing the Application

The app is mounted under `/slacathon26` (FastAPI `root_path`).

- **Landing Page:** `https://your-domain.com/slacathon26/`
- **Leaderboard:** `https://your-domain.com/slacathon26/board`
- **Team Page:** `https://your-domain.com/slacathon26/team`
- **Task Info / Schema:** `GET https://your-domain.com/slacathon26/task`
- **Validate (job-based):** `POST https://your-domain.com/slacathon26/validate`
- **Submit to leaderboard:** `POST https://your-domain.com/slacathon26/submit`
- **History / Leaderboard:** `GET /history`, `GET /leaderboard`

Use `X-API-Key` header for protected endpoints. See `/task` for the exact input shape expected by the currently active task.

## Features

- 🚀 FastAPI + Gunicorn
- 🔐 API key authentication + per-user quotas
- 🔌 Pluggable tasks (`tasks/*.py` + `ACTIVE_TASK` env)
- 📊 Dynamic input schema (`GET /task`)
- 📈 Job-based validation + full history
- 🏆 Leaderboard with duplicate detection
- 🧪 Example GP optimizer client (GPOptimizer.py)

## License

Stanford License

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Support

For questions or issues, please open an issue on GitHub or contact the team.
