#pragma once
// ============================================================================
// Phase 6 — RS-485 multi-drop frame protocol (Building Gateway <-> door
// nodes), shared wire format.
//
// This header is intentionally plain, hardware-agnostic C (no Arduino types,
// no dynamic allocation) for two reasons:
//   1. It's included directly by the ESP32 firmware (main.cpp).
//   2. It is ALSO compiled standalone with plain gcc in
//      tests/rs485_protocol_test.c to cross-check, byte for byte, against
//      the independent Python re-implementation in gateway/protocol.py.
//      That cross-language test is the actual verification for this wire
//      format — the ESP32 toolchain could not be run in this sandbox (same
//      limitation noted throughout this firmware), so the framing/checksum/
//      byte-stuffing logic is proven correct via gcc + Python instead of on
//      real hardware. See tests/README.md for how that test is run and what
//      it does and doesn't prove.
//
// --- Topology -----------------------------------------------------------
// One Building Gateway is the RS-485 bus master. It polls each door node in
// turn (round-robin); a node only transmits in the short window right after
// being polled. This avoids bus contention entirely without needing
// token-passing or CSMA/collision-detection logic on the ESP32 side — the
// standard, simplest-to-implement pattern for a small multi-drop RS-485
// deployment (single master avoids two nodes ever driving the line at once).
//
// --- Frame format (before byte-stuffing) ---------------------------------
//   [0]         SOF        0x7E
//   [1]         ADDR       node address, 1-15 (0 reserved: broadcast, unused
//                          in Phase 6; the gateway itself has no address, it
//                          is implicitly "whoever is polling")
//   [2]         TYPE       0x01 = POLL (gateway -> node)
//                          0x02 = DATA (node -> gateway)
//   [3]         LEN        payload length in bytes, 0-200
//   [4..4+LEN)  PAYLOAD    UTF-8 JSON
//   [4+LEN]     CHECKSUM   XOR of ADDR, TYPE, LEN, and every payload byte
//   [5+LEN]     EOF        0x7F
//
// --- Byte stuffing --------------------------------------------------------
// SOF/EOF/ESC bytes appearing inside ADDR/TYPE/LEN/PAYLOAD/CHECKSUM are
// escaped so the receiver can find frame boundaries unambiguously on a
// streaming UART: if a byte to be sent equals 0x7E, 0x7F, or 0x7D, it is
// replaced with 0x7D followed by (byte ^ 0x20). This is the same technique
// PPP/HDLC use and is simple enough to hand-implement identically in C and
// Python without a shared library.
//
// --- Payloads --------------------------------------------------------------
// POLL payload:  {}                      (no pending command)
//             or {"cmd":"unlock"}        (also "lock", "clear_tamper")
// DATA payload:  {"online":true,"locked":true,
//                 "events":[{"method":"card","result":"granted"}, ...],
//                 "alerts":[{"type":"tamper"}, ...]}
//             Node clears its own local event/alert queues once a DATA
//             frame carrying them has been sent (same "send then drop"
//             semantics as the existing MQTT offline-event buffer).
// ============================================================================

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define RS485_SOF   0x7E
#define RS485_EOF   0x7F
#define RS485_ESC   0x7D
#define RS485_ESC_XOR 0x20

#define RS485_TYPE_POLL 0x01
#define RS485_TYPE_DATA 0x02

#define RS485_MAX_PAYLOAD 200
// Raw (post-stuffing) worst case: SOF + EOF + checksum, each ADDR/TYPE/LEN/
// payload/checksum byte possibly doubled by stuffing.
#define RS485_MAX_FRAME_RAW (2 + 2 * (3 + RS485_MAX_PAYLOAD + 1))

// ---------------------------------------------------------------------------
// Encoding: builds a fully stuffed, on-wire frame ready to write to the UART.
// Returns the number of bytes written to out_buf, or 0 on failure (payload
// too long / output buffer too small).
// ---------------------------------------------------------------------------
static inline size_t rs485_encode_frame(uint8_t addr, uint8_t type,
                                         const uint8_t *payload, uint8_t payload_len,
                                         uint8_t *out_buf, size_t out_buf_size) {
  if (payload_len > RS485_MAX_PAYLOAD) return 0;
  if (out_buf_size < RS485_MAX_FRAME_RAW) return 0;

  uint8_t checksum = (uint8_t)(addr ^ type ^ payload_len);
  for (uint8_t i = 0; i < payload_len; i++) checksum ^= payload[i];

  size_t n = 0;
  out_buf[n++] = RS485_SOF;

  // Helper macro: stuff-and-emit one body byte (ADDR/TYPE/LEN/PAYLOAD/CHECKSUM).
  #define RS485_EMIT(b) do { \
    uint8_t _b = (b); \
    if (_b == RS485_SOF || _b == RS485_EOF || _b == RS485_ESC) { \
      out_buf[n++] = RS485_ESC; \
      out_buf[n++] = (uint8_t)(_b ^ RS485_ESC_XOR); \
    } else { \
      out_buf[n++] = _b; \
    } \
  } while (0)

  RS485_EMIT(addr);
  RS485_EMIT(type);
  RS485_EMIT(payload_len);
  for (uint8_t i = 0; i < payload_len; i++) RS485_EMIT(payload[i]);
  RS485_EMIT(checksum);

  #undef RS485_EMIT

  out_buf[n++] = RS485_EOF;
  return n;
}

// ---------------------------------------------------------------------------
// Streaming decoder: feed one raw (still-stuffed) byte at a time as it
// arrives from the UART. Returns 1 when `addr_out`/`type_out`/`payload_out`/
// `payload_len_out` hold a complete, checksum-verified frame; 0 otherwise
// (including "still waiting for more bytes" and "bad frame, resynchronizing").
// This mirrors how the ESP32 firmware actually receives bytes (one at a time
// from rs485Serial.read() inside a loop), rather than assuming a whole frame
// is available at once.
// ---------------------------------------------------------------------------
typedef enum {
  RS485_PSTATE_WAIT_SOF,
  RS485_PSTATE_BODY,
  RS485_PSTATE_ESCAPED,
} Rs485ParserState;

typedef struct {
  Rs485ParserState state;
  uint8_t body[3 + RS485_MAX_PAYLOAD + 1];  // ADDR, TYPE, LEN, payload..., CHECKSUM
  size_t body_len;
} Rs485Parser;

static inline void rs485_parser_init(Rs485Parser *p) {
  p->state = RS485_PSTATE_WAIT_SOF;
  p->body_len = 0;
}

static inline int rs485_parser_feed(Rs485Parser *p, uint8_t byte,
                                     uint8_t *addr_out, uint8_t *type_out,
                                     uint8_t *payload_out, uint8_t *payload_len_out) {
  switch (p->state) {
    case RS485_PSTATE_WAIT_SOF:
      if (byte == RS485_SOF) {
        p->body_len = 0;
        p->state = RS485_PSTATE_BODY;
      }
      return 0;

    case RS485_PSTATE_ESCAPED:
      if (p->body_len >= sizeof(p->body)) { p->state = RS485_PSTATE_WAIT_SOF; return 0; }
      p->body[p->body_len++] = (uint8_t)(byte ^ RS485_ESC_XOR);
      p->state = RS485_PSTATE_BODY;
      return 0;

    case RS485_PSTATE_BODY:
    default:
      if (byte == RS485_SOF) {
        // Unexpected SOF mid-frame — resync onto this new frame rather than
        // silently concatenating two frames together.
        p->body_len = 0;
        p->state = RS485_PSTATE_BODY;
        return 0;
      }
      if (byte == RS485_ESC) {
        p->state = RS485_PSTATE_ESCAPED;
        return 0;
      }
      if (byte == RS485_EOF) {
        p->state = RS485_PSTATE_WAIT_SOF;
        // Minimum body: ADDR, TYPE, LEN, CHECKSUM = 4 bytes.
        if (p->body_len < 4) return 0;
        uint8_t addr = p->body[0];
        uint8_t type = p->body[1];
        uint8_t len  = p->body[2];
        if ((size_t)(3 + len + 1) != p->body_len) return 0;  // length mismatch
        uint8_t checksum = (uint8_t)(addr ^ type ^ len);
        for (uint8_t i = 0; i < len; i++) checksum ^= p->body[3 + i];
        if (checksum != p->body[3 + len]) return 0;  // corrupt frame, drop it

        *addr_out = addr;
        *type_out = type;
        *payload_len_out = len;
        memcpy(payload_out, &p->body[3], len);
        return 1;
      }
      if (p->body_len >= sizeof(p->body)) { p->state = RS485_PSTATE_WAIT_SOF; return 0; }
      p->body[p->body_len++] = byte;
      return 0;
  }
}
