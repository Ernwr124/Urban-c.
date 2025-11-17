# 🚀 Project-0 Production Deployment Guide

## 📋 Prerequisites

- Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- Python 3.9+
- Ollama installed
- 4GB+ RAM
- SSL certificate (Let's Encrypt recommended)

## 🔧 Method 1: Manual Deployment

### Step 1: System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx

# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh
```

### Step 2: Create User & Directory

```bash
# Create user
sudo useradd -r -s /bin/bash -d /opt/project0 project0

# Create directory
sudo mkdir -p /opt/project0
sudo chown project0:project0 /opt/project0
```

### Step 3: Deploy Application

```bash
# Switch to project0 user
sudo su - project0

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Copy files
cd /opt/project0
# Upload project0.py and requirements.txt

# Install dependencies
pip install -r requirements.txt

# Download model
ollama pull glm-4.6:cloud
```

### Step 4: Setup Systemd Service

```bash
# Copy systemd service file
sudo cp systemd.service /etc/systemd/system/project0.service

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable project0
sudo systemctl start project0

# Check status
sudo systemctl status project0
```

### Step 5: Configure Nginx

```bash
# Copy nginx configuration
sudo cp nginx.conf /etc/nginx/sites-available/project0
sudo ln -s /etc/nginx/sites-available/project0 /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Restart nginx
sudo systemctl restart nginx
```

### Step 6: Configure Firewall

```bash
# Allow HTTP, HTTPS, SSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

## 🐳 Method 2: Docker Deployment

### Step 1: Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose -y

# Add user to docker group
sudo usermod -aG docker $USER
```

### Step 2: Build and Run

```bash
# Clone repository
git clone your-repo-url
cd project0

# Start Ollama (on host)
ollama serve &
ollama pull glm-4.6:cloud

# Build and run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Step 3: Nginx Proxy (optional)

Use the same nginx configuration as Method 1.

## 🔍 Method 3: Cloud Platform Deployment

### AWS EC2

```bash
# Launch EC2 instance (t3.medium or larger)
# Ubuntu 20.04 LTS
# Security Group: Allow 80, 443, 22

# SSH to instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Follow Manual Deployment steps
```

### Google Cloud Platform

```bash
# Create Compute Engine instance
gcloud compute instances create project0 \
  --machine-type=n1-standard-2 \
  --image-family=ubuntu-2004-lts \
  --image-project=ubuntu-os-cloud \
  --zone=us-central1-a

# SSH to instance
gcloud compute ssh project0

# Follow Manual Deployment steps
```

### DigitalOcean

```bash
# Create Droplet (4GB RAM minimum)
# Ubuntu 20.04 LTS

# SSH to droplet
ssh root@your-droplet-ip

# Follow Manual Deployment steps
```

## 📊 Monitoring & Logging

### Setup Logging

```bash
# Create log directory
sudo mkdir -p /var/log/project0
sudo chown project0:project0 /var/log/project0

# View logs
sudo journalctl -u project0 -f
```

### Setup Monitoring (Prometheus + Grafana)

```bash
# Install Prometheus
sudo apt install prometheus -y

# Install Grafana
sudo apt-get install -y software-properties-common
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install grafana -y

# Enable and start
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
```

## 🔐 Security Hardening

### 1. Firewall Configuration

```bash
# Use UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 2. Fail2Ban

```bash
# Install Fail2Ban
sudo apt install fail2ban -y

# Configure
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. SSL/TLS

```bash
# Use Let's Encrypt
sudo certbot certonly --nginx -d your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### 4. Environment Variables

```bash
# Never commit secrets
# Use .env file
cp .env.example .env
nano .env  # Edit with your values

# Restrict permissions
chmod 600 .env
```

## 🔄 Updates & Maintenance

### Update Application

```bash
# Pull latest code
cd /opt/project0
git pull

# Restart service
sudo systemctl restart project0
```

### Update Model

```bash
# Update GLM model
ollama pull glm-4.6:cloud

# Restart application
sudo systemctl restart project0
```

### Backup

```bash
# Backup configuration
tar -czf project0-backup-$(date +%Y%m%d).tar.gz \
  /opt/project0/*.py \
  /opt/project0/.env \
  /etc/nginx/sites-available/project0

# Store backup offsite
```

## 📈 Performance Tuning

### 1. Nginx Optimization

```nginx
# Add to nginx.conf
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    use epoll;
}

http {
    # Enable gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    
    # Keep alive
    keepalive_timeout 65;
    keepalive_requests 100;
}
```

### 2. Python Optimization

```python
# Use Gunicorn for production
pip install gunicorn

# Run with multiple workers
gunicorn project0:app -w 4 -k uvicorn.workers.UvicornWorker
```

### 3. System Limits

```bash
# Edit /etc/security/limits.conf
* soft nofile 65535
* hard nofile 65535
```

## 🆘 Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u project0 -n 50

# Check Ollama
ollama list
ps aux | grep ollama
```

### High memory usage

```bash
# Monitor resources
htop

# Check Ollama memory
ps aux | grep ollama

# Restart if needed
sudo systemctl restart project0
```

### Connection refused

```bash
# Check if service is running
sudo systemctl status project0

# Check port
sudo netstat -tlnp | grep 8000

# Check firewall
sudo ufw status
```

## 📞 Support

For issues and questions:
- Check logs: `sudo journalctl -u project0 -f`
- Test health: `curl http://localhost:8000/api/health`
- Monitor resources: `htop`

---

**Production deployment complete! 🎉**
