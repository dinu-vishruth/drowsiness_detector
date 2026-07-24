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
            admin = User(username='admin_test', email='admin@test.com', is_admin=True)
            admin.set_password('Admin123!')
            regular = User(username='regular_user', email='user@test.com')
            regular.set_password('User123!')
            db.session.add_all([admin, regular])
            db.session.commit()
        self.client = app.test_client()

    def test_regular_user_cannot_access_admin_panel(self):
        self.client.post('/login', data={'username': 'regular_user', 'password': 'User123!'}, follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard', response.headers['Location'])

    def test_admin_can_access_admin_panel(self):
        self.client.post('/login', data={'username': 'admin_test', 'password': 'Admin123!'}, follow_redirects=False)
        response = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Panel', response.data)


if __name__ == '__main__':
    unittest.main()
