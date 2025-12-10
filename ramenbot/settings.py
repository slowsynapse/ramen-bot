"""
Django settings for RAMEN bot project.

Adapted from spicebot for BCH-1 Hackcelerator.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.1/ref/settings/
"""

import os
from decouple import config
import redis

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'zu_jn)inc@e5-#@8$mujfto*c^5a(z+e@e(zy00tg4y@dfsa8r'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'main',
    'rest_framework',
    'rest_framework.authtoken'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day'
    },
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication'
    ]
}

ROOT_URLCONF = 'ramenbot.urls'

CORS_ORIGIN_WHITELIST = [
    'http://localhost:5555',
    'https://spice.network',
    'http://localhost:8080',
    'https://spicefeed-dev.scibizinformatics.com',
    'https://spicefeed-staging.scibizinformatics.com'
]

CORS_ALLOW_CREDENTIALS = True

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ramenbot.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': config('POSTGRES_DB', default='ramenbot'),
        'HOST': config('POSTGRES_HOST', default='localhost'),
        'PORT': config('POSTGRES_PORT', default=5432, cast=int),
        'USER': config('POSTGRES_USER', default='postgres'),
        'PASSWORD': config('POSTGRES_PASSWORD', default='badpassword')
    }
}

# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    }
]


# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Logging settings

DJANGO_LOG_LEVEL = 'DEBUG'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format': '[%(asctime)s %(name)s] %(levelname)s [%(pathname)s:%(lineno)d] - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console'
        },
    },
    'loggers': {
        '': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False
        },
        'django': {
            'handlers': ['console'],
            'level': DJANGO_LOG_LEVEL,
            'propagate': False
        },
        'main': {
            'handlers': ['console'],
            'level': DJANGO_LOG_LEVEL,
            'propagate': False
        },
        'django.template': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False
        }
    },
}


DEPLOYMENT_INSTANCE = config('DEPLOYMENT_INSTANCE', default='dev')


# Celery settings
REDIS_HOST = config('REDIS_HOST', default='localhost')
REDIS_PASSWORD = config('REDIS_PASSWORD', default='')
REDIS_PORT = config('REDIS_PORT', default=6379)

CELERY_IMPORTS = ('main.tasks',)

DB_NUM = [0,1,3]
if DEPLOYMENT_INSTANCE == 'dev':
    DB_NUM = [4,5,6]
if DEPLOYMENT_INSTANCE == 'staging':
    DB_NUM = [7,8,9]

if REDIS_PASSWORD:
    CELERY_BROKER_URL = 'redis://user:%s@%s:%s/%s' % (REDIS_PASSWORD, REDIS_HOST, REDIS_PORT, DB_NUM[0])
    CELERY_RESULT_BACKEND = 'redis://user:%s@%s:%s/%s' % (REDIS_PASSWORD, REDIS_HOST, REDIS_PORT, DB_NUM[1])

    REDISKV = redis.StrictRedis(
        host=REDIS_HOST,
        password=REDIS_PASSWORD,
        port=6379,
        db=DB_NUM[2]
    )
else:
    CELERY_BROKER_URL = 'redis://%s:%s/%s' % (REDIS_HOST, REDIS_PORT, DB_NUM[0])
    CELERY_RESULT_BACKEND = 'redis://%s:%s/%s' % (REDIS_HOST, REDIS_PORT, DB_NUM[1])
 
    REDISKV = redis.StrictRedis(
        host=REDIS_HOST,
        port=6379,
        db=DB_NUM[2]
    )

CELERY_TASK_ACKS_LATE = True
CELERYD_PREFETCH_MULTIPLIER = 1
CELERYD_MAX_TASKS_PER_CHILD = 5

CELERY_BEAT_SCHEDULE = {
    # Scheduled tasks for RAMEN
    # 'weekly-snapshot': {
    #     'task': 'main.tasks.publish_ipfs_snapshot',
    #     'schedule': crontab(day_of_week='sun', hour=0)
    # },
    # 'weekly-leaderboard': {
    #     'task': 'main.tasks.post_weekly_leaderboard',
    #     'schedule': crontab(day_of_week='sun', hour=1)
    # },
}


# Telegram bot settings
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_BOT_USER = config('TELEGRAM_BOT_USER', default='')


# Twitter API settings (for verification and tweet fetching)
TWITTER_BEARER_TOKEN = config('TWITTER_BEARER_TOKEN', default='')

# Claude API settings (for LLM scoring)
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')

# IPFS/Pinata settings (for ledger snapshots)
PINATA_API_KEY = config('PINATA_API_KEY', default='')
PINATA_SECRET_KEY = config('PINATA_SECRET_KEY', default='')

# RAMEN specific settings
RAMEN_SALT = config('RAMEN_SALT', default='change_this_secret')
TELEGRAM_CHANNEL_ID = config('TELEGRAM_CHANNEL_ID', default='')  # For leaderboard posts

# Keep for future CashToken distribution
PARENT_XPUBKEY = config('PARENT_XPUBKEY', default='')

ALLOWED_SYMBOLS = {
    "\ufe0f": 0, # this character is sometimes inserted in between emojis
    "\U0001F35C": 100, # ramen bowl 🍜
    "\U0001f525": 5, # fire 🔥
    "\U0001f48b": 50, # kiss mark 💋
    "\U0001f48e": 1000, # gem stone 💎
    "\U0001f37c": 0.00000001, # baby bottle 🍼
    "\U0001F344": "undefined" # mushroom 🍄 (random 0-999)
}

# Reaction-based tipping settings
# Set to False to disable reaction tipping entirely (easy feature toggle)
REACTION_TIPPING_ENABLED = True

# Emoji reactions that trigger tips (only these will be processed)
# Note: These must be valid Telegram reaction emoji
REACTION_SYMBOLS = {
    "\U0001f525": 50,  # fire 🔥 - 50 RAMEN
    "\u2764": 25,      # red heart ❤ - 25 RAMEN
}

POF_SYMBOLS = {
    0: "\U0001F966",
    1: "\U0001F954",
    2: "\U0001F31E",
    3: "\u2668",
    4: "\U0001F321",
    5: "\U0001F525",
    6: "\U0001F4A6"
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'