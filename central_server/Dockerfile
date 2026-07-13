FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mqtt_subscriber.py .
COPY database_handler.py .

CMD ["python", "-u", "mqtt_subscriber.py"]
