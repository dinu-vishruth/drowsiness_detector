import os
import secrets
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    points = db.Column(db.Integer, default=0)
    streak_days = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Password reset fields
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    sessions = db.relationship('Session', backref='user', lazy=True, cascade='all, delete-orphan')
    achievements = db.relationship('Achievement', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_reset_token(self):
        """Generate a secure password reset token valid for 1 hour."""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        return self.reset_token
    
    def verify_reset_token(self, token):
        """Verify if the reset token is valid and not expired."""
        if not self.reset_token or not self.reset_token_expires:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        return secrets.compare_digest(self.reset_token, token)
    
    def clear_reset_token(self):
        """Clear the reset token after password change."""
        self.reset_token = None
        self.reset_token_expires = None
        db.session.commit()

class Session(db.Model):
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration_seconds = db.Column(db.Integer, default=0)
    avg_alertness = db.Column(db.Float, default=100.0)
    yawns_count = db.Column(db.Integer, default=0)
    blinks_count = db.Column(db.Integer, default=0)
    nods_count = db.Column(db.Integer, default=0)
    alerts_count = db.Column(db.Integer, default=0)
    focus_score = db.Column(db.Float, default=100.0)
    
    # Relationships
    alert_events = db.relationship('AlertEvent', backref='session', lazy=True, cascade='all, delete-orphan')

    @property
    def formatted_duration(self):
        mins, secs = divmod(self.duration_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins}m {secs}s"
        elif mins > 0:
            return f"{mins}m {secs}s"
        return f"{secs}s"

class AlertEvent(db.Model):
    __tablename__ = 'alert_events'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    severity_level = db.Column(db.String(50), nullable=False) # Warning / Critical
    trigger_reason = db.Column(db.String(100), nullable=False) # Eyes Closed, Yawning, Head Nodding, Eye Rubbing

class Achievement(db.Model):
    __tablename__ = 'achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    achievement_key = db.Column(db.String(100), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)

# Achievement definition constant
ACHIEVEMENT_DEFINITIONS = {
    'fresh_start': {
        'title': 'Fresh Start',
        'description': 'Completed your first alertness monitoring session.',
        'icon': '🌱',
        'points_reward': 50
    },
    'focus_champion': {
        'title': 'Focus Champion',
        'description': 'Completed a session of at least 30 minutes with a Focus Score above 90%.',
        'icon': '🏆',
        'points_reward': 150
    },
    'iron_will': {
        'title': 'Iron Will',
        'description': 'Successfully completed 5 cognitive challenges.',
        'icon': '🧠',
        'points_reward': 100
    },
    'ninja_reflexes': {
        'title': 'Ninja Reflexes',
        'description': 'Completed a physical challenge in under 7 seconds.',
        'icon': '⚡',
        'points_reward': 100
    },
    'habit_builder': {
        'title': 'Habit Builder',
        'description': 'Maintained a 3-day daily streak.',
        'icon': '📅',
        'points_reward': 200
    },
    'bulletproof_focus': {
        'title': 'Bulletproof Focus',
        'description': 'Completed a session of at least 15 minutes with 0 drowsiness alerts.',
        'icon': '🛡️',
        'points_reward': 250
    }
}

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
