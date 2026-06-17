# Adra-AI

[![Live](https://img.shields.io/badge/Live-https%3A%2F%2Fadra--ai.vercel.app-blue?style=for-the-badge&logo=vercel)](https://adra-ai.vercel.app)

A multi-agent coding assistant SaaS platform that turns natural-language prompts into working codebases or edits existing repositories. Built with [LangGraph](https://langchain-ai.github.io/langgraph/) and LangChain, Adra-AI features a modern web application with real-time updates and operates in three modes:

1. **Project Generation** — Creates new projects from scratch using a four-stage pipeline: Planner → Architect → Coder → Integrator
2. **Repository-Aware Editing** — Edits existing repositories with context-aware RAG (Retrieval-Augmented Generation)
3. **Question Answering** — Asks questions about codebases without making changes

## Architecture

Adra-AI now features a full SaaS architecture with:

- **Backend**: FastAPI with PostgreSQL database and Qdrant vector store
- **Frontend**: Next.js with React, TypeScript, and Tailwind CSS
- **Authentication**: OAuth 2.0 (Google & GitHub)
- **Real-time Updates**: WebSocket support for live progress tracking
- **Deployment**: Docker Compose setup for easy deployment

### Architecture Diagram

```mermaid
flowchart TB
    subgraph Frontend["Frontend (Next.js)"]
        UI[User Interface]
        Auth[OAuth Authentication]
        WS[WebSocket Client]
    end
    
    subgraph Backend["Backend (FastAPI)"]
        API[REST API]
        OAuth[OAuth Handlers]
        WSManager[WebSocket Manager]
        BGTasks[Background Tasks]
    end
    
    subgraph Storage["Storage Layer"]
        PG[(PostgreSQL)]
        Qdrant[(Qdrant Vector Store)]
    end
    
    subgraph Agents["Agent Pipeline"]
        Planner[Planner Agent]
        Architect[Architect Agent]
        Coder[Coder Agent]
        Integrator[Integrator Agent]
        RepoAgent[Repository Agent]
        Explainer[Explainer Agent]
    end
    
    UI --> API
    Auth --> OAuth
    WS --> WSManager
    API --> Planner
    API --> RepoAgent
    WSManager --> BGTasks
    BGTasks --> Agents
    API --> PG
    RepoAgent --> Qdrant
    
    style Frontend fill:#e1f5ff
    style Backend fill:#fff4e1
    style Storage fill:#e8f5e9
    style Agents fill:#f3e5f5
```

## How it works

### Project Generation Mode

```mermaid
flowchart LR

    A([User Prompt])
    B[Planner]
    C[Architect]
    D[Coder]
    E{Tasks Complete?}
    F[Integrator]
    G([Generated Project])

    A --> B
    B --> C
    C --> D
    D --> E

    E -->|No| D
    E -->|Yes| F

    F --> G
```

1. **Planner** — Converts your prompt into a structured project plan: app name, description, tech stack, features, and target files.
2. **Architect** — Breaks the plan into ordered implementation steps, each with a file path and detailed task description. One step per file, ordered by dependency.
3. **Coder** — Executes one step at a time using file tools (`read_file`, `write_file`) to create and update code. Each step receives context from already-written sibling files so imports, exports, and APIs stay aligned as the project grows.
4. **Integrator** — After all coder steps finish, reads the full project and fixes cross-file issues: missing exports, mismatched imports, wrong paths, and logic bugs that block end-to-end behavior. Only files that need correction are rewritten.

### Repository-Aware Editing Mode

```mermaid
flowchart LR

    A([User Prompt + Repository])
    B[Repository Agent]
    C[Planner]
    D[Architect]
    E[Coder]
    F{Tasks Complete?}
    G[Integrator]
    H([Updated Project])

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F

    F -->|No| E
    F -->|Yes| G

    G --> H
```

1. **Repository Agent** — Scans, chunks, and indexes the repository into Qdrant vector store; retrieves relevant code snippets via semantic search
2. **Planner** — Creates project plan using repository context to prefer modifying existing files over creating duplicate functionality
3. **Architect** — Breaks the plan into implementation steps with awareness of existing codebase structure
4. **Coder** — Implements changes using both project context and repository-specific code snippets
5. **Integrator** — Reviews and fixes cross-file integration issues in the updated codebase

### Question Answering Mode

```mermaid
flowchart LR

    A([User Question + Repository])
    B[Repository Agent]
    C[Explainer Agent]
    D([Answer])

    A --> B
    B --> C
    C --> D
```

1. **Repository Agent** — Retrieves relevant code snippets from the indexed repository based on the question
2. **Explainer Agent** — Analyzes the retrieved context and provides accurate answers about the codebase without making changes

## Features

### Core Features
- **Structured planning** — Pydantic schemas enforce consistent plans, task breakdowns, and integration results
- **Step-by-step implementation** — Each file is built in dependency order with live context from prior files
- **Cross-file integration pass** — The integrator agent reviews the whole codebase and patches integration bugs the coder may have missed
- **Centralized LLM client** — Throttled API calls, automatic retries on rate limits, and context truncation
- **Pluggable LLM backend** — Swap between Google Gemini and Groq models via configuration

### Repository-Aware Features
- **Repository scanning** — Automatically scans repositories for supported file types (Python, JavaScript, TypeScript, HTML, CSS, Markdown, JSON)
- **Code-aware chunking** — Language-specific chunking strategies (AST-based for Python, regex-based for JS/TS)
- **File hashing** — SHA256-based content hashing for change detection
- **Incremental indexing** — Only re-index changed files based on content hashes
- **Embedding generation** — Generates vector embeddings for semantic search
- **Vector store** — Qdrant-backed persistent storage for code chunks and embeddings
- **Semantic search** — Retrieves relevant code snippets based on natural language queries
- **GitHub integration** — Clone and index GitHub repositories automatically
- **Context-aware planning** — Leverages existing code patterns and structure when planning changes

### SaaS Platform Features
- **OAuth authentication** — Secure sign-in with Google and GitHub
- **User management** — Multi-tenant support with user-specific projects and repositories
- **Project management** — Create, view, and manage generated projects
- **Repository management** — Connect and index multiple repositories
- **Real-time updates** — WebSocket-based progress tracking for long-running tasks
- **Background processing** — Async task processing for agent operations
- **Rate limiting** — Configurable rate limits for API endpoints
- **Error handling** — Comprehensive error handling and logging

## Tech stack

| Layer | Tools |
|-------|-------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12+ |
| Database | PostgreSQL 16 |
| Vector Store | Qdrant 1.12.0 |
| Orchestration | LangGraph, LangChain |
| LLM (default) | Google Gemini 2.5 Flash |
| LLM (optional) | Groq (`openai/gpt-oss-120b`) |
| Authentication | OAuth 2.0 (Google, GitHub) |
| Real-time | WebSockets |
| Deployment | Docker, Docker Compose |
| State Management | Zustand |
| Data Fetching | TanStack Query |

## Prerequisites

### For Web Application (Docker)
- Docker and Docker Compose
- OAuth credentials (Google and/or GitHub)
- LLM API keys (Groq, Google, or other supported providers)

### For CLI Usage
- Python **3.12+**
- An API key for your chosen LLM provider:
  - **Groq** (default): [Groq Console](https://console.groq.com/)
  - **Google Gemini** (optional): [Google AI Studio](https://aistudio.google.com/apikey)
- Git (for GitHub repository cloning)

## Installation

### Option A — Docker Deployment (Recommended for Web App)

1. Clone the repository:
```bash
git clone https://github.com/adityaxxz/Adra-AI.git
cd Adra-AI
```

2. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
# Database Configuration
DATABASE_URL=postgresql://adrai:adrai_password@localhost:5432/adrai

# Qdrant Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Security
SECRET_KEY=your-secret-key-change-in-production-min-32-characters

# OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID=your-google-oauth-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-oauth-client-secret
GITHUB_OAUTH_CLIENT_ID=your-github-oauth-client-id
GITHUB_OAUTH_CLIENT_SECRET=your-github-oauth-client-secret

# Frontend URL for OAuth callbacks
FRONTEND_URL=http://localhost:3000

# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID=your-google-oauth-client-id
NEXT_PUBLIC_GITHUB_OAUTH_CLIENT_ID=your-github-oauth-client-id

# LLM Configuration
GROQ_API_KEY=your-groq-api-key
GOOGLE_API_KEY=your-google-api-key
```

3. Start all services:
```bash
docker-compose up -d
```

This will start:
- PostgreSQL (port 5432)
- Qdrant (port 6333)
- FastAPI Backend (port 8000)
- Next.js Frontend (port 3000)

4. Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### Option B — CLI Usage (uv recommended)

Install [uv](https://docs.astral.sh/uv/) first, then:

```bash
git clone https://github.com/adityaxxz/Adra-AI.git
cd Adra-AI

uv venv
.\.venv\Scripts\Activate.ps1  # On Windows
source .venv/bin/activate  # On Linux/Mac

uv sync
```

Or with pip:

```bash
git clone https://github.com/adityaxxz/Adra-AI.git
cd Adra-AI

python -m venv .venv
.\.venv\Scripts\Activate.ps1  # On Windows
source .venv/bin/activate  # On Linux/Mac

pip install -r requirements.txt
```

Configure CLI-only environment:
```env
GROQ_API_KEY="your-groq-api-key"
GOOGLE_API_KEY="your-google-api-key"

LLM_MIN_INTERVAL_SEC=2.1
LLM_MAX_RETRIES=5
LLM_MAX_CONTENT_CHARS=10000
```

## Usage

### Web Application

1. **Authenticate**: Sign in with Google or GitHub OAuth
2. **Create Project**: Use the project generation mode to create new projects
3. **Connect Repository**: Add repositories for editing or question answering
4. **Track Progress**: Real-time updates via WebSocket during generation
5. **Manage Projects**: View, download, or delete generated projects

### CLI - Project Generation Mode

Run the CLI and enter a project description:

```bash
python main.py
```

Example prompts:

```text
Create a simple to-do list web application using HTML, CSS, and JavaScript
Create a simple calculator web application.
Create a simple blog API in FastAPI with a SQLite database.
Create a tic-tac-toe game with HTML, CSS, and JavaScript.
```

Optional flags:

```bash
python main.py --recursion-limit 100
python main.py -r 150
```

### CLI - Repository-Aware Editing Mode

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

Example prompts for repository editing:

```text
Add user authentication to this FastAPI application
Add error handling to all API endpoints
Refactor the database layer to use async operations
Add unit tests for the user service module
```

### CLI - Question Answering Mode

Ask questions about a repository without making changes:

```bash
python main.py --repo /path/to/repository --question
```

Example questions:

```text
How does the authentication system work in this codebase?
What is the purpose of the UserService class?
How are API endpoints structured in this application?
```

## OAuth Setup

### Google OAuth
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs:
   - Local development: `http://localhost:3000/auth/google/callback`
   - Production: `https://adra-ai.vercel.app/auth/google/callback`
6. Copy Client ID and Client Secret to `.env`

### GitHub OAuth
1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Create a new OAuth App
3. Set Authorization callback URLs:
   - Local development: `http://localhost:3000/auth/github/callback`
   - Production: `https://adra-ai.vercel.app/auth/github/callback`
4. Copy Client ID and Client Secret to `.env`

## Advanced Repository Features

### Code-Aware Chunking
The system uses language-specific chunking strategies:

- **Python**: AST-based parsing to extract imports, classes, functions, and modules
- **JavaScript/TypeScript**: Regex-based parsing for functions, classes, and components
- **Markdown**: Section-based chunking by headers
- **Generic**: Recursive character splitting with overlap

### Incremental Indexing
- Files are hashed using SHA256 to detect changes
- Only modified files are re-indexed
- Deleted files are removed from the vector store
- Significantly reduces indexing time for large repositories

### File Hash Management
- Consistent hashing for content integrity
- Hash-based change detection
- Efficient incremental updates

## API Documentation

Once the backend is running, access the interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Main API Endpoints

- `POST /projects` - Create a new project
- `GET /projects` - List user's projects
- `GET /projects/{id}` - Get project details
- `POST /repositories` - Add a repository
- `GET /repositories` - List user's repositories
- `POST /repositories/{id}/index` - Index a repository
- `POST /generate` - Start code generation
- `WS /ws/{session_id}` - WebSocket for real-time updates

## Deployment

For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).

### Live Production Architecture
The live project is fully deployed and configured using:
* **Frontend**: Deployed on [Vercel](https://vercel.com) (Next.js serverless app).
* **Backend**: Hosted on a [DigitalOcean Droplet](https://digitalocean.com) in the Bangalore (`blr1`) region, running:
  - **Docker Compose** container network (FastAPI API, PostgreSQL, Qdrant).
  - **Nginx** reverse proxy routing requests and handling WebSockets.
  - **Certbot / Let's Encrypt** for automated SSL/HTTPS.

### Quick Docker Deployment (Local)

```bash
docker-compose up -d
```

## Development

### Backend Development

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## Project Structure

```
Adra-AI/
├── agent/                 # Agent pipeline implementation
│   ├── graph.py          # LangGraph agent orchestration
│   ├── llm_client.py     # LLM client with throttling
│   ├── prompts.py        # Agent prompts
│   ├── repository/       # Repository-aware features
│   │   ├── code_aware_chunker.py
│   │   ├── file_hash.py
│   │   ├── scanner.py
│   │   ├── service.py
│   │   └── vector_store.py
│   └── tools.py          # File I/O tools
├── backend/              # FastAPI backend
│   ├── main.py           # API endpoints
│   ├── auth.py           # OAuth handlers
│   ├── db_models.py      # SQLAlchemy models
│   ├── websocket_manager.py
│   ├── background_tasks.py
│   └── services/
├── frontend/             # Next.js frontend
│   ├── app/
│   ├── components/
│   ├── api-client.ts
│   └── websocket-hook.ts
├── docker-compose.yml    # Docker services
├── main.py              # CLI entry point
└── requirements.txt     # Python dependencies
```

## Troubleshooting

### Docker Issues
```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Clean restart
docker-compose down -v
docker-compose up -d
```

### Database Issues
```bash
# Reset PostgreSQL
docker-compose exec postgres psql -U adrai -d adrai
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

### Vector Store Issues
```bash
# Reset Qdrant
docker-compose exec qdrant curl -X DELETE http://localhost:6333/collections/repo_chunks
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) file for details

## Acknowledgments

- Built with [LangGraph](https://langchain-ai.github.io/langgraph/) and [LangChain](https://github.com/langchain-ai/langchain)
- LLM providers: [Groq](https://groq.com/) and [Google AI](https://ai.google.dev/)
- Vector storage: [Qdrant](https://qdrant.tech/)
- Web framework: [FastAPI](https://fastapi.tiangolo.com/) and [Next.js](https://nextjs.org/)
