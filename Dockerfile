FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies first (better layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY agent/ ./agent/

# Copy backend code (all files, including __init__.py)
COPY backend/ ./backend/

# main.py must also live at /app root (uvicorn main:app)
COPY backend/main.py .

# Create necessary directories
RUN mkdir -p generated_projects uploaded_repos temp_repos

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/backend

# Expose port (informational; actual bind port comes from $PORT at runtime)
EXPOSE 8000

# Run the application - Heroku assigns a dynamic $PORT, so this must be shell form
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
