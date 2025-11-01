"""
Django settings for nailbot project (refactor).

- Django REST Framework & CORS
- Env vars untuk model & Gemini 2.5
- Static/Media paths
- Batas upload & logging sederhana
"""

from pathlib import Path
import os

# (Opsional) load .env jika kamu pakai python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()  # otomatis baca berkas .env di root proyek
except Exception:
    pass

# ==== Path dasar ====
BASE_DIR = Path(__file__).resolve().parent.parent

# ==== Keamanan & mode ====
# Selalu ambil dari ENV di produksi
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-key")
DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes", "on")

# Format: ALLOWED_HOSTS=localhost,127.0.0.1,example.com
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# (Opsional) untuk dev/frontend lokal
# CSRF_TRUSTED_ORIGINS=https://app.example.com,http://localhost:5173
_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o for o in _csrf.split(",") if o]

# ==== Aplikasi ====
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Pihak ketiga
    'rest_framework',
    'corsheaders',

    # App internal
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS di awal
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nailbot.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],  # kalau butuh template kustom
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

WSGI_APPLICATION = 'nailbot.wsgi.application'

# ==== Database (default sqlite) ====
# Atur ENV untuk produksi (Postgres dsb)
DATABASES = {
    'default': {
        'ENGINE': os.getenv("DB_ENGINE", 'django.db.backends.sqlite3'),
        'NAME': os.getenv("DB_NAME", str(BASE_DIR / 'db.sqlite3')),
        'USER': os.getenv("DB_USER", ""),
        'PASSWORD': os.getenv("DB_PASSWORD", ""),
        'HOST': os.getenv("DB_HOST", ""),
        'PORT': os.getenv("DB_PORT", ""),
    }
}

# ==== Password validators ====
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==== I18N / TZ ====
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.getenv("TIME_ZONE", 'Asia/Jakarta')
USE_I18N = True
USE_TZ = True

# ==== Static & Media ====
STATIC_URL = '/static/'
STATIC_ROOT = os.getenv("STATIC_ROOT", str(BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = os.getenv("MEDIA_ROOT", str(BASE_DIR / "media"))

# ==== Default PK field ====
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==== Django REST Framework (basic) ====
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # Tambahkan BrowsableAPIRenderer kalau mau UI dev
        # "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

# ==== CORS ====
# DEV: izinkan semua; PRODUKSI: set False & isi whitelist
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "True").lower() in ("1", "true", "yes", "on")
# Atau spesifik:
# CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "https://ui-domain.com"]
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o for o in _cors_origins.split(",") if o]

# ==== Batas ukuran upload (in-memory) ====
# Default Django 2.5MB. Di sini kita longgarkan untuk gambar medis (mis. 10MB).
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", 10 * 1024 * 1024))  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", 10 * 1024 * 1024))  # 10 MB

# ==== Konfigurasi Model & Gemini (dipakai di api/model_loader.py & api/llm.py) ====
CKPT_PATH = os.getenv("CKPT_PATH", str(BASE_DIR / "best_efficientnet_b0.pt"))
LABELS_JSON = os.getenv("LABELS_JSON", str(BASE_DIR / "labels.json"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ==== Security headers (rekomendasi produksi) ====
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if os.getenv("BEHIND_PROXY", "False").lower() in ("1","true","yes","on") else None
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("1","true","yes","on")
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False").lower() in ("1","true","yes","on")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))  # set >0 untuk produksi (mis. 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False").lower() in ("1","true","yes","on")
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() in ("1","true","yes","on")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() in ("1","true","yes","on")

# ==== Logging sederhana ====
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std": {"format": "[%(levelname)s] %(asctime)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "std",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}
