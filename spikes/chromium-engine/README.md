# Chromium engine spike

Mục tiêu của spike là đo cùng một schema trên binary thật, không dùng điểm số marketing và không thay engine production.

## Probe

`probe.py` nhận một executable rõ ràng, tạo/khởi động lại persistent `user-data-dir`, attach và reconnect CDP, rồi ghi JSON canonical có SHA-256. Các surface: binary, persistence, CDP, UA/UA-CH, main/Worker, WebGL/WebGPU, fonts, canvas/audio/client rects, WebRTC/DNS và trạng thái TLS/HTTP2.

```bash
python spikes/chromium-engine/probe.py \
  --candidate stock-chromium \
  --executable /absolute/path/to/chrome \
  --user-data-dir /tmp/phantom-probe-profile \
  --output spike/chromium-engine-results/stock.json
```

Probe chạy headless để tái lập trong CI. `--no-sandbox` chỉ dành cho môi trường spike/container bị hạn chế, không phải default runtime. TLS/HTTP2 được ghi `not_measured` có lý do vì JavaScript trong browser không thể tự chứng thực TLS ClientHello hay HTTP/2 framing; Task 16 phải dùng server/packet capture kiểm soát.

## Runs ngày 2026-07-20 (Linux x86_64)

| Candidate | Browser | Binary SHA-256 | Persistence | CDP reconnect | Report SHA-256 |
|---|---|---|---|---|---|
| Playwright stock Chromium 1223 | 148.0.7778.96 | `adc1c21ceed5c2a67184766376fe816ac03e556cc0ca3f782e8212235fe05c6f` | PASS | PASS | `47027554d90547f285ae987be35013d7b4b83ac40441287406f7d4b01414396c` |
| Clearcote v0.1.0-pre.22 | 149.0.7827.114 | `aea54f3c1b5bfc43b4c42aff00d41df49393575950df7c644cc580f72462db4a` | PASS | PASS | `c464c10eb2d5dfb676905cad6426c04c752033e53e38220add61db569694581f` |
| fingerprint-chromium 148.0.7778.215 | 148.0.7778.215 | `abd700e6015e259a00f1a31e99ad16f99f63365222328937454e8f603f575284` | PASS | PASS | `b93542a3587a3faa8e08ca1d423a0d40399857f330d5e02e6107e2c80932cd0d` |

Raw reports nằm trong `spike/chromium-engine-results/`. Candidate archives/profiles không được giữ trong source tree.

## Candidate availability / boundary

- **Clearcote:** BSD-3-Clause, patch/source repo và signed/checksummed Linux x64 + Windows x64 assets. Downloaded Linux archive checksum matched publisher SHA-256 (`662597…ec53`). Rapid pre-release cadence; compatibility risk remains.
- **fingerprint-chromium:** BSD-3-Clause metadata, Linux x64 and Windows x64 release binaries. Probe works, but distribution/source provenance and update process need stronger audit before adoption.
- **Donut/Wayfern:** Donut app has Linux/Windows artifacts but is AGPL-3.0. Wayfern is a separately downloaded browser with explicit terms acceptance and is managed by Donut; this is not a clean redistributable engine artifact for Phantom. Not installed/run in this spike.
- Windows binary availability was audited from release assets only. **No Windows execution claim.**

Xem ADR: `docs/chromium-engine-decision.md`.
