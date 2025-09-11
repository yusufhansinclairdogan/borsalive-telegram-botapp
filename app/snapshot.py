from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import io
import os

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
    if v in (None, ""):
        return "—"
    try:
        n = int(v)
        return f"{n:,}".replace(",", ".")
    except Exception:
        return str(v)


def _fmt_price(v) -> str:
    if v in (None, ""):
        return "—"
    try:
        f = float(v)
        s = f"{f:,.2f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    except Exception:
        return str(v)


# --- Presets: (w, h, header_h, row_h) ---
_PRESETS: dict[str, Tuple[int, int, int, int]] = {
    "mobile": (1080, 1700, 180, 110),
    "square": (1200, 1200, 160, 100),
    "wide": (1600, 900, 150, 90),
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
    Snapshot:
      - Üst bar: Hisse, Son Fiyat, Değişim(%) ve Değişim(TL), mini istatistik (Önceki, Yüksek, Düşük, Tavan, Taban, Hacim)
      - Orta: 10 kademe (alış/satış)
      - Alt: Son 5 işlem
      - Arka: Ortada çapraz yarı saydam watermark (iki satır)
    """
    width, height, header_h, row_h = _PRESETS.get(size, _PRESETS["mobile"])
    W, H = width * scale, height * scale
    HEADER_H, ROW_H = header_h * scale, row_h * scale
    PAD = 32 * scale
    GAP = 20 * scale

    # Dark tema
    BG = (12, 18, 24)
    PANEL = (20, 26, 32)
    LINE = (55, 66, 77)
    TXT = (235, 240, 248)
    MUTE = (168, 178, 190)
    BID = (34, 197, 94)
    ASK = (239, 68, 68)

    title_f = _load_font(_DEF_SANS_BOLD, int(50 * scale))
    head_f = _load_font(_DEF_SANS_BOLD, int(36 * scale))
    num_f = _load_font(_DEF_SANS, int(38 * scale))
    small_f = _load_font(_DEF_SANS, int(28 * scale))

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Header panel
    top_y = PAD
    d.rounded_rectangle(
        (PAD, top_y, W - PAD, top_y + HEADER_H),
        radius=20 * scale,
        fill=PANEL,
        outline=LINE,
        width=2,
    )

    left_x = PAD + 24 * scale
    ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    d.text(
        (W - PAD - d.textlength(ts, font=small_f), top_y + 16 * scale),
        ts,
        fill=MUTE,
        font=small_f,
    )
    d.text(
        (left_x, top_y + 16 * scale), f"{symbol} — 10 Kademe", fill=TXT, font=title_f
    )

    # Fiyat / değişim
    px = (quote or {}).get("last")
    prev = (quote or {}).get("prev_close")
    hi = (quote or {}).get("high")
    lo = (quote or {}).get("low")
    vol = (quote or {}).get("volume")

    # Değişimleri hesapla (abs & %)
    change_abs = None
    change_pct = None
    if isinstance(px, (int, float)) and isinstance(prev, (int, float)) and prev:
        change_abs = px - prev
        change_pct = (change_abs / prev) * 100.0

    px_s = _fmt_price(px)
    chp_s = f"{change_pct:+.2f}%" if isinstance(change_pct, (int, float)) else "—"
    cha_s = f"{change_abs:+.2f}" if isinstance(change_abs, (int, float)) else ""
    col = BID if (isinstance(change_pct, (int, float)) and change_pct >= 0) else ASK

    d.text(
        (left_x, top_y + 90 * scale),
        f"Fiyat: {px_s}   Değişim: {chp_s} {cha_s}",
        fill=col,
        font=head_f,
    )

    # mini stats
    stats_y = top_y + 140 * scale

    def _label(x, text, val, col=TXT):
        d.text((x, stats_y), text, fill=MUTE, font=small_f)
        d.text((x, stats_y + 32 * scale), val, fill=col, font=num_f)

    ceil = (quote or {}).get("ceiling")
    floor = (quote or {}).get("floor")
    if ceil is None and isinstance(prev, (int, float)):
        ceil = prev * 1.10
    if floor is None and isinstance(prev, (int, float)):
        floor = prev * 0.90

    cols_x = [
        left_x,
        left_x + 280 * scale,
        left_x + 530 * scale,
        left_x + 780 * scale,
        left_x + 1030 * scale,
        left_x + 1280 * scale,
    ]
    items = [
        ("Önceki", _fmt_price(prev)),
        ("Yüksek", _fmt_price(hi)),
        ("Düşük", _fmt_price(lo)),
        ("Tavan", _fmt_price(ceil)),
        ("Taban", _fmt_price(floor)),
        ("Hacim", _fmt_qty(vol)),
    ]
    for i, (k, v) in enumerate(items):
        _label(
            cols_x[i],
            k,
            v,
            (
                BID
                if k in ("Yüksek", "Tavan")
                else (ASK if k in ("Düşük", "Taban") else TXT)
            ),
        )

    # Depth panel (10 kademe)
    list_top = top_y + HEADER_H + GAP
    d.rounded_rectangle(
        (PAD, list_top, W - PAD, list_top + 10 * ROW_H + 60 * scale),
        radius=20 * scale,
        fill=PANEL,
        outline=LINE,
        width=2,
    )
    mid = W // 2
    d.text((PAD + 24 * scale, list_top + 16 * scale), "ALIŞ", fill=BID, font=head_f)
    d.text((mid + 24 * scale, list_top + 16 * scale), "SATIŞ", fill=ASK, font=head_f)

    def head_labels(x0):
        d.text((x0, list_top + 60 * scale), "Fiyat", fill=MUTE, font=small_f)
        d.text(
            (x0 + 260 * scale, list_top + 60 * scale), "Miktar", fill=MUTE, font=small_f
        )
        d.text(
            (x0 + 470 * scale, list_top + 60 * scale), "Emir#", fill=MUTE, font=small_f
        )

    head_labels(PAD + 24 * scale)
    head_labels(mid + 24 * scale)

    base_y = list_top + 100 * scale
    for i in range(10):
        y = base_y + i * ROW_H
        if i % 2 == 0:
            d.rectangle(
                (PAD, y - 8 * scale, W - PAD, y + ROW_H - 8 * scale), fill=(24, 30, 36)
            )
        row = levels[i] if i < len(levels) else {}
        d.text(
            (PAD + 24 * scale, y),
            _fmt_price(row.get("bid_price")),
            fill=TXT,
            font=num_f,
        )
        d.text(
            (PAD + 24 * scale + 260 * scale, y),
            _fmt_qty(row.get("bid_qty")),
            fill=TXT,
            font=num_f,
        )
        d.text(
            (PAD + 24 * scale + 470 * scale, y),
            _fmt_qty(row.get("bid_order")),
            fill=MUTE,
            font=num_f,
        )
        d.text(
            (mid + 24 * scale, y),
            _fmt_price(row.get("ask_price")),
            fill=TXT,
            font=num_f,
        )
        d.text(
            (mid + 24 * scale + 260 * scale, y),
            _fmt_qty(row.get("ask_qty")),
            fill=TXT,
            font=num_f,
        )
        d.text(
            (mid + 24 * scale + 470 * scale, y),
            _fmt_qty(row.get("ask_order")),
            fill=MUTE,
            font=num_f,
        )

    # Trades panel (son 5)
    trades_top = base_y + 10 * ROW_H + 30 * scale
    d.rounded_rectangle(
        (PAD, trades_top, W - PAD, trades_top + 5 * ROW_H + 70 * scale),
        radius=20 * scale,
        fill=PANEL,
        outline=LINE,
        width=2,
    )
    d.text(
        (PAD + 24 * scale, trades_top + 16 * scale),
        "Son İşlemler",
        fill=TXT,
        font=head_f,
    )
    th_y = trades_top + 60 * scale
    heads = [
        ("Saat", 0),
        ("Fiyat", 220 * scale),
        ("Miktar", 420 * scale),
        ("Alıcı", 640 * scale),
        ("Satıcı", 920 * scale),
    ]
    for h, dx in heads:
        d.text((PAD + 24 * scale + dx, th_y), h, fill=MUTE, font=small_f)

    ty0 = trades_top + 100 * scale
    for i in range(min(5, len(trades))):
        t = trades[i]
        y = ty0 + i * ROW_H
        if i % 2 == 0:
            d.rectangle(
                (PAD, y - 8 * scale, W - PAD, y + ROW_H - 8 * scale), fill=(24, 30, 36)
            )
        # saat
        ts = t.get("ts", 0)
        try:
            ms = int(ts)
            if ms > 1e14:
                ms //= 1_000_000
            elif ms > 1e12:
                ms //= 1_000
            txt_time = datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S")
        except Exception:
            txt_time = "—"
        price = _fmt_price(t.get("price"))
        qty = _fmt_qty(t.get("qty"))
        buyer = t.get("buyer") or "—"
        seller = t.get("seller") or "—"
        side = (t.get("side") or "").lower()[:1]
        colp = BID if side == "b" else ASK

        d.text((PAD + 24 * scale + 0, y), txt_time, fill=MUTE, font=num_f)
        d.text((PAD + 24 * scale + 220 * scale, y), price, fill=colp, font=num_f)
        d.text((PAD + 24 * scale + 420 * scale, y), qty, fill=colp, font=num_f)
        d.text((PAD + 24 * scale + 640 * scale, y), str(buyer), fill=TXT, font=num_f)
        d.text((PAD + 24 * scale + 920 * scale, y), str(seller), fill=TXT, font=num_f)

    # --- WATERMARK (en sonda üstte ve çapraz) ---
    wm_top = "Borsa Live"
    wm_bot = "App by Yusufhan Doğan"
    wm_f1 = _load_font(_DEF_SANS_BOLD, int(110 * scale))
    wm_f2 = _load_font(_DEF_SANS_BOLD, int(70 * scale))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    text_w = int(
        max(od.textlength(wm_top, font=wm_f1), od.textlength(wm_bot, font=wm_f2))
        + 80 * scale
    )
    text_h = int(200 * scale)
    slab = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(slab)
    col = (255, 255, 255, 28)  # şeffaflık
    sd.text((0, 0), wm_top, fill=col, font=wm_f1)
    sd.text((0, int(120 * scale)), wm_bot, fill=col, font=wm_f2)
    slab = slab.rotate(45, expand=True)
    cx, cy = W // 2, H // 2
    overlay.alpha_composite(slab, dest=(cx - slab.width // 2, cy - slab.height // 2))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    if scale > 1:
        img = img.resize((width, height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
