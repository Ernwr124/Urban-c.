# Ollama Setup Guide for HR Agent

Complete guide to set up Ollama with gpt-oss:20b-cloud model for HR Agent.

## 📥 Installation

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### macOS
```bash
brew install ollama
```

### Windows
Download from: https://ollama.com/download

---

## 🚀 Quick Setup

### 1. Start Ollama Server
```bash
ollama serve
```

Leave this terminal open. Open a new terminal for next steps.

### 2. Pull the Model
```bash
ollama pull gpt-oss:20b-cloud
```

**Note**: This downloads ~12GB. May take 10-30 minutes depending on your internet speed.

### 3. Test the Model
```bash
ollama run gpt-oss:20b-cloud "Hello, how are you?"
```

If you get a response, Ollama is working!

### 4. Run HR Agent
```bash
python hr_platform.py
```

---

## ✅ Verification

### Check Ollama is Running
```bash
curl http://localhost:11434/api/tags
```

**Expected output**: JSON with list of installed models

### Check Model is Installed
```bash
ollama list
```

**Expected**: Should show `gpt-oss:20b-cloud` in the list

### Test API Connection
```bash
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-oss:20b-cloud",
    "prompt": "Say hello",
    "stream": false
  }'
```

**Expected**: JSON response with generated text

---

## 🔧 Configuration

### Default Settings
- **URL**: `http://localhost:11434/api/generate`
- **Model**: `gpt-oss:20b-cloud`
- **Port**: `11434`

### Custom Configuration
Create `.env` file:
```bash
OLLAMA_API_URL=http://your-server:11434/api/generate
```

---

## 🐛 Troubleshooting

### Error: "Connection refused"
**Problem**: Ollama server not running

**Solution**:
```bash
# Start Ollama server
ollama serve
```

### Error: "Model not found"
**Problem**: Model not downloaded

**Solution**:
```bash
# Pull the model
ollama pull gpt-oss:20b-cloud
```

### Error: "Out of memory"
**Problem**: Not enough RAM

**Requirements**:
- Minimum: 8GB RAM
- Recommended: 16GB+ RAM

**Solution**:
- Close other applications
- Or use smaller model: `ollama pull gpt-oss:7b-cloud`

### Slow Response
**Causes**:
1. **First request**: Model loading (60-90 seconds) - normal
2. **Always slow**: Hardware limitations
3. **CPU usage**: Model running on CPU instead of GPU

**Solutions**:
- Wait for first request (subsequent are faster)
- Upgrade hardware
- Enable GPU support (if available)

### Port Already in Use
**Problem**: Port 11434 is occupied

**Check what's using it**:
```bash
lsof -i :11434
```

**Solution**:
```bash
# Kill the process
kill -9 <PID>

# Or change Ollama port
OLLAMA_HOST=0.0.0.0:11435 ollama serve
```

Then update HR Agent `.env`:
```bash
OLLAMA_API_URL=http://localhost:11435/api/generate
```

---

## 🌐 Remote Ollama Server

### Setup Remote Access

**On server**:
```bash
# Allow external connections
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

**On HR Agent machine**:
Update `.env`:
```bash
OLLAMA_API_URL=http://server-ip:11434/api/generate
```

**Security**: Use VPN or reverse proxy (nginx) for production!

---

## 📊 Performance

### Hardware Requirements
- **Minimum**: 8GB RAM, 4 CPU cores
- **Recommended**: 16GB RAM, 8 CPU cores
- **Optimal**: 32GB RAM, GPU support

### Speed Expectations
- **First request**: 60-90 seconds (loading)
- **Subsequent**: 10-30 seconds
- **With GPU**: 5-15 seconds

### Model Sizes
- `gpt-oss:7b-cloud` - ~4GB (faster, less accurate)
- `gpt-oss:20b-cloud` - ~12GB (recommended, best accuracy)
- `gpt-oss:70b-cloud` - ~40GB (slowest, highest accuracy)

---

## 🔄 Running as Service

### Linux (systemd)

Create `/etc/systemd/system/ollama.service`:
```ini
[Unit]
Description=Ollama Service
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/usr/local/bin/ollama serve
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama
```

### macOS (launchd)

Create `~/Library/LaunchAgents/com.ollama.server.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ollama.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/ollama</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Load:
```bash
launchctl load ~/Library/LaunchAgents/com.ollama.server.plist
```

---

## 💾 Model Management

### List Installed Models
```bash
ollama list
```

### Remove Model (free space)
```bash
ollama rm gpt-oss:20b-cloud
```

### Update Model
```bash
ollama pull gpt-oss:20b-cloud
```

### Storage Location
- **Linux**: `~/.ollama/models/`
- **macOS**: `~/.ollama/models/`
- **Windows**: `%USERPROFILE%\.ollama\models\`

---

## 🔐 Security Best Practices

### Local Development
Default setup (localhost only) is secure.

### Production
1. **Use reverse proxy** (nginx)
2. **Enable HTTPS**
3. **Add authentication**
4. **Use firewall rules**
5. **VPN for remote access**

### Example nginx config:
```nginx
server {
    listen 443 ssl;
    server_name ollama.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:11434;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📚 Additional Resources

- **Official Docs**: https://ollama.com/docs
- **GitHub**: https://github.com/ollama/ollama
- **Models**: https://ollama.com/library
- **Community**: https://discord.gg/ollama

---

## ✅ Pre-flight Checklist

Before running HR Agent:

- [ ] Ollama installed
- [ ] `ollama serve` running
- [ ] `gpt-oss:20b-cloud` model pulled
- [ ] Model tested with `ollama run`
- [ ] API responding to curl test
- [ ] HR Agent dependencies installed
- [ ] Port 11434 accessible

---

**Ready to analyze resumes with AI!** 🤖
