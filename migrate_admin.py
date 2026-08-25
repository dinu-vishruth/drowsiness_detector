"""Standalone, idempotent admin migration.

Run this directly on the server (inside the venv) to add the is_admin column
and create the single administrator WITHOUT depending on the app restart cycle:

    python migrate_admin.py

It uses the SAME database the Flask app uses (it imports the app config), and
it prints the exact database URI and the users columns before/after — so if the
column still appears missing afterwards, the printed URI tells you which DB file
your `sqlite3` inspection should target.
"""
from sqlalchemy import text, inspect

# Importing app applies its DB config (DATABASE_URL or instance/drowsiness.db).
from app import app, db, ensure_admin_exists
from database import User


def run():
    with app.app_context():
        uri = app.config.get('SQLALCHEMY_DATABASE_URI')
        print(f"[migrate] database in use: {uri}")

        insp = inspect(db.engine)
        cols_before = sorted(c['name'] for c in insp.get_columns('users'))
        print(f"[migrate] users columns before: {cols_before}")

        if 'is_admin' not in cols_before:
            default = '0' if db.engine.dialect.name == 'sqlite' else 'FALSE'
            db.session.execute(
                text(f'ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT {default}')
            )
            db.session.commit()
            print("[migrate] added is_admin column.")
        else:
            print("[migrate] is_admin already present; skipping ALTER.")

        # Create/promote exactly one admin from ADMIN_USERNAME / ADMIN_PASSWORD.
        ensure_admin_exists(app)

        insp2 = inspect(db.engine)
        cols_after = sorted(c['name'] for c in insp2.get_columns('users'))
        print(f"[migrate] users columns after:  {cols_after}")

        admins = User.query.filter_by(is_admin=True).all()
        print(f"[migrate] admin count: {len(admins)}")
        for a in admins:
            print(f"[migrate]   admin -> {a.username} <{a.email}>")
        print("[migrate] done.")


if __name__ == '__main__':
    run()
