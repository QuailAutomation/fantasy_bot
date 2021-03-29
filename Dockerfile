FROM python:3.8-slim AS compile-image
RUN apt-get update
RUN apt-get install -y --no-install-recommends build-essential gcc git libxml2 libxslt-dev

RUN python -m venv /opt/venv
# Make sure we use the virtualenv:
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements /requirements
RUN pip install --no-cache-dir -r /requirements/prod.txt

# lets grab gekko runtimes
WORKDIR /
RUN git clone https://github.com/APMonitor/apm_server.git


FROM python:3.8-slim AS build-image
#RUN apt-get update
#RUN apt-get install -y gnupg2 libnss3 libgconf-2-4 wget

#RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
# RUN echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' | tee /etc/apt/sources.list.d/google-chrome.list
#RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
#RUN apt install -y ./google-chrome-stable_current_amd64.deb
#RUN apt-get install -y google-chrome-stable

COPY --from=compile-image /opt/venv /opt/venv
COPY --from=compile-image /apm_server/apm_linux/bin/apm /usr/local/bin
RUN chmod a+x /usr/local/bin/apm

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# COPY requirements.txt .
COPY library ./library


COPY csh_fantasy_bot ./csh_fantasy_bot
# COPY oauth2.json .
COPY run_ga.py .
# COPY compare_player_rankings.py .
COPY player_lookup.py .
COPY chrome-ublock.crx .
COPY run_pygenetic.py .
COPY run_roster_check.py .
COPY run.py .
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
