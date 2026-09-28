#!/usr/bin/env python3
"""
MeowTool Web - Replit Edition
Auto-send results to Discord webhook
"""

import os
import sys
import subprocess
import json
import requests
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ═══════════════════════════════════════════════════════════
# KONFIGURASI DETEKSI REPLIT
# ═══════════════════════════════════════════════════════════

IS_REPLIT = os.environ.get('REPL_ID') is not None
REPL_URL = os.environ.get('REPL_URL', '')  # Set di Secrets

if IS_REPLIT:
    # Replit workdir
    BASE_DIR = f"/home/runner/{os.environ.get('REPL_SLUG', 'meowtool-web')}"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folder paths
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
RESULTS_FOLDER = os.path.join(BASE_DIR, 'results')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# SECRETS - Ambil dari Replit Secrets
# ═══════════════════════════════════════════════════════════

DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK', 'https://discord.com/api/webhooks/1554229527276691517/5Hqw5P5wb3a2Hy-Gof7oa9JUvnzDRWiy3djpvf4azfpUZRW0TFGBXYK6dRLy8IL-RrM8')
WEB_PASSWORD = os.environ.get('WEB_PASSWORD', 'astasuratata')  # GANTI!

# Path MeowTool (clone dari repo)
MEOWTOOL_PATH = os.path.join(BASE_DIR, 'MeowTool.py')

# Simpan proses berjalan
running_processes = {}

# ═══════════════════════════════════════════════════════════
# KEEP ALIVE - Anti Sleep Replit
# ═══════════════════════════════════════════════════════════

def keep_alive():
    """Ping diri sendiri agar Replit tidak sleep"""
    if not IS_REPLIT or not REPL_URL:
        return
    
    print(f"[KeepAlive] Starting ping to {REPL_URL}")
    while True:
        try:
            time.sleep(300)  # Ping setiap 5 menit
            url = f"{REPL_URL.rstrip('/')}/api/status"
            response = requests.get(url, timeout=10)
            print(f"[KeepAlive] Ping status: {response.status_code}")
        except Exception as e:
            print(f"[KeepAlive] Ping failed: {e}")

# Start keep-alive thread
if IS_REPLIT:
    threading.Thread(target=keep_alive, daemon=True).start()

# ═══════════════════════════════════════════════════════════
# DISCORD FUNCTIONS
# ═══════════════════════════════════════════════════════════

def send_to_discord(content=None, file_path=None, action_name="Unknown"):
    """Kirim pesan/file ke Discord webhook"""
    if not DISCORD_WEBHOOK:
        return False
    
    try:
        data = {
            "username": "MeowTool Bot",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/616/616408.png",
            "embeds": [{
                "title": f"🐱 MeowTool - {action_name}",
                "color": 0x00ff00 if file_path else 0xffaa00,
                "timestamp": datetime.utcnow().isoformat(),
                "fields": []
            }]
        }
        
        if content:
            if len(content) > 1000:
                content = content[:1000] + "\n... (truncated)"
            data["embeds"][0]["fields"].append({
                "name": "Output",
                "value": f"```\n{content}\n```",
                "inline": False
            })
        
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            data["embeds"][0]["fields"].append({
                "name": "File",
                "value": f"📎 `{os.path.basename(file_path)}` ({file_size/1024:.1f} KB)",
                "inline": False
            })
            
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f)}
                response = requests.post(DISCORD_WEBHOOK, json=data, files=files, timeout=30)
        else:
            response = requests.post(DISCORD_WEBHOOK, json=data, timeout=30)
        
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"Discord error: {e}")
        return False

def send_simple_message(message):
    """Kirim pesan teks sederhana"""
    if not DISCORD_WEBHOOK:
        return
    
    try:
        requests.post(DISCORD_WEBHOOK, json={
            "username": "MeowTool Bot",
            "content": message
        }, timeout=10)
    except:
        pass

# ═══════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════

@app.route('/')
def index():
    if 'auth' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', 
                         webhook_configured=bool(DISCORD_WEBHOOK),
                         is_replit=IS_REPLIT)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == WEB_PASSWORD:
            session['auth'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Password salah!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('auth', None)
    return redirect(url_for('login'))

@app.route('/api/status')
def status():
    """Endpoint untuk keep-alive ping"""
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now().isoformat(),
        'running_processes': len(running_processes),
        'is_replit': IS_REPLIT
    })

@app.route('/api/run', methods=['POST'])
def run_tool():
    if 'auth' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    action = data.get('action')
    input_file = data.get('input_file')
    
    allowed_actions = {
        'check': 'Check Cookies',
        'sort': 'Sort Cookies',
        'refresh': 'Refresh Cookies',
        'proxy': 'Check Proxy'
    }
    
    if action not in allowed_actions:
        return jsonify({'error': 'Action tidak valid'}), 400
    
    # Build command
    cmd = [sys.executable, MEOWTOOL_PATH, action]
    if input_file:
        cmd.extend(['-i', os.path.join(UPLOAD_FOLDER, input_file)])
    
    # Notifikasi start
    send_simple_message(f"🚀 **Started**: {allowed_actions[action]} at {datetime.now().strftime('%H:%M:%S')}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=BASE_DIR
        )
        
        pid = process.pid
        running_processes[pid] = {
            'process': process,
            'action': action,
            'start_time': datetime.now()
        }
        
        try:
            stdout, stderr = process.communicate(timeout=600)
            del running_processes[pid]
            
            # Cari file hasil terbaru
            result_files = []
            if os.path.exists(RESULTS_FOLDER):
                result_files = [
                    os.path.join(RESULTS_FOLDER, f)
                    for f in os.listdir(RESULTS_FOLDER)
                    if os.path.isfile(os.path.join(RESULTS_FOLDER, f))
                ]
                result_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            # Kirim ke Discord
            discord_sent = False
            if result_files:
                for rf in result_files[:3]:
                    discord_sent = send_to_discord(
                        content=stdout[-500:] if stdout else None,
                        file_path=rf,
                        action_name=allowed_actions[action]
                    )
            else:
                discord_sent = send_to_discord(
                    content=stdout or stderr,
                    action_name=allowed_actions[action]
                )
            
            return jsonify({
                'success': True,
                'stdout': stdout,
                'stderr': stderr,
                'discord_sent': discord_sent,
                'result_files': [os.path.basename(f) for f in result_files[:3]]
            })
            
        except subprocess.TimeoutExpired:
            process.kill()
            del running_processes[pid]
            send_simple_message(f"⏱️ **Timeout**: {allowed_actions[action]} dihentikan")
            return jsonify({'error': 'Timeout'}), 408
            
    except Exception as e:
        send_simple_message(f"❌ **Error**: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'auth' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No filename'}), 400
    
    safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._-")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{safe_filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    send_simple_message(f"📤 **Upload**: `{safe_filename}` ({os.path.getsize(filepath)/1024:.1f} KB)")
    
    return jsonify({
        'success': True,
        'filename': filename,
        'original_name': file.filename
    })

@app.route('/api/files')
def list_files():
    if 'auth' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    files = []
    for folder, label in [(UPLOAD_FOLDER, 'upload'), (RESULTS_FOLDER, 'result')]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp):
                    files.append({
                        'name': f,
                        'folder': label,
                        'size': os.path.getsize(fp),
                        'modified': datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M:%S')
                    })
    
    return jsonify({'files': sorted(files, key=lambda x: x['modified'], reverse=True)})

@app.route('/api/test-webhook', methods=['POST'])
def test_webhook():
    if 'auth' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    success = send_to_discord(
        content="✅ Webhook berhasil dikonfigurasi!\nMeowTool siap digunakan.",
        action_name="Test Connection"
    )
    
    return jsonify({'success': success})

# ═══════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🐱 MeowTool Web starting...")
    print(f"📁 Base dir: {BASE_DIR}")
    print(f"📁 Upload: {UPLOAD_FOLDER}")
    print(f"📁 Results: {RESULTS_FOLDER}")
    print(f"🔗 Discord: {'✅' if DISCORD_WEBHOOK else '❌ Not set'}")
    print(f"🌐 Replit: {'✅' if IS_REPLIT else '❌'}")
    
    app.run(host='0.0.0.0', port=port, threaded=True)
