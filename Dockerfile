FROM python:3.8-slim AS compile-image
RUN apt-get update
RUN apt-get install -y --no-install-recommends build-essential gcc git

RUN python -m venv /opt/venv
# Make sure we use the virtualenv:
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements /requirements
RUN pip install --no-cache-dir -r /requirements/prod.txt

FROM python:3.8-slim AS build-image
COPY --from=compile-image /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
COPY library ./library


COPY csh_fantasy_bot ./csh_fantasy_bot
# COPY oauth2.json .
COPY run_ga.py .
# COPY compare_player_rankings.py .
COPY player_lookup.py .
COPY run_pygenetic.py .
# WORKDIR /app

CMD ["python","compare_player_rankings.py"]

# # FROM python:3.8-buster
# FROM craigham/pandas:latest
# RUN apt-get update
# RUN apt-get install -y --no-install-recommends build-essential gcc
# # Make sure we use the virtualenv:
# ENV PATH="/opt/venv/bin:$PATH"

# WORKDIR /app
# COPY requirements.txt .
# COPY library ./library
# RUN pip install --no-cache-dir -r requirements.txt

# COPY csh_fantasy_bot ./csh_fantasy_bot
# # COPY oauth2.json .
# COPY run_ga.py .
# # COPY compare_player_rankings.py .
# COPY player_lookup.py .
# COPY run_pygenetic.py .
# # WORKDIR /app

# CMD ["python","compare_player_rankings.py"]
#celery -A csh_fantasy_bot worker
# celery -A csh_fantasy_bot beat --loglevel=DEBUG
