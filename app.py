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

@socketio.on("send_message")
def handle_message(data):
    msg = data.get("message")
    if msg:
        # Save to file for persistence
        with open(MESSAGES_FILE, "a") as f:
            f.write(msg + "\n")
        # Broadcast to EVERYONE connected
        emit("new_message", {"message": msg}, broadcast=True)

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

