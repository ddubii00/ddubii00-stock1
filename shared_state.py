import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from contextlib import closing

from flask import jsonify, redirect, render_template, request, session


STATE_LIMITS = {'holding_stocks': 30, 'favorite_stocks': 30, 'recent_searches': 10}


def install_shared_state(app):
    data_dir = Path(os.environ.get('STOCK_DATA_DIR', str(Path(app.root_path) / 'data')))
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_path = data_dir / 'session.key'
    try:
        with secret_path.open('x') as file:
            os.chmod(secret_path, 0o600)
            file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    app.secret_key = secret_path.read_text().strip()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_NAME='stock1_session',
                      SESSION_COOKIE_SECURE=os.environ.get('STOCK_COOKIE_SECURE') == '1')
    database = data_dir / 'state.sqlite3'
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')

    @app.before_request
    def require_login():
        password = os.environ.get('STOCK_APP_PASSWORD', '')
        if password and request.endpoint not in ('login', 'static') and not session.get('authenticated'):
            if request.path.startswith('/api/'):
                return jsonify(error='로그인이 필요합니다.'), 401
            return redirect('./login')
        if request.path == '/api/state' and request.method == 'PATCH':
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token', '').encode('utf-8'), session.get('csrf', secrets.token_hex(32)).encode('utf-8')):
                return jsonify(error='인증이 만료되었습니다. 새로고침해 주세요.'), 403

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = ''
        if request.method == 'POST':
            expected = os.environ.get('STOCK_APP_PASSWORD', '')
            if expected and hmac.compare_digest(request.form.get('password', '').encode('utf-8'), expected.encode('utf-8')):
                session.clear()
                session['authenticated'] = True
                return redirect('./')
            error = '비밀번호가 올바르지 않습니다.'
        return render_template('login.html', error=error)

    @app.route('/api/state', methods=['GET', 'PATCH'])
    def shared_state():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
            if request.method == 'PATCH':
                connection.execute('BEGIN IMMEDIATE')
                updates = request.get_json(silent=True) or {}
                if not isinstance(updates, dict) or any(key not in STATE_LIMITS for key in updates):
                    return jsonify(error='잘못된 저장 항목입니다.'), 400
                if any(not isinstance(value, list) for value in updates.values()):
                    return jsonify(error='목록 형식이 올바르지 않습니다.'), 400
                if len(json.dumps(updates)) > 100000:
                    return jsonify(error='저장 내용이 너무 큽니다.'), 400
                if request.headers.get('X-State-Import-If-Empty') == '1' and connection.execute('SELECT 1 FROM state LIMIT 1').fetchone():
                    updates = {}
                for key, value in updates.items():
                    connection.execute('INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                       (key, json.dumps(value[:STATE_LIMITS[key]], ensure_ascii=False)))
            rows = connection.execute('SELECT key, value FROM state').fetchall()
        return jsonify(state={key: json.loads(value) for key, value in rows}, initialized=bool(rows), csrf=session['csrf'])
