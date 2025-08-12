# app/connect_builder.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import typing as _t

# ---------- MQTT benzeri VLQ (Remaining Length) ----------
def _read_vlq(buf: bytes, i: int) -> tuple[int, int]:
    m = 1
    val = 0
    n = 0
    while True:
        if i + n >= len(buf):
            raise ValueError("VLQ out of range")
        b = buf[i + n]
        n += 1
        val += (b & 0x7F) * m
        if (b & 0x80) == 0:
            break
        m *= 128
        if m > (128**3):
            raise ValueError("VLQ too large")
    return val, n

def _enc_vlq(n: int) -> bytes:
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

def _is_b64url_byte(b: int) -> bool:
    # A-Z a-z 0-9 - _  .
    return (
        0x30 <= b <= 0x39 or  # 0-9
        0x41 <= b <= 0x5A or  # A-Z
        0x61 <= b <= 0x7A or  # a-z
        b in (0x2D, 0x5F, 0x2E)  # - _ .
    )

def _find_jwt_span(body: bytes) -> tuple[int, int]:
    """
    body içinde base64url charset'inden oluşan, iki '.' içeren en uzun segmenti bul.
    Dönüş: (start, end) [end dahil değil]
    """
    n = len(body)
    best = (-1, -1)
    i = 0
    while i < n:
        # 'eyJ' ile başlayan adayları ara
        if body[i:i+3] != b"eyJ":
            i += 1
            continue
        j = i + 3
        dots = 0
        while j < n and _is_b64url_byte(body[j]):
            if body[j] == 0x2E:  # '.'
                dots += 1
                if dots == 2:
                    # imzayı da al: imza parçası da b64url'dir
                    j += 1
                    while j < n and _is_b64url_byte(body[j]) and body[j] != 0x2E:
                        j += 1
                    # Tam JWT: 3 parça
                    if j - i >= 16:  # aşırı kısa olmasın
                        if j - i > 4096:
                            raise ValueError("JWT span too long")
                        return (i, j)
                    break
            j += 1
        i = j
    return best

def replace_jwt_in_connect(template: bytes, new_jwt: bytes) -> bytes:
    """
    template: (başı 0x10 olabilir veya olmayabilir) + [RL][BODY]
    Dönen: **0x10 OLMADAN** [RL'][BODY'] (preamble'ı WS tarafında ayrı gönderiyoruz)
    """
    # Eğer başta 0x10 varsa at
    if template and template[0] == 0x10:
        tail = template[1:]
    else:
        tail = template[:]

    # [RL][BODY]
    rl_val, rl_n = _read_vlq(tail, 0)
    body = bytearray(tail[rl_n:])

    # BODY içinde JWT'yi bul
    s, e = _find_jwt_span(body)
    if s < 0:
        raise ValueError("JWT not found in CONNECT body")

    # JWT'nin hemen öncesinde 2-bayt BE uzunluk bekliyoruz
    if s < 2:
        raise ValueError("No room for password length field before JWT")
    old_plen = (body[s-2] << 8) | body[s-1]

    # Eski uzunluk uyuşmasa da (bazı sağlayıcı farkları) zorlayıp değiştiririz
    new_plen = len(new_jwt)
    if new_plen > 0xFFFF:
        raise ValueError("JWT too long")

    # 1) length'i yaz
    body[s-2] = (new_plen >> 8) & 0xFF
    body[s-1] = new_plen & 0xFF

    # 2) içerik değişimi
    old_len = e - s
    if new_plen == old_len:
        body[s:e] = new_jwt
    else:
        before = body[:s]
        after  = body[e:]
        body = bytearray(before + new_jwt + after)

    # Yeni Remaining Length = len(body)
    new_rl = len(body)
    tail_out = _enc_vlq(new_rl) + bytes(body)
    return tail_out
