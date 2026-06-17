from flask import Flask, request, jsonify, send_from_directory
import requests, os

app = Flask(__name__)
FRONTEND_DIR = '/home/shashank/xoyo/frontend'

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)

@app.route('/command', methods=['POST'])
def proxy_command():
    try:
        resp = requests.post('http://localhost:9000/command', json=request.json, timeout=30)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090)
