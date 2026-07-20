# Task 16 — Stealth coherence release gate

Gate offline: `python scripts/stealth-coherence.py REPORT --output VERDICT`. Exit 1 khi drift/incoherence; `conditional_pass` cho optional surfaces đo không được và vẫn hiển thị `unsupported` (không giả PASS). `--require-complete` dùng khi release policy yêu cầu TLS/HTTP2/WebGPU/UA-CH đầy đủ.

Raw report có schema v1, tối thiểu hai `runs`; mỗi run bắt buộc `main`, `worker`, `shared_worker`, `service_worker`. Proxy credentials/token được redact trước artifact. Geo expected/observed được gate offline; probe mạng bên ngoài chỉ informational.

## Linux evidence 2026-07-20

Controlled localhost stock Chromium, persistent profile relaunch hai lần:

- raw: `task16-artifacts/linux-stock-chromium-raw.json`
- verdict: `task16-artifacts/linux-stock-chromium-verdict.json`
- checksums: `task16-artifacts/SHA256SUMS`
- verdict: `conditional_pass`, 21 pass / 0 fail / 6 unsupported
- unsupported: WebGPU adapter attestation, controlled TLS ClientHello và HTTP/2 capture (mỗi run)

Không dùng external anti-bot site làm gate. Không có bằng chứng Windows hay TLS capture trong repo.

## Readiness matrix

| Hạng mục | Linux | Windows | Blocker chính xác |
|---|---|---|---|
| Core Python/control plane | PASS | Chưa native verify | Task 13 Windows CI |
| Desktop/package release | PASS (Task 14) | IMPLEMENTED/PENDING | Native `windows-latest` installer/portable cold-start, browser launch/stop/no-orphan chưa chạy |
| Task16 deterministic coherence | PASS có unsupported explicit | Workflow đã cấu hình, chưa chạy | Native Windows artifact/evidence chưa có |
| Dedicated/Shared/Service Worker | PASS controlled Linux | Pending | Native Windows run |
| UA/UA-CH | PASS stock Chromium Linux | Pending | Native Windows run |
| WebGL/WebGPU | WebGL PASS; WebGPU unsupported | Pending | GPU thật/adapter attestation |
| Locale/timezone/proxy geo | Offline deterministic PASS | Pending | Real proxy network geo chỉ informational, không chạy trong unit gate |
| Fonts/WebRTC | PASS controlled (không STUN) | Pending | Real proxy/STUN leak probe informational |
| TLS ClientHello/HTTP2 | UNSUPPORTED, không claim | UNSUPPORTED | Cần controlled server/packet capture |

**Project overall: chưa release-ready đa nền tảng** do Task 13 native Windows CI và controlled TLS/HTTP2/GPU acceptance còn thiếu. Linux roadmap/task acceptance hoàn tất theo policy cho phép unsupported được công khai.
