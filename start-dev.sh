#!/bin/bash
set -e

echo "Aethos Docker Startup"
echo "===================="

if [ ! -f .env ]; then
    echo ".env not found. Creating from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your API keys, then run again."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found. Please install Docker first."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 not found. Please update Docker."
    exit 1
fi

echo "Configuration looks good."
echo

echo "Building and starting services..."
docker compose up -d --build

echo
echo "Waiting for services to become healthy..."
sleep 10

echo "Health checks"

if curl -fsS http://localhost:8080/v1/models > /dev/null; then
    echo "  [OK]   Backend: http://localhost:8080"
else
    echo "  [FAIL] Backend: http://localhost:8080"
fi

if curl -fsS http://localhost:3000 > /dev/null; then
    echo "  [OK]   Frontend: http://localhost:3000"
else
    echo "  [FAIL] Frontend: http://localhost:3000"
fi

echo
echo "Startup complete."
echo "Open http://localhost:3000 in your browser."
echo
echo "Useful commands"
echo "  docker compose ps"
echo "  docker compose logs -f aethos-backend"
echo "  docker compose logs -f aethos-frontend"
echo "  docker compose down"
