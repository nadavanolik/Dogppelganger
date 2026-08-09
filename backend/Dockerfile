# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
# 2 gunicorn workers serving the Flask app factory (main.py exposes `app`).
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "main:app"]
