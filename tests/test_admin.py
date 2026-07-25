import os
import unittest

os.environ['SECRET_KEY'] = 'test-secret'
os.environ['ADMIN_USERNAME'] = 'admin_test'
os.environ['ADMIN_PASSWORD'] = 'Admin123!'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import app, db, User


class AdminAccessTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        with app.app_context():
            db.drop_all()
            db.create_all()
            # A normal user deliberately named "admin" must NOT gain admin access.
            impostor = User(username='admin', email='impostor@test.com')
            impostor.set_password('User123!')
            regular = User(username='regular_user', email='user@test.com')
            regular.set_password('User123!')
            db.session.add_all([impostor, regular])
            db.session.commit()
        self.client = app.test_client()

    def test_regular_user_cannot_access_admin_panel(self):
        self.client.post('/login', data={'username': 'regular_user', 'password': 'User123!'}, follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_db_user_named_admin_cannot_access_admin_panel(self):
        # Logging in as the DB user "admin" must not set the admin session flag.
        self.client.post('/login', data={'username': 'admin', 'password': 'User123!'}, follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_admin_login_with_env_credentials_grants_access(self):
        self.client.post('/admin/login', data={'username': 'admin_test', 'password': 'Admin123!'}, follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Panel', response.data)

    def test_admin_login_with_wrong_credentials_rejected(self):
        self.client.post('/admin/login', data={'username': 'admin_test', 'password': 'wrong'}, follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_admin_logout_clears_session(self):
        self.client.post('/admin/login', data={'username': 'admin_test', 'password': 'Admin123!'}, follow_redirects=False)
        self.client.get('/admin/logout', follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])


if __name__ == '__main__':
    unittest.main()
