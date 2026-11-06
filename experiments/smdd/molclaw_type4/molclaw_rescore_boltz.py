"""Process-local network timeouts; Boltz algorithms and parameters stay unchanged."""
import runpy, sys
from urllib.parse import urlsplit
import requests

original_request = requests.sessions.Session.request
def request_with_msa_timeout(self, method, url, **kwargs):
    parsed = urlsplit(url)
    if method.upper() == 'GET' and parsed.hostname == 'api.colabfold.com':
        if parsed.path.startswith('/result/download/'):
            kwargs['timeout'] = (30, 180)
        elif parsed.path.startswith('/ticket/'):
            kwargs['timeout'] = (30, 60)
    return original_request(self, method, url, **kwargs)

if __name__ == '__main__':
    requests.sessions.Session.request = request_with_msa_timeout
    if sys.argv[1:] == ['--transport-self-test']:
        captured=[]
        def fake(self,method,url,**kwargs):
            captured.append(kwargs.get('timeout'))
        original_request=fake
        session=requests.Session()
        session.get('https://api.colabfold.com/result/download/probe',timeout=6.02)
        session.get('https://api.colabfold.com/ticket/probe',timeout=6.02)
        session.get('https://example.com/probe',timeout=6.02)
        assert captured == [(30,180),(30,60),6.02], captured
        print('TRANSPORT_SELF_TEST_PASSED',captured)
    else:
        print('RESCORE_MSA_NETWORK_TIMEOUT download=(30,180) ticket=(30,60)',flush=True)
        runpy.run_module('boltz.main',run_name='__main__')
