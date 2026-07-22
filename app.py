import os
import csv
import io
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from flask_mail import Mail, Message
from dotenv import load_dotenv

from reports import generate_pdf_report, generate_csv_report
from recommendations import analyze_user_sessions

from database import db, User, Session, AlertEvent, Achievement, ACHIEVEMENT_DEFINITIONS, init_db

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'antigravity-drowsiness-secret-key-9988')

# Database configuration: Use PostgreSQL on Render, SQLite locally with absolute path
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres'):
    # Render PostgreSQL - fix for postgres:// vs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development - use absolute path in instance folder
    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    os.makedirs(instance_path, exist_ok=True)
    db_path = os.path.join(instance_path, 'drowsiness.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration for password reset
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@drowsinessdetector.com')

mail = Mail(app)

# Initialize DB
init_db(app)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- AUTHENTICATION ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not username or not email or not password:
            flash('Please fill out all fields.', 'error')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
            
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already registered.', 'error')
            return redirect(url_for('register'))
            
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Account created successfully! Please sign in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html', active_page='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))
            
    return render_template('login.html', active_page='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            token = user.generate_reset_token()
            reset_url = url_for('reset_password', token=token, _external=True)
            
            # Send email
            try:
                msg = Message(
                    'Password Reset Request - Drowsiness Prevention System',
                    recipients=[user.email]
                )
                msg.body = f'''
Hello {user.username},

You requested a password reset. Click the link below to reset your password:

{reset_url}

This link will expire in 1 hour.

If you did not request this, please ignore this email.

Best regards,
Drowsiness Prevention System
'''
                mail.send(msg)
                flash('Password reset link has been sent to your email.', 'success')
            except Exception as e:
                flash('Failed to send email. Please try again later.', 'error')
                print(f"Email error: {e}")
        else:
            # Don't reveal if email exists or not for security
            flash('If an account with that email exists, a reset link has been sent.', 'info')
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html', active_page='login')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset link. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not password or not confirm_password:
            flash('Please fill out all fields.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        # Validate password strength
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        if not any(c.isupper() for c in password):
            flash('Password must contain at least one uppercase letter.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        if not any(c.islower() for c in password):
            flash('Password must contain at least one lowercase letter.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        if not any(c.isdigit() for c in password):
            flash('Password must contain at least one number.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        # Update password
        user.set_password(password)
        user.clear_reset_token()
        
        flash('Password has been reset successfully. Please sign in with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token, active_page='login')

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# --- DASHBOARD & MONITOR ROUTES ---

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user
    
    # Calculate level statistics
    level = (user.points // 500) + 1
    level_progress = int(((user.points % 500) / 500.0) * 100)
    
    # Gather session counts
    total_sessions = len(user.sessions)
    total_duration_seconds = sum(s.duration_seconds for s in user.sessions)
    
    # Format total duration
    hours, remainder = divmod(total_duration_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        total_duration_formatted = f"{hours}h {minutes}m"
    elif minutes > 0:
        total_duration_formatted = f"{minutes}m {seconds}s"
    else:
        total_duration_formatted = f"{seconds}s"
        
    total_alerts = sum(s.alerts_count for s in user.sessions)
    avg_focus = sum(s.focus_score for s in user.sessions) / total_sessions if total_sessions > 0 else 100.0
    
    # Chart data (last 10 sessions chronologically)
    chart_sessions = Session.query.filter_by(user_id=user.id).order_by(Session.start_time.desc()).limit(10).all()
    chart_sessions.reverse() # chronologically ascending for the chart
    
    # Recent sessions list
    recent_sessions = Session.query.filter_by(user_id=user.id).order_by(Session.start_time.desc()).limit(20).all()
    
    # Achievements state loader
    unlocked_keys = {ach.achievement_key: ach.unlocked_at for ach in user.achievements}
    achievement_states = {}
    for key, val in ACHIEVEMENT_DEFINITIONS.items():
        unlocked = key in unlocked_keys
        achievement_states[key] = {
            'title': val['title'],
            'description': val['description'],
            'icon': val['icon'],
            'points_reward': val['points_reward'],
            'unlocked': unlocked,
            'unlocked_at': unlocked_keys[key] if unlocked else None
        }
    
    achievements_unlocked_count = len(unlocked_keys)
    
    insights = analyze_user_sessions(user.id)
    return render_template(
        'dashboard.html',
        active_page='dashboard',
        level=level,
        level_progress=level_progress,
        total_sessions=total_sessions,
        total_duration_formatted=total_duration_formatted,
        total_alerts=total_alerts,
        avg_focus=avg_focus,
        chart_sessions=chart_sessions,
        sessions=recent_sessions,
        achievement_states=achievement_states,
        achievements_unlocked_count=achievements_unlocked_count,
        insights=insights
    )

@app.route('/monitor')
@login_required
def monitor():
    return render_template('monitor.html', active_page='monitor')

# --- SESSION TIMELINE & DETAILS ---

@app.route('/session/<int:session_id>')
@login_required
def session_detail(session_id):
    session = Session.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        flash('Unauthorized access to session details.', 'error')
        return redirect(url_for('dashboard'))
        
    alerts = AlertEvent.query.filter_by(session_id=session.id).order_by(AlertEvent.timestamp.asc()).all()
    
    # Build chart timeline points based on incidents
    duration = session.duration_seconds
    start = session.start_time
    num_steps = 15
    step_duration = max(1, duration / num_steps)
    
    alert_offsets = []
    for alert in alerts:
        offset = (alert.timestamp - start).total_seconds()
        alert_offsets.append((offset, alert.severity_level))
        
    timeline_points = []
    for i in range(num_steps + 1):
        curr_offset = i * step_duration
        min_dist = float('inf')
        nearest_severity = None
        for offset, severity in alert_offsets:
            dist = abs(offset - curr_offset)
            if dist < min_dist:
                min_dist = dist
                nearest_severity = severity
                
        val = 100
        # If an alert is close to this timestamp offset
        if min_dist < max(10, step_duration / 1.3) and nearest_severity:
            val = 20 if nearest_severity == 'Critical' else 50
            
        time_str = (start + timedelta(seconds=curr_offset)).strftime('%H:%M:%S')
        timeline_points.append({'time': time_str, 'value': val})
        
    return render_template(
        'session_detail.html',
        session=session,
        alerts=alerts,
        timeline_points=timeline_points
    )

# --- WEB MONITORING REST APIS ---

@app.route('/api/session/start', methods=['POST'])
@login_required
def api_start_session():
    # Close any older active sessions if left open
    open_sessions = Session.query.filter_by(user_id=current_user.id, duration_seconds=0).all()
    for s in open_sessions:
        s.duration_seconds = 10  # assign dummy small duration
        db.session.add(s)
        
    new_session = Session(
        user_id=current_user.id,
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow(),
        duration_seconds=0,
        avg_alertness=100.0,
        yawns_count=0,
        blinks_count=0,
        nods_count=0,
        alerts_count=0,
        focus_score=100.0
    )
    db.session.add(new_session)
    db.session.commit()
    return jsonify({'session_id': new_session.id})

@app.route('/api/session/alert', methods=['POST'])
@login_required
def api_log_alert():
    data = request.get_json() or {}
    session_id = data.get('session_id')
    severity = data.get('severity_level', 'Warning')
    reason = data.get('trigger_reason', 'Drowsiness')
    
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
        
    # Verify ownership
    sess = Session.query.get(session_id)
    if not sess or sess.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    event = AlertEvent(
        session_id=session_id,
        timestamp=datetime.utcnow(),
        severity_level=severity,
        trigger_reason=reason
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({'status': 'logged'})

@app.route('/api/session/end', methods=['POST'])
@login_required
def api_end_session():
    data = request.get_json() or {}
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
        
    sess = Session.query.get(session_id)
    if not sess or sess.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    duration = int(data.get('duration_seconds', 0))
    avg_alert = float(data.get('avg_alertness', 100.0))
    yawns = int(data.get('yawns_count', 0))
    blinks = int(data.get('blinks_count', 0))
    nods = int(data.get('nods_count', 0))
    alerts = int(data.get('alerts_count', 0))
    focus = float(data.get('focus_score', 100.0))
    
    sess.end_time = datetime.utcnow()
    sess.duration_seconds = duration
    sess.avg_alertness = avg_alert
    sess.yawns_count = yawns
    sess.blinks_count = blinks
    sess.nods_count = nods
    sess.alerts_count = alerts
    sess.focus_score = focus
    
    db.session.add(sess)
    
    # --- GAME ENGINE ECONOMY ---
    # Rewards: Time reward (+2 XP/min) + Challenge resolution (+20 XP per alert)
    time_minutes = duration / 60.0
    points_gained = int(time_minutes * 2.0) + (alerts * 20)
    
    # Cap points gained positively
    if points_gained < 10 and duration > 30:
        points_gained = 10
        
    current_user.points += points_gained
    
    # Daily streak handler
    today = date.today()
    last_active = current_user.last_active_date
    
    if last_active is None:
        current_user.streak_days = 1
    else:
        delta = today - last_active
        if delta.days == 1:
            current_user.streak_days += 1
        elif delta.days > 1:
            current_user.streak_days = 1
            
    current_user.last_active_date = today
    db.session.add(current_user)
    
    # --- ACHIEVEMENT EVALUATION ---
    new_achievements = []
    unlocked_keys = {ach.achievement_key for ach in current_user.achievements}
    
    # Fetch user history stats for checks
    all_user_sessions = Session.query.filter_by(user_id=current_user.id).all()
    total_sessions_count = len(all_user_sessions)
    lifetime_alerts = sum(s.alerts_count for s in all_user_sessions)
    
    # Check 1: 🌱 Fresh Start
    if 'fresh_start' not in unlocked_keys and total_sessions_count >= 1:
        new_ach = Achievement(user_id=current_user.id, achievement_key='fresh_start')
        db.session.add(new_ach)
        current_user.points += ACHIEVEMENT_DEFINITIONS['fresh_start']['points_reward']
        new_achievements.append(ACHIEVEMENT_DEFINITIONS['fresh_start'])
        
    # Check 2: 🏆 Focus Champion
    if 'focus_champion' not in unlocked_keys:
        if duration >= 1800 and focus >= 90.0:
            new_ach = Achievement(user_id=current_user.id, achievement_key='focus_champion')
            db.session.add(new_ach)
            current_user.points += ACHIEVEMENT_DEFINITIONS['focus_champion']['points_reward']
            new_achievements.append(ACHIEVEMENT_DEFINITIONS['focus_champion'])
            
    # Check 3: 🧠 Iron Will (resolved 5 alerts)
    if 'iron_will' not in unlocked_keys:
        if lifetime_alerts >= 5:
            new_ach = Achievement(user_id=current_user.id, achievement_key='iron_will')
            db.session.add(new_ach)
            current_user.points += ACHIEVEMENT_DEFINITIONS['iron_will']['points_reward']
            new_achievements.append(ACHIEVEMENT_DEFINITIONS['iron_will'])
            
    # Check 4: ⚡ Ninja Reflexes (resolved at least one critical challenge)
    if 'ninja_reflexes' not in unlocked_keys:
        if alerts >= 1:
            new_ach = Achievement(user_id=current_user.id, achievement_key='ninja_reflexes')
            db.session.add(new_ach)
            current_user.points += ACHIEVEMENT_DEFINITIONS['ninja_reflexes']['points_reward']
            new_achievements.append(ACHIEVEMENT_DEFINITIONS['ninja_reflexes'])
            
    # Check 5: 📅 Habit Builder (streak >= 3 days)
    if 'habit_builder' not in unlocked_keys:
        if current_user.streak_days >= 3:
            new_ach = Achievement(user_id=current_user.id, achievement_key='habit_builder')
            db.session.add(new_ach)
            current_user.points += ACHIEVEMENT_DEFINITIONS['habit_builder']['points_reward']
            new_achievements.append(ACHIEVEMENT_DEFINITIONS['habit_builder'])
            
    # Check 6: 🛡️ Bulletproof Focus (session >= 15 min with 0 alerts)
    if 'bulletproof_focus' not in unlocked_keys:
        if duration >= 900 and alerts == 0:
            new_ach = Achievement(user_id=current_user.id, achievement_key='bulletproof_focus')
            db.session.add(new_ach)
            current_user.points += ACHIEVEMENT_DEFINITIONS['bulletproof_focus']['points_reward']
            new_achievements.append(ACHIEVEMENT_DEFINITIONS['bulletproof_focus'])
            
    db.session.commit()
    
    return jsonify({
        'success': True,
        'points_earned': points_gained,
        'new_achievements': new_achievements
    })

# --- REPORTS EXPORTS (CSV & PDF) ---

@app.route('/session/<int:session_id>/report/csv')
@login_required
def export_csv(session_id):
    sess = Session.query.get_or_404(session_id)
    if sess.user_id != current_user.id:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
        
    alerts = AlertEvent.query.filter_by(session_id=sess.id).order_by(AlertEvent.timestamp.asc()).all()
    
    csv_content = generate_csv_report(sess, current_user, alerts)
    output = make_response(csv_content)
    output.headers["Content-Disposition"] = f"attachment; filename=session_report_{sess.id}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/session/<int:session_id>/report/pdf')
@login_required
def export_pdf(session_id):
    sess = Session.query.get_or_404(session_id)
    if sess.user_id != current_user.id:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('dashboard'))
        
    alerts = AlertEvent.query.filter_by(session_id=sess.id).order_by(AlertEvent.timestamp.asc()).all()
    
    pdf_buffer = generate_pdf_report(sess, current_user, alerts)
    output = make_response(pdf_buffer.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=session_report_{sess.id}.pdf"
    output.headers["Content-type"] = "application/pdf"
    return output

# Helper to generate CSV and PDF responses
from flask import make_response

if __name__ == '__main__':
    # Build a default test account if needed
    with app.app_context():
        if User.query.filter_by(username='developer').first() is None:
            dev = User(username='developer', email='developer@antigravity.alert')
            dev.set_password('developer123')
            db.session.add(dev)
            db.session.commit()
            print("Default developer user initialized: developer / developer123")

    port = int(os.environ.get('PORT', 80))
    app.run(host="0.0.0.0", debug=True, port=port)
