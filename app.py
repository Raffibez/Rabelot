from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from datetime import  datetime 

app = Flask(__name__)
CORS(app) # This allows GitHub to talk to your tablet

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/save', methods=['POST'])
def save_message():
    user_data = request.json
    msg = user_data.get("message", "No message")

    #Create a timestamp (e.g., 2026-02-09 01:55:01)
    timestamp = datetime.now().srftime("%Y-$m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}

    with open("messages.txt", "a") as f:
        f.write(msg + "\n")

    return jsonify({"status": "succes", "saved": entry})

@app.route('/messages', methods=['GET'])
def get_message():
    try:
        with open(messages.txt", "r") as f:
            messages = [line.strip() for line in f.readlines()]
        return jsonify{"messages": messages})
    except FileNotFoundError
        return jsonify{"messages": messages})

@app.route('/clear', methods=['POST'])
def clear_messages():
    with open(messages.txt", "w") as f:
        f.write("")
    return jsonify{"status": "File Cleared"})   

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
