FROM python:3.11-slim

WORKDIR /app

ADD https://www.syndiode.com/downloads/nomad_sustainability_worker.py /app/nomad_sustainability_worker.py

ENV PYTHONUNBUFFERED=1
ENV NOMAD_BASE_URL=https://www.syndiode.com

CMD ["python", "/app/nomad_sustainability_worker.py", "--heartbeat", "--loop", "--cycles", "0"]
