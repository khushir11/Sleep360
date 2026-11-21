FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 APP_ENV=production
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home app && mkdir -p instance && chown -R app /app
USER app

EXPOSE 8000
# Apply migrations, then serve. 2 workers x 4 threads suits a small instance.
CMD ["sh", "-c", "flask --app wsgi db upgrade && gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --access-logfile -"]
