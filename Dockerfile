FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git && \
    rm -rf /var/lib/apt/lists/*

RUN curl https://cursor.com/install -fsS | bash

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --only main --with cursor

COPY code_agents/ code_agents/
COPY agents/ agents/

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python", "-m", "code_agents.main"]
