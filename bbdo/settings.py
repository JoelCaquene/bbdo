"""
Django settings for bbdo project.
Configurado para Testagem Local e Produção no Render.com.
"""

from pathlib import Path
import os
import dj_database_url
from decouple import config
from django.utils.translation import gettext_lazy as _

# Caminho base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent

# SEGURANÇA: DEBUG deve ser False em produção
DEBUG = config('DEBUG', default=False, cast=bool)

SECRET_KEY = config('SECRET_KEY', default='django-insecure-mudar-isso-em-producao')

# ======================================================================
# CONFIGURAÇÃO DOS HOSTS PERMITIDOS E CSRF
# ======================================================================

# No Render, o host costuma ser 'seu-app.onrender.com'
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost').split(',')

RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# ADICIONADO: Seus domínios personalizados para produção (Corrigido para .pro)
ALLOWED_HOSTS.extend([
    'bbdo.pro',
    'www.bbdo.pro',
    'bbdo-c31p.onrender.com'
])

# FORÇAR REDIRECIONAMENTO PARA WWW (Isso torna o www o principal)
if not DEBUG:
    PREPEND_WWW = True

# Configuração de origens confiáveis para CSRF
CSRF_TRUSTED_ORIGINS = [f"https://{host.strip()}" for host in ALLOWED_HOSTS if host.strip()]

# ======================================================================
# APPS E MIDDLEWARE
# ======================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',  # WhiteNoise antes do staticfiles
    'django.contrib.staticfiles',
    
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'bbdo.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
            ],
        },
    },
]

WSGI_APPLICATION = 'bbdo.wsgi.application'

# ======================================================================
# DATABASE (SQLITE LOCAL / POSTGRES EM PRODUÇÃO)
# ======================================================================
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3'),
        conn_max_age=600
    )
}

# ======================================================================
# INTERNACIONALIZAÇÃO
# ======================================================================
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'Africa/Luanda'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ('pt', _('Português')),
    ('en', _('English')),
    ('fr', _('Français')),
]

# Caminho onde as pastas de tradução (locale) ficarão
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

# ======================================================================
# STATIC E MEDIA FILES
# ======================================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Armazenamento otimizado para produção
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ======================================================================
# SEGURANÇA EXTRA (ATIVADA APENAS EM PRODUÇÃO)
# ======================================================================
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.CustomUser'
LOGIN_URL = 'login'
