# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
# Single worker on purpose: the WebSocket connection registry is in-memory,
# so all live sockets must live in one process (scale later via Redis pub/sub).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
