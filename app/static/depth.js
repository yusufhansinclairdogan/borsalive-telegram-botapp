(function(){
  const qs = (s)=>document.querySelector(s);
  const tbody = qs("#tbody");
  const statusEl = qs("#status");
  let symbol = (new URLSearchParams(location.search)).get("symbol") || (window.SYMBOL || "ASTOR");
  let ws;

  function rowTpl(r){
    const td = (t,cls="px-3 py-2 text-xs sm:text-sm")=>`<td class="${cls}">${t ?? ""}</td>`;
    return `<tr class="bg-slate-900/40 hover:bg-slate-800/40">
      ${td(r.level)}${td(r.bid_order)}${td(r.bid_qty)}${td(r.bid_price)}
      ${td(r.ask_price)}${td(r.ask_qty)}${td(r.ask_order)}
    </tr>`;
  }

  function render(levels){
    tbody.innerHTML = (levels && levels.length)
      ? levels.slice(0,10).map(rowTpl).join("")
      : `<tr><td colspan="7" class="px-3 py-6 text-center text-slate-400 text-sm">Veri bekleniyor…</td></tr>`;
  }

  function bindExpert(){
    const btn = qs("#ask-expert");
    if (!btn) return;
    btn.addEventListener("click", ()=>{
      // ileride kanal seçimi eklenecek
      alert("Uzmana yönlendirme yakında.");
    });
  }
  function bindSymbolChange(){
    const input = qs("#symbolInput");
    const go = qs("#goSymbol");
    if (!input || !go) return;
    input.value = symbol.toUpperCase();
    go.addEventListener("click", ()=>{
      const v = (input.value || "").trim().toUpperCase();
      if (!v) return;
      symbol = v;
      history.replaceState(null, "", `/webapp/depth?symbol=${symbol}`);
      connect();
    });
  }
 function connect(){
    if (ws) { try{ ws.close(); }catch{} }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${proto}://${location.host}/ws/depth/${symbol.toUpperCase()}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = ()=>{ statusEl.textContent = `Bağlı: ${symbol.toUpperCase()}`; };
    ws.onclose = ()=>{ statusEl.textContent = "Bağlantı kapandı"; setTimeout(connect, 1500); };
    ws.onerror = ()=>{ statusEl.textContent = "Hata"; };

    ws.onmessage = (ev)=>{
      try{
        const msg = JSON.parse(ev.data);
        if (msg.status === "reconnecting") {
          statusEl.textContent = `Yeniden bağlanıyor… (${symbol.toUpperCase()})`;
          return;
        }
        if (msg.levels) render(msg.levels);
      } catch(e){}
    };
  }

  bindExpert();
  bindSymbolChange();
  render([]);
  connect();
})();
