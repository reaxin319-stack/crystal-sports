from app import app

c = app.test_client()
resp = c.post('/login', data={'username': 'testuser', 'password': 'pass123'}, follow_redirects=True)
print('login status', resp.status_code)
resp2 = c.get('/predictions', follow_redirects=True)
print('predictions status', resp2.status_code)
print(resp2.data.decode()[:800])
