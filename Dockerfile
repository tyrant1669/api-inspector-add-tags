
# FROM mcr.microsoft.com/playwright/python:v1.48.0-focal

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

EXPOSE 5000


CMD ["python", "app.py"]
