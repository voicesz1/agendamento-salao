FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system salon \
    && useradd --system --gid salon --home-dir /nonexistent salon

COPY app ./app
RUN mkdir -p /data && chown salon:salon /data

USER salon
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD-SHELL python -c "import os; from urllib.request import urlopen; urlopen('http://127.0.0.1:%s/healthz' % os.getenv('PORT', '8000'), timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
