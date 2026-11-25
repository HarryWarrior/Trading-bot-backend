# Build from the repository root so libs/shared is in the context:
#   docker build -f services/journal/Dockerfile -t journal-service .
FROM python:3.12-slim

WORKDIR /srv
COPY libs/shared /srv/libs/shared
COPY services/journal /srv/service

RUN pip install --no-cache-dir /srv/libs/shared /srv/service

EXPOSE 8000
CMD ["uvicorn", "journal_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
