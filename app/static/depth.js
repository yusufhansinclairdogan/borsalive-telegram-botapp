// app/static/depth.js
(function () {
  const $ = (s) => document.querySelector(s);
  const tbody = $("#tbody");
  const statusEl = $("#status");
  const input = $("#symbolInput");
  const goBtn = $("#goSymbol");

  let symbol = (new URLSearchParams(location.search)).get("symbol") || (window.SYMBOL || "ASTOR");
  let ws;
  let prevRows = null;          // önceki snapshot
  const rowRefs = new Map();    // level -> { tds: {bid_order,...} }

  // Seviye kolonu yok!
  const COLS = ["bid_order","bid_qty","bid_price","ask_price","ask_qty","ask_order"];
  const BID_COLS = new Set(["bid_order","bid_qty","bid_price"]);
  const ASK_COLS = new Set(["ask_price","ask_qty","ask_order"]);

  function fmt(v){
    if (v === null || v === undefined || v === "") return "";
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    return n.toLocaleString("tr-TR", {maximumFractionDigits: 4});
  }

  function buildSkeleton(){
    tbody.innerHTML = "";
    rowRefs.clear();
    for (let i=1;i<=10;i++){
      const tr = document.createElement("tr");
      tr.className = "bg-slate-900/40 hover:bg-slate-800/40";
      const tds = {};
      for (const c of COLS){
        const td = document.createElement("td");
        td.className = "px-3 py-2 text-xs sm:text-sm";
        td.dataset.v = "";     // diff için ham değer cache
        td.textContent = "";   // ilk başta boş
        tr.appendChild(td);
        tds[c] = td;
      }
      tbody.appendChild(tr);
      rowRefs.set(i, { tds });
    }
  }

  // repaint/flicker’i azaltmak için frame’e batchle
  let rafQueued = false;
  const toPatch = [];

  function queuePatch(levels){
    toPatch.push(levels);
    if (rafQueued) return;
    rafQueued = true;
    requestAnimationFrame(()=>{
      try {
        // sadece son geleni uygula (ara mesajları at)
        const last = toPatch[toPatch.length - 1];
        toPatch.length = 0;
        applyPatch(last);
      } finally {
        rafQueued = false;
      }
    });
  }

  function flash(td, side){
    td.classList.remove("flash-bid","flash-ask");
    // reflow hilesi
    void td.offsetWidth;
    td.classList.add(side === "bid" ? "flash-bid" : "flash-ask");
    setTimeout(()=>td.classList.remove("flash-bid","flash-ask"), 650);
  }

  function applyPatch(rows){
    if (!rows || !rows.length) return;
    for (let i=0;i<Math.min(10, rows.length); i++){
      const r = rows[i];
      const level = r.level || (i+1);
      const ref = rowRefs.get(level);
      if (!ref) continue;

      for (const c of COLS){
        const td = ref.tds[c];
        const newVal = (r[c] ?? "");
        const oldVal = td.dataset.v ?? "";
        // Ham değer karşılaştırması (formatlı metin değil)
        if (String(newVal) !== String(oldVal)){
          td.dataset.v = String(newVal);
          td.textContent = fmt(newVal);
          if (BID_COLS.has(c)) flash(td, "bid");
          else if (ASK_COLS.has(c)) flash(td, "ask");
        }
      }
    }
  }

  function bindSymbol(){
    if (input) input.value = symbol.toUpperCase();
    if (goBtn){
      goBtn.addEventListener("click", ()=>{
        const v = (input.value || "").trim().toUpperCase();
        if (!v) return;
        symbol = v;
        history.replaceState(null, "", `/webapp/depth?symbol=${symbol}`);
        connect(true);
      });
    }
  }

  function connect(reset=false){
    if (ws){ try{ ws.close(); }catch{} }
    if (reset){ prevRows = null; buildSkeleton(); }

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${proto}://${location.host}/ws/depth/${symbol.toUpperCase()}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = ()=>{ statusEl.textContent = `Bağlı: ${symbol.toUpperCase()}`; };
    ws.onclose = ()=>{ statusEl.textContent = "Bağlantı kapandı, yeniden deneniyor…"; setTimeout(()=>connect(), 1200); };
    ws.onerror = ()=>{ statusEl.textContent = "Hata"; };

    ws.onmessage = (ev)=>{
      try{
        const msg = JSON.parse(ev.data);
        if (msg.status === "reconnecting"){
          statusEl.textContent = `Yeniden bağlanıyor… (${symbol.toUpperCase()})`;
          return;
        }
        if (msg.levels){
          if (!prevRows){ buildSkeleton(); }
          queuePatch(msg.levels);     // sadece değişeni güncelle
          prevRows = msg.levels;
        }
      }catch(e){}
    };
  }

  bindSymbol();
  buildSkeleton();
  connect();
})();
