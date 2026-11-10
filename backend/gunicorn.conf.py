"""Run from backend/: .venv/bin/gunicorn --config gunicorn.conf.py wsgi:app"""
import os

bind = os.environ.get('BIND', '0.0.0.0:5000')
workers = int(os.environ.get('WEB_WORKERS', '2'))
threads = int(os.environ.get('WEB_THREADS', '2'))
worker_class = 'gthread'
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 2000
max_requests_jitter = 200
preload_app = False
# Flask logs method, route template, status and request ID without raw query/body data.
accesslog = None
errorlog = '-'
loglevel = 'info'
capture_output = True
