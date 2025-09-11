# app/trade_parser.py
# -*- coding: utf-8 -*-
"""
MQTT PUBLISH payload'ındaki tradefeed.Trade mesajını (proto3)
google protobuf'a ihtiyaç duymadan decode eder.
Alanlar:
  1: topic (string)
  2: symbol (string)
  3: price (float - wire type 5, 32-bit)
  4: qty (varint)
  5: side (string)  -> "a" (ask / satış), "b" (bid / alış)
  6: ts (varint)
  7: buyer (string)
  8: seller (string)
"""
from __future__ import annotations
import struct
from typing import Dict, Any, Tuple


def _get_varint(b: bytes, i: int) -> Tuple[int, int]:
    """varint -> (value, new_index)"""
    val = 0
    shift = 0
    while True:
        if i >= len(b):
            raise ValueError("varint out of range")
        c = b[i]
        i += 1
        val |= (c & 0x7F) << shift
        if (c & 0x80) == 0:
            break
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    return val, i


def _get_len_delimited(b: bytes, i: int) -> Tuple[bytes, int]:
    ln, i = _get_varint(b, i)
    if i + ln > len(b):
        raise ValueError("len-delimited out of range")
    return b[i : i + ln], i + ln


def decode_trade(payload: bytes) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    i = 0
    L = len(payload)
    while i < L:
        key, i = _get_varint(payload, i)
        field_no = key >> 3
        wtype = key & 0x7

        if wtype == 0:  # varint
            val, i = _get_varint(payload, i)
            if field_no == 4:
                out["qty"] = val
            elif field_no == 6:
                out["ts"] = val
            else:
                # başka varint alan yok şu an
                pass

        elif wtype == 2:  # length-delimited (string/bytes)
            chunk, i = _get_len_delimited(payload, i)
            try:
                s = chunk.decode("utf-8", "ignore")
            except Exception:
                s = ""
            if field_no == 1:
                out["topic"] = s
            elif field_no == 2:
                out["symbol"] = s
            elif field_no == 5:
                out["side"] = s
            elif field_no == 7:
                out["buyer"] = s
            elif field_no == 8:
                out["seller"] = s

        elif wtype == 5:  # 32-bit (float)
            if i + 4 > L:
                break
            val = struct.unpack("<f", payload[i : i + 4])[0]
            i += 4
            if field_no == 3:
                out["price"] = float(val)

        else:
            # 64-bit veya diğer tipler beklenmiyor; atla
            if wtype == 1:  # 64-bit
                i += 8
            elif wtype == 3 or wtype == 4:
                # start/end group (proto2), beklemiyoruz
                pass
            else:
                # bilinmeyen -> kır
                break

    # defaults
    out.setdefault("topic", "")
    out.setdefault("symbol", "")
    out.setdefault("price", None)
    out.setdefault("qty", None)
    out.setdefault("side", "")
    out.setdefault("ts", None)
    out.setdefault("buyer", "")
    out.setdefault("seller", "")
    return out
