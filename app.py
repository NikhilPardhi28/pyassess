from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json, os, uuid, hashlib
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'pytest_secret_2024_change_in_prod'

DATA_DIR       = os.path.join(os.path.dirname(__file__), 'data')
RESULTS_FILE   = os.path.join(DATA_DIR, 'results.json')
SESSIONS_FILE  = os.path.join(DATA_DIR, 'sessions.json')
QUESTIONS_FILE = os.path.join(DATA_DIR, 'questions.json')
CONFIG_FILE    = os.path.join(DATA_DIR, 'config.json')
USERS_FILE     = os.path.join(DATA_DIR, 'users.json')

ADMIN_USER        = 'admin'
DEFAULT_PASS_HASH = hashlib.sha256('Admin@PyTest2024'.encode()).hexdigest()

# ── preset portal users ──────────────────────────────────────────────────────
DEFAULT_USERS = {
    "nikhilrpardhi@gmail.com": {
        "name":      "Nikhil Pardhi",
        "email":     "nikhilrpardhi@gmail.com",
        "pass_hash": hashlib.sha256("test123".encode()).hexdigest()
    },
    "tanvichute75@gmail.com": {
        "name":      "Tanvi Chute",
        "email":     "tanvichute75@gmail.com",
        "pass_hash": hashlib.sha256("test123".encode()).hexdigest()
    }
}

# ── helpers ──────────────────────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def get_admin_pass_hash():
    cfg = load_json(CONFIG_FILE, {})
    return cfg.get('admin_pass_hash', DEFAULT_PASS_HASH)

def get_users():
    stored = load_json(USERS_FILE, {})
    merged = dict(DEFAULT_USERS)
    merged.update(stored)
    return merged

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return d

def user_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('user_logged_in'):
            return redirect(url_for('user_login'))
        return f(*a, **kw)
    return d

def check_window(s):
    now = datetime.now()
    ws, we = s.get('window_start',''), s.get('window_end','')
    if not ws or not we:
        return True, ''
    try:
        start = datetime.fromisoformat(ws)
        end   = datetime.fromisoformat(we)
        if now < start:
            return False, f"Your test window hasn't opened yet. It opens on {start.strftime('%d %b %Y at %I:%M %p')}."
        if now > end:
            return False, f"Your test window has expired. It closed on {end.strftime('%d %b %Y at %I:%M %p')}."
        return True, ''
    except Exception:
        return True, ''

# ════════════════════════════════════════════════════════════════════════════
# USER PORTAL ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET','POST'])
def user_login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        pwd   = request.form.get('password','')
        users = get_users()
        u = users.get(email)
        if u and hashlib.sha256(pwd.encode()).hexdigest() == u['pass_hash']:
            session['user_logged_in'] = True
            session['user_email']     = email
            session['user_name']      = u['name']
            return redirect(url_for('user_portal'))
        error = 'Invalid email or password'
    return render_template('user_login.html', error=error)

@app.route('/user-logout')
def user_logout():
    session.pop('user_logged_in', None)
    session.pop('user_email', None)
    session.pop('user_name', None)
    return redirect(url_for('user_login'))

@app.route('/portal')
@user_required
def user_portal():
    email    = session['user_email']
    sessions = load_json(SESSIONS_FILE, {})
    results  = load_json(RESULTS_FILE, {})
    # find existing sessions for this user
    my_sessions = {t: s for t, s in sessions.items() if s.get('user_email') == email}
    my_results  = {}
    for t, s in my_sessions.items():
        rid = s.get('result_id')
        if rid and rid in results:
            my_results[rid] = results[rid]
    return render_template('user_portal.html',
                           user_name=session['user_name'],
                           user_email=email,
                           my_sessions=my_sessions,
                           my_results=my_results)

@app.route('/portal/start-test', methods=['POST'])
@user_required
def user_start_test():
    email    = session['user_email']
    name     = session['user_name']
    sessions = load_json(SESSIONS_FILE, {})
    # check no active pending session
    for t, s in sessions.items():
        if s.get('user_email') == email and s.get('status') == 'pending':
            return jsonify({'token': t})
    # create new session immediately (no time window)
    token = str(uuid.uuid4())
    sessions[token] = {
        'name':         name,
        'email':        email,
        'user_email':   email,
        'created_at':   datetime.now().isoformat(),
        'window_start': '',
        'window_end':   '',
        'status':       'pending',
        'source':       'user_portal'
    }
    save_json(SESSIONS_FILE, sessions)
    return jsonify({'token': token})

# ════════════════════════════════════════════════════════════════════════════
# CANDIDATE / TEST ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test/<token>')
def test_page(token):
    sessions = load_json(SESSIONS_FILE, {})
    if token not in sessions:
        return render_template('error.html', msg="Invalid or expired test link.")
    s = sessions[token]
    if s.get('status') == 'completed':
        return render_template('error.html', msg="This test has already been completed.")
    if s.get('status') == 'ejected':
        return render_template('error.html', msg="You were removed from this test due to a proctoring violation.")
    allowed, msg = check_window(s)
    if not allowed:
        return render_template('error.html', msg=msg)
    return render_template('test.html', token=token,
                           candidate_name=s.get('name','Candidate'),
                           window_end_iso=s.get('window_end',''))

@app.route('/api/questions/<token>')
def get_questions(token):
    sessions = load_json(SESSIONS_FILE, {})
    if token not in sessions:
        return jsonify({'error': 'Invalid token'}), 403
    allowed, msg = check_window(sessions[token])
    if not allowed:
        return jsonify({'error': msg}), 403
    questions = load_json(QUESTIONS_FILE, [])
    safe = [{k:v for k,v in q.items() if k not in ('answer','level')} for q in questions]
    return jsonify(safe)

@app.route('/api/submit', methods=['POST'])
def submit_test():
    data    = request.json
    token   = data.get('token')
    answers = data.get('answers', {})
    events  = data.get('proctoring_events', [])
    ejected = data.get('ejected', False)

    sessions = load_json(SESSIONS_FILE, {})
    if token not in sessions:
        return jsonify({'error': 'Invalid token'}), 403

    questions = load_json(QUESTIONS_FILE, [])
    results   = load_json(RESULTS_FILE, {})

    score = 0; total_auto = 0; graded = {}; code_answers = {}
    for q in questions:
        qid = str(q['id'])
        if q['type'] == 'mcq':
            total_auto += 1
            user_ans = answers.get(qid,'').strip().upper()
            ok = user_ans == q['answer'].strip().upper()
            if ok: score += 1
            graded[qid] = {'user_answer': answers.get(qid,''), 'correct_answer': q['answer'],
                           'is_correct': ok, 'question': q['question'], 'level': q['level']}
        else:
            code_answers[qid] = {'question': q['question'], 'user_code': answers.get(qid,''),
                                 'admin_reviewed': False, 'admin_score': None, 'admin_note': ''}

    rid = str(uuid.uuid4())[:8]
    results[rid] = {
        'result_id': rid, 'token': token,
        'candidate_name':  sessions[token].get('name','Unknown'),
        'candidate_email': sessions[token].get('email',''),
        'submitted_at':    datetime.now().isoformat(),
        'ejected': ejected, 'proctoring_events': events,
        'mcq_score': score, 'mcq_total': total_auto,
        'mcq_percentage': round((score/total_auto*100) if total_auto else 0, 1),
        'graded_answers': graded, 'code_answers': code_answers,
        'final_score': None,
        'status': 'ejected' if ejected else 'completed',
        'source': sessions[token].get('source','admin')
    }
    save_json(RESULTS_FILE, results)
    sessions[token]['status']    = 'ejected' if ejected else 'completed'
    sessions[token]['result_id'] = rid
    save_json(SESSIONS_FILE, sessions)
    return jsonify({'success': True})

@app.route('/api/proctor-warning', methods=['POST'])
def proctor_warning():
    """Just logs a warning event, no eject."""
    data  = request.json
    token = data.get('token')
    sessions = load_json(SESSIONS_FILE, {})
    if token in sessions:
        if 'warning_count' not in sessions[token]:
            sessions[token]['warning_count'] = 0
        sessions[token]['warning_count'] += 1
        save_json(SESSIONS_FILE, sessions)
        return jsonify({'warning_count': sessions[token]['warning_count']})
    return jsonify({'warning_count': 0})

@app.route('/completed')
def completed():
    # detect if came from user portal
    came_from_portal = request.args.get('portal') == '1'
    return render_template('completed.html', portal=came_from_portal)

# ════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        u = request.form.get('username','')
        p = request.form.get('password','')
        if u == ADMIN_USER and hashlib.sha256(p.encode()).hexdigest() == get_admin_pass_hash():
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        error = 'Invalid credentials'
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    results  = load_json(RESULTS_FILE, {})
    sessions = load_json(SESSIONS_FILE, {})
    return render_template('admin_dashboard.html', results=results, sessions=sessions)

@app.route('/admin/change-password', methods=['POST'])
@admin_required
def change_password():
    data    = request.json
    current = data.get('current','')
    np      = data.get('new_pass','')
    confirm = data.get('confirm','')
    if hashlib.sha256(current.encode()).hexdigest() != get_admin_pass_hash():
        return jsonify({'error': 'Current password is incorrect'}), 400
    if len(np) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400
    if np != confirm:
        return jsonify({'error': 'Passwords do not match'}), 400
    cfg = load_json(CONFIG_FILE, {})
    cfg['admin_pass_hash'] = hashlib.sha256(np.encode()).hexdigest()
    save_json(CONFIG_FILE, cfg)
    return jsonify({'success': True})

@app.route('/admin/create-session', methods=['POST'])
@admin_required
def create_session():
    data  = request.json
    name  = data.get('name','').strip()
    email = data.get('email','').strip()
    ws    = data.get('window_start','').strip()
    we    = data.get('window_end','').strip()
    if not name or not email:
        return jsonify({'error': 'Name and email required'}), 400
    if ws and we:
        try:
            s2 = datetime.fromisoformat(ws); e2 = datetime.fromisoformat(we)
            if e2 <= s2: return jsonify({'error': 'End time must be after start time'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    token    = str(uuid.uuid4())
    sessions = load_json(SESSIONS_FILE, {})
    sessions[token] = {'name': name, 'email': email, 'created_at': datetime.now().isoformat(),
                       'window_start': ws, 'window_end': we, 'status': 'pending', 'source': 'admin'}
    save_json(SESSIONS_FILE, sessions)
    link = f"{request.host_url.rstrip('/')}/test/{token}"
    return jsonify({'token': token, 'link': link, 'name': name,
                    'window_start': ws, 'window_end': we})

@app.route('/admin/result/<rid>')
@admin_required
def view_result(rid):
    results = load_json(RESULTS_FILE, {})
    result  = results.get(rid)
    if not result:
        return render_template('error.html', msg='Result not found')
    return render_template('admin_result.html', result=result, result_id=rid)

@app.route('/admin/update-code-review', methods=['POST'])
@admin_required
def update_code_review():
    data = request.json
    rid  = data.get('result_id'); qid = data.get('question_id')
    score = data.get('score');    note = data.get('note','')
    results = load_json(RESULTS_FILE, {})
    if rid in results and qid in results[rid].get('code_answers',{}):
        results[rid]['code_answers'][qid].update(
            {'admin_score': score, 'admin_note': note, 'admin_reviewed': True})
        r = results[rid]
        cs = [v['admin_score'] for v in r['code_answers'].values() if v.get('admin_score') is not None]
        r['final_score'] = r['mcq_score'] + sum(cs)
        save_json(RESULTS_FILE, results)
        return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404

@app.route('/admin/delete-session/<token>', methods=['POST'])
@admin_required
def delete_session(token):
    sessions = load_json(SESSIONS_FILE, {})
    sessions.pop(token, None)
    save_json(SESSIONS_FILE, sessions)
    return jsonify({'success': True})

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True, port=5000)