import os
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
MESSAGE_FILE = "message.txt"

# Ensure the messages file exists
if not os.path.exists(MESSAGE_FILE):
    with open(MESSAGE_FILE, "w") as f:
        f.write("")

# Put your Corrected HTML Template here
HTML_TEMPLATE = """
[Paste the Corrected HTML/JS from my previous response here]
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/messages", methods=["GET"])
def get_messages():
    with open(MESSAGES_FILE, "r") as f:
        lines = f.readlines()
    return jsonify({"messages": [line.strip() for line in lines]})

@app.route('/save', methods=['POST'])
def save_message():
    data = request.json
    message = data.get("message")
    if message:
        with open(MESSAGES_FILE, "a") as f:
            f.write(message + "\n")
        return jsonify({"status": "success"}), 201
    return jsonify({"status": "error"}), 400

@app.route('/clear', methods=['POST'])
def clear_messages():
    with open(MESSAGE_FILE, "w") as f:
        f.write("")
    return jsonify{"status": "cleared"}), 200   

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
