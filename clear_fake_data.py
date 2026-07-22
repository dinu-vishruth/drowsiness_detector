import os
import sys
from datetime import datetime

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import db, User, Session, AlertEvent, Achievement
from app import app

def clear_fake_data():
    """Clear the hardcoded developer user and associated fake data."""
    
    with app.app_context():
        # Find and delete the developer user
        developer_user = User.query.filter_by(username='developer').first()
        
        if developer_user:
            print(f"Found developer user: {developer_user.username} (ID: {developer_user.id})")
            
            # Delete associated sessions, alerts, and achievements (cascade should handle this)
            # but let's be explicit to ensure cleanup
            session_count = Session.query.filter_by(user_id=developer_user.id).count()
            alert_count = AlertEvent.query.join(Session).filter(Session.user_id == developer_user.id).count()
            achievement_count = Achievement.query.filter_by(user_id=developer_user.id).count()
            
            print(f"  - Associated sessions: {session_count}")
            print(f"  - Associated alerts: {alert_count}")
            print(f"  - Associated achievements: {achievement_count}")
            
            # Delete the user (cascade will delete related records)
            db.session.delete(developer_user)
            db.session.commit()
            
            print("✓ Developer user and all associated data deleted successfully!")
        else:
            print("No developer user found in database.")
        
        # Show remaining users
        remaining_users = User.query.all()
        print(f"\nRemaining users in database: {len(remaining_users)}")
        for user in remaining_users:
            print(f"  - {user.username} ({user.email}) - Created: {user.created_at}")
        
        # Show remaining sessions
        remaining_sessions = Session.query.all()
        print(f"\nRemaining sessions in database: {len(remaining_sessions)}")
        
        # Show remaining alerts
        remaining_alerts = AlertEvent.query.all()
        print(f"Remaining alerts in database: {len(remaining_alerts)}")

if __name__ == '__main__':
    print("Clearing fake data from database...")
    print("=" * 50)
    clear_fake_data()
    print("=" * 50)
    print("Done!")
