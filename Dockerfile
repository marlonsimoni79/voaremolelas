FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY static ./static

EXPOSE 5555

CMD ["gunicorn", "-b", "0.0.0.0:5555", "--workers", "2", "--timeout", "60", "app.main:app"]
