# app/gole_subscribe.py
from typing import Iterable, Tuple

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            break
    return bytes(out)

def build_gole_subscribe(topics: Iterable[Tuple[int, str]]) -> bytes:
    """
    topics: [(id, "mx/depth/SYMBOL@lvl2"), (id+1, "mx/depth/SYMBOL@lvl3"), (id+2,"mx/depthstats/SYMBOL")]
    Dönen bytes'ı doğrudan ws.send(...) ile yolla.
    """
    chunks = bytearray()
    first = True
    for rid, path in topics:
        if not first:
            chunks.append(0x82)  # örnekte 2. ve 3. girdiden önce 0x82 var
        first = False
        chunks.append(0x18)           # "id" için sabit önek (gözlenen format)
        chunks += _varint(int(rid))   # varint encoded route id
        path_b = path.encode("utf-8")
        plen = len(path_b)
        if plen > 0xFFFF:
            raise ValueError("path too long")
        # MQTT tarzı 2-bayt uzunluk (big-endian) gibi davranıyor: 0x00 <len>
        chunks += bytes([0x00, plen & 0xFF])
        chunks += path_b
        chunks.append(0x00)  # QoS 0
    return bytes(chunks)
