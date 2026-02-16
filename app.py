from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit
from datetime import datetime

import os
# Get the directory where the script is located
base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(base_dir, "static"),
    static_url_path="/static"
)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

MESSAGES_FILE = "messages.txt"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>S8+ Message Hub</title>
    <style>
        body { font-family: sans-serif; padding: 20px; background: #121212; color: white; }
        input { padding: 10px; width: 250px; border-radius: 5px; border: none; }
        button { padding: 10px 20px; cursor: pointer; background: #007bff; color: white; border: none; border-radius:5px; }
        ul { background: #1e1e1e; margin: 5px 0; padding: 10px; border-radius: 4px; border-left: 4px solid #007bff; font-family: monospace; list-style: none; }
        .meta { color: #888; font-size: 0.85em; margin-right: 10px; }
    </style>
</head>
<body>
    <h1>S8+ Message Hub</h1>
    <input type="text" id="msgInput" placeholder="Type a message...">
    <button onclick="sendMessage()">Send</button>
    <button onclick="clearAll()" style="background: #dc3545;">Clear History</button>
    <h3>Message History</h3>
    <ul id="messageList"></ul>

    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        const socket = io();
        const list = document.getElementById('messageList');

        socket.on("load_history", (data) => {
            list.innerHTML = '';
            data.messages.forEach(msg => addMessageToList(msg));
        });

        socket.on("new_message", (data) => {
            addMessageToList(data.message);
        });

        socket.on("history_cleared", () => {
            list.innerHTML = '';
        });

        function addMessageToList(msg) {
            const li = document.createElement('li');
            if (msg.startsWith('[')) {
                const parts = msg.split(') ');
                const meta = parts[0] + ')';
                const text = parts[1] || "";
                li.innerHTML = `<span class="meta">${meta}</span> ${text}`;
            } else {
                li.textContent = msg;
            }
            list.appendChild(li);
            window.scrollTo(0, document.body.scrollHeight);
        }

        function sendMessage() {
            const input = document.getElementById('msgInput');
            if (input.value) {
                socket.emit("send_message", {message: input.value});
                input.value = '';
            }
        }

        function clearAll() {
            if (confirm("Delete all messages for everyone?")) {
                socket.emit("clear_history");
            }
        }
    </script>
</body>
</html>
"""

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
    socketio.run(app, host="0.0.0.0", port=5000)

