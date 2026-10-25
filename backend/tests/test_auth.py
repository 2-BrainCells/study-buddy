import secrets

from app.main import hash_token, token_matches


def test_hash_is_not_the_token():
    token = secrets.token_urlsafe(32)

    hashed = hash_token(token)

    assert hashed != token
    assert len(hashed) == 64
    assert hash_token(token) == hashed


def test_right_token_matches():
    token = secrets.token_urlsafe(32)
    stored_hash = hash_token(token)

    assert token_matches(token, stored_hash) is True


def test_wrong_or_missing_token_does_not_match():
    token = secrets.token_urlsafe(32)
    stored_hash = hash_token(token)

    assert token_matches(secrets.token_urlsafe(32), stored_hash) is False
    assert token_matches("", stored_hash) is False
    assert token_matches(None, stored_hash) is False
