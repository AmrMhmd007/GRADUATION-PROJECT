# RS-485 Protocol Cross-Language Test

The ESP32/PlatformIO toolchain could not be run in this development
environment (no hardware, and the Espressif platform download did not
complete within the sandbox — the same limitation noted throughout this
firmware's other READMEs). That means `rs485_protocol.h`'s framing,
checksum, and byte-stuffing logic has never been compiled as part of the
real firmware here.

What *has* been done instead: `rs485_protocol.h` is plain, hardware-agnostic
C (no Arduino types), so it can also be compiled standalone with ordinary
`gcc` — completely outside the ESP32 toolchain — and exercised against an
independent Python re-implementation of the same wire format
(`../../gateway/protocol.py`). If both implementations, written separately,
agree byte-for-byte on every encode/decode/corruption case, that's real
evidence the protocol definition itself is correct — it just doesn't tell
you anything about how the ESP32's actual UART hardware behaves.

## Running it

```
cd tests
gcc -std=c11 -Wall -Wextra -I../include -o rs485_protocol_test rs485_protocol_test.c
python3 -m pytest test_cross_lang.py -v
```

Expected: 5 passed (encode parity, C-decodes-Python-frames,
Python-decodes-C-frames, corrupt-frame rejection, back-to-back frames on
one stream).

## What this proves and doesn't prove

Proves: the frame format (SOF/ADDR/TYPE/LEN/PAYLOAD/CHECKSUM/EOF), the
byte-stuffing escape logic, and checksum validation are unambiguous and
implemented identically by two independent codebases — including edge
cases like payload bytes that collide with the SOF/EOF/ESC markers, and
recovery from a corrupted frame.

Does not prove: that the ESP32's `HardwareSerial`, the MAX485 transceiver's
driver-enable turnaround timing, or real RS-485 bus electrical behavior
(reflections, noise, termination) work correctly with this protocol. That
requires a real board and a real bus — flagged as an open bench-test item
in `Phase6_Multi_Node_Deployment_Guide.docx`, same as the DESFire AES
handshake was flagged in Phase 5.
