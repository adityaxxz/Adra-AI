FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy existing agent code
COPY agent/ ./agent/

# Copy backend code
COPY backend/main.py .
COPY backend/auth.py backend/
COPY backend/db_models.py backend/
COPY backend/websocket_manager.py backend/
COPY backend/background_tasks.py backend/
COPY backend/agent_integration.py backend/
COPY backend/error_handlers.py backend/
COPY backend/rate_limit.py backend/

# Create necessary directories
RUN mkdir -p generated_projects

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/backend

# Expose port (informational; actual bind port comes from $PORT at runtime)
EXPOSE 8000

# Run the application - Heroku assigns a dynamic $PORT, so this must be shell form
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
