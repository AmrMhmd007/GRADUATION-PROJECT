#pragma once
// ============================================================================
// MIFARE DESFire EV1 native AES authentication (command 0xAA)
//
// Phase 5 security work: replaces the Phase 2 prototype's UID-only card
// read with an actual cryptographic proof that the presented card holds
// the shared AES-128 key, not just a UID that can be copied onto a
// cloned/emulated tag. This is the exact gap flagged since the original
// proposal review ("cloning a card's UID would fool this build").
//
// SCOPE / VERIFICATION NOTE — read before trusting this in the field:
//  - This implements the publicly documented DESFire EV1 native AES
//    mutual-authentication handshake (0xAA -> EncRndB -> EncRndA||RndB' ->
//    EncRndA') using mbedTLS's AES-128-CBC, which ships with the ESP32
//    Arduino core, so no extra library dependency was needed.
//  - It has NOT been run against a real DESFire card in this environment
//    — there was no hardware available to test against, and the ESP32
//    toolchain itself could not be compiled here either (see the Phase 2
//    README). Treat this the same way: review the logic, then validate
//    against a real card on the bench before relying on it. Byte-order or
//    framing mistakes in a hand-implemented crypto handshake are exactly
//    the kind of bug that looks fine on paper and fails silently on real
//    hardware, so budget real bench time for this specifically.
//  - Uses ONE shared AES key across all cards at a site (DESFIRE_AES_KEY
//    in config.h), not per-card diversified keys. That's a reasonable
//    scope boundary for a graduation project, but a real deployment
//    should diversify keys per card (e.g. AES-CMAC-based diversification
//    from a UID + master key) so that extracting one card's key doesn't
//    compromise every card at the site.
//  - The session key derivable from RndA/RndB at the end of a successful
//    handshake is not used here — we only need proof of key possession,
//    not to read/write DESFire file data afterward.
// ============================================================================

#include <Adafruit_PN532.h>
#include <stdint.h>

// Returns true if the currently-selected card (i.e. right after a
// successful nfc.readPassiveTargetID() call) proves possession of `key`
// under key number `keyNo`. `key` must point to 16 bytes (AES-128).
bool desfireAuthenticateAES(Adafruit_PN532 &nfc, const uint8_t *key, uint8_t keyNo);
