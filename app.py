import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit
from datetime import datetime 

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

MESSAGES_FILE = "messages.txt"

def load_history():
    if os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, "r") as f:
            return [line.strip() for line in f.readlines()]
    return []

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

from datetime import datetime
from flask import request

@socketio.on("send_message")
def handle_message(data):
    msg_text = data.get("message")
    if msg_text:
        # Create timestamp and get sender IP
        timestamp = datetime.now().strftime("%H:%M")
        sender_ip = request.remote_addr.split('.')[-1] # Just the last part (e.g., .71)
        
        full_message = f"[{timestamp}] (.{sender_ip}) {msg_text}"
        
        # Save to file
        with open(MESSAGES_FILE, "a") as f:
            f.write(full_message + "\n")
            
        # Broadcast the formatted message
        emit("new_message", {"message": full_message}, broadcast=True)

@socketio.on("clear_history")
def handle_clear():
    with open(MESSAGES_FILE, "w") as f:
        f.write("")
    emit("history_cleared", broadcast=True)

@socketio.on("connect")
def handle_connect():
    # Send existing messages only to the person who just joined
    history = load_history()
    emit("load_history", {"messages": history})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8000)

