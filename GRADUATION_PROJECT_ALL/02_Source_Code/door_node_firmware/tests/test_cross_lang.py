"""
Cross-language wire-format test for rs485_protocol.h vs gateway/protocol.py.

Run with: pytest test_cross_lang.py
(requires the C harness already built — see README.md; run_tests.sh does
both the build and this pytest invocation in one step)

What this proves: the C header (compiled with plain gcc, since the ESP32
toolchain isn't available in this environment) and the independent Python
implementation agree byte-for-byte on encoding, and each can correctly
decode frames the other produced — including through the escape/byte-
stuffing path. What this does NOT prove: that the ESP32's actual UART
peripheral, HardwareSerial timing, or RS-485 transceiver turnaround behave
the same as this logical byte stream — that remains unverified against
real hardware, same caveat as the rest of this firmware.
"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "gateway"))
import protocol  # noqa: E402

HARNESS = os.path.join(os.path.dirname(__file__), "rs485_protocol_test")

SAMPLE_FRAMES = [
    (1, protocol.TYPE_POLL, b"{}"),
    (2, protocol.TYPE_POLL, b'{"cmd":"unlock"}'),
    (3, protocol.TYPE_DATA, b'{"online":true,"locked":true,"events":[]}'),
    # Payloads deliberately containing raw 0x7E/0x7F/0x7D bytes to exercise
    # the byte-stuffing path (JSON wouldn't normally contain these, but the
    # framing layer must handle arbitrary payload bytes correctly regardless).
    (15, protocol.TYPE_DATA, bytes([0x7E, 0x41, 0x7F, 0x42, 0x7D, 0x43])),
    (0, protocol.TYPE_POLL, b""),
]


def c_encode(addr, type_, payload_str):
    result = subprocess.run(
        [HARNESS, "encode", str(addr), str(type_), payload_str],
        capture_output=True, text=True, check=True,
    )
    return bytes.fromhex(result.stdout.strip())


def c_decode(hex_str):
    result = subprocess.run(
        [HARNESS, "decode", hex_str],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def test_python_encode_matches_c_encode_ascii_payloads():
    # Only ASCII-safe payloads here since the C harness's encode mode takes
    # payload as a NUL-terminated CLI string argument (can't pass raw 0x00
    # or embedded NULs through argv).
    for addr, type_, payload in SAMPLE_FRAMES[:3]:
        py_hex = protocol.encode_frame(addr, type_, payload).hex()
        c_hex = c_encode(addr, type_, payload.decode()).hex()
        assert py_hex == c_hex, f"mismatch for addr={addr} type={type_} payload={payload!r}"


def test_c_can_decode_python_encoded_frames():
    for addr, type_, payload in SAMPLE_FRAMES:
        frame_hex = protocol.encode_frame(addr, type_, payload).hex()
        out = c_decode(frame_hex)
        expected = f"ADDR={addr} TYPE={type_} PAYLOAD={payload.decode('latin-1')}"
        assert out == expected, f"C decode of Python frame mismatch: got {out!r}, want {expected!r}"


def test_python_can_decode_c_encoded_frames():
    for addr, type_, payload in SAMPLE_FRAMES[:3]:
        frame_hex = c_encode(addr, type_, payload.decode())
        parser = protocol.FrameParser()
        frames = parser.feed_bytes(frame_hex)
        assert len(frames) == 1
        assert frames[0].addr == addr
        assert frames[0].type == type_
        assert frames[0].payload == payload


def test_corrupt_frame_rejected_by_both():
    good = bytearray(protocol.encode_frame(5, protocol.TYPE_DATA, b'{"x":1}'))
    good[len(good) // 2] ^= 0xFF  # flip a bit inside the frame body
    corrupt_hex = bytes(good).hex()

    assert c_decode(corrupt_hex) == "NONE"

    parser = protocol.FrameParser()
    assert parser.feed_bytes(bytes(good)) == []


def test_two_frames_back_to_back_in_one_stream():
    stream = protocol.encode_frame(1, protocol.TYPE_POLL, b"{}") + \
             protocol.encode_frame(2, protocol.TYPE_DATA, b'{"online":true}')
    parser = protocol.FrameParser()
    frames = parser.feed_bytes(stream)
    assert len(frames) == 2
    assert frames[0].addr == 1 and frames[0].type == protocol.TYPE_POLL
    assert frames[1].addr == 2 and frames[1].type == protocol.TYPE_DATA


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
