# ADR: Chromium engine-level backend

- **Ngày:** 2026-07-20
- **Trạng thái:** Chấp nhận có điều kiện — chọn Clearcote cho adapter experimental; chưa thay default Camoufox

## Bối cảnh

Phantom cần Chromium engine-level thay vì JavaScript injection. Task 15 yêu cầu đo binary thật theo matrix, từ chối kiến trúc mù và không auto-fallback. Probe/schema được viết trước khi cài candidate; raw reports và checksums được lưu tại `spike/chromium-engine-results/`.

## Kết quả Linux đo được

Cả stock Chromium 148, Clearcote 149 pre.22 và fingerprint-chromium 148 đều:

- launch bằng persistent user-data-dir;
- attach/reconnect CDP và giữ localStorage qua browser relaunch;
- trả main/DedicatedWorker đồng nhất cho UA/platform/languages/hardwareConcurrency;
- expose UA/UA-CH, WebGL/WebGPU, fonts, canvas/audio/client rects;
- không có lỗi probe.

Sai khác raw đáng chú ý:

- Stock có `HeadlessChrome` UA, SwiftShader và WebRTC host candidates mDNS.
- Clearcote trả Chrome UA (không `HeadlessChrome`), main/worker đồng nhất, Intel/D3D11-shaped renderer, 48 kHz audio và không trả ICE candidate trong fixture.
- fingerprint-chromium trả Chrome UA, main/worker đồng nhất, SwiftShader và không trả ICE candidate.
- Canvas của cả ba bằng nhau trong fixture này. Đây không phải bằng chứng stealth đầy đủ.
- TLS/HTTP2 chưa đo vì cần controlled capture ngoài browser. ServiceWorker chỉ xác nhận API support; chưa có execution parity assertion. Windows chỉ xác nhận có release asset, chưa chạy.

## Ma trận quyết định

| Tiêu chí | Clearcote | fingerprint-chromium | Donut/Wayfern |
|---|---|---|---|
| Linux + Windows binaries | Có, release assets | Có, release assets | Donut app có; Wayfern riêng |
| Persistent UDD / CDP | PASS Linux | PASS Linux | Chưa probe |
| Engine-level claim/source | Chromium C++ patches, public build | Chromium fork/patches | Wayfern binary qua manager |
| License | BSD-3-Clause | BSD-3-Clause metadata | Donut AGPL-3.0; Wayfern terms riêng |
| Update cadence | Nhanh nhưng pre-release | Active | Active app, coupling cao |
| Redistributable adapter fit | Tốt nhất trong các candidate | Cần provenance audit thêm | Không phù hợp core adapter hiện tại |

## Quyết định

1. **Clearcote là candidate duy nhất cho một adapter Chromium experimental**, sau Task 16 coherence gate và native Windows run.
2. **Camoufox vẫn là default production.** Task 15 không thêm engine vào profile/runtime và không quảng cáo parity.
3. Engine phải là lựa chọn explicit trong profile (`camoufox` hoặc future `clearcote`); **không auto-fallback** giữa engines.
4. Không chọn Donut/Wayfern: đó là app/manager có coupling và terms/license riêng, không phải dependency engine sạch cho core.
5. Không chọn fingerprint-chromium lúc này: probe cơ bản tốt nhưng lợi thế đo được so với Clearcote thấp hơn và provenance/update/redistribution cần audit sâu hơn.
6. Không chấp nhận candidate JS-injection-only làm default antidetect engine.

## Điều kiện trước khi adapter production

Task 16 phải gate relaunch determinism; main/Worker/SharedWorker/ServiceWorker; UA/UA-CH; WebGL/WebGPU trên GPU thật; font metrics; timezone/locale/proxy geo; WebRTC leak; và TLS ClientHello/HTTP2 capture. Chạy native Linux headed và Windows, archive report; đánh giá license/security của downloader và checksum/signature pinning. Nếu gate không xanh, defer Chromium thay vì fallback âm thầm.
