from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict
import io
from datetime import datetime

def render_depth_png(levels: List[Dict], symbol: str) -> bytes:
    """
    Basit ve net bir tabloyu PNG olarak üretir (snapshot).
    """
    # Görsel ölçüleri
    W, H = 1200, 600
    img = Image.new("RGB", (W, H), (12, 18, 24))
    d = ImageDraw.Draw(img)

    # Font — sistemde yoksa default
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font = ImageFont.truetype("DejaVuSans.ttf", 24)
    except:
        font_title = ImageFont.load_default()
        font = ImageFont.load_default()

    title = f"{symbol} | 10 Kademe Derinlik — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    d.text((24, 20), title, fill=(220, 230, 240), font=font_title)

    # Kolon başlıkları
    headers = ["Seviye", "Alış Emri#", "Alış Miktar", "Alış Fiyat", "Satış Fiyat", "Satış Miktar", "Satış Emri#"]
    x = [24, 160, 320, 520, 720, 920, 1100]
    d.rectangle((20, 80, W-20, 120), outline=(80,90,100), width=1)
    for i, h in enumerate(headers):
        d.text((x[i], 90), h, fill=(180, 190, 200), font=font)

    # Satırlar
    row_h = 40
    for idx, row in enumerate(levels[:10]):
        y = 120 + idx*row_h
        if idx % 2 == 0:
            d.rectangle((20, y, W-20, y+row_h), fill=(20, 26, 32))
        else:
            d.rectangle((20, y, W-20, y+row_h), fill=(24, 30, 36))
        vals = [
            str(row.get("level","")),
            str(row.get("bid_order","")),
            str(row.get("bid_qty","")),
            str(row.get("bid_price","")),
            str(row.get("ask_price","")),
            str(row.get("ask_qty","")),
            str(row.get("ask_order","")),
        ]
        for i, v in enumerate(vals):
            d.text((x[i], y+8), v, fill=(220, 230, 240), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
