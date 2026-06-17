# Adra-AI CLI Usage Guide

This guide covers how to set up and use the Adra-AI Command Line Interface (CLI) to generate projects, edit repositories, and ask questions about your codebase.

## Prerequisites

- Python **3.12+**
- An API key for your chosen LLM provider:
  - **Google Gemini** (default): [Google AI Studio](https://aistudio.google.com/apikey)
  - **Groq** (optional): [Groq Console](https://console.groq.com/)
- Git (for cloning GitHub repositories)

## Installation

### Using uv (Recommended)

Install [uv](https://docs.astral.sh/uv/) first, then run:

```bash
git clone https://github.com/adityaxxz/Adra-AI.git
cd Adra-AI

uv venv
# On Windows:
.\.venv\Scripts\Activate.ps1
# On Linux/Mac:
source .venv/bin/activate

uv sync
```

### Using standard pip

```bash
git clone https://github.com/adityaxxz/Adra-AI.git
cd Adra-AI

python -m venv .venv
# On Windows:
.\.venv\Scripts\Activate.ps1
# On Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

## Environment Configuration

Create a `.env` file in the root directory for CLI usage:

```env
GOOGLE_API_KEY="your-google-api-key"
GROQ_API_KEY="your-groq-api-key"

LLM_MIN_INTERVAL_SEC=2.1
LLM_MAX_RETRIES=5
LLM_MAX_CONTENT_CHARS=10000
```

## CLI Usage Modes

### 1. Project Generation Mode

Run the CLI and enter a project description:

```bash
python main.py
```

Example prompts:
- *Create a simple to-do list web application using HTML, CSS, and JavaScript*
- *Create a simple calculator web application.*
- *Create a simple blog API in FastAPI with a SQLite database.*
- *Create a tic-tac-toe game with HTML, CSS, and JavaScript.*

Optional flags:
```bash
python main.py --recursion-limit 100
python main.py -r 150
```

### 2. Repository-Aware Editing Mode

Edit an existing local repository:
```bash
python main.py --repo /path/to/your/repository
```

Clone and edit a GitHub repository:
```bash
python main.py --github https://github.com/username/repository
```

Specify a custom collection name for the vector store:
```bash
python main.py --repo /path/to/repo --collection my-custom-collection
```

Example prompts for editing:
- *Add user authentication to this FastAPI application*
- *Add error handling to all API endpoints*
- *Refactor the database layer to use async operations*
- *Add unit tests for the user service module*

### 3. Question Answering Mode

Ask questions about a repository without making changes:
```bash
python main.py --repo /path/to/repository --question
```

Example questions:
- *How does the authentication system work in this codebase?*
- *What is the purpose of the UserService class?*
- *How are API endpoints structured in this application?*
