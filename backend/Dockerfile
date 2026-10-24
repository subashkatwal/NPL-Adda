# Builds the NPL Adda Django application image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Fonts for server-side meme rendering (Latin + Devanagari for Nepali captions) and libraqm,
# which Pillow loads to shape Devanagari conjuncts and vowel signs correctly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-core libraqm0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY npl_adda/ /app/

# Static files (admin, API docs) are collected at build time and served by WhiteNoise.
# Settings require these variables at import; placeholders suffice because collectstatic never connects.
RUN DJANGO_SECRET_KEY=build POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

# Applies migrations, then serves on $PORT (set by hosts such as Render; 8000 locally).
# WEB_CONCURRENCY workers; keep WEB_CONCURRENCY x DB_POOL_MAX_SIZE below Postgres max_connections.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --max-requests 1000 --max-requests-jitter 100"]
