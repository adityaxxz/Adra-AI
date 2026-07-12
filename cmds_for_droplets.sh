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

