FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code is mounted via volumes at runtime
ENV PYTHONPATH=/app:/opt

CMD ["uvicorn", "admin.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
