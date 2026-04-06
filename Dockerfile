FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY templates/ templates/
COPY static/ static/
COPY run_web.py .

# Data directory (mount a Railway volume here at /data)
RUN mkdir -p /data

ENV DATA_DIR=/data
ENV PORT=8080

EXPOSE 8080

# Single gunicorn worker to avoid race conditions with background polling thread
CMD ["gunicorn", "-w", "1", "--bind", "0.0.0.0:8080", "--timeout", "120", "run_web:app"]
