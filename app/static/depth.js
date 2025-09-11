(function () {
  "use strict";

  // ----------------- helpers -----------------
  const qs = (s, el = document) => el.querySelector(s);
  const qsa = (s, el = document) => Array.prototype.slice.call(el.querySelectorAll(s));
  const cssEscape = (window.CSS && CSS.escape) ? CSS.escape : (s) => String(s).replace(/"/g, '\\"');
  const fmtN = (v) => (v == null || v === "" || isNaN(v)) ? "" : Number(v).toLocaleString("tr-TR");
  const fmtP = (v, d = 2) => (v == null || v === "" || isNaN(v)) ? "" : Number(v).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const toTime = (ts) => {
    if (ts == null) return "";
    let n = Number(ts);
    if (n > 1e14) n = Math.floor(n / 1e6);
    else if (n > 1e12) n = Math.floor(n / 1e3);
    if (n < 1500000000000 || n > 4102444800000) n = Date.now();
    try { return new Date(n).toLocaleTimeString("tr-TR"); } catch { return ""; }
  };
  const firstNonEmpty = (arr) => { for (let v of arr) { if (v == null) continue; v = String(v).trim(); if (v) return v; } return ""; };
  const normSym = (x) => (x || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  const debounce = (fn, ms=300) => { let t; return (...a)=>{clearTimeout(t); t=setTimeout(()=>fn(...a),ms);} };

  // ----------------- theme -----------------
  const root = document.documentElement;
  const themeBtn = qs("#themeToggle");
  try { const saved = localStorage.getItem("theme"); if (saved === "dark") root.classList.add("dark"); } catch {}
  const THEME_ICONS = {
    sun: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 4a1 1 0 011 1v1a1 1 0 11-2 0V5a1 1 0 011-1zm0 13a4 4 0 100-8 4 4 0 000 8zm0 2a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM4 11a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm13 0a1 1 0 011-1h2a1 1 0 110 2h-2a1 1 0 01-1-1zM6.343 6.343a1 1 0 011.414 0l.707.707A1 1 0 017.757 8.1l-.707-.707a1 1 0 010-1.414zm9.193 9.193a1 1 0 011.414 0l.707.707a1 1 0 01-1.414 1.414l-.707-.707a1 1 0 010-1.414zM17.657 6.343a1 1 0 010 1.414L16.95 8.464A1 1 0 1115.536 7.05l.707-.707a1 1 0 011.414 0zM7.757 15.536a1 1 0 010 1.414l-.707.707A1 1 0 015.636 16.243l.707-.707a1 1 0 011.414 0z"></path></svg>',
    moon:'<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"></path></svg>'
  };
  function paintThemeIcon() {
    if (!themeBtn) return;
    const dark = root.classList.contains("dark");
    themeBtn.innerHTML = `<span class="knob"></span>${dark ? THEME_ICONS.sun : THEME_ICONS.moon}`;
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      root.classList.toggle("dark");
      try { localStorage.setItem("theme", root.classList.contains("dark") ? "dark" : "light"); } catch {}
      paintThemeIcon();
    });
    themeBtn.addEventListener("pointerdown", (e) => { e.preventDefault(); }, { passive: false });
    paintThemeIcon();
  }

  // ----------------- DOM refs -----------------
  const rowsEl = qs("#rows");
  const statusEl = qs("#status");
  const lastEl = qs("#lastUpdate");
  const liveBadge = qs("#liveBadge");
  const depthEmpty = qs("#depthEmpty");

  const headlineLast = qs("#headlineLast");
  const headlineDiff = qs("#headlineDiff");
  const headlineDiffPct = qs("#headlineDiffPct");

  const snapToggle = qs("#snapToggle");
  const snapBody = qs("#snapBody");
  const s_bid = qs("#s_bid");
  const s_ask = qs("#s_ask");
  const s_qty = qs("#s_qty");
  const s_prev = qs("#s_prev");
  const s_high = qs("#s_high");
  const s_low = qs("#s_low");
  const s_ceil = qs("#s_ceil");
  const s_floor = qs("#s_floor");
  const s_turn = qs("#s_turn");

  const searchWrap = document.getElementById("searchWrap");
  const searchBtn = document.getElementById("searchBtn");
  const searchInput = document.getElementById("searchInput");

  const tradesList = document.getElementById("tradesList");
  const tradesEmpty = document.getElementById("tradesEmpty");

  // ----------------- status/live -----------------
  const setStatus = (t) => { if (statusEl) statusEl.textContent = t; };
  const setLive = (on) => { if (liveBadge) liveBadge.classList.toggle("off", !on); };

  // ----------------- snapshot toggle -----------------
  if (snapToggle && snapBody) {
    snapToggle.addEventListener("click", () => {
      snapBody.classList.toggle("open");
      snapToggle.setAttribute("aria-expanded", snapBody.classList.contains("open") ? "true" : "false");
    });
  }

  // ----------------- logo load -----------------
  (async () => {
    const sym = (new URLSearchParams(location.search)).get("symbol") || (window.SYMBOL || "").toString();
    const s = normSym(sym);
    const img = document.getElementById("brandLogo");
    if (!img || !s) return;
    try {
      const r = await fetch(`/logo/${encodeURIComponent(s)}`, { cache: "no-cache" });
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        img.onload = () => { try { URL.revokeObjectURL(url); } catch {} };
        img.src = url;
      }
    } catch {}
  })();

  // ================= SYMBOL VALIDATION =================
  const VALID_CACHE_KEY = "bl_valid_symbols_v1";
  const VALID_CACHE_TTL_MS = 15 * 60 * 1000;

  function _loadCachedSymbols() {
    try {
      const raw = localStorage.getItem(VALID_CACHE_KEY);
      if (!raw) return null;
      const { t, arr } = JSON.parse(raw);
      if (!t || !Array.isArray(arr)) return null;
      if (Date.now() - t > VALID_CACHE_TTL_MS) return null;
      return new Set(arr);
    } catch { return null; }
  }
  function _saveCachedSymbols(set) {
    try {
      const arr = Array.from(set);
      localStorage.setItem(VALID_CACHE_KEY, JSON.stringify({ t: Date.now(), arr }));
    } catch {}
  }

  async function fetchSectoralBriefFresh() {
    const url = `/api/sectoral-brief?ngsw-bypass=true&_=${Date.now()}`;
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error("sectoral-brief non-200");
    const data = await r.json();
    const s = new Set();
    if (Array.isArray(data)) {
      for (const sec of data) {
        if (Array.isArray(sec?.symbols)) {
          for (let sym of sec.symbols) { const u = normSym(sym); if (u) s.add(u); }
        }
        const idx = sec?.symbolCode; if (idx) s.add(normSym(idx));
      }
    }
    _saveCachedSymbols(s);
    return s;
  }
  let _freshPromise = null;
  async function fetchValidSymbols() {
    const cached = _loadCachedSymbols();
    if (!_freshPromise) {
      _freshPromise = fetchSectoralBriefFresh().catch(()=>null).finally(()=>{ _freshPromise = null; });
    }
    return cached || await fetchSectoralBriefFresh();
  }

  // -------- modal ----------
  function ensureModal() {
    if (document.getElementById("invalidModal")) return;
    const div = document.createElement("div");
    div.id = "invalidModal";
    div.className = "modal-overlay";
    div.innerHTML = `
      <div class="modal">
        <div class="modal-title">Geçersiz Hisse Sembolü</div>
        <div class="modal-body">Girdiğiniz kod hatalı veya desteklenmiyor.</div>
        <div class="modal-actions"><button id="modalOk" class="btn">Tamam</button></div>
      </div>`;
    document.body.appendChild(div);
    div.addEventListener("click", (e) => {
      if (e.target.id === "invalidModal" || e.target.id === "modalOk") div.style.display = "none";
    });
  }
  function showInvalidModal() { ensureModal(); const m = document.getElementById("invalidModal"); if (m) m.style.display = "flex"; }

  // ================= AUTOCOMPLETE =================
  let suggestBox = null, suggestOpen = false, suggestIndex = -1, suggestItems = [];
  function ensureSuggestBox() {
    if (suggestBox) return suggestBox;
    suggestBox = document.createElement("ul");
    suggestBox.id = "searchSuggest";
    suggestBox.className = "suggest";
    // konum: searchWrap içinde, input’un hemen altı
    searchWrap.appendChild(suggestBox);
    return suggestBox;
  }
  function closeSuggest() {
    suggestOpen = false; suggestIndex = -1; suggestItems = [];
    if (suggestBox) suggestBox.style.display = "none";
  }
  function openSuggest() {
    if (!suggestBox) ensureSuggestBox();
    suggestOpen = true;
    suggestBox.style.display = "block";
  }
  function paintSuggest(list, query) {
    ensureSuggestBox();
    suggestBox.innerHTML = "";
    if (!list.length) { closeSuggest(); return; }
    openSuggest();
    // render
    list.forEach((sym, i) => {
      const li = document.createElement("li");
      li.className = "sg-item";
      // basit highlight
      const q = query.toUpperCase();
      const pos = sym.indexOf(q);
      if (pos >= 0) {
        const a = sym.slice(0, pos), b = sym.slice(pos, pos+q.length), c = sym.slice(pos+q.length);
        li.innerHTML = `${a}<strong>${b}</strong>${c}`;
      } else {
        li.textContent = sym;
      }
      li.setAttribute("data-sym", sym);
      li.addEventListener("mousedown", (e) => { // mousedown: blur olmadan yakala
        e.preventDefault();
        validateAndGo(sym);
      });
      suggestBox.appendChild(li);
    });
    suggestItems = Array.from(suggestBox.querySelectorAll(".sg-item"));
    suggestIndex = -1;
  }
  function setActive(idx) {
    suggestItems.forEach((el,i)=> el.classList.toggle("active", i===idx));
    suggestIndex = idx;
  }
  async function updateSuggest() {
    const q = (searchInput.value || "").trim().toUpperCase();
    if (!q) { closeSuggest(); return; }
    // veri
    let set = _loadCachedSymbols();
    if (!set) {
      try { set = await fetchSectoralBriefFresh(); } catch { closeSuggest(); return; }
    }
    const all = Array.from(set);
    // skor: önce startsWith, sonra includes; en fazla 12
    const starts = [], contains = [];
    for (const s of all) {
      if (s.startsWith(q)) starts.push(s);
      else if (s.includes(q)) contains.push(s);
      if (starts.length >= 12) break;
    }
    const combined = (starts.concat(contains)).slice(0,12);
    paintSuggest(combined, q);
  }

  // ================= SEARCH =================
  function _goto(sym) {
    const u = new URL(location.href);
    u.searchParams.set("symbol", sym);
    location.assign(u);
  }

  async function validateAndGo(inputSym) {
    const clean = normSym(inputSym);
    if (!clean) return;
    try {
      const cached = _loadCachedSymbols();
      if (cached && cached.has(clean)) return _goto(clean);
      const fresh = await fetchSectoralBriefFresh();
      if (fresh && fresh.has(clean)) return _goto(clean);
      showInvalidModal();
    } catch {
      _goto(clean);
    }
  }

  if (searchBtn && searchWrap && searchInput) {
    const toggleOrSubmit = () => {
      if (!searchWrap.classList.contains("open")) {
        searchWrap.classList.add("open");
        setTimeout(() => { try { searchInput.focus(); } catch {} }, 30);
        // açılınca öneriyi hazırla
        updateSuggest();
      } else {
        const v = (searchInput.value || "").trim();
        if (v) validateAndGo(v); else { try { searchInput.focus(); } catch {} }
      }
    };
    ["pointerdown", "click"].forEach(evt => {
      searchBtn.addEventListener(evt, (e) => { e.preventDefault(); e.stopPropagation(); toggleOrSubmit(); }, { passive: false });
    });

    // input değiştikçe öneri
    const debUpd = debounce(updateSuggest, 300);
    searchInput.addEventListener("input", debUpd);

    // klavye navigasyon
    searchInput.addEventListener("keydown", (e) => {
      if (!suggestOpen || !suggestItems.length) {
        if (e.key === "Enter") { e.preventDefault(); validateAndGo(searchInput.value.trim()); }
        else if (e.key === "Escape") { searchWrap.classList.remove("open"); searchInput.value = ""; closeSuggest(); }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = (suggestIndex + 1) % suggestItems.length;
        setActive(next);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = (suggestIndex - 1 + suggestItems.length) % suggestItems.length;
        setActive(prev);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const pick = suggestIndex >= 0 ? suggestItems[suggestIndex].getAttribute("data-sym") : (searchInput.value || "").trim();
        if (pick) validateAndGo(pick);
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeSuggest();
      }
    });

    // dışarı tıklayınca kapat
    document.addEventListener("click", (e) => {
      if (!searchWrap.contains(e.target)) {
        if (!searchInput.value.trim()) searchWrap.classList.remove("open");
        closeSuggest();
      }
    });
    searchInput.addEventListener("blur", () => {
      // kısa gecikme: mousedown ile seçim yapılabilsin
      setTimeout(closeSuggest, 120);
      if (!searchInput.value.trim()) searchWrap.classList.remove("open");
    });
  }

  // ================= DEPTH TABLE =================
  const lastValues = Object.create(null);
  function buildTable() {
    if (!rowsEl) return;
    rowsEl.innerHTML = "";
    for (const k of Object.keys(lastValues)) delete lastValues[k];
    for (let i = 0; i < 10; i++) {
      const tr = document.createElement("tr");
      tr.dataset.row = String(i);
      tr.innerHTML = `
        <td class="num meta" data-field="r${i}.bid_order"></td>
        <td class="num bid"  data-field="r${i}.bid_qty"></td>
        <td class="num bid"  data-field="r${i}.bid_price"></td>
        <td class="num ask"  data-field="r${i}.ask_price"></td>
        <td class="num ask"  data-field="r${i}.ask_qty"></td>
        <td class="num meta" data-field="r${i}.ask_order"></td>`;
      rowsEl.appendChild(tr);
    }
  }
  function patch(field, txt, side) {
    const el = qsa(`[data-field="${cssEscape(field)}"]`, rowsEl)[0];
    if (!el) return;
    const old = lastValues[field];
    if (old === txt) return;
    el.textContent = (txt == null ? "" : String(txt));
    el.classList.remove("flash-green", "flash-red");
    if (old !== undefined && txt !== "") {
      el.classList.add(side === "bid" ? "flash-green" : "flash-red");
      setTimeout(() => el.classList.remove("flash-green", "flash-red"), 600);
    }
    lastValues[field] = txt;
  }
  function renderDepth(levels) {
    for (let i = 0; i < 10; i++) {
      const r = (levels && levels[i]) || {};
      patch(`r${i}.bid_order`, fmtN(r.bid_order), "bid");
      patch(`r${i}.bid_qty`, fmtN(r.bid_qty), "bid");
      patch(`r${i}.bid_price`, fmtP(r.bid_price), "bid");
      patch(`r${i}.ask_price`, fmtP(r.ask_price), "ask");
      patch(`r${i}.ask_qty`, fmtN(r.ask_qty), "ask");
      patch(`r${i}.ask_order`, fmtN(r.ask_order), "ask");
    }
  }

  // anti-flap
  const RECO_SHOW_MS = 2500;
  let lastDepthAt = performance.now();

  // ================= TRADES (binary decoder) =================
  function rdVarint(buf, i) { let x = 0, s = 0, b = 0; do { b = buf[i++]; x |= (b & 0x7f) << s; s += 7; } while (b & 0x80); return [x, i]; }
  function rdStr(buf, i) { let len;[len, i] = rdVarint(buf, i); const end = i + len; const sub = buf.subarray(i, end); i = end; return [new TextDecoder("utf-8").decode(sub), i]; }
  function rdF32(buf, i) { const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength); const v = view.getFloat32(i, true); return [v, i + 4]; }
  function decodeTrade(u8) {
    let i = 0, L = u8.length; const out = {}; while (i < L) {
      let tag;[tag, i] = rdVarint(u8, i); const f = tag >> 3, wt = tag & 7;
      if (f === 1 && wt === 2) { let s;[s, i] = rdStr(u8, i); out.symbol = s; continue; }
      if (f === 2 && wt === 2) { let s;[s, i] = rdStr(u8, i); out.trade_id = s; continue; }
      if (f === 3 && wt === 5) { let v;[v, i] = rdF32(u8, i); out.price = v; continue; }
      if (f === 4 && wt === 0) { let v;[v, i] = rdVarint(u8, i); out.qty = v; continue; }
      if (f === 5 && wt === 2) { let s;[s, i] = rdStr(u8, i); out.side = s; continue; }
      if (f === 6 && wt === 0) { let v;[v, i] = rdVarint(u8, i); out.ts = v; continue; }
      if (f === 7 && wt === 2) { let s;[s, i] = rdStr(u8, i); out.buyer = s; continue; }
      if (f === 8 && wt === 2) { let s;[s, i] = rdStr(u8, i); out.seller = s; continue; }
      if (wt === 0) { let _;[_, i] = rdVarint(u8, i); }
      else if (wt === 1) { i += 8; }
      else if (wt === 2) { let l;[l, i] = rdVarint(u8, i); i += l; }
      else if (wt === 5) { i += 4; }
      else { break; }
    } return out;
  }
  const MAX_TRADES = 50;
  function addTrade(t) {
    if (!tradesList) return;
    const pageSym = normSym((new URLSearchParams(location.search)).get("symbol") || (window.SYMBOL || ""));
    if (t.symbol && normSym(t.symbol) !== pageSym) return;
    if (!t.price || !t.qty || Number(t.price) <= 0 || Number(t.qty) <= 0) return;

    const side = String(t.side || "").trim().toLowerCase();
    const isBuy = (side === "b" || side.startsWith("b"));
    const isSell = (side === "a" || side.startsWith("s"));
    const sideCls = isSell ? "sell" : (isBuy ? "buy" : "");

    const buyerVal = firstNonEmpty([t.buyer, t.buyer_code, t.buyerTag, t.b]) || "—";
    const sellerVal = firstNonEmpty([t.seller, t.seller_code, t.sellerTag, t.s]) || "—";

    const li = document.createElement("li");
    li.className = "trade-item";
    li.innerHTML =
      `<div class="trade-row ${sideCls}">
         <div class="c c-time">${toTime(t.ts)}</div>
         <div class="c c-price">${fmtP(t.price)}</div>
         <div class="c c-qty">${fmtN(t.qty)}</div>
         <div class="c c-buyer" title="${buyerVal}">${buyerVal}</div>
         <div class="c c-seller" title="${sellerVal}">${sellerVal}</div>
       </div>`;
    if (tradesList.firstChild) tradesList.insertBefore(li, tradesList.firstChild);
    else tradesList.appendChild(li);
    while (tradesList.children.length > MAX_TRADES) tradesList.removeChild(tradesList.lastChild);
    if (tradesEmpty) tradesEmpty.style.display = tradesList.children.length ? "none" : "";
  }

  // ================= MARKET SNAPSHOT (RawSnapshot) =================
  function vRead(buf, i) { let x = 0n, s = 0n, b = 0; do { b = buf[i++]; x |= BigInt(b & 0x7f) << s; s += 7n; } while (b & 0x80); return [Number(x), i]; }
  function f64(buf, i) { const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength); const v = dv.getFloat64(i, true); return [v, i + 8]; }
  function decodeRawSnapshot(u8) {
    let i = 0, L = u8.length, out = {};
    while (i < L) {
      let tag;[tag, i] = vRead(u8, i);
      const f = (tag >> 3), wt = (tag & 7);
      if (wt === 1) { let v;[v, i] = f64(u8, i); out[f] = v; continue; }
      else if (wt === 0) { let v;[v, i] = vRead(u8, i); out[f] = v; continue; }
      else if (wt === 2) { let len;[len, i] = vRead(u8, i); i += len; continue; }
      else if (wt === 5) { i += 4; continue; }
      else break;
    }
    return out;
  }
  function pickFirst(...vals) { for (const v of vals) { if (v != null && Number.isFinite(v)) return v; } return undefined; }
  function mapFields(m) {
    const last = pickFirst(m[5], m[25]);
    const ask  = pickFirst(m[6]);
    const bid  = pickFirst(m[10], m[42]);
    const high = pickFirst(m[8], m[13], m[54]);
    const low  = pickFirst(m[12], m[55]);
    const ceil = pickFirst(m[26], m[21]);
    const floor= pickFirst(m[27], m[22]);
    const vol  = pickFirst(m[14], m[48]);
    const turn = pickFirst(m[15], m[38], m[80], m[81], m[28], m[33]);
    const prev = pickFirst(m[9], m[62], m[47]);
    const tcnt = pickFirst(m[60], m[61]);
    return { last, ask, bid, high, low, ceil, floor, vol, turn, prev, tcnt };
  }

  const col = { pos: "var(--bid)", neg: "var(--ask)", amb: "#f59e0b", ask: "var(--ask)", bid: "var(--bid)" };
  function renderSnapshot(qsState) {
    const bid_display  = qsState.prev; // ekranda ALIŞ
    const prev_display = qsState.bid;  // ekranda ÖNCEKİ
    const last = qsState.last;

    let diff, diffPct;
    if (last != null && prev_display != null && prev_display !== 0) {
      const delta = last - prev_display;
      diff = delta;
      diffPct = (delta / prev_display) * 100;
    }

    if (s_bid)   { s_bid.textContent   = bid_display != null ? fmtP(bid_display) : "—"; s_bid.style.color = col.bid; }
    if (s_ask)   { s_ask.textContent   = qsState.ask  != null ? fmtP(qsState.ask) : "—"; s_ask.style.color = col.ask; }
    if (s_prev)  { s_prev.textContent  = prev_display!= null ? fmtP(prev_display) : "—"; }
    if (s_high)  { s_high.textContent  = qsState.high != null ? fmtP(qsState.high) : "—"; s_high.style.color = col.pos; }
    if (s_low)   { s_low.textContent   = qsState.low  != null ? fmtP(qsState.low)  : "—"; s_low.style.color = col.neg; }
    if (s_ceil)  { s_ceil.textContent  = qsState.ceil != null ? fmtP(qsState.ceil) : "—"; s_ceil.style.color = col.pos; }
    if (s_floor) { s_floor.textContent = qsState.floor!= null ? fmtP(qsState.floor): "—"; s_floor.style.color = col.neg; }
    if (s_qty)   { s_qty.textContent   = qsState.vol  != null ? fmtN(qsState.vol)  : "—"; }
    if (s_turn)  { s_turn.textContent  = qsState.turn != null ? Number(qsState.turn).toLocaleString("tr-TR") : "—"; s_turn.style.color = col.amb; }

    const color = diff != null ? (diff >= 0 ? col.pos : col.neg) : "";
    if (headlineLast) { headlineLast.textContent = last != null ? fmtP(last) : "—"; headlineLast.style.color = "inherit"; }
    if (headlineDiff) { headlineDiff.textContent = (diff != null ? (diff > 0 ? " +" : " ") + fmtP(diff) : " —"); headlineDiff.style.color = color; }
    if (headlineDiffPct) { headlineDiffPct.textContent = (diffPct != null ? ` (${diffPct > 0 ? "+" : ""}${fmtP(diffPct,2)}%)` : ""); headlineDiffPct.style.color = color; }
  }

  // ================= WS CONNECTORS =================
  const symParam = normSym((new URLSearchParams(location.search)).get("symbol") || (window.SYMBOL || "ASTOR"));
  const WS_ORIGIN = (location.protocol === "https:" ? "wss://" : "ws://") + location.host;

  // depth
  let wsDepth = null, depthConnId = 0;
  function connectDepth(sym) {
    buildTable();
    depthConnId++;
    const myId = depthConnId;
    const WS_PATH = (typeof window.WS_PATH === "string" && window.WS_PATH) || ("/ws/depth/" + sym);
    const wsURL = WS_ORIGIN + WS_PATH;

    setStatus(`Bağlanıyor… (${sym})`); setLive(false);
    if (depthEmpty) depthEmpty.style.display = "";

    try { wsDepth && wsDepth.close(); } catch {}
    wsDepth = null;
    let backoff = 800;
    function scheduleReconnect() {
      if (myId !== depthConnId) return;
      setTimeout(() => connectDepth(sym), backoff + Math.floor(Math.random()*300));
      backoff = Math.min(backoff * 1.7, 10000);
    }
    try { wsDepth = new WebSocket(wsURL); } catch { setStatus("Bağlantı hatası"); return scheduleReconnect(); }

    wsDepth.onopen = () => { if (myId !== depthConnId) return; setStatus(`Bağlı: ${sym}`); setLive(true); backoff = 800; };
    wsDepth.onclose= () => {
      if (myId !== depthConnId) return;
      setTimeout(() => {
        if (myId !== depthConnId) return;
        if (performance.now() - lastDepthAt >= RECO_SHOW_MS) {
          setStatus(`Yeniden bağlanıyor… (${sym})`); setLive(false);
          if (depthEmpty) depthEmpty.style.display = "";
        }
      }, 1200);
      scheduleReconnect();
    };
    wsDepth.onerror = () => {};
    wsDepth.onmessage = (ev) => {
      if (myId !== depthConnId) return;
      try {
        const msg = JSON.parse(ev.data);
        if (msg && msg.status === "reconnecting") {
          if (performance.now() - lastDepthAt >= RECO_SHOW_MS) {
            setStatus(`Yeniden bağlanıyor… (${sym})`); setLive(false);
            if (depthEmpty) depthEmpty.style.display = "";
          }
          return;
        }
        if (msg && msg.levels && msg.levels.length) {
          renderDepth(msg.levels);
          lastDepthAt = performance.now();
          setStatus(`Bağlı: ${sym}`); setLive(true);
          if (depthEmpty) depthEmpty.style.display = "none";
          if (lastEl) lastEl.textContent = `Son Canlı Veri: ${new Date().toLocaleTimeString("tr-TR")}`;
        }
      } catch {}
    };
  }

  // trades
  let wsTrade = null, tradeConnId = 0;
  function connectTrades(sym) {
    tradeConnId++; const myId = tradeConnId;
    if (tradesEmpty) tradesEmpty.style.display = "";
    const PATH = (typeof window.WS_TRADE_PATH === "string" && window.WS_TRADE_PATH) || ("/ws/trade/" + sym);
    const url = WS_ORIGIN + PATH;

    try { wsTrade && wsTrade.close(); } catch {}
    wsTrade = null; let backoff = 800;
    function scheduleReconnect() {
      if (myId !== tradeConnId) return;
      setTimeout(() => connectTrades(sym), backoff + Math.floor(Math.random()*300));
      backoff = Math.min(backoff * 1.7, 10000);
    }
    try { wsTrade = new WebSocket(url); } catch { return scheduleReconnect(); }
    wsTrade.onopen = () => { if (myId !== tradeConnId) return; backoff = 800; };
    wsTrade.onclose= () => { if (myId !== tradeConnId) return; if (tradesEmpty) tradesEmpty.style.display = ""; scheduleReconnect(); };
    wsTrade.onerror = () => {};
    wsTrade.onmessage = (ev) => {
      if (myId !== tradeConnId) return;
      try {
        if (typeof ev.data === "string" && ev.data.trim().startsWith("{")) {
          const msg = JSON.parse(ev.data); const t = msg && msg.trade;
          if (t) { addTrade(t); return; }
        }
      } catch {}
      try {
        const bin = atob(ev.data); const u8 = new Uint8Array(bin.length); for (let i=0;i<bin.length;i++) u8[i]=bin.charCodeAt(i);
        const t = decodeTrade(u8); if (t) addTrade(t);
      } catch {}
    };
  }

  // market snapshot
  let wsMkt = null, mktConnId = 0, lastMarketMs = 0;
  function connectMarket(sym) {
    mktConnId++; const myId = mktConnId;
    const PATH = (typeof window.WS_MARKET_PATH === "string" && window.WS_MARKET_PATH) || ("/ws/market/" + sym);
    const url = WS_ORIGIN + PATH;
    try { wsMkt && wsMkt.close(); } catch {}
    wsMkt = null; let backoff = 800;
    function scheduleReconnect() {
      if (myId !== mktConnId) return;
      setTimeout(() => connectMarket(sym), backoff + Math.floor(Math.random()*300));
      backoff = Math.min(backoff * 1.7, 10000);
    }
    try { wsMkt = new WebSocket(url); } catch { return scheduleReconnect(); }
    wsMkt.onopen = () => { if (myId !== mktConnId) return; backoff = 800; };
    wsMkt.onclose= () => { if (myId !== mktConnId) return; scheduleReconnect(); };
    wsMkt.onerror = () => {};
    const qsState = { last: undefined, ask: undefined, bid: undefined, high: undefined, low: undefined, ceil: undefined, floor: undefined, vol: undefined, turn: undefined, prev: undefined, tcnt: undefined };
    wsMkt.onmessage = (ev) => {
      if (myId !== mktConnId) return;
      try {
        const bin = atob(ev.data); const u8 = new Uint8Array(bin.length); for (let i=0;i<bin.length;i++) u8[i]=bin.charCodeAt(i);
        const raw = decodeRawSnapshot(u8);
        const m = mapFields(raw);
        for (const k of Object.keys(m)) if (m[k] != null && Number.isFinite(m[k])) qsState[k] = m[k];
        renderSnapshot(qsState);
        lastMarketMs = performance.now();
      } catch {}
    };
    setInterval(() => {
      if (!lastMarketMs) return;
      const delta = performance.now() - lastMarketMs;
      if (delta > 15000 && headlineDiff) headlineDiff.style.color = col.amb;
    }, 3000);
  }

  // ================= INIT FLOW =================
  async function init() {
    try { window.Telegram && Telegram.WebApp && Telegram.WebApp.ready(); } catch {}
    try { window.Telegram?.WebApp?.expand?.(); } catch {}

    const symbol = normSym((new URLSearchParams(location.search)).get("symbol") || (window.SYMBOL || "ASTOR"));
    if (!symbol) return;

    try {
      const cached = _loadCachedSymbols();
      if (!(cached && cached.has(symbol))) {
        const fresh = await fetchSectoralBriefFresh();
        if (!(fresh && fresh.has(symbol))) {
          showInvalidModal();
        }
      } else {
        fetchSectoralBriefFresh().catch(()=>{});
      }
    } catch {}

    connectDepth(symbol);
    connectTrades(symbol);
    connectMarket(symbol);
  }
// --- sticky bottom bar & drawer ---
(function(){
  const bar = document.getElementById("bottombar");
  const btnMenu = document.getElementById("btnMenu");
  const btnInfo = document.getElementById("btnInfo");
  const drawer = document.getElementById("drawer");
  const backdrop = document.getElementById("backdrop");
  const btnClose = document.getElementById("drawerClose");

  // scroll direction hide/show
  let lastY = window.scrollY, ticking=false, hidden=false;
  function onScroll(){
    const y = window.scrollY;
    if(Math.abs(y-lastY) < 6) return;
    if(y > lastY && !hidden){ bar && bar.classList.add("hide"); hidden = true; }
    else if(y < lastY && hidden){ bar && bar.classList.remove("hide"); hidden = false; }
    lastY = y;
  }
  window.addEventListener("scroll", ()=>{ if(!ticking){ requestAnimationFrame(()=>{ onScroll(); ticking=false; }); ticking=true; }});

  function openDrawer(){
    drawer && drawer.classList.add("open");
    backdrop && backdrop.classList.add("show");
    document.documentElement.style.overflow = "hidden";
  }
  function closeDrawer(){
    drawer && drawer.classList.remove("open");
    backdrop && backdrop.classList.remove("show");
    document.documentElement.style.overflow = "";
  }
  btnMenu && btnMenu.addEventListener("click", openDrawer);
  btnClose && btnClose.addEventListener("click", closeDrawer);
  backdrop && backdrop.addEventListener("click", closeDrawer);

  btnInfo && btnInfo.addEventListener("click", ()=>{
    const t = document.createElement("div");
    t.className="info-toast";
    t.textContent="BorsaLive • hızlı piyasa araçları";
    document.body.appendChild(t);
    requestAnimationFrame(()=> t.classList.add("show"));
    setTimeout(()=>{ t.classList.remove("show"); setTimeout(()=>t.remove(), 250); }, 1800);
  });
})();

  init();

  // ------- küçük öneri CSS (opsiyonel, eklemezsen de çalışır) -------
  // .suggest { position:absolute; top:100%; left:0; right:0; max-height:240px; overflow:auto; background:var(--bg); border:1px solid var(--muted); border-radius:10px; padding:6px 0; z-index:50; display:none; }
  // .sg-item{ padding:8px 10px; cursor:pointer; font-variant:tabular-nums; }
  // .sg-item strong{ font-weight:700; }
  // .sg-item.active, .sg-item:hover{ background:var(--muted-2); }
})();
