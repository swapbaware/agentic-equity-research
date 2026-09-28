FROM python:3.11-slim AS builder

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir uvicorn[standard]

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
