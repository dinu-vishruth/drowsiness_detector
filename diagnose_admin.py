"""Diagnose why admin login fails on a deployed instance.

Run this ON THE SERVER, from the app directory, with the same user/venv the
service uses:

    cd /home/ubuntu/drowiness_detector
    ./venv/bin/python diagnose_admin.py

It reports, without printing any secret values:
  * whether load_dotenv() actually found a .env, and from where
  * whether ADMIN_USERNAME / ADMIN_PASSWORD reached the process
  * which database file/URL the app is really using, and if it is writable
  * whether the users table has the is_admin column
  * whether an admin row exists, and whether ADMIN_PASSWORD authenticates it
"""
import os
import sys

from dotenv import find_dotenv, load_dotenv

print("=" * 68)
print("ADMIN LOGIN DIAGNOSTIC")
print("=" * 68)

# --- 1. .env discovery -----------------------------------------------------
# load_dotenv() searches upward from the CWD, so a service started with a
# different WorkingDirectory can silently miss the file.
print(f"\n[1] Working directory: {os.getcwd()}")
dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    print(f"    .env found at: {dotenv_path}")
else:
    print("    .env NOT FOUND from this working directory  <-- PROBLEM")
    print("    load_dotenv() searches upward from the CWD. Confirm the file is")
    print("    named exactly '.env' and sits in the directory the service runs in.")
load_dotenv()

# --- 2. Admin credentials in the environment ------------------------------
admin_username = os.getenv("ADMIN_USERNAME")
admin_password = os.getenv("ADMIN_PASSWORD")
admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")

print("\n[2] Admin credentials visible to this process:")
print(f"    ADMIN_USERNAME : {admin_username!r}")
print(f"    ADMIN_PASSWORD : {'set (%d chars)' % len(admin_password) if admin_password else 'MISSING'}")
print(f"    ADMIN_EMAIL    : {admin_email!r}"
      f"{'  (default - not set in .env)' if not os.getenv('ADMIN_EMAIL') else ''}")

if not admin_username or not admin_password:
    print("\n    --> ensure_admin_exists() FAILS CLOSED when either is missing:")
    print("        no admin is created and login can never succeed.")
    print("        Add both to .env, then restart the service.")

# --- 3. Which database is the app actually using? -------------------------
# Import after load_dotenv so app.py sees the same environment.
from app import app  # noqa: E402
from database import User, db  # noqa: E402

uri = app.config["SQLALCHEMY_DATABASE_URI"]
print("\n[3] Database the app is using:")
if uri.startswith("sqlite:///"):
    db_file = uri[len("sqlite:///"):]
    exists = os.path.exists(db_file)
    print(f"    SQLite file: {db_file}")
    print(f"    exists     : {exists}")
    if exists:
        st = os.stat(db_file)
        print(f"    size       : {st.st_size} bytes")
        # getuid() is POSIX-only; skip the ownership line when run on Windows.
        if hasattr(os, "getuid"):
            print(f"    owner uid  : {st.st_uid}   (this process runs as uid {os.getuid()})")
        print(f"    writable   : {os.access(db_file, os.W_OK)}")
        if not os.access(db_file, os.W_OK):
            print("    --> NOT WRITABLE: admin creation cannot commit.  <-- PROBLEM")
            print("        Often caused by a previous run under sudo/root leaving")
            print("        instance/ owned by root. Fix with:")
            print("        sudo chown -R $USER:$USER instance/")
    else:
        print("    --> A fresh database will be created on next start.")
else:
    # Never print credentials embedded in a Postgres URL.
    scheme = uri.split("://", 1)[0]
    print(f"    External database (scheme: {scheme}) via DATABASE_URL")

# --- 4. Schema + admin row ------------------------------------------------
with app.app_context():
    print("\n[4] Schema check:")
    try:
        columns = {c["name"] for c in db.inspect(db.engine).get_columns("users")}
    except Exception as exc:
        print(f"    Could not inspect users table: {exc}  <-- PROBLEM")
        sys.exit(1)
    print(f"    is_admin column present: {'is_admin' in columns}")
    if "is_admin" not in columns:
        print("    --> Migration did not run. Restart the app so init_db() adds it.")

    print("\n[5] Users in the database:")
    users = User.query.order_by(User.id).all()
    if not users:
        print("    (none)")
    for u in users:
        flag = "ADMIN" if u.is_admin else "user "
        print(f"    #{u.id:<4} [{flag}] {u.username!r}  <{u.email}>")

    admins = [u for u in users if u.is_admin]
    print(f"\n[6] Admin accounts found: {len(admins)}")

    if not admins:
        print("    --> NO ADMIN EXISTS. This is why login fails.")
        if admin_username and admin_password:
            print("        Credentials are present, so ensure_admin_exists() should")
            print("        create one on the next start. Restart the service:")
            print("        sudo systemctl restart drowsiness-detector")
        else:
            print("        Add ADMIN_USERNAME and ADMIN_PASSWORD to .env, then restart.")
    else:
        for a in admins:
            print(f"\n    Admin: {a.username!r} <{a.email}>")
            if admin_password:
                ok = a.check_password(admin_password)
                print(f"    ADMIN_PASSWORD from .env authenticates this account: {ok}")
                if not ok:
                    print("    --> PASSWORD MISMATCH.  <-- PROBLEM")
                    print("        ensure_admin_exists() only acts when ZERO admins exist.")
                    print("        If this account was PROMOTED from an existing user, its")
                    print("        original password was kept and ADMIN_PASSWORD was never")
                    print("        applied. Editing ADMIN_PASSWORD later has no effect.")
                    print("        Log in with the account's original password, or reset it:")
                    print("          ./venv/bin/python -c \"from app import app; from database "
                          "import db, User; app.app_context().push(); "
                          "u=User.query.filter_by(is_admin=True).first(); "
                          "u.set_password('NEW_PASSWORD'); db.session.commit()\"")
            if admin_username and a.username != admin_username:
                print(f"    --> Note: ADMIN_USERNAME is {admin_username!r} but the existing")
                print(f"        admin is {a.username!r}. Log in as {a.username!r}.")

    print("\n[7] Sign-in URL:")
    print("    Use /login  (the shared login page).")
    print("    /admin/login was removed in commit 01bd98d and now returns 404.")
    print("    After signing in, the admin is redirected to /admin automatically.")

print("\n" + "=" * 68)
