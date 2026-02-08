from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # This allows GitHub to talk to your tablet

@app.route('/data')
def get_data():
    return jsonify({"message": "Hello from your Samsung S8 Server!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
