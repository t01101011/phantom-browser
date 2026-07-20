#!/bin/sh
set -eu
umask 077
if [ "$(id -u)" = 0 ]; then
  mkdir -p /data /data/artifacts /tmp/phantom-runtime
  chown -R phantom:phantom /data /tmp/phantom-runtime
  exec gosu phantom "$0" "$@"
fi
export DISPLAY="${DISPLAY:-:99}"
mkdir -p /data /data/artifacts /tmp/phantom-runtime
chmod 700 /data /data/artifacts /tmp/phantom-runtime

children=""
cleanup() {
  trap - TERM INT EXIT
  for pid in $children; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in $children; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup TERM INT EXIT

Xvfb "$DISPLAY" -screen 0 "${PHANTOM_SCREEN:-1920x1080x24}" -nolisten tcp &
children="$children $!"

if [ "${PHANTOM_NOVNC:-0}" = "1" ]; then
  : "${PHANTOM_VNC_PASSWORD_FILE:?mount PHANTOM_VNC_PASSWORD_FILE to enable noVNC}"
  test -r "$PHANTOM_VNC_PASSWORD_FILE"
  x11vnc -display "$DISPLAY" -localhost -forever -shared -rfbauth "$PHANTOM_VNC_PASSWORD_FILE" &
  children="$children $!"
  websockify --web=/usr/share/novnc/ "${PHANTOM_NOVNC_LISTEN:-127.0.0.1:6080}" localhost:5900 &
  children="$children $!"
fi

uvicorn 'phantom.api.app:create_app' --factory --host "${PHANTOM_BIND:-0.0.0.0}" --port "${PHANTOM_PORT:-5100}" &
api_pid=$!
children="$children $api_pid"
wait "$api_pid"
