export const BROWSER_PROBE_SOURCE = String.raw`async () => {
  const digest = async (value) => {
    // Stable non-cryptographic digest: runtime probes can execute in engines
    // where WebCrypto is unavailable. Binary provenance still uses SHA-256
    // in the Node harness.
    const text = String(value);
    let first = 0x811c9dc5; let second = 0x9e3779b9;
    for (let index = 0; index < text.length; index += 1) {
      const code = text.charCodeAt(index);
      first = Math.imul(first ^ code, 0x01000193) >>> 0;
      second = Math.imul(second ^ code, 0x85ebca6b) >>> 0;
    }
    return first.toString(16).padStart(8, "0") + second.toString(16).padStart(8, "0");
  };
  const result = {};
  const safe = async (name, probe) => {
    try {
      result[name] = { status: "OBSERVED", method: "browser-runtime", value: await probe() };
    } catch (error) {
      result[name] = { status: "UNKNOWN", method: "browser-runtime", reason: String(error?.message ?? error) };
    }
  };

  await safe("canvas", async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 320; canvas.height = 80;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    ctx.textBaseline = "alphabetic";
    ctx.font = "18px Arial";
    ctx.fillStyle = "#13202b"; ctx.fillRect(0, 0, 320, 80);
    ctx.fillStyle = "#95ff8f"; ctx.fillText("Phantom coverage 0123456789", 8, 34);
    ctx.strokeStyle = "#71384f"; ctx.arc(250, 42, 24, 0, Math.PI * 1.7); ctx.stroke();
    return { digest: await digest(canvas.toDataURL()), width: canvas.width, height: canvas.height };
  });

  await safe("audioContext", async () => {
    const Audio = globalThis.OfflineAudioContext ?? globalThis.webkitOfflineAudioContext;
    if (!Audio) throw new Error("OfflineAudioContext unavailable");
    const context = new Audio(1, 4096, 44100);
    const oscillator = context.createOscillator();
    const compressor = context.createDynamicsCompressor();
    oscillator.type = "triangle"; oscillator.frequency.value = 10000;
    oscillator.connect(compressor); compressor.connect(context.destination); oscillator.start(0);
    const rendered = await context.startRendering();
    const sample = Array.from(rendered.getChannelData(0).slice(0, 512));
    return { digest: await digest(sample.map((v) => v.toFixed(8)).join(",")), sampleCount: sample.length, sampleRate: rendered.sampleRate };
  });

  await safe("webgl", async () => {
    const gl = document.createElement("canvas").getContext("webgl");
    if (!gl) throw new Error("WebGL unavailable");
    const extension = gl.getExtension("WEBGL_debug_renderer_info");
    const pixels = new Uint8Array(4);
    gl.clearColor(0.125, 0.25, 0.5, 1); gl.clear(gl.COLOR_BUFFER_BIT); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    return {
      vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER),
      unmaskedVendor: extension ? gl.getParameter(extension.UNMASKED_VENDOR_WEBGL) : null,
      unmaskedRenderer: extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : null,
      readbackDigest: await digest(Array.from(pixels).join(",")),
    };
  });

  await safe("fonts", async () => {
    const candidates = ["Arial", "Times New Roman", "Courier New", "Noto Sans", "Segoe UI", "Helvetica Neue"];
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas text metrics unavailable");
    const sample = "mmmmmmmmmmlliWW00";
    context.font = "72px monospace";
    const baseline = context.measureText(sample).width;
    const widths = {};
    for (const font of candidates) {
      context.font = '72px "' + font + '", monospace';
      const width = context.measureText(sample).width;
      widths[font] = { width: Number(width.toFixed(4)), differsFromFallback: Math.abs(width - baseline) > 0.01 };
    }
    return { sampleDigest: await digest(sample), baseline: Number(baseline.toFixed(4)), candidates: widths };
  });

  await safe("domRect", async () => {
    const box = document.createElement("div");
    box.style.cssText = "position:absolute;left:13.25px;top:7.5px;width:123.75px;height:45.5px;padding:3.25px;border:1.5px solid transparent;font:13px Arial";
    box.textContent = "Phantom DOMRect probe wraps text consistently";
    document.body.append(box);
    const rect = box.getBoundingClientRect(); const clientRects = Array.from(box.getClientRects(), (r) => [r.x, r.y, r.width, r.height]);
    box.remove();
    const tuple = [rect.x, rect.y, rect.width, rect.height, ...clientRects.flat()].map((v) => Number(v.toFixed(4)));
    return { tuple, digest: await digest(tuple.join(",")) };
  });

  await safe("uaClientHints", async () => {
    const uaData = navigator.userAgentData;
    const highEntropy = uaData?.getHighEntropyValues ? await uaData.getHighEntropyValues(["architecture", "bitness", "model", "platformVersion", "uaFullVersion", "fullVersionList", "wow64"]) : null;
    return { userAgent: navigator.userAgent, appVersion: navigator.appVersion, uaData: uaData ? { brands: uaData.brands, mobile: uaData.mobile, platform: uaData.platform, highEntropy } : null };
  });

  await safe("screen", () => ({
    width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight,
    colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth, dpr: devicePixelRatio,
    innerWidth, innerHeight, outerWidth, outerHeight,
  }));
  await safe("cpuRam", () => ({ hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory ?? null }));
  await safe("timezone", () => ({ timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone, offsetMinutes: new Date().getTimezoneOffset() }));
  await safe("localeLanguages", () => ({ language: navigator.language, languages: navigator.languages, intlLocale: Intl.DateTimeFormat().resolvedOptions().locale }));

  await safe("geolocation", async () => {
    if (!navigator.geolocation) throw new Error("Geolocation API unavailable");
    const position = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Geolocation timed out")), 3000);
      navigator.geolocation.getCurrentPosition((value) => { clearTimeout(timer); resolve(value); }, (error) => { clearTimeout(timer); reject(new Error('Geolocation error ' + error.code)); }, { timeout: 2500, maximumAge: 0 });
    });
    return { latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy };
  });

  await safe("webrtc", async () => {
    if (!globalThis.RTCPeerConnection) throw new Error("RTCPeerConnection unavailable");
    const pc = new RTCPeerConnection({ iceServers: [] });
    const candidates = [];
    pc.createDataChannel("probe");
    pc.onicecandidate = (event) => { if (event.candidate?.candidate) candidates.push(event.candidate.candidate); };
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((resolve) => { const timer = setTimeout(resolve, 2500); pc.onicegatheringstatechange = () => { if (pc.iceGatheringState === "complete") { clearTimeout(timer); resolve(); } }; });
    const stats = await pc.getStats();
    const statsTypes = {}; stats.forEach((entry) => { statsTypes[entry.type] = (statsTypes[entry.type] ?? 0) + 1; });
    pc.close();
    return { candidateTypes: candidates.map((candidate) => candidate.match(/ typ ([a-z]+)/)?.[1] ?? "unknown"), candidateCount: candidates.length, statsTypes };
  });

  return result;
}`;
