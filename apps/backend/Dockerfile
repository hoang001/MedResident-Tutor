FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/backend/pyproject.toml ./
COPY apps/backend/app ./app
RUN pip install --no-cache-dir .
COPY apps/backend/alembic.ini ./
COPY apps/backend/alembic ./alembic
COPY model-training/src /opt/pilot/src
ENV PYTHONPATH=/opt/pilot
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
