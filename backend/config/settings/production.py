from .base import *

DEBUG = False
CORS_ALLOW_ALL_ORIGINS = False

if ALLOWED_HOSTS:
    CSRF_TRUSTED_ORIGINS = [
        f"https://{host}" if not host.startswith(("http://", "https://")) else host.rstrip('/')
        for host in ALLOWED_HOSTS
        if host
    ]
else:
    CSRF_TRUSTED_ORIGINS = []

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
