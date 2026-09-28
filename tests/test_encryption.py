import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text

from src.core.database import AsyncSessionLocal, init_db
from src.integrations.brokers.enums import BrokerName
from src.modules.broker import BrokerModule
from src.utils.encryption import EncryptionNotConfiguredError, InvalidToken, TokenCipher


def test_round_trip_and_tamper_detection():
    cipher = TokenCipher()
    ciphertext = cipher.encrypt(SecretStr("kite-token"))
    assert "kite-token" not in ciphertext
    assert cipher.decrypt(ciphertext).get_secret_value() == "kite-token"
    with pytest.raises(InvalidToken):  # authenticated: a flipped byte is detected, not decrypted to garbage
        cipher.decrypt(ciphertext[:-2] + ("A" if ciphertext[-2] != "A" else "B") + ciphertext[-1])


def test_key_rotation_new_key_first_old_still_decrypts():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    stored_before_rotation = TokenCipher(SecretStr(old)).encrypt(SecretStr("t"))
    rotated = TokenCipher(SecretStr(f"{new},{old}"))
    assert rotated.decrypt(stored_before_rotation).get_secret_value() == "t"
    with pytest.raises(InvalidToken):  # new ciphertexts use the new key only
        TokenCipher(SecretStr(old)).decrypt(rotated.encrypt(SecretStr("t")))


def test_missing_key_fails_loudly(monkeypatch):
    from src.utils import encryption
    monkeypatch.setattr(encryption.settings, "token_encryption_keys", None)
    with pytest.raises(EncryptionNotConfiguredError):
        TokenCipher()


async def test_token_is_encrypted_at_rest():
    await init_db()
    async with AsyncSessionLocal() as session:
        await BrokerModule(session).connect("rest-user", BrokerName.ZERODHA, SecretStr("plain-token"), None, None)
        stored = (await session.execute(text(
            "SELECT encrypted_access_token FROM broker_connections WHERE user_id = 'rest-user'"))).scalar_one()
        assert "plain-token" not in stored
        creds = await BrokerModule(session).credentials("rest-user", BrokerName.ZERODHA)
        assert creds.access_token.get_secret_value() == "plain-token"
