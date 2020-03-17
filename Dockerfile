#FROM python:3.7-buster
FROM craigham/pandas-1.0.1:latest
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
COPY compare_player_rankings.py /app
WORKDIR /app

CMD ["python","compare_player_rankings.py"]
#celery -A csh_fantasy_bot worker
# celery -A csh_fantasy_bot beat --loglevel=DEBUG
