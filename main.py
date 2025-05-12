!pip install python-telegram-bot==20.3 flask flask-socketio requests pyngrok nest-asyncio python-multipart

import logging
import asyncio
import nest_asyncio
import os
from io import BytesIO
nest_asyncio.apply()
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Forbidden
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import threading
import random
import string
import time
from datetime import datetime
from pyngrok import ngrok
from werkzeug.utils import secure_filename

# Disable warnings
import warnings
warnings.filterwarnings("ignore")

# Configuration
TOKEN = "7255116298:AAHTBHc7IfDtO3toHLtdXCkB-SvzEkD5Z8E"
PORT = 5000
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov'}

# Initialize ngrok
ngrok.set_auth_token("2wTVvc39faTOlQRNxX0Zf8J9LMn_33xMvDzPjMEXZRjcCBvXF")
tunnel = ngrok.connect(PORT, "http")
web_url = tunnel.public_url
print(f"🌍 Web Interface: {web_url}")

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app, async_mode='threading')

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Message storage
messages = []
users = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%I:%M %p')

async def send_to_telegram(chat_id, text=None, file_path=None, file_type=None, reply_to=None):
    application = Application.builder().token(TOKEN).build()
    
    try:
        if file_path and file_type:
            with open(file_path, 'rb') as file:
                if file_type == 'photo':
                    await application.bot.send_photo(chat_id=chat_id, photo=InputFile(file), caption=text, reply_to_message_id=reply_to)
                elif file_type == 'video':
                    await application.bot.send_video(chat_id=chat_id, video=InputFile(file), caption=text, reply_to_message_id=reply_to)
        else:
            await application.bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to)
    except Forbidden:
        print(f"Bot was blocked by user {chat_id}")
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            user = update.effective_user
            users[user.id] = {'name': user.full_name, 'chat_id': update.message.chat_id}
            await update.message.reply_text(f'Messages will appear at: {web_url}')
    except Exception as e:
        print(f"Error in start handler: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message:
            return
            
        user = update.effective_user
        chat_id = update.message.chat_id
        
        # Store user info if not already stored
        if user.id not in users:
            users[user.id] = {'name': user.full_name, 'chat_id': chat_id}
        
        msg_data = {
            'id': update.message.message_id,
            'user_id': user.id,
            'name': user.full_name,
            'text': update.message.text or '',
            'time': format_time(update.message.date.timestamp()),
            'is_reply': False,
            'media': None,
            'media_type': None
        }
        
        # Handle media
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            file_bytes = BytesIO(await file.download_as_bytearray())
            filename = f"{int(time.time())}_{user.id}.jpg"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(file_bytes.getbuffer())
            msg_data['media'] = filename
            msg_data['media_type'] = 'photo'
        elif update.message.video:
            file = await update.message.video.get_file()
            file_bytes = BytesIO(await file.download_as_bytearray())
            filename = f"{int(time.time())}_{user.id}.mp4"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(file_bytes.getbuffer())
            msg_data['media'] = filename
            msg_data['media_type'] = 'video'
        
        if update.message.reply_to_message:
            msg_data.update({
                'is_reply': True,
                'reply_to_id': update.message.reply_to_message.message_id,
                'reply_to_text': update.message.reply_to_message.text or ''
            })
        
        messages.append(msg_data)
        socketio.emit('new_message', msg_data)
        
        if not (update.message.photo or update.message.video):
            await update.message.reply_text("✓ Sent")
    except Exception as e:
        print(f"Error in message handler: {e}")

# Web Interface
@app.route('/')
def index():
    return render_template('index.html', messages=messages, web_url=web_url)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/send', methods=['POST'])
def send_message():
    try:
        text = request.form.get('text', '')
        reply_to = request.form.get('reply_to', None)
        file = request.files.get('file')
        
        msg = {
            'id': int(time.time()*1000),
            'user_id': 'web',
            'name': 'You',
            'text': text,
            'time': format_time(time.time()),
            'is_reply': False,
            'media': None,
            'media_type': None
        }
        
        if reply_to:
            msg.update({
                'is_reply': True,
                'reply_to_id': int(reply_to),
                'reply_to_text': next((m['text'] for m in messages if m['id'] == int(reply_to)), "")
            })
        
        # Handle file upload
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{int(time.time())}_web_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            file_type = 'photo' if file.filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'} else 'video'
            msg['media'] = filename
            msg['media_type'] = file_type
            
            # Send to Telegram
            for user_id, user_data in users.items():
                asyncio.run(send_to_telegram(
                    user_data['chat_id'],
                    text=text,
                    file_path=filepath,
                    file_type=file_type,
                    reply_to=reply_to
                ))
        else:
            # Send text to Telegram
            for user_id, user_data in users.items():
                asyncio.run(send_to_telegram(
                    user_data['chat_id'],
                    text=text,
                    reply_to=reply_to
                ))
        
        messages.append(msg)
        socketio.emit('new_message', msg)
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Error in send_message: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# HTML Template with improved UI
html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Web Interface</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --primary-color: #0088cc;
            --secondary-color: #f0f2f5;
            --text-color: #333;
            --light-text: #666;
            --border-color: #ddd;
            --message-bg: white;
            --reply-bg: #f9f9f9;
            --input-bg: white;
            --button-bg: #0088cc;
            --button-hover: #0077bb;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }
        
        body {
            background-color: var(--secondary-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 0;
            margin: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background-color: var(--primary-color);
            color: white;
            padding: 15px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .message-container {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            padding-bottom: 70px;
        }
        
        .message {
            background-color: var(--message-bg);
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
            position: relative;
            transition: transform 0.3s, background-color 0.3s;
            touch-action: pan-y;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
            max-width: 80%;
            word-wrap: break-word;
        }
        
        .message.reply {
            border-left: 4px solid var(--primary-color);
        }
        
        .message.left {
            align-self: flex-start;
            margin-right: auto;
        }
        
        .message.right {
            align-self: flex-end;
            margin-left: auto;
            background-color: #dcf8c6;
        }
        
        .message.highlight {
            background-color: rgba(0, 136, 204, 0.1);
        }
        
        .reply-preview {
            font-size: 0.8em;
            color: var(--light-text);
            border-left: 2px solid var(--border-color);
            padding-left: 8px;
            margin-bottom: 8px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            background-color: var(--reply-bg);
            padding: 6px;
            border-radius: 4px;
        }
        
        .name {
            font-weight: bold;
            color: var(--primary-color);
            margin-bottom: 4px;
            font-size: 0.9em;
        }
        
        .time {
            font-size: 0.7em;
            color: var(--light-text);
            float: right;
            margin-left: 10px;
        }
        
        .text {
            margin-bottom: 4px;
        }
        
        .media {
            max-width: 100%;
            border-radius: 8px;
            margin-top: 8px;
            display: block;
        }
        
        .video-container {
            position: relative;
            padding-bottom: 56.25%; /* 16:9 */
            height: 0;
            overflow: hidden;
            margin-top: 8px;
            border-radius: 8px;
        }
        
        .video-container video {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .input-area {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 10px;
            background-color: var(--input-bg);
            box-shadow: 0 -2px 5px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .input-wrapper {
            flex: 1;
            display: flex;
            align-items: center;
            background-color: var(--input-bg);
            border-radius: 20px;
            padding: 5px 15px;
            border: 1px solid var(--border-color);
        }
        
        #message-input {
            flex: 1;
            border: none;
            outline: none;
            padding: 8px;
            background: transparent;
            resize: none;
            max-height: 100px;
        }
        
        #file-input {
            display: none;
        }
        
        .file-btn, .send-btn {
            background: none;
            border: none;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            transition: background-color 0.2s;
        }
        
        .file-btn:hover, .send-btn:hover {
            background-color: rgba(0, 0, 0, 0.1);
        }
        
        .send-btn {
            background-color: var(--button-bg);
            color: white;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
        }
        
        .send-btn:hover {
            background-color: var(--button-hover);
        }
        
        .cancel-reply {
            position: absolute;
            top: 5px;
            right: 5px;
            background: none;
            border: none;
            color: var(--light-text);
            cursor: pointer;
            font-size: 0.8em;
        }
        
        .reply-indicator {
            background-color: var(--reply-bg);
            padding: 8px;
            border-radius: 8px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .reply-text {
            font-size: 0.8em;
            color: var(--light-text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex: 1;
        }
        
        @media (max-width: 600px) {
            .message {
                max-width: 90%;
            }
            
            .input-area {
                padding: 8px;
            }
            
            .input-wrapper {
                padding: 5px 10px;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h2>Telegram Web Interface</h2>
    </div>
    
    <div class="message-container" id="messages">
        {% for msg in messages %}
        <div class="message {% if msg.is_reply %}reply{% endif %} {% if msg.user_id == 'web' %}right{% else %}left{% endif %}" 
             id="msg-{{ msg.id }}" 
             data-id="{{ msg.id }}">
            {% if msg.is_reply %}
            <div class="reply-preview">Replying: {{ msg.reply_to_text }}</div>
            {% endif %}
            <span class="name">{{ msg.name }}</span>
            <span class="time">{{ msg.time }}</span>
            <div class="text">{{ msg.text }}</div>
            {% if msg.media %}
                {% if msg.media_type == 'photo' %}
                <img src="/uploads/{{ msg.media }}" class="media" alt="Photo">
                {% elif msg.media_type == 'video' %}
                <div class="video-container">
                    <video controls class="media">
                        <source src="/uploads/{{ msg.media }}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                </div>
                {% endif %}
            {% endif %}
        </div>
        {% endfor %}
    </div>
    
    <div class="input-area">
        <input type="file" id="file-input" accept="image/*,video/*">
        <button class="file-btn" id="file-btn" title="Attach file">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
            </svg>
        </button>
        
        <div class="input-wrapper">
            <div id="reply-indicator" class="reply-indicator" style="display: none;">
                <div class="reply-text">Replying to: <span id="reply-preview-text"></span></div>
                <button class="cancel-reply" id="cancel-reply">✕</button>
            </div>
            <textarea id="message-input" placeholder="Type a message..." rows="1"></textarea>
        </div>
        
        <button class="send-btn" id="send-btn" title="Send">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
        </button>
    </div>

    <script>
        const socket = io();
        let activeReply = null;
        let startX = null;
        let isSwiping = false;
        
        // File input handling
        document.getElementById('file-btn').addEventListener('click', () => {
            document.getElementById('file-input').click();
        });
        
        document.getElementById('file-input').addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                sendMessage(e.target.files[0]);
                e.target.value = ''; // Reset file input
            }
        });
        
        // Swipe to reply
        document.addEventListener('touchstart', (e) => {
            if (e.target.closest('.message')) {
                const message = e.target.closest('.message');
                startX = e.touches[0].clientX;
                isSwiping = true;
                
                // Highlight the message being swiped
                message.classList.add('highlight');
            }
        });
        
        document.addEventListener('touchmove', (e) => {
            if (!isSwiping || startX === null) return;
            
            const message = e.target.closest('.message');
            if (!message) return;
            
            const x = e.touches[0].clientX;
            const diff = startX - x;
            
            if (diff > 50) { // Swipe right threshold
                message.style.transform = 'translateX(20px)';
            } else if (diff < -50) { // Swipe left to cancel
                message.style.transform = 'translateX(0)';
                message.classList.remove('highlight');
                isSwiping = false;
            }
        });
        
        document.addEventListener('touchend', (e) => {
            if (!isSwiping || startX === null) return;
            
            const message = e.target.closest('.message');
            if (!message) return;
            
            const x = e.changedTouches[0].clientX;
            const diff = startX - x;
            
            if (diff > 50) { // Swipe right to reply
                activeReply = message.dataset.id;
                document.getElementById('reply-indicator').style.display = 'flex';
                document.getElementById('reply-preview-text').textContent = 
                    message.querySelector('.text').textContent || 'media message';
                
                // Scroll to input
                document.querySelector('.input-area').scrollIntoView({ behavior: 'smooth' });
            }
            
            // Reset swipe state
            message.style.transform = '';
            message.classList.remove('highlight');
            startX = null;
            isSwiping = false;
        });
        
        // Cancel reply
        document.getElementById('cancel-reply').addEventListener('click', () => {
            activeReply = null;
            document.getElementById('reply-indicator').style.display = 'none';
        });
        
        // Send message
        document.getElementById('send-btn').addEventListener('click', () => {
            sendMessage();
        });
        
        // Auto-resize textarea
        document.getElementById('message-input').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
        
        function sendMessage(file = null) {
            const input = document.getElementById('message-input');
            const text = input.value.trim();
            
            if (text || file) {
                const formData = new FormData();
                if (text) formData.append('text', text);
                if (file) formData.append('file', file);
                if (activeReply) formData.append('reply_to', activeReply);
                
                fetch('/send', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'ok') {
                        input.value = '';
                        input.style.height = 'auto';
                        activeReply = null;
                        document.getElementById('reply-indicator').style.display = 'none';
                    }
                })
                .catch(error => console.error('Error:', error));
            }
        }
        
        // New message handler
        socket.on('new_message', (msg) => {
            const messagesDiv = document.getElementById('messages');
            
            let replyHtml = '';
            if (msg.is_reply) {
                replyHtml = `<div class="reply-preview">Replying: ${msg.reply_to_text || 'media message'}</div>`;
            }
            
            let mediaHtml = '';
            if (msg.media) {
                if (msg.media_type === 'photo') {
                    mediaHtml = `<img src="/uploads/${msg.media}" class="media" alt="Photo">`;
                } else if (msg.media_type === 'video') {
                    mediaHtml = `
                        <div class="video-container">
                            <video controls class="media">
                                <source src="/uploads/${msg.media}" type="video/mp4">
                                Your browser does not support the video tag.
                            </video>
                        </div>
                    `;
                }
            }
            
            const messageClass = msg.user_id === 'web' ? 'right' : 'left';
            const messageHtml = `
                <div class="message ${msg.is_reply ? 'reply' : ''} ${messageClass}" 
                     id="msg-${msg.id}" 
                     data-id="${msg.id}">
                    ${replyHtml}
                    <span class="name">${msg.name}</span>
                    <span class="time">${msg.time}</span>
                    <div class="text">${msg.text}</div>
                    ${mediaHtml}
                </div>
            `;
            
            messagesDiv.insertAdjacentHTML('beforeend', messageHtml);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        });
    </script>
</body>
</html>
"""

# Save template
from pathlib import Path
Path("templates").mkdir(exist_ok=True)
with open("templates/index.html", "w") as f:
    f.write(html_template)

# Run Flask in a separate thread
def run_flask():
    socketio.run(app, host='0.0.0.0', port=PORT, allow_unsafe_werkzeug=True)

flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Run Telegram bot
async def run_bot():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    await application.run_polling()

# Start the bot
loop = asyncio.get_event_loop()
loop.run_until_complete(run_bot())
