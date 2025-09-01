(function () {
  "use strict";

  // ------- helpers -------
  const qs=(s,el=document)=>el.querySelector(s);
  const qsa=(s,el=document)=>Array.prototype.slice.call(el.querySelectorAll(s));
  const fmtN = v => (v==null||v===""||isNaN(v))?"":Number(v).toLocaleString("tr-TR");
  const fmtP = (v,d=2)=> (v==null||v===""||isNaN(v))?"":Number(v).toLocaleString("tr-TR",{minimumFractionDigits:d,maximumFractionDigits:d});
  const cssEscape=(CSS&&CSS.escape)?CSS.escape:(s)=>String(s).replace(/"/g,'\\"');
  function toTime(ts){ if(ts==null) return ""; let n=Number(ts); if(n>1e14)n=Math.floor(n/1e6); else if(n>1e12)n=Math.floor(n/1e3); if(n<1500000000000||n>4102444800000)n=Date.now(); try{return new Date(n).toLocaleTimeString('tr-TR')}catch{return""} }
  const firstNonEmpty = (arr)=>{ for(let v of arr){ if(v==null) continue; v=String(v).trim(); if(v) return v; } return ""; };

  // ------- logo -------
  (async ()=>{
    const sym=(new URLSearchParams(location.search)).get("symbol")||(window.SYMBOL||"");
    const s=(sym||"").toUpperCase().replace(/[^A-Z0-9]/g,"");
    const img=document.getElementById("brandLogo"); if(!img||!s) return;
    try{
      const r=await fetch(`/logo/${encodeURIComponent(s)}`,{cache:"no-cache"});
      if(r.ok){ const blob=await r.blob(); const url=URL.createObjectURL(blob); img.onload=()=>{ try{URL.revokeObjectURL(url)}catch{} }; img.src=url; }
    }catch{}
  })();

  // ------- DOM refs -------
  const rowsEl=qs("#rows"), statusEl=qs("#status"), lastEl=qs("#lastUpdate");
  const liveBadge=qs("#liveBadge"), themeBtn=qs("#themeToggle"), root=document.documentElement;
  const depthEmpty=qs("#depthEmpty");

  const headlineLast=qs("#headlineLast"), headlineDiff=qs("#headlineDiff"), headlineDiffPct=qs("#headlineDiffPct");

  const snapToggle=qs("#snapToggle"), snapBody=qs("#snapBody");
  const s_bid=qs("#s_bid"), s_ask=qs("#s_ask"), s_qty=qs("#s_qty"), s_prev=qs("#s_prev"),
        s_high=qs("#s_high"), s_low=qs("#s_low"), s_ceil=qs("#s_ceil"), s_floor=qs("#s_floor"), s_turn=qs("#s_turn");

  const searchWrap=document.getElementById("searchWrap"), searchBtn=document.getElementById("searchBtn"), searchInput=document.getElementById("searchInput");
  const tradesList=document.getElementById("tradesList"), tradesEmpty=document.getElementById("tradesEmpty");

  // ------- theme -------
  try{ const saved=localStorage.getItem("theme"); if(saved==="dark") root.classList.add("dark"); }catch{}
  if(themeBtn){
    themeBtn.addEventListener("click",()=>{ root.classList.toggle("dark"); try{ localStorage.setItem("theme", root.classList.contains("dark")?"dark":"light"); }catch{} });
    themeBtn.addEventListener("pointerdown",(e)=>{ e.preventDefault(); },{passive:false});
  }

  // ------- search -------
  function gotoSymbol(sym){ sym=(sym||"").toUpperCase().replace(/[^A-Z0-9]/g,""); if(!sym) return; const u=new URL(location.href); u.searchParams.set("symbol",sym); location.assign(u); }
  if(searchBtn&&searchWrap&&searchInput){
    const toggleOrSubmit=()=>{
      if(!searchWrap.classList.contains("open")){ searchWrap.classList.add("open"); setTimeout(()=>{ try{searchInput.focus()}catch{} },30); }
      else { const v=(searchInput.value||"").trim(); if(v) gotoSymbol(v); else { try{searchInput.focus()}catch{} } }
    };
    ["pointerdown","click"].forEach(evt=> searchBtn.addEventListener(evt,(e)=>{ e.preventDefault(); e.stopPropagation(); toggleOrSubmit(); },{passive:false}));
    searchInput.addEventListener("keydown",(e)=>{ if(e.key==="Enter"){ e.preventDefault(); gotoSymbol(searchInput.value.trim()); } else if(e.key==="Escape"){ searchWrap.classList.remove("open"); searchInput.value=""; }});
    document.addEventListener("click",(e)=>{ if(!searchWrap.contains(e.target)){ if(!searchInput.value.trim()) searchWrap.classList.remove("open"); }});
    searchInput.addEventListener("blur",()=>{ if(!searchInput.value.trim()) searchWrap.classList.remove("open"); });
  }

  // ------- status/live -------
  const setStatus=t=>{ if(statusEl) statusEl.textContent=t; };
  const setLive=on=>{ if(liveBadge) liveBadge.classList.toggle("off",!on); };

  // ------- snapshot toggle -------
  if(snapToggle&&snapBody){
    snapToggle.addEventListener("click",()=>{ snapBody.classList.toggle("open"); snapToggle.setAttribute("aria-expanded", String(snapBody.classList.contains("open"))); });
  }

  // ------- depth table -------
  const lastValues=Object.create(null);
  function buildTable(){
    if(!rowsEl) return; rowsEl.innerHTML=""; for(const k of Object.keys(lastValues)) delete lastValues[k];
    for(let i=0;i<10;i++){
      const tr=document.createElement("tr"); tr.dataset.row=String(i);
      tr.innerHTML=`
        <td class="num meta" data-field="r${i}.bid_order"></td>
        <td class="num bid"  data-field="r${i}.bid_qty"></td>
        <td class="num bid"  data-field="r${i}.bid_price"></td>
        <td class="num ask"  data-field="r${i}.ask_price"></td>
        <td class="num ask"  data-field="r${i}.ask_qty"></td>
        <td class="num meta" data-field="r${i}.ask_order"></td>`;
      rowsEl.appendChild(tr);
    }
  }
  function patch(field,txt,side){
    const el=qsa(`[data-field="${cssEscape(field)}"]`,rowsEl)[0]; if(!el) return;
    const old=lastValues[field]; if(old===txt) return;
    el.textContent=(txt==null?"":String(txt));
    el.classList.remove("flash-green","flash-red");
    if(old!==undefined && txt!==""){ el.classList.add(side==="bid"?"flash-green":"flash-red"); setTimeout(()=>el.classList.remove("flash-green","flash-red"),600); }
    lastValues[field]=txt;
  }
  function renderDepth(levels){
    for(let i=0;i<10;i++){
      const r=(levels&&levels[i])||{};
      patch(`r${i}.bid_order`,fmtN(r.bid_order),"bid");
      patch(`r${i}.bid_qty`,fmtN(r.bid_qty),"bid");
      patch(`r${i}.bid_price`,fmtP(r.bid_price),"bid");
      patch(`r${i}.ask_price`,fmtP(r.ask_price),"ask");
      patch(`r${i}.ask_qty`,fmtN(r.ask_qty),"ask");
      patch(`r${i}.ask_order`,fmtN(r.ask_order),"ask");
    }
  }

  // ------- depth WS -------
  const RECO_SHOW_MS=2500; let lastDepthAt=performance.now();
  let wsDepth=null, depthConnId=0;
  function connectDepth(){
    buildTable(); depthConnId++; const myId=depthConnId;
    const sym=(new URLSearchParams(location.search)).get("symbol")||(window.SYMBOL||"ASTOR");
    const sUp=(sym||"ASTOR").toUpperCase();
    const wsURL=((location.protocol==="https:")?"wss://":"ws://")+location.host+((typeof window.WS_PATH==="string"&&window.WS_PATH)||("/ws/depth/"+sUp));
    setStatus(`Bağlanıyor… (${sUp})`); setLive(false); if(depthEmpty) depthEmpty.style.display="";
    try{ wsDepth&&wsDepth.close(); }catch{} wsDepth=null;
    let backoff=800; const schedule=()=>{ if(myId!==depthConnId) return; setTimeout(connectDepth, backoff+Math.random()*300|0); backoff=Math.min(backoff*1.7,10000); };
    try{ wsDepth=new WebSocket(wsURL); }catch{ setStatus("Bağlantı hatası"); return schedule(); }
    wsDepth.onopen=()=>{ if(myId!==depthConnId) return; setStatus(`Bağlı: ${sUp}`); setLive(true); backoff=800; };
    wsDepth.onclose=()=>{ if(myId!==depthConnId) return; setTimeout(()=>{ if(myId!==depthConnId) return; if(performance.now()-lastDepthAt>=RECO_SHOW_MS){ setStatus(`Yeniden bağlanıyor… (${sUp})`); setLive(false); if(depthEmpty) depthEmpty.style.display=""; } },1200); schedule(); };
    wsDepth.onerror=()=>{};
    wsDepth.onmessage=(ev)=>{
      if(myId!==depthConnId) return;
      try{
        const msg=JSON.parse(ev.data);
        if(msg && msg.status==="reconnecting"){ if(performance.now()-lastDepthAt>=RECO_SHOW_MS){ setStatus(`Yeniden bağlanıyor… (${sUp})`); setLive(false); if(depthEmpty) depthEmpty.style.display=""; } return; }
        if(msg && msg.levels && msg.levels.length){
          renderDepth(msg.levels); lastDepthAt=performance.now();
          setStatus(`Bağlı: ${sUp}`); setLive(true);
          if(depthEmpty) depthEmpty.style.display="none"; if(lastEl) lastEl.textContent=`Son Canlı Veri: ${new Date().toLocaleTimeString("tr-TR")}`;
        }
      }catch{}
    };
  }

  // ------- trades (for LAST) -------
  function rvint(buf,i){ let x=0,s=0,b=0; do{ b=buf[i++]; x|=(b&0x7f)<<s; s+=7; }while(b&0x80); return [x,i]; }
  function rstr(buf,i){ let len;[len,i]=rvint(buf,i); const end=i+len; const sub=buf.subarray(i,end); i=end; return [new TextDecoder("utf-8").decode(sub),i]; }
  function rf32(buf,i){ const v=new DataView(buf.buffer,buf.byteOffset,buf.byteLength).getFloat32(i,true); return [v,i+4]; }
  function decodeTrade(u8){ let i=0,L=u8.length,out={}; while(i<L){ let tag;[tag,i]=rvint(u8,i); const f=tag>>3,wt=tag&7;
    if(f===1&&wt===2){ let s;[s,i]=rstr(u8,i); out.symbol=s; continue; }
    if(f===2&&wt===2){ let s;[s,i]=rstr(u8,i); out.trade_id=s; continue; }
    if(f===3&&wt===5){ let v;[v,i]=rf32(u8,i); out.price=v; continue; }
    if(f===4&&wt===0){ let v;[v,i]=rvint(u8,i); out.qty=v; continue; }
    if(f===5&&wt===2){ let s;[s,i]=rstr(u8,i); out.side=s; continue; }
    if(f===6&&wt===0){ let v;[v,i]=rvint(u8,i); out.ts=v; continue; }
    if(f===7&&wt===2){ let s;[s,i]=rstr(u8,i); out.buyer=s; continue; }
    if(f===8&&wt===2){ let s;[s,i]=rstr(u8,i); out.seller=s; continue; }
    if(wt===0){ let _;[_,i]=rvint(u8,i); } else if(wt===1){ i+=8; } else if(wt===2){ let l;[l,i]=rvint(u8,i); i+=l; } else if(wt===5){ i+=4; } else break;
  } return out; }

  const MAX_TRADES=50;
  let lastFromTrade=null; // *** SON fiyat kaynağımız ***
  function addTrade(t){
    const pageSym=((new URLSearchParams(location.search)).get("symbol")||(window.SYMBOL||"")).toUpperCase();
    if(t.symbol && t.symbol.toUpperCase()!==pageSym) return;
    if(t.price && Number(t.price)>0){ lastFromTrade = Number(t.price); renderHeaderAndDiff(); } // son fiyat güncelle
    if(!tradesList) return;
    if(!t.price || !t.qty || Number(t.price)<=0 || Number(t.qty)<=0) return;
    const side=String(t.side||"").trim().toLowerCase(); const isBuy=(side==="b"||side.startsWith("b")); const isSell=(side==="a"||side.startsWith("s"));
    const sideCls=isSell?"sell":(isBuy?"buy":"");
    const buyerVal=firstNonEmpty([t.buyer,t.buyer_code,t.buyerTag,t.b])||"—";
    const sellerVal=firstNonEmpty([t.seller,t.seller_code,t.sellerTag,t.s])||"—";
    const li=document.createElement("li"); li.className="trade-item";
    li.innerHTML=`<div class="trade-row ${sideCls}">
      <div class="c c-time">${toTime(t.ts)}</div>
      <div class="c c-price">${fmtP(t.price)}</div>
      <div class="c c-qty">${fmtN(t.qty)}</div>
      <div class="c c-buyer" title="${buyerVal}">${buyerVal}</div>
      <div class="c c-seller" title="${sellerVal}">${sellerVal}</div>
    </div>`;
    if(tradesList.firstChild) tradesList.insertBefore(li,tradesList.firstChild); else tradesList.appendChild(li);
    while(tradesList.children.length>MAX_TRADES) tradesList.removeChild(tradesList.lastChild);
    if(tradesEmpty) tradesEmpty.style.display = tradesList.children.length?"none":"";
  }
  let wsTrade=null, tradeConnId=0;
  function connectTrades(){
    tradeConnId++; const myId=tradeConnId;
    if(tradesEmpty) tradesEmpty.style.display="";
    const sym=(new URLSearchParams(location.search)).get("symbol")||(window.SYMBOL||"ASTOR"); const sUp=(sym||"ASTOR").toUpperCase();
    const url=((location.protocol==="https:")?"wss://":"ws://")+location.host+((typeof window.WS_TRADE_PATH==="string"&&window.WS_TRADE_PATH)||("/ws/trade/"+sUp));
    try{ wsTrade&&wsTrade.close(); }catch{} wsTrade=null;
    let backoff=800; const schedule=()=>{ if(myId!==tradeConnId) return; setTimeout(connectTrades, backoff+Math.random()*300|0); backoff=Math.min(backoff*1.7,10000); };
    try{ wsTrade=new WebSocket(url); }catch{ return schedule(); }
    wsTrade.onopen =()=>{ if(myId!==tradeConnId) return; backoff=800; };
    wsTrade.onclose=()=>{ if(myId!==tradeConnId) return; if(tradesEmpty) tradesEmpty.style.display=""; schedule(); };
    wsTrade.onerror=()=>{};
    wsTrade.onmessage=(ev)=>{
      if(myId!==tradeConnId) return;
      try{
        if(typeof ev.data==="string" && ev.data.trim().startsWith("{")){
          const msg=JSON.parse(ev.data); const t=msg && msg.trade; if(t){ addTrade(t); return; }
        }
      }catch{}
      try{
        const bin=atob(ev.data); const u8=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) u8[i]=bin.charCodeAt(i);
        const t=decodeTrade(u8); if(t) addTrade(t);
      }catch{}
    };
  }

  // ------- market snapshot (proto doubles/varint) -------
  function rv64(buf,i){ let x=0n,s=0n,b=0; do{ b=buf[i++]; x|=BigInt(b&0x7f)<<s; s+=7n; }while(b&0x80); return [Number(x),i]; }
  function rf64(buf,i){ const dv=new DataView(buf.buffer,buf.byteOffset,buf.byteLength); const v=dv.getFloat64(i,true); return [v,i+8]; }
  function decodeRawSnapshot(u8){ let i=0,L=u8.length,out={}; while(i<L){ let tag;[tag,i]=rv64(u8,i); const f=(tag>>3),wt=(tag&7);
    if(wt===1){ let v;[v,i]=rf64(u8,i); out[f]=v; continue; }
    if(wt===0){ let v;[v,i]=rv64(u8,i); out[f]=v; continue; }
    if(wt===2){ let len;[len,i]=rv64(u8,i); i+=len; continue; }
    if(wt===5){ i+=4; continue; } break;
  } return out; }
  function pickNumber(...c){ for(const v of c){ if(v==null) continue; const n=Number(v); if(Number.isFinite(n)) return n; } return undefined; }

  const mkt = { lastSnap:undefined, prev:undefined, bid:undefined, ask:undefined, high:undefined, low:undefined, ceil:undefined, floor:undefined, volume:undefined, turnover:undefined };
  function renderHeaderAndDiff(){
    const last = (lastFromTrade!=null ? lastFromTrade : mkt.lastSnap);
    const prev = mkt.prev;
    let diff=null, diffPct=null;
    if(last!=null && prev!=null && prev!==0){ diff = last - prev; diffPct = diff/prev*100; }
    if(headlineLast){ headlineLast.textContent = last!=null ? fmtP(last) : "—"; headlineLast.style.color="inherit"; }
    const color = diff==null ? "" : (diff>=0 ? "var(--bid)" : "var(--ask)");
    if(headlineDiff){ headlineDiff.textContent = (diff!=null) ? `${diff>=0?"+":""}${fmtP(diff)}` : "—"; headlineDiff.style.color=color; }
    if(headlineDiffPct){ headlineDiffPct.textContent = (diffPct!=null) ? `(${diffPct>=0?"+":""}${fmtP(diffPct,2)}%)` : ""; headlineDiffPct.style.color=color; }
  }
  function renderPanel(){
    if(s_bid)  s_bid.textContent  = mkt.bid  !=null ? fmtP(mkt.bid)  : "—";
    if(s_ask)  s_ask.textContent  = mkt.ask  !=null ? fmtP(mkt.ask)  : "—";
    if(s_prev) s_prev.textContent = mkt.prev !=null ? fmtP(mkt.prev) : "—";
    if(s_high) s_high.textContent = mkt.high !=null ? fmtP(mkt.high) : "—";
    if(s_low)  s_low.textContent  = mkt.low  !=null ? fmtP(mkt.low)  : "—";
    if(s_ceil) s_ceil.textContent = mkt.ceil !=null ? fmtP(mkt.ceil) : "—";
    if(s_floor)s_floor.textContent= mkt.floor!=null ? fmtP(mkt.floor): "—";
    if(s_qty)  s_qty.textContent  = mkt.volume!=null ? fmtN(mkt.volume) : "—";
    if(s_turn) s_turn.textContent = mkt.turnover!=null ? Number(mkt.turnover).toLocaleString("tr-TR") : "—";
    renderHeaderAndDiff();
  }

  let wsMkt=null, mktConnId=0;
  function connectMarket(){
    mktConnId++; const myId=mktConnId;
    const sym=(new URLSearchParams(location.search)).get("symbol")||(window.SYMBOL||"ASTOR");
    const sUp=(sym||"ASTOR").toUpperCase();
    const url=((location.protocol==="https:")?"wss://":"ws://")+location.host+(window.WS_MARKET_PATH || ("/ws/market/"+sUp));
    try{ wsMkt&&wsMkt.close(); }catch{} wsMkt=null;
    let backoff=800; const schedule=()=>{ if(myId!==mktConnId) return; setTimeout(connectMarket, backoff+Math.random()*300|0); backoff=Math.min(backoff*1.7,10000); };
    try{ wsMkt=new WebSocket(url); }catch{ return schedule(); }
    wsMkt.onopen =()=>{ backoff=800; };
    wsMkt.onclose=()=>{ schedule(); };
    wsMkt.onerror=()=>{};
    wsMkt.onmessage=(ev)=>{
      if(myId!==mktConnId) return;
      try{
        const bin=atob(ev.data); const u8=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) u8[i]=bin.charCodeAt(i);
        const raw=decodeRawSnapshot(u8);

        // eşleştirme (DÜZ: Alış ≠ Önceki, karışıklık giderildi)
        mkt.lastSnap = pickNumber(raw[5], raw[25])                ?? mkt.lastSnap;   // snapshot last (yedek)
        mkt.ask      = pickNumber(raw[6])                          ?? mkt.ask;        // Satış
        mkt.bid      = pickNumber(raw[10], raw[42], raw[7])        ?? mkt.bid;        // Alış (VWAP öncelik)
        mkt.high     = pickNumber(raw[8], raw[13], raw[54])        ?? mkt.high;
        mkt.low      = pickNumber(raw[12], raw[55])                ?? mkt.low;
        mkt.ceil     = pickNumber(raw[26], raw[21])                ?? mkt.ceil;
        mkt.floor    = pickNumber(raw[27], raw[22])                ?? mkt.floor;
        mkt.volume   = pickNumber(raw[14], raw[48])                ?? mkt.volume;
        mkt.turnover = pickNumber(raw[15], raw[38], raw[80], raw[81], raw[28], raw[33]) ?? mkt.turnover;
        mkt.prev     = pickNumber(raw[9], raw[62], raw[47])        ?? mkt.prev;       // Önceki Kapanış SADECE bu tag'lar

        renderPanel(); // panel + header/diff
      }catch{}
    };
  }

  // ------- init -------
  try{ window.Telegram && Telegram.WebApp && Telegram.WebApp.ready(); }catch{}
  try{ window.Telegram?.WebApp?.expand?.(); }catch{}

  connectDepth();
  connectTrades(); // last burada canlı
  connectMarket();
})();
