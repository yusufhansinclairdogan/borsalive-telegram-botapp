(function () {
  "use strict";

  const qs = (sel, el = document) => el.querySelector(sel);
  const clamp = (val, min, max) => Math.min(max, Math.max(min, val));
  const fmtNumber = (v, d = 2) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  const fmtPercent = (v, d = 2) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    const formatted = n.toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
    return (n >= 0 ? "+" : "") + formatted + "%";
  };
  const toNumber = (v) => {
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const normSymbol = (sym) => (sym || "").toString().trim().toUpperCase();
  const timeFromTs = (ts) => {
    if (!ts) return null;
    let n = Number(ts);
    if (!Number.isFinite(n)) return null;
    if (n > 1e14) n = Math.round(n / 1000);
    if (n > 1e11) {
      try {
        return new Date(n).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      } catch (err) {
        return null;
      }
    }
    return null;
  };

  const root = document.documentElement;
  const themeBtn = qs("#themeToggle");
  const THEME_ICONS = {
    sun: '<span class="knob"></span><svg class="sun" viewBox="0 0 24 24" width="18" height="18"><path d="M12 4V2m0 20v-2M4.93 4.93L3.51 3.51m16.98 16.98l-1.42-1.42M4 12H2m20 0h-2M4.93 19.07l-1.42 1.42m16.98-16.98l-1.42 1.42M12 8a4 4 0 100 8 4 4 0 000-8z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path></svg>',
    moon: '<span class="knob"></span><svg class="moon" viewBox="0 0 24 24" width="18" height="18"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"></path></svg>'
  };

  function paintThemeIcon() {
    if (!themeBtn) return;
    const dark = root.classList.contains("dark");
    themeBtn.innerHTML = dark ? THEME_ICONS.sun : THEME_ICONS.moon;
  }

  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      root.classList.toggle("dark");
      try { localStorage.setItem("theme", root.classList.contains("dark") ? "dark" : "light"); } catch (err) { }
      paintThemeIcon();
    });
    themeBtn.addEventListener("pointerdown", (e) => e.preventDefault(), { passive: false });
    paintThemeIcon();
  }

  const statusEl = qs("#status");
  const lastUpdateEl = qs("#lastUpdate");
  const liveBadge = qs("#liveBadge");
  const gridEl = qs("#heatmapGrid");
  const emptyEl = qs("#heatmapEmpty");
  const infoPanel = qs("#infoPanel");
  const infoClose = qs("#infoClose");
  const btnInfo = qs("#btnInfo");
  const drawer = qs("#drawer");
  const backdrop = qs("#backdrop");
  const btnMenu = qs("#btnMenu");
  const btnCloseDrawer = qs("#drawerClose");
  const navDepth = qs("#navDepth");
  const navAkd = qs("#navAkd");
  const drawerDepth = qs("#drawerDepth");
  const drawerAkd = qs("#drawerAkd");
  const MAX_TILES = 60;

  const tiles = new Map();

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setLive(on) {
    if (liveBadge) liveBadge.classList.toggle("off", !on);
  }

  function hideEmpty() {
    emptyEl && emptyEl.classList.add("hide");
  }

  function showEmpty(msg) {
    if (emptyEl) {
      emptyEl.textContent = msg || "Veri bekleniyor…";
      emptyEl.classList.remove("hide");
    }
  }

  function gradientFor(pct) {
    const n = Number(pct);
    if (!Number.isFinite(n)) {
      return {
        start: "rgba(30, 41, 59, 0.6)",
        stop: "rgba(15, 23, 42, 0.7)",
      };
    }
    const clamped = clamp(n, -12, 12);
    const ratio = (clamped + 12) / 24; // 0-1
    const hue = 6 + ratio * 110; // red (~6) to green (~116)
    const intensity = Math.min(1, Math.abs(clamped) / 8);
    const sat = 60 + intensity * 30;
    const light = 40 - intensity * 12;
    const delta = (ratio - 0.5) * 28;
    return {
      start: `hsla(${hue.toFixed(2)}, ${sat.toFixed(1)}%, ${(light + 4).toFixed(1)}%, 0.95)`,
      stop: `hsla(${(hue + delta).toFixed(2)}, ${(sat + 6).toFixed(1)}%, ${(light - 4).toFixed(1)}%, 0.9)`,
    };
  }

  function ensureTile(symbol) {
    let tile = tiles.get(symbol);
    if (tile) return tile;
    tile = document.createElement("button");
    tile.type = "button";
    tile.className = "heatmap-tile";
    tile.dataset.symbol = symbol;

    const head = document.createElement("div");
    head.className = "tile-head";
    const symEl = document.createElement("span");
    symEl.className = "tile-symbol";
    symEl.textContent = symbol;
    const pctEl = document.createElement("span");
    pctEl.className = "tile-pct";
    pctEl.textContent = "—";
    head.appendChild(symEl);
    head.appendChild(pctEl);

    const body = document.createElement("div");
    body.className = "tile-body";
    const lastEl = document.createElement("span");
    lastEl.className = "tile-last";
    lastEl.textContent = "—";
    const labelEl = document.createElement("span");
    labelEl.className = "tile-label";
    labelEl.textContent = "Son Fiyat";
    body.appendChild(lastEl);
    body.appendChild(labelEl);

    tile.appendChild(head);
    tile.appendChild(body);

    tile._refs = { symEl, pctEl, lastEl };

    tile.addEventListener("click", () => {
      const sym = tile.dataset.symbol;
      if (!sym) return;
      const target = `/webapp/depth?symbol=${encodeURIComponent(sym)}`;
      if (window.Telegram?.WebApp) {
        try {
          window.location.href = target;
          return;
        } catch (err) { }

      }
      window.location.href = target;
    });

    tiles.set(symbol, tile);
    return tile;
  }

  function updateTile(tile, payload) {
    const refs = tile._refs || {};
    if (refs.symEl) refs.symEl.textContent = tile.dataset.symbol;

    let pct = toNumber(payload.change_pct ?? payload.changePct ?? payload.pct ?? payload.changePercent ?? payload.diffPct);
    const last = toNumber(payload.last ?? payload.price ?? payload.close ?? payload.l);
    const prev = toNumber(payload.prev ?? payload.prev_close ?? payload.prevClose ?? payload.reference);
    if (pct == null && last != null && prev) {
      if (prev !== 0) pct = ((last - prev) / prev) * 100;
    }
    if (pct == null && toNumber(payload.change) != null && last != null) {
      const diff = Number(payload.change);
      if (last - diff !== 0) pct = (diff / (last - diff)) * 100;
    }

    if (refs.pctEl) refs.pctEl.textContent = fmtPercent(pct, Math.abs(Number(pct || 0)) >= 5 ? 1 : 2);
    if (refs.lastEl) refs.lastEl.textContent = fmtNumber(last, last && Math.abs(last) >= 100 ? 1 : 2);

    tile.classList.toggle("positive", Number(pct) > 0);
    tile.classList.toggle("negative", Number(pct) < 0);
    const gradient = gradientFor(pct);
    tile.style.setProperty("--heat-start", gradient.start);
    tile.style.setProperty("--heat-stop", gradient.stop);
  }

  function renderTiles(items) {
    if (!gridEl) return;
    const frag = document.createDocumentFragment();
    const seen = new Set();
    for (const item of items) {
      const sym = normSymbol(item.symbol || item.sym || item.code || item.ticker);
      if (!sym || seen.has(sym)) continue;
      seen.add(sym);
      const tile = ensureTile(sym);
      updateTile(tile, item);
      frag.appendChild(tile);
    }
    gridEl.innerHTML = "";
    gridEl.appendChild(frag);
    tiles.forEach((tile, sym) => { if (!seen.has(sym)) tiles.delete(sym); });
    if (!seen.size) {
      showEmpty("Veri bekleniyor…");
    } else {
      hideEmpty();
      updateNavTargets(seen.values().next().value);
    }
  }

  function updateNavTargets(symbol) {
    if (!symbol) return;
    const depthHref = `/webapp/depth?symbol=${encodeURIComponent(symbol)}`;
    const akdHref = `/webapp/akd?symbol=${encodeURIComponent(symbol)}`;
    if (navDepth) navDepth.href = depthHref;
    if (navAkd) navAkd.href = akdHref;
    if (drawerDepth) drawerDepth.href = depthHref;
    if (drawerAkd) drawerAkd.href = akdHref;
  }

  function normalizePayload(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload.quotes)) return payload.quotes;

    if (Array.isArray(payload.tiles)) return payload.tiles;
    if (Array.isArray(payload.symbols)) return payload.symbols;
    if (Array.isArray(payload.data)) return payload.data;
    if (Array.isArray(payload.items)) return payload.items;
    return [];
  }

  const wsPath = window.WS_PATH || "/ws/heatmap";
  let ws = null;
  let reconnectTimer = null;
  let backoff = 2000;

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = wsPath.startsWith("ws") ? wsPath : `${proto}://${location.host}${wsPath}`;
    try { if (ws) ws.close(); } catch (err) { }
    ws = new WebSocket(url);
    setStatus("Bağlanıyor…");
    setLive(false);

    ws.addEventListener("open", () => {
      setStatus("Bağlandı");
      setLive(true);
      backoff = 2000;
    });

    ws.addEventListener("message", (ev) => {
      let data = null;
      try { data = JSON.parse(ev.data); }
      catch (err) { return; }
      if (data == null) return;
      if (data.status) {
        if (data.status === "connected") setStatus("Canlı veri hazır");
        else if (data.status === "reconnecting") setStatus("Kaynak yeniden bağlanıyor…");
      }
      const ts = data.ts || data.time || data.updated || data.updated_at || data.timestamp;
      const timeText = timeFromTs(ts) || timeFromTs(Date.now());
      if (timeText && lastUpdateEl) lastUpdateEl.textContent = `Son Güncelleme: ${timeText}`;
      const arr = normalizePayload(data);
      if (arr && arr.length) {
        const sorted = arr
          .map((item) => ({ ...item, symbol: normSymbol(item.symbol || item.sym || item.code || item.ticker) }))
          .filter((item) => item.symbol)
          .sort((a, b) => {
            const ap = toNumber(a.change_pct ?? a.changePct ?? a.pct ?? a.changePercent ?? a.diffPct) ?? -9999;
            const bp = toNumber(b.change_pct ?? b.changePct ?? b.pct ?? b.changePercent ?? b.diffPct) ?? -9999;
            return bp - ap;
          })
          .slice(0, MAX_TILES);
        renderTiles(sorted);
      }
    });

    ws.addEventListener("close", () => {
      setLive(false);
      setStatus("Bağlantı koptu, yeniden denenecek…");
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      try { ws.close(); } catch (err) { }
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      backoff = Math.min(backoff * 1.6, 12000);
      connect();
    }, backoff);
  }

  connect();

  if (btnInfo && infoPanel) {
    btnInfo.addEventListener("click", () => {
      infoPanel.classList.toggle("open");
    });
  }
  infoClose && infoClose.addEventListener("click", () => infoPanel.classList.remove("open"));

  function openDrawer() {
    drawer && drawer.classList.add("open");
    backdrop && backdrop.classList.add("show");
    document.documentElement.style.overflow = "hidden";
  }
  function closeDrawer() {
    drawer && drawer.classList.remove("open");
    backdrop && backdrop.classList.remove("show");
    document.documentElement.style.overflow = "";
  }

  btnMenu && btnMenu.addEventListener("click", openDrawer);
  btnCloseDrawer && btnCloseDrawer.addEventListener("click", closeDrawer);
  backdrop && backdrop.addEventListener("click", closeDrawer);

  (function () {
    const bar = qs("#bottombar");
    if (!bar) return;
    let lastY = window.scrollY;
    let ticking = false;
    let hidden = false;
    function onScroll() {
      const y = window.scrollY;
      if (Math.abs(y - lastY) < 6) return;
      if (y > lastY && !hidden) { bar.classList.add("hide"); hidden = true; }
      else if (y < lastY && hidden) { bar.classList.remove("hide"); hidden = false; }
      lastY = y;
    }
    window.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(() => { onScroll(); ticking = false; });
        ticking = true;
      }
    });
  })();

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && (!ws || ws.readyState === WebSocket.CLOSED)) {
      connect();
    }
  });

  updateNavTargets(normSymbol(window.FALLBACK_SYMBOL || "ASELS"));

})();