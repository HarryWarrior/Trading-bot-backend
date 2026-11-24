# Build from the repository root so libs/shared is in the context:
#   docker build -f services/mt5/Dockerfile -t mt5-service .
FROM python:3.12-slim

WORKDIR /srv
COPY libs/shared /srv/libs/shared
COPY services/mt5 /srv/service

RUN pip install --no-cache-dir /srv/libs/shared /srv/service

EXPOSE 8000
CMD ["uvicorn", "mt5_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
