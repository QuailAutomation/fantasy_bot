FROM python:3.7-buster

RUN apt-get update
RUN apt-get install -y --no-install-recommends build-essential gcc
# Make sure we use the virtualenv:
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY csh_fantasy_bot /app/csh_fantasy_bot
#COPY oauth2.json /app
COPY run_ga.py /app
WORKDIR /app

CMD ["python","run_ga.py"]
