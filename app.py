from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json, os, uuid, hashlib
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'pytest_secret_2024_change_in_prod'

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
RESULTS_FILE  = os.path.join(DATA_DIR, 'results.json')
SESSIONS_FILE = os.path.join(DATA_DIR, 'sessions.json')
QUESTIONS_FILE= os.path.join(DATA_DIR, 'questions.json')
CONFIG_FILE   = os.path.join(DATA_DIR, 'config.json')

ADMIN_USER        = 'admin'
DEFAULT_PASS_HASH = hashlib.sha256('Admin@PyTest2024'.encode()).hexdigest()

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
    config = load_json(CONFIG_FILE, {})
    return config.get('admin_pass_hash', DEFAULT_PASS_HASH)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def check_window(s):
    """Returns (allowed: bool, message: str)"""
    now = datetime.now()
    ws  = s.get('window_start')
    we  = s.get('window_end')
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

# ── CANDIDATE ROUTES ─────────────────────────────────────────────────────────
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
        return render_template('error.html', msg="You were ejected from this test due to a proctoring violation.")
    allowed, msg = check_window(s)
    if not allowed:
        return render_template('error.html', msg=msg)
    ws = s.get('window_start','')
    we = s.get('window_end','')
    window_end_iso = we  # pass to JS for countdown
    return render_template('test.html', token=token,
                           candidate_name=s.get('name','Candidate'),
                           window_end_iso=window_end_iso)

@app.route('/api/questions/<token>')
def get_questions(token):
    sessions = load_json(SESSIONS_FILE, {})
    if token not in sessions:
        return jsonify({'error': 'Invalid token'}), 403
    allowed, msg = check_window(sessions[token])
    if not allowed:
        return jsonify({'error': msg}), 403
    questions = load_json(QUESTIONS_FILE, [])
    safe_qs = [{k:v for k,v in q.items() if k != 'answer'} for q in questions]
    return jsonify(safe_qs)

@app.route('/api/submit', methods=['POST'])
def submit_test():
    data     = request.json
    token    = data.get('token')
    answers  = data.get('answers', {})
    events   = data.get('proctoring_events', [])
    ejected  = data.get('ejected', False)

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
            correct  = q['answer'].strip().upper()
            ok = user_ans == correct
            if ok: score += 1
            graded[qid] = {'user_answer': answers.get(qid,''), 'correct_answer': q['answer'],
                           'is_correct': ok, 'question': q['question'], 'level': q['level']}
        elif q['type'] == 'code':
            code_answers[qid] = {'question': q['question'], 'user_code': answers.get(qid,''),
                                 'admin_reviewed': False, 'admin_score': None, 'admin_note': ''}

    result_id = str(uuid.uuid4())[:8]
    results[result_id] = {
        'result_id': result_id, 'token': token,
        'candidate_name':  sessions[token].get('name','Unknown'),
        'candidate_email': sessions[token].get('email',''),
        'submitted_at': datetime.now().isoformat(),
        'ejected': ejected, 'proctoring_events': events,
        'mcq_score': score, 'mcq_total': total_auto,
        'mcq_percentage': round((score/total_auto*100) if total_auto else 0, 1),
        'graded_answers': graded, 'code_answers': code_answers,
        'final_score': None,
        'status': 'ejected' if ejected else 'completed'
    }
    save_json(RESULTS_FILE, results)
    sessions[token]['status']    = 'ejected' if ejected else 'completed'
    sessions[token]['result_id'] = result_id
    save_json(SESSIONS_FILE, sessions)
    return jsonify({'success': True})

@app.route('/api/eject', methods=['POST'])
def eject_candidate():
    data  = request.json
    token = data.get('token')
    sessions = load_json(SESSIONS_FILE, {})
    if token in sessions:
        sessions[token]['status']     = 'ejected'
        sessions[token]['ejected_at'] = datetime.now().isoformat()
        save_json(SESSIONS_FILE, sessions)
    return jsonify({'ejected': True})

@app.route('/completed')
def completed():
    return render_template('completed.html')

# ── ADMIN ROUTES ─────────────────────────────────────────────────────────────
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
    data        = request.json
    current     = data.get('current','')
    new_pass    = data.get('new_pass','')
    confirm     = data.get('confirm','')
    if hashlib.sha256(current.encode()).hexdigest() != get_admin_pass_hash():
        return jsonify({'error': 'Current password is incorrect'}), 400
    if len(new_pass) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400
    if new_pass != confirm:
        return jsonify({'error': 'Passwords do not match'}), 400
    config = load_json(CONFIG_FILE, {})
    config['admin_pass_hash'] = hashlib.sha256(new_pass.encode()).hexdigest()
    save_json(CONFIG_FILE, config)
    return jsonify({'success': True})

@app.route('/admin/create-session', methods=['POST'])
@admin_required
def create_session():
    data         = request.json
    name         = data.get('name','').strip()
    email        = data.get('email','').strip()
    window_start = data.get('window_start','').strip()
    window_end   = data.get('window_end','').strip()
    if not name or not email:
        return jsonify({'error': 'Name and email required'}), 400
    # validate window if provided
    if window_start and window_end:
        try:
            s = datetime.fromisoformat(window_start)
            e = datetime.fromisoformat(window_end)
            if e <= s:
                return jsonify({'error': 'End time must be after start time'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    token    = str(uuid.uuid4())
    sessions = load_json(SESSIONS_FILE, {})
    sessions[token] = {
        'name': name, 'email': email,
        'created_at':   datetime.now().isoformat(),
        'window_start': window_start,
        'window_end':   window_end,
        'status': 'pending'
    }
    save_json(SESSIONS_FILE, sessions)
    base_url = request.host_url.rstrip('/')
    link     = f"{base_url}/test/{token}"
    return jsonify({'token': token, 'link': link, 'name': name, 'email': email,
                    'window_start': window_start, 'window_end': window_end})

@app.route('/admin/result/<result_id>')
@admin_required
def view_result(result_id):
    results = load_json(RESULTS_FILE, {})
    result  = results.get(result_id)
    if not result:
        return render_template('error.html', msg='Result not found')
    return render_template('admin_result.html', result=result, result_id=result_id)

@app.route('/admin/update-code-review', methods=['POST'])
@admin_required
def update_code_review():
    data      = request.json
    result_id = data.get('result_id')
    qid       = data.get('question_id')
    score     = data.get('score')
    note      = data.get('note','')
    results   = load_json(RESULTS_FILE, {})
    if result_id in results and qid in results[result_id].get('code_answers',{}):
        results[result_id]['code_answers'][qid].update(
            {'admin_score': score, 'admin_note': note, 'admin_reviewed': True})
        r = results[result_id]
        code_scores = [v['admin_score'] for v in r['code_answers'].values() if v.get('admin_score') is not None]
        r['final_score'] = r['mcq_score'] + sum(code_scores)
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