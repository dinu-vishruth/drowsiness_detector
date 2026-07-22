import os
import sys
from datetime import datetime, timedelta

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import db, User
from app import app

def migrate_database():
    """Add password reset fields to the User table."""
    
    with app.app_context():
        # Check if columns already exist
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'reset_token' in columns and 'reset_token_expires' in columns:
            print("✓ Migration already completed. Password reset fields exist.")
            return
        
        print("Adding password reset fields to users table...")
        
        # Add new columns using raw SQL for SQLite
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN reset_token VARCHAR(100)"))
                conn.execute(db.text("ALTER TABLE users ADD COLUMN reset_token_expires DATETIME"))
                conn.commit()
            
            print("✓ Successfully added reset_token and reset_token_expires columns")
            print("✓ Migration completed successfully!")
            
        except Exception as e:
            print(f"✗ Migration failed: {e}")
            print("Note: If you're using SQLite, you may need to recreate the database.")
            print("The new fields will be added automatically when you recreate the database.")

if __name__ == '__main__':
    print("Database Migration - Adding Password Reset Fields")
    print("=" * 60)
    migrate_database()
    print("=" * 60)
