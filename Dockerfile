FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the GPT-2 tokenizer (used to budget prompt truncation) into the image, so the server never downloads it from
# Hugging Face at runtime (that happened on the first request after every restart). See agent/llm_client.py.
RUN python -c "from tokenizers import Tokenizer; Tokenizer.from_pretrained('gpt2').save('/app/gpt2-tokenizer.json')"
ENV TOKENIZER_FILE=/app/gpt2-tokenizer.json

# Copy agent code
COPY agent/ ./agent/

# Copy backend code (all files, including __init__.py)
COPY backend/ ./backend/
# The LLM judge (evals/evaluators/judge.py) grades real runs for the online evals (backend/online_eval.py).
COPY evals/ ./evals/

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
