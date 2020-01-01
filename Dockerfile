FROM python:3.7-buster

RUN apt-get update
RUN apt-get install -y --no-install-recommends build-essential gcc
# Make sure we use the virtualenv:
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY csh_fantasy_bot /app/csh_fantasy_bot
COPY run_ga.py /app
WORKDIR /app
#CMD ["gunicorn", "-w 4", "main:app"]