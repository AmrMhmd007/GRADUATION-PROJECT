#include "desfire_auth.h"
#include <mbedtls/aes.h>
#include <esp_system.h>
#include <string.h>

static void rotateLeft16(const uint8_t *in, uint8_t *out) {
  // Rotate a 16-byte block left by one byte: [b0 b1 ... b15] -> [b1 ... b15 b0]
  memcpy(out, in + 1, 15);
  out[15] = in[0];
}

static void fillRandom16(uint8_t *out) {
  for (int i = 0; i < 4; i++) {
    uint32_t r = esp_random();
    memcpy(out + i * 4, &r, 4);
  }
}

// AES-128-CBC over `len` bytes (must be a multiple of 16). `iv` is
// consumed/mutated by mbedtls as it chains blocks, matching the DESFire
// spec's rule that each authentication frame's IV is the previous frame's
// ciphertext.
static bool aesCbc(bool encrypt, const uint8_t *key, uint8_t *iv,
                    const uint8_t *input, uint8_t *output, size_t len) {
  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  int rc;
  if (encrypt) {
    rc = mbedtls_aes_setkey_enc(&ctx, key, 128);
  } else {
    rc = mbedtls_aes_setkey_dec(&ctx, key, 128);
  }
  if (rc != 0) {
    mbedtls_aes_free(&ctx);
    return false;
  }
  rc = mbedtls_aes_crypt_cbc(&ctx, encrypt ? MBEDTLS_AES_ENCRYPT : MBEDTLS_AES_DECRYPT,
                              len, iv, input, output);
  mbedtls_aes_free(&ctx);
  return rc == 0;
}

bool desfireAuthenticateAES(Adafruit_PN532 &nfc, const uint8_t *key, uint8_t keyNo) {
  uint8_t send[2] = { 0xAA, keyNo };
  uint8_t resp[32];
  uint8_t respLen = sizeof(resp);

  // --- Frame 1: request authentication, receive EncRndB ---
  if (!nfc.inDataExchange(send, sizeof(send), resp, &respLen)) return false;
  if (respLen != 17 || resp[0] != 0xAF) return false;  // 0xAF = "more frames follow"

  uint8_t encRndB[16];
  memcpy(encRndB, resp + 1, 16);

  uint8_t ivA[16] = {0};  // first frame's IV is all-zero per the DESFire spec
  uint8_t rndB[16];
  if (!aesCbc(false, key, ivA, encRndB, rndB, 16)) return false;

  uint8_t rndBRot[16];
  rotateLeft16(rndB, rndBRot);

  uint8_t rndA[16];
  fillRandom16(rndA);

  uint8_t plain2[32];
  memcpy(plain2, rndA, 16);
  memcpy(plain2 + 16, rndBRot, 16);

  // Chaining IV for this frame is the ciphertext just received (EncRndB),
  // per the DESFire native-AES handshake.
  uint8_t ivB[16];
  memcpy(ivB, encRndB, 16);
  uint8_t cipher2[32];
  if (!aesCbc(true, key, ivB, plain2, cipher2, 32)) return false;

  // --- Frame 2: send EncRndA||RndB', receive EncRndA' ---
  uint8_t send2[33];
  send2[0] = 0xAF;
  memcpy(send2 + 1, cipher2, 32);
  respLen = sizeof(resp);
  if (!nfc.inDataExchange(send2, sizeof(send2), resp, &respLen)) return false;
  if (respLen != 17 || resp[0] != 0x00) return false;  // 0x00 = success, no more frames

  uint8_t encRndARot[16];
  memcpy(encRndARot, resp + 1, 16);

  // IV for this decryption is the last ciphertext block we sent (second
  // 16 bytes of cipher2), continuing the CBC chain.
  uint8_t ivC[16];
  memcpy(ivC, cipher2 + 16, 16);
  uint8_t rndARotReceived[16];
  if (!aesCbc(false, key, ivC, encRndARot, rndARotReceived, 16)) return false;

  uint8_t rndARotExpected[16];
  rotateLeft16(rndA, rndARotExpected);

  return memcmp(rndARotReceived, rndARotExpected, 16) == 0;
  // A successful return here proves the card holds `key` — it does not by
  // itself set up a secure-messaging session, since none of this
  // firmware's subsequent operations (relock timers, door sensor polling)
  // need encrypted file access to the card.
}
