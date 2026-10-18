# Self-contained: the build context is this directory. Standard library only,
# so there is nothing to install.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

COPY app ./app

# Unprivileged, because this is the process that talks to the internet and
# parses what comes back. It needs to write nothing.
RUN useradd --system --uid 10001 --no-create-home sidecar
USER sidecar

# Documentation only: the compose service publishes NO host port.
EXPOSE 8000

CMD ["python", "-m", "app.server"]
