FROM python:3.12-slim

# System dependencies (WeasyPrint needs GTK/Pango)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput --settings=docflow.settings.production || true

EXPOSE 8000

CMD ["gunicorn", "docflow.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
