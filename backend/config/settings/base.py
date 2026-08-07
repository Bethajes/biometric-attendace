"""Base Django settings for SmartAttend."""

import os
import urllib.parse
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv()

def get_env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ('1', 'true', 'yes', 'on')

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('The SECRET_KEY environment variable is not set.')

DEBUG = get_env_bool('DEBUG', False)

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]

def parse_database_url(db_url):
    if not db_url:
        raise ImproperlyConfigured('DATABASE_URL environment variable is not set.')
    if db_url.startswith('sqlite:///'):
        path = db_url[10:]
        if path.startswith('/'):
            return {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': path,
            }
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / path),
        }
    url = urllib.parse.urlparse(db_url)
    if url.scheme in ('postgres', 'postgresql'):
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': url.path.lstrip('/'),
            'USER': urllib.parse.unquote(url.username) if url.username else '',
            'PASSWORD': urllib.parse.unquote(url.password) if url.password else '',
            'HOST': url.hostname or '',
            'PORT': str(url.port or 5432),
            'OPTIONS': {
                'sslmode': 'require',
            },
        }
    raise ImproperlyConfigured(f'Unsupported DATABASE_URL scheme: {url.scheme}')

DATABASES = {
    'default': parse_database_url(os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}'))
}

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'channels',
    'rest_framework',
    'corsheaders',
    'organizations',
    'attendance',
    'device_manager',
    'payroll',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0')
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
        },
    },
}

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

WHITENOISE_USE_FINDERS = True

JAZZMIN_SETTINGS = {
    'site_header': 'SmartAttend Enterprise',
    'site_title': 'SmartAttend',
    'site_brand': 'SmartAttend',
    'welcome_sign': 'Welcome to SmartAttend Admin Panel',
    'copyright': 'SmartAttend Ltd',
    'show_sidebar': True,
    'navigation_expanded': True,
    'hide_apps': [],
    'hide_models': [],
    'order_with_respect_to': [
        'auth',
        'attendance',
        'device_manager',
    ],
    'icons': {
        'auth': 'fas fa-users-cog',
        'auth.Group': 'fas fa-users',
        'auth.User': 'fas fa-user-shield',
        'attendance.Employee': 'fas fa-user-tie',
        'attendance.Department': 'fas fa-building',
        'attendance.OfficeLocation': 'fas fa-map-marker-alt',
        'attendance.Shift': 'fas fa-clock',
        'attendance.EmployeeSchedule': 'fas fa-calendar-alt',
        'attendance.AttendanceLog': 'fas fa-fingerprint',
        'attendance.AttendanceRecord': 'fas fa-clipboard-list',
        'attendance.LeaveRequest': 'fas fa-plane-departure',
        'attendance.LeaveBalance': 'fas fa-coins',
        'attendance.Holiday': 'fas fa-umbrella-beach',
        'attendance.EnrollmentRequest': 'fas fa-id-card',
        'attendance.BiometricDevice': 'fas fa-microchip',
        'attendance.DeviceCommand': 'fas fa-terminal',
        'attendance.DeviceEvent': 'fas fa-stream',
        'attendance.Notification': 'fas fa-bell',
        'attendance.SystemSetting': 'fas fa-cog',
    },
    'default_icon_parents': 'fas fa-folder-open',
    'default_icon_children': 'fas fa-circle',
    'topmenu_links': [
        {'name': 'Home', 'url': 'admin:index', 'permissions': ['auth.view_user']},
        {'name': 'Dashboard', 'url': 'dashboard', 'new_window': True},
        {'name': 'Device Manager', 'url': 'device_dashboard', 'new_window': True},
        {'model': 'attendance.Employee'},
        {'app': 'attendance'},
    ],
    'show_ui_builder': False,
    'changeform_format': 'horizontal_tabs',
    'changeform_format_overrides': {
        'auth.User': 'vertical_tabs',
        'attendance.Employee': 'horizontal_tabs',
        'attendance.BiometricDevice': 'horizontal_tabs',
        'attendance.AttendanceRecord': 'vertical_tabs',
    },
    'related_modal_active': True,
    'brand_colour': '#126b8f',
    'accent': '#1f8a70',
    'brand_306b99': '#126b8f',
    'accent_1f8a70': '#1f8a70',
    'use_google_fonts': True,
    'show_version': True,
}

JAZZMIN_UI_TWEAKS = {
    'navbar_small_text': False,
    'footer_small_text': False,
    'body_small_text': False,
    'brand_small_text': False,
    'brand_colour': False,
    'accent': 'accent-teal',
    'navbar': 'navbar-dark',
    'no_navbar_border': False,
    'navbar_fixed': True,
    'layout_boxed': False,
    'footer_fixed': False,
    'sidebar_fixed': True,
    'sidebar': 'sidebar-dark-primary',
    'sidebar_nav_small_text': False,
    'sidebar_disable_expand': False,
}

EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'webmaster@localhost')
