from typing import List, Dict, Any
from app.matriks_pb2 import DepthSnapshot  # protoc çıktısı

def decode_depth_snapshot(payload: bytes) -> List[Dict[str, Any]]:
    """
    PUBLISH payload'ından DepthSnapshot parse eder ve 10 kademelik birleşik tablo döner.
    Kolonlar: level, bid_order, bid_qty, bid_price, ask_price, ask_qty, ask_order
    """
    snap = DepthSnapshot()
    snap.ParseFromString(payload)

    # bids ve asks’i level hizalayıp 10 satır çıkaralım
    # Not: Sağlayıcı en iyi fiyat 0. indexte -> level = i+1
    rows: List[Dict[str, Any]] = []
    max_len = max(len(snap.bids), len(snap.asks), 10)
    for i in range(min(max_len, 10)):
        bid = snap.bids[i] if i < len(snap.bids) else None
        ask = snap.asks[i] if i < len(snap.asks) else None
        rows.append({
            "level": i + 1,
            "bid_order": (bid.orders if bid else None),
            "bid_qty": (bid.qty if bid else None),
            "bid_price": (f"{bid.price:.2f}" if bid else None),
            "ask_price": (f"{ask.price:.2f}" if ask else None),
            "ask_qty": (ask.qty if ask else None),
            "ask_order": (ask.orders if ask else None),
        })
    return rows