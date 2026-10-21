# hermes-jarvis: CPU only. The image holds no secrets and no voices; both live in the /data volume.
FROM python:3.12-slim

ARG EXTRAS=""
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".${EXTRAS:+[$EXTRAS]}"

RUN useradd --create-home --uid 1000 jarvis && mkdir /data && chown jarvis /data
USER jarvis

ENV HERMES_JARVIS_CONFIG=/data/config.yaml HJ_DATA_DIR=/data
VOLUME /data
# 8651: speech clips the device downloads (and /healthz). 8650: admin UI, only if ADMIN_PASSWORD is set.
EXPOSE 8651 8650

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["hermes-jarvis", "healthcheck"]

CMD ["hermes-jarvis", "run"]
