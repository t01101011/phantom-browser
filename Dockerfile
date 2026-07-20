FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PHANTOM_DATA_DIR=/data XDG_RUNTIME_DIR=/tmp/phantom-runtime DISPLAY=:99
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gosu xvfb x11vnc novnc websockify libgtk-3-0 libdbus-glib-1-2 \
      libasound2 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 phantom && useradd --uid 10001 --gid phantom --create-home phantom
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && python -m camoufox fetch \
    && chown -R phantom:phantom /app /home/phantom
COPY --chmod=755 packaging/linux-entrypoint.sh /usr/local/bin/phantom-linux
RUN mkdir -p /data /tmp/phantom-runtime && chown -R phantom:phantom /data /tmp/phantom-runtime
USER root
VOLUME ["/data"]
EXPOSE 5100
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
  CMD curl --fail --silent http://127.0.0.1:5100/healthz || exit 1
ENTRYPOINT ["/usr/local/bin/phantom-linux"]
