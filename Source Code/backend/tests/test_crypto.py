from app import crypto


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt_uid("DEADBEEF")
    assert token != "DEADBEEF"
    assert crypto.decrypt_uid(token) == "DEADBEEF"


def test_ciphertext_not_deterministic():
    # Fernet includes a random IV/timestamp, so encrypting the same UID
    # twice must not produce identical ciphertext (defends against an
    # attacker spotting repeated UIDs just by comparing encrypted blobs).
    a = crypto.encrypt_uid("DEADBEEF")
    b = crypto.encrypt_uid("DEADBEEF")
    assert a != b
    assert crypto.decrypt_uid(a) == crypto.decrypt_uid(b) == "DEADBEEF"


def test_index_is_deterministic():
    # Unlike the ciphertext, the blind index MUST be stable so equality
    # lookups work — same UID always yields the same index.
    assert crypto.uid_index("DEADBEEF") == crypto.uid_index("DEADBEEF")


def test_index_differs_for_different_uids():
    assert crypto.uid_index("DEADBEEF") != crypto.uid_index("12345678")


def test_decrypt_rejects_tampered_ciphertext():
    token = crypto.encrypt_uid("DEADBEEF")
    tampered = token[:-4] + ("A" * 4)
    assert crypto.decrypt_uid(tampered) is None


def test_decrypt_rejects_garbage():
    assert crypto.decrypt_uid("not-a-real-token") is None
