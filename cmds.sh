uv add groq langchain langchain-core langchain-groq langgraph pydantic python-dotenv langchain-google-genai langchain-community

uv sync
uv pip install -r pyproject.toml


#run  backend (from root)
uvicorn backend.main:app --reload --port 8000

#run frontend from /frontend
npm run dev

# web console - ssh@root
cd /opt/adra-ai
git pull origin main
docker compose -f docker-compose.prod.yml down

docker compose -f docker-compose.prod.yml up -d --build

docker compose -f docker-compose.prod.yml up -d --build backend
docker compose -f docker-compose.prod.yml up -d --force-recreate backend

---

# logs
## Check Container Status:
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend

---

# state
docker stats --no-stream

---

cd /opt/adra-ai

# 1. Stop current docker services
docker compose -f docker-compose.prod.yml down

# 2. Run certbot for generating SSL cert
sudo certbot certonly --standalone -d adraai.adra.pw --agree-tos --email adityaranjan5995@gmail.com

# 3. Start services back up
docker compose -f docker-compose.prod.yml up -d --build


--- 

# After backend build regen the certs, nginx needs to verify

certbot certonly --standalone -d adraai.adra.pw

docker compose -f docker-compose.prod.yml up -d --build


---


