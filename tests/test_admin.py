import os
import unittest

os.environ['SECRET_KEY'] = 'test-secret'
os.environ['ADMIN_USERNAME'] = 'admin_test'
os.environ['ADMIN_PASSWORD'] = 'Admin123!'
os.environ['ADMIN_EMAIL'] = 'admin_test@example.com'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import app, db, User, ensure_admin_exists


class AdminAccessTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        with app.app_context():
            db.drop_all()
            db.create_all()
            regular = User(username='regular_user', email='user@test.com')
            regular.set_password('User123!')
            db.session.add(regular)
            db.session.commit()
        # Recreate the single admin against the fresh in-memory schema.
        ensure_admin_exists(app)
        self.client = app.test_client()

    # --- admin creation ---

    def test_admin_created_on_startup(self):
        with app.app_context():
            admin = User.query.filter_by(is_admin=True).first()
            self.assertIsNotNone(admin)
            self.assertEqual(admin.username, 'admin_test')
            self.assertEqual(admin.email, 'admin_test@example.com')

    def test_only_one_admin_exists(self):
        with app.app_context():
            self.assertEqual(User.query.filter_by(is_admin=True).count(), 1)

    def test_ensure_admin_is_idempotent(self):
        ensure_admin_exists(app)
        ensure_admin_exists(app)
        with app.app_context():
            self.assertEqual(User.query.filter_by(is_admin=True).count(), 1)

    def test_admin_password_is_hashed(self):
        with app.app_context():
            admin = User.query.filter_by(is_admin=True).first()
            self.assertNotEqual(admin.password_hash, 'Admin123!')
            self.assertTrue(admin.check_password('Admin123!'))

    # --- registration never creates admins ---

    def test_registration_creates_non_admin(self):
        self.client.post('/register', data={
            'username': 'newbie', 'email': 'newbie@test.com',
            'password': 'Newbie123!', 'confirm_password': 'Newbie123!'
        }, follow_redirects=False)
        with app.app_context():
            u = User.query.filter_by(username='newbie').first()
            self.assertIsNotNone(u)
            self.assertFalse(u.is_admin)

    def test_registration_ignores_is_admin_field(self):
        # A crafted request injecting is_admin must not self-promote.
        self.client.post('/register', data={
            'username': 'attacker', 'email': 'attacker@test.com',
            'password': 'Attack123!', 'confirm_password': 'Attack123!',
            'is_admin': 'true'
        }, follow_redirects=False)
        with app.app_context():
            u = User.query.filter_by(username='attacker').first()
            self.assertIsNotNone(u)
            self.assertFalse(u.is_admin)

    # --- login (shared page) ---

    def test_regular_user_login_works(self):
        resp = self.client.post('/login', data={'username': 'regular_user', 'password': 'User123!'}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard', resp.headers['Location'])

    def test_admin_login_via_shared_page(self):
        resp = self.client.post('/login', data={'username': 'admin_test', 'password': 'Admin123!'}, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin', resp.headers['Location'])

    def test_no_separate_admin_login_route(self):
        # The dedicated admin login page must be gone.
        resp = self.client.get('/admin/login')
        self.assertEqual(resp.status_code, 404)

    # --- authorization ---

    def test_admin_can_access_panel(self):
        self.client.post('/login', data={'username': 'admin_test', 'password': 'Admin123!'}, follow_redirects=False)
        resp = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Admin Panel', resp.data)

    def test_non_admin_gets_403(self):
        self.client.post('/login', data={'username': 'regular_user', 'password': 'User123!'}, follow_redirects=False)
        resp = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])


if __name__ == '__main__':
    unittest.main()
