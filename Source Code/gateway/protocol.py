"""
Phase 6 — RS-485 multi-drop frame protocol, Python side.

This is an independent re-implementation of the exact wire format defined in
door_node_firmware/include/rs485_protocol.h (SOF/ADDR/TYPE/LEN/PAYLOAD/
CHECKSUM/EOF with PPP-style byte stuffing). It is deliberately NOT imported
from a shared source file — the point of having two from-scratch
implementations is that door_node_firmware/tests/rs485_protocol_test.c
(compiled with plain gcc) and this module can cross-check each other's
output byte-for-byte, which is a much stronger correctness signal for a
hand-rolled framing protocol than either implementation "trusting itself".
See door_node_firmware/tests/README.md for how that cross-check is run.
"""
from dataclasses import dataclass, field

SOF = 0x7E
EOF = 0x7F
ESC = 0x7D
ESC_XOR = 0x20

TYPE_POLL = 0x01
TYPE_DATA = 0x02

MAX_PAYLOAD = 200


def encode_frame(addr: int, type_: int, payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too long ({len(payload)} > {MAX_PAYLOAD})")

    checksum = addr ^ type_ ^ len(payload)
    for b in payload:
        checksum ^= b
    checksum &= 0xFF

    def emit(b: int, out: bytearray):
        if b in (SOF, EOF, ESC):
            out.append(ESC)
            out.append(b ^ ESC_XOR)
        else:
            out.append(b)

    out = bytearray()
    out.append(SOF)
    emit(addr, out)
    emit(type_, out)
    emit(len(payload), out)
    for b in payload:
        emit(b, out)
    emit(checksum, out)
    out.append(EOF)
    return bytes(out)


@dataclass
class DecodedFrame:
    addr: int
    type: int
    payload: bytes


class FrameParser:
    """Streaming decoder — feed bytes one at a time (or in chunks via
    feed_bytes), exactly like the ESP32 firmware's rs485_parser_feed()
    consuming rs485Serial.read() one byte at a time. Mirrors its states:
    WAIT_SOF -> BODY -> ESCAPED -> BODY -> ... -> emit on EOF.
    """

    def __init__(self):
        self._state = "WAIT_SOF"
        self._body = bytearray()

    def feed_bytes(self, data: bytes):
        frames = []
        for b in data:
            f = self._feed_one(b)
            if f is not None:
                frames.append(f)
        return frames

    def _feed_one(self, byte: int):
        if self._state == "WAIT_SOF":
            if byte == SOF:
                self._body = bytearray()
                self._state = "BODY"
            return None

        if self._state == "ESCAPED":
            self._body.append(byte ^ ESC_XOR)
            self._state = "BODY"
            return None

        # BODY
        if byte == SOF:
            # Resync onto the new frame rather than concatenating.
            self._body = bytearray()
            self._state = "BODY"
            return None
        if byte == ESC:
            self._state = "ESCAPED"
            return None
        if byte == EOF:
            self._state = "WAIT_SOF"
            body = self._body
            if len(body) < 4:
                return None
            addr, type_, length = body[0], body[1], body[2]
            if len(body) != 3 + length + 1:
                return None
            checksum = addr ^ type_ ^ length
            for b in body[3:3 + length]:
                checksum ^= b
            checksum &= 0xFF
            if checksum != body[3 + length]:
                return None  # corrupt frame, dropped
            return DecodedFrame(addr=addr, type=type_, payload=bytes(body[3:3 + length]))

        self._body.append(byte)
        return None
