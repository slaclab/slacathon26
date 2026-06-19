# AI Hackathon DEMO Framework with FastAPI

This is a framework for hosting beamphysics AI hackathons. Example problem is round-to-flat beam optimization (MagnetOptimizer). 
See <a href="https://halavanau.group/slacathon26">halavanau.group</a> and GP optimizer notebook for demo.

## Installation Instructions

### 1. Clone the repository
```bash
git clone https://github.com/balticfish/slacathon26.git
cd slacathon26
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
```

**Activate the environment:**
- On macOS/Linux: 
```bash
  source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install numpy scipy fastapi uvicorn gunicorn
```

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
WorkingDirectory=/home/alex/app
Environment="PATH=/home/alex/app/venv/bin"
ExecStart=/home/alex/app/start.sh
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

    # Main application at /app
    location /app/ {
        proxy_pass http://127.0.0.1:8000/app/;
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
        alias /home/alex/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Optional: Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/app/health;
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
    
    location /app/ {
        limit_req zone=api_limit burst=20 nodelay;
        
        proxy_pass http://127.0.0.1:8000/app/;
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
slacathon26/
├── app/
│   ├── venv/
│   ├── main.py
│   ├── middleware.py
│   ├── models.py
│   ├── logic.py
│   ├── start.sh
│   ├── index.html
│   ├── leaderboard.html
│   ├── team.html
│   └── requirements.txt
└── README.md
```

## Development

To run the application in development mode:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Production Deployment

For production, use Gunicorn with Uvicorn workers:
```bash
gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000
```

**Note:** When behind Nginx, bind to `127.0.0.1` instead of `0.0.0.0` for security.

## Accessing the Application

Once deployed:

- **Landing Page:** `https://your-domain.com/app/`
- **Leaderboard:** `https://your-domain.com/app/board`
- **Team Page:** `https://your-domain.com/app/team`
- **API Validation:** `POST https://your-domain.com/app/validate`
- **API Submit:** `POST https://your-domain.com/app/submit`

## Features

- 🚀 FastAPI-based REST API
- 🔐 API key authentication
- 📊 Real-time leaderboard
- 🎯 Optimization challenge framework
- 📈 Historical tracking of submissions

## License

Stanford License

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Support

For questions or issues, please open an issue on GitHub or contact the team.
