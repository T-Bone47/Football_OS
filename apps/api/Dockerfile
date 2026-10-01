# Python version matches CI and requirements.lock (3.11).
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY apps/api/app ./app
# Migrations ship with the image so a release can run `alembic upgrade head`
# from the same artifact it deploys.
COPY alembic.ini ./
COPY database ./database
# Registered model artifacts: serving verifies their SHA-256 against the registry.
COPY data/models ./data/models
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
