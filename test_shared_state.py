import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from shared_state import install_shared_state


class SharedStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, STOCK_APP_PASSWORD='1222', STOCK_DATA_DIR=self.directory.name)
        self.environment.start()
        self.app = Flask(__name__, template_folder='templates')
        self.app.add_url_rule('/', 'home', lambda: 'private')
        install_shared_state(self.app)

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def login(self, client):
        self.assertEqual(client.post('/login', data={'password': '1222'}).status_code, 302)
        return client.get('/api/state').json['csrf']

    def test_password_and_api_protection(self):
        client = self.app.test_client()
        self.assertEqual(client.get('/').status_code, 302)
        self.assertEqual(client.get('/api/state').status_code, 401)
        self.assertIn('비밀번호가 올바르지', client.post('/login', data={'password': 'wrong'}).text)
        response = client.post('/login', data={'password': '암호１２２２'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('비밀번호가 올바르지', response.text)
        self.assertEqual(client.get('/api/state').status_code, 401)
        self.login(client)
        self.assertEqual(client.patch('/api/state', json={'favorite_stocks': []}).status_code, 403)

    def test_shared_persistent_state_and_limits(self):
        first = self.app.test_client()
        csrf = self.login(first)
        holdings = [{'name': str(i), 'code': str(i), 'quantity': 100, 'core': True} for i in range(35)]
        response = first.patch('/api/state', json={'holding_stocks': holdings, 'favorite_stocks': [str(i) for i in range(35)]}, headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        second = self.app.test_client()
        token = self.login(second)
        state = second.get('/api/state').json['state']
        self.assertEqual(len(state['holding_stocks']), 30)
        self.assertEqual(len(state['favorite_stocks']), 30)
        self.assertEqual(state['holding_stocks'][0]['quantity'], 100)
        response = second.patch('/api/state', json={'holding_stocks': []}, headers={'X-CSRF-Token': token, 'X-State-Import-If-Empty': '1'})
        self.assertEqual(len(response.json['state']['holding_stocks']), 30)
        new_app = Flask('restarted')
        install_shared_state(new_app)
        restarted = new_app.test_client()
        self.login(restarted)
        self.assertEqual(restarted.get('/api/state').json['state'], state)


if __name__ == '__main__':
    unittest.main()
