FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --chown=app:app app ./app
COPY --chown=app:app tests ./tests
COPY docker-entrypoint.sh /usr/local/bin/ml-app-entrypoint
RUN chmod 755 /usr/local/bin/ml-app-entrypoint && chown app:app /app

ENTRYPOINT ["ml-app-entrypoint"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
