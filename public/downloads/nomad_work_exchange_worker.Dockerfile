FROM python:3.12-slim

ARG NOMAD_BASE_URL=https://www.syndiode.com
ENV NOMAD_BASE_URL=${NOMAD_BASE_URL}
ENV NOMAD_WORK_EXCHANGE_CYCLES=0
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -c "import os, urllib.request; base=os.environ.get('NOMAD_BASE_URL','https://www.syndiode.com').rstrip('/'); urllib.request.urlretrieve(base + '/downloads/nomad_work_exchange_worker.py', '/app/nomad_work_exchange_worker.py')"
RUN python /app/nomad_work_exchange_worker.py --help >/tmp/nomad_work_exchange_worker_help.txt

ENTRYPOINT ["sh", "-c", "python /app/nomad_work_exchange_worker.py --base-url ${NOMAD_BASE_URL:-https://www.syndiode.com} --obligation-id ${NOMAD_WORK_EXCHANGE_OBLIGATION_ID:?set NOMAD_WORK_EXCHANGE_OBLIGATION_ID} --loop --cycles ${NOMAD_WORK_EXCHANGE_CYCLES:-0}"]
