# app/mqtt_subscribe_chunked.py
from typing import List


def _enc_vlq(n: int) -> bytes:
    # MQTT remaining length (varint)
    out = bytearray()
    while True:
        d = n % 128
        n //= 128
        if n:
            d |= 0x80
        out.append(d)
        if not n:
            break
    return bytes(out)


def _enc_u16(n: int) -> bytes:
    return n.to_bytes(2, "big")


def _enc_topic(t: str) -> bytes:
    b = t.encode("utf-8")
    return _enc_u16(len(b)) + b


def _build_sub_body(packet_id: int, topic: str, qos: int = 0) -> bytes:
    # Variable header (2) + payload(topic len+data + qos)
    payload = _enc_topic(topic) + bytes([qos & 0x03])
    body = _enc_u16(packet_id) + payload
    rl = _enc_vlq(len(body))
    return rl + body


def build_chunked_subscribe(topics: List[str], base_packet_id: int) -> bytes:
    """
    topics: ["mx/depth/SYM@lvl2", "mx/depth/SYM@lvl3", "mx/depthstats/SYM"]
    Dönen bytes, 'gg==' (0x82) frame'inden HEMEN SONRA tek parça olarak gönderilir.
    Yapı:
      [RL+Body(pktid=base)] + [0x82 + RL+Body(pktid=base+1)] + [0x82 + RL+Body(pktid=base+2)]
    """
    out = bytearray()
    # 1. parça: BAŞLIK YOK (çünkü önce gg== gönderiyoruz)
    out += _build_sub_body(base_packet_id + 0, topics[0])
    # 2. ve 3. parça: başında 0x82 (SUBSCRIBE header)
    for i in range(1, len(topics)):
        out.append(0x82)
        out += _build_sub_body(base_packet_id + i, topics[i])
    return bytes(out)
