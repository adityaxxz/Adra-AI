SaaS Transformation Plan for Adra-AI
Transform the CLI-based multi-agent coding assistant into a production-quality SaaS with Next.js + FastAPI + PostgreSQL + Qdrant.

Architecture Overview


┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                       │
│  - OAuth auth (Google/GitHub)                               │
│  - Project dashboard                                         │
│  - WebSocket real-time progress                              │
│  - Repository upload & QA interface                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ WebSocket + REST API
┌──────────────────────▼──────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  - OAuth authentication middleware                          │
│  - REST API endpoints                                        │
│  - WebSocket manager for progress streaming                  │
│  - Background task processing                                │
│  - Existing agent pipeline (LangGraph)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
┌───────▼─────────┐        ┌────────▼────────┐
│  PostgreSQL     │        │    Qdrant        │
│  - Users        │        │  - Vector store  │
│  - Projects     │        │  - Collections   │
│  - Repositories │        │  - Embeddings    │
│  - Sessions     │        │                 │
└─────────────────┘        └─────────────────┘
Implementation Steps
Phase 1: Infrastructure Setup

Create project structure: frontend/ (Next.js) + backend/ (FastAPI)
Set up Docker Compose with PostgreSQL, Qdrant, and backend services
Configure environment variables for OAuth, databases, and LLM keys
Phase 2: Backend Core 4. Migrate vector store from ChromaDB to Qdrant 5. Create PostgreSQL models (User, Project, Repository, Session) 6. Implement OAuth authentication (NextAuth/JWT) 7. Set up WebSocket manager for real-time progress streaming 8. Create background task processor (Celery/async tasks) for agent execution 9. Build REST API endpoints (auth, projects, repositories, generation) 10. Integrate existing agent pipeline with database storage

Phase 3: Frontend Development 11. Set up Next.js with TypeScript and Tailwind CSS 12. Implement OAuth authentication flow 13. Create project dashboard with project list/creation 14. Build project generation UI with WebSocket progress updates 15. Create repository upload/management interface 16. Implement question-answering interface 17. Add project preview and download functionality

Phase 4: Integration & Polish 18. End-to-end testing of all three modes (generation, editing, QA) 19. Add error handling and rate limiting 20. Create deployment documentation (Docker + cloud setup)

Key Files to Create/Modify
New Structure:



Adra-AI/
├── frontend/              # Next.js app
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
├── backend/               # FastAPI app
│   ├── api/               # API routes
│   ├── core/              # Auth, config, security
│   ├── models/            # Database models
│   ├── services/          # Business logic
│   ├── websocket/         # WebSocket manager
│   ├── agent/             # Existing agent code (migrated)
│   ├── main.py
│   └── requirements.txt
├── docker-compose.yml     # Multi-service orchestration
└── .env.example           # Updated config
Major Changes:

Replace ChromaDB → Qdrant in backend/agent/repository/vector_store.py
Add OAuth auth in backend/core/auth.py
Create PostgreSQL models in backend/models/
Add WebSocket manager in backend/websocket/manager.py
Migrate agent execution to async background tasks
Store generated projects in PostgreSQL instead of filesystem
Verification Strategy
Run Docker Compose and verify all services start
Test OAuth flow (Google/GitHub login)
Create a project via UI and verify WebSocket progress streaming
Test repository upload and indexing
Verify all three agent modes work end-to-end
Test deployment on VPS (optional cloud validation)
Risks/Considerations
Complexity tradeoff: Adding auth, WebSocket, and background tasks increases complexity
Agent execution time: Long-running agent tasks need proper timeout handling
Qdrant migration: Need to handle ChromaDB → Qdrant data format differences
Resume scope: Keep scope minimal - avoid admin panels, billing, advanced analytics