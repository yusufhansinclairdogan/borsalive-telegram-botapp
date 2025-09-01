from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import io
import os
import math

# --- Fonts ---
_DEF_SANS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_DEF_SANS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def _load_font(cands: list[str], size: int):
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()

# --- helpers ---
def _fmt_qty(v) -> str:
    if v in (None, ""): return ""
    try:
        n = int(v)
        return f"{n:,}".replace(",", ".")
    except Exception:
        return str(v)

def _fmt_price(v) -> str:
    if v in (None, ""): return ""
    try:
        f = float(v)
        s = f"{f:,.2f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    except Exception:
        return str(v)

# --- Presets: (w,h, header_h, row_h) ---
_PRESETS: dict[str, Tuple[int, int, int, int]] = {
    "mobile": (1080, 1700, 180, 110),
    "square": (1200, 1200, 160, 100),
    "wide":   (1600, 900,  150, 90),
}

def render_depth_png(
    levels: List[Dict],
    trades: List[Dict],
    symbol: str,
    quote: Optional[Dict] = None,
    size: str = "mobile",
    scale: int = 2,
) -> bytes:
    """
    Mobil uyumlu snapshot: üstte quote bar, ortada 10 kademe,
    altta Son İşlemler (6 satır), arkada watermark.
    """
    width, height, header_h, row_h = _PRESETS.get(size, _PRESETS["mobile"])
    W, H = width*scale, height*scale
    HEADER_H, ROW_H = header_h*scale, row_h*scale
    PAD = 32*scale
    GAP = 20*scale

    # Dark tema paleti
    BG=(12,18,24); PANEL=(20,26,32); LINE=(55,66,77)
    TXT=(235,240,248); MUTE=(168,178,190); BID=(34,197,94); ASK=(239,68,68)

    title_f = _load_font(_DEF_SANS_BOLD, int(50*scale))
    head_f  = _load_font(_DEF_SANS_BOLD, int(36*scale))
    num_f   = _load_font(_DEF_SANS,      int(38*scale))
    small_f = _load_font(_DEF_SANS,      int(28*scale))

    img = Image.new("RGB", (W,H), BG)
    d = ImageDraw.Draw(img)

    # Watermark (diagonal)
    wm = "Borsa Live — App by Yusufhan Doğan"
    wm_f = _load_font(_DEF_SANS_BOLD, int(72*scale))
    wt = d.textlength(wm, font=wm_f)
    d.text((W*0.5 - wt*0.5, H*0.55), wm, fill=(255,255,255,12), font=wm_f)

    # Header: Symbol + price + % + mini stats row
    top_y = PAD
    d.rounded_rectangle((PAD, top_y, W-PAD, top_y+HEADER_H), radius=20*scale, fill=PANEL, outline=LINE, width=2)

    left_x = PAD + 24*scale
    ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    d.text((W-PAD- d.textlength(ts, font=small_f), top_y+16*scale), ts, fill=MUTE, font=small_f)

    d.text((left_x, top_y+16*scale), f"{symbol} — 10 Kademe", fill=TXT, font=title_f)

    # price & change
    px = quote.get("last") if quote else None
    chp = quote.get("change_pct") if quote else None
    px_s = _fmt_price(px) if px is not None else "—"
    chp_s = f"{chp:+.2f}%" if isinstance(chp,(int,float)) else "—"
    col = BID if (isinstance(chp,(int,float)) and chp>=0) else ASK
    d.text((left_x, top_y+90*scale), f"Fiyat: {px_s}   Değişim: {chp_s}", fill=col, font=head_f)

    # mini stats row
    stats_y = top_y + 140*scale
    def _label(x, text, val, col=TXT):
        d.text((x, stats_y), f"{text}", fill=MUTE, font=small_f)
        d.text((x, stats_y+32*scale), val, fill=col, font=num_f)

    pc = quote.get("prev_close") if quote else None
    hi = quote.get("high") if quote else None
    lo = quote.get("low") if quote else None
    ceil = quote.get("ceiling") if quote else (pc*1.10 if pc else None)
    floor= quote.get("floor") if quote else (pc*0.90 if pc else None)
    vol = quote.get("volume") if quote else None

    cols_x = [left_x, left_x+280*scale, left_x+530*scale, left_x+780*scale, left_x+1030*scale, left_x+1280*scale]
    items = [("Önceki", _fmt_price(pc) if pc else "—"),
             ("Yüksek", _fmt_price(hi) if hi else "—"),
             ("Düşük",  _fmt_price(lo) if lo else "—"),
             ("Tavan",  _fmt_price(ceil) if ceil else "—"),
             ("Taban",  _fmt_price(floor) if floor else "—"),
             ("Hacim",  _fmt_qty(vol) if vol else "—")]
    for i,(k,v) in enumerate(items[:6]):
        _label(cols_x[i], k, v, (BID if k in ("Yüksek","Tavan") else (ASK if k in ("Düşük","Taban") else TXT)))

    # Depth panel
    list_top = top_y + HEADER_H + GAP
    d.rounded_rectangle((PAD, list_top, W-PAD, list_top + 10*ROW_H + 60*scale), radius=20*scale, fill=PANEL, outline=LINE, width=2)

    # headers
    mid = W//2
    d.text((PAD+24*scale, list_top+16*scale), "ALIŞ", fill=BID, font=head_f)
    d.text((mid+24*scale, list_top+16*scale), "SATIŞ", fill=ASK, font=head_f)
    def head_labels(x0):
        d.text((x0, list_top+60*scale), "Fiyat", fill=MUTE, font=small_f)
        d.text((x0+260*scale, list_top+60*scale), "Miktar", fill=MUTE, font=small_f)
        d.text((x0+470*scale, list_top+60*scale), "Emir#", fill=MUTE, font=small_f)
    head_labels(PAD+24*scale); head_labels(mid+24*scale)

    # rows
    base_y = list_top + 100*scale
    for i in range(10):
        y = base_y + i*ROW_H
        if i%2==0:
            d.rectangle((PAD, y-8*scale, W-PAD, y+ROW_H-8*scale), fill=(24,30,36))
        row = levels[i] if i < len(levels) else {}
        # bid
        d.text((PAD+24*scale, y), _fmt_price(row.get("bid_price")), fill=TXT, font=num_f)
        d.text((PAD+24*scale+260*scale, y), _fmt_qty(row.get("bid_qty")), fill=TXT, font=num_f)
        d.text((PAD+24*scale+470*scale, y), _fmt_qty(row.get("bid_order")), fill=MUTE, font=num_f)
        # ask
        d.text((mid+24*scale, y), _fmt_price(row.get("ask_price")), fill=TXT, font=num_f)
        d.text((mid+24*scale+260*scale, y), _fmt_qty(row.get("ask_qty")), fill=TXT, font=num_f)
        d.text((mid+24*scale+470*scale, y), _fmt_qty(row.get("ask_order")), fill=MUTE, font=num_f)

    # Trades panel (6 satır)
    trades_top = base_y + 10*ROW_H + 30*scale
    d.rounded_rectangle((PAD, trades_top, W-PAD, trades_top + 6*ROW_H + 70*scale),
                        radius=20*scale, fill=PANEL, outline=LINE, width=2)
    d.text((PAD+24*scale, trades_top+16*scale), "Son İşlemler", fill=TXT, font=head_f)
    # header cols
    th_y = trades_top+60*scale
    heads = [("Saat", 0), ("Fiyat", 220*scale), ("Miktar", 420*scale), ("Alıcı", 640*scale), ("Satıcı", 920*scale)]
    for h,dx in heads:
        d.text((PAD+24*scale+dx, th_y), h, fill=MUTE, font=small_f)

    ty0 = trades_top+100*scale
    for i in range(min(6, len(trades))):
        t = trades[i]
        y = ty0 + i*ROW_H
        if i%2==0:
            d.rectangle((PAD, y-8*scale, W-PAD, y+ROW_H-8*scale), fill=(24,30,36))
        # vals
        # time
        ts = t.get("ts", 0)
        try:
            ms = int(ts)
            if ms > 1e14: ms//=1_000_000
            elif ms > 1e12: ms//=1_000
            txt_time = datetime.fromtimestamp(ms/1000).strftime("%H:%M:%S")
        except Exception:
            txt_time = "—"
        price = _fmt_price(t.get("price"))
        qty   = _fmt_qty(t.get("qty"))
        buyer = (t.get("buyer") or "—")
        seller= (t.get("seller") or "—")
        side  = (t.get("side") or "").lower()[:1]
        colp  = BID if side=="b" else ASK

        d.text((PAD+24*scale+0,   y), txt_time, fill=MUTE, font=num_f)
        d.text((PAD+24*scale+220*scale, y), price, fill=colp, font=num_f)
        d.text((PAD+24*scale+420*scale, y), qty,   fill=colp, font=num_f)
        d.text((PAD+24*scale+640*scale, y), str(buyer), fill=TXT, font=num_f)
        d.text((PAD+24*scale+920*scale, y), str(seller), fill=TXT, font=num_f)

    if scale>1:
        img = img.resize((width, height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
