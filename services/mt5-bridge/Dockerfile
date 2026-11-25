# Build from the repository root so libs/shared is in the context:
#   docker build -f services/mt5-bridge/Dockerfile -t mt5-bridge-service .
FROM python:3.12-slim

WORKDIR /srv
COPY libs/shared /srv/libs/shared
COPY services/mt5-bridge /srv/service

RUN pip install --no-cache-dir /srv/libs/shared /srv/service

# The package is installed non-editable, so point at the EA shipped in the service folder.
ENV EA_FILE_PATH=/srv/service/ea/TradingJournalBridge.ex5

EXPOSE 8000
CMD ["uvicorn", "mt5_bridge_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
