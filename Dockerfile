# Container image for the web API. Render deploys from render.yaml without this file;
# it is here so the service runs the same way on any container host.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wp_brief_agent ./wp_brief_agent
COPY fixtures ./fixtures

RUN useradd --create-home app
USER app

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn wp_brief_agent.api:app --host 0.0.0.0 --port ${PORT}"]
