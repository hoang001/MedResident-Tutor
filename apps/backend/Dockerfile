FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/backend/pyproject.toml ./
COPY apps/backend/app ./app
ARG INSTALL_RETRIEVAL=false
RUN if [ "$INSTALL_RETRIEVAL" = "true" ]; then pip install --no-cache-dir '.[retrieval]'; else pip install --no-cache-dir .; fi
COPY apps/backend/alembic.ini ./
COPY apps/backend/alembic ./alembic
COPY model-training/src /opt/pilot/src
COPY services/medical/medical_service /opt/model-service/medical_service
ENV PYTHONPATH=/opt/pilot
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
