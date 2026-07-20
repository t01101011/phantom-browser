# noVNC human takeover

noVNC is optional and controls the **same Xvfb display/browser process** as the
agent. It does not launch a second browser. Enable only after creating an
x11vnc password file (`x11vnc -storepasswd`) outside the repository:

```sh
PHANTOM_NOVNC=1 PHANTOM_VNC_PASSWORD_FILE=$HOME/.config/phantom/vnc.pass \
  docker compose up -d
ssh -N -L 6080:127.0.0.1:6080 user@vps
# open http://127.0.0.1:6080/vnc.html locally
```

API and viewer ports bind to loopback on the host by default. For remote access
use SSH, Tailscale, or an authenticated TLS reverse tunnel. Never publish 6080
or 5100 directly to the Internet. The VNC password file and API token under the
persistent data volume are runtime secrets; do not put either in image layers,
Compose environment values, source control, URLs, or logs.

Takeover protocol:
1. Agent calls `POST /v1/sessions/{id}/takeover` with its lease token and generation.
2. Agent input is rejected while the human uses noVNC.
3. Human/controller calls `POST .../takeover/release` with the one-time takeover token.
4. A new agent lease is returned; the first action must be `snapshot` so stale refs cannot be reused.

CAPTCHA and third-party login remain manual acceptance boundaries; this feature
does not bypass challenges.
