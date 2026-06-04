FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy existing agent code
COPY agent/ ./agent/

# Copy backend code
COPY main.py .
COPY auth.py backend/
COPY db_models.py backend/
COPY websocket_manager.py backend/
COPY background_tasks.py backend/
COPY agent_integration.py backend/
COPY services/ backend/services/

# Create necessary directories
RUN mkdir -p generated_projects

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/backend

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
