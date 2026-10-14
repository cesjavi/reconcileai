# Build context: repository root (see docker-compose.yml)
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/srv/apps/api:/srv/services/reconciliation:/srv/services/inference:/srv/services/evolus
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt
COPY apps/api apps/api
COPY services services
COPY demo demo
WORKDIR /srv/apps/api
ENV DEMO_DIR=/srv/demo
RUN useradd -m app && chown -R app /srv
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
