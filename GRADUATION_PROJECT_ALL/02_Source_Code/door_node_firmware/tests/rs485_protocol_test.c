// Standalone gcc test harness for rs485_protocol.h — deliberately built
// OUTSIDE the PlatformIO/Arduino/ESP32 toolchain (which could not be run in
// this sandbox) so the framing/checksum/byte-stuffing logic can still be
// compiled and executed for real, and cross-checked byte-for-byte against
// the independent Python re-implementation in gateway/protocol.py.
//
// Build:   gcc -std=c11 -I../include -o rs485_protocol_test rs485_protocol_test.c
// Usage:
//   rs485_protocol_test encode <addr> <type> <payload-string>
//       -> prints the on-wire frame as lowercase hex, no separators
//   rs485_protocol_test decode <hex-frame>
//       -> feeds those bytes through the streaming parser one at a time and
//          prints "ADDR=<n> TYPE=<n> PAYLOAD=<string>" for each frame found,
//          or "NONE" if the bytes never produced a complete valid frame
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/rs485_protocol.h"

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: %s encode|decode ...\n", argv[0]);
    return 2;
  }

  if (strcmp(argv[1], "encode") == 0) {
    if (argc != 5) { fprintf(stderr, "usage: %s encode <addr> <type> <payload>\n", argv[0]); return 2; }
    uint8_t addr = (uint8_t)atoi(argv[2]);
    uint8_t type = (uint8_t)atoi(argv[3]);
    const char *payload = argv[4];
    uint8_t out[RS485_MAX_FRAME_RAW];
    size_t n = rs485_encode_frame(addr, type, (const uint8_t *)payload, (uint8_t)strlen(payload), out, sizeof(out));
    if (n == 0) { fprintf(stderr, "encode failed\n"); return 1; }
    for (size_t i = 0; i < n; i++) printf("%02x", out[i]);
    printf("\n");
    return 0;
  }

  if (strcmp(argv[1], "decode") == 0) {
    if (argc != 3) { fprintf(stderr, "usage: %s decode <hex>\n", argv[0]); return 2; }
    const char *hex = argv[2];
    size_t hexlen = strlen(hex);
    if (hexlen % 2 != 0) { fprintf(stderr, "odd hex length\n"); return 2; }

    Rs485Parser parser;
    rs485_parser_init(&parser);
    uint8_t payload[RS485_MAX_PAYLOAD + 1];
    int found = 0;

    for (size_t i = 0; i < hexlen; i += 2) {
      int hi = hexval(hex[i]), lo = hexval(hex[i + 1]);
      if (hi < 0 || lo < 0) { fprintf(stderr, "bad hex\n"); return 2; }
      uint8_t byte = (uint8_t)((hi << 4) | lo);

      uint8_t addr, type, plen;
      if (rs485_parser_feed(&parser, byte, &addr, &type, payload, &plen)) {
        payload[plen] = '\0';
        printf("ADDR=%u TYPE=%u PAYLOAD=%s\n", addr, type, (const char *)payload);
        found = 1;
      }
    }
    if (!found) printf("NONE\n");
    return 0;
  }

  fprintf(stderr, "unknown mode '%s'\n", argv[1]);
  return 2;
}
