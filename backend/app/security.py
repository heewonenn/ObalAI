import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
ALGORITHM = 'HS256'
ACCESS_TOKEN_MINUTES = 60


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hash.verify(password, stored_hash)


def create_access_token(user_id: UUID) -> str:
    secret = os.getenv('JWT_SECRET_KEY')
    if not secret:
        raise RuntimeError('JWT_SECRET_KEY must be set in the environment.')
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {'sub': str(user_id), 'exp': expires_at}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> UUID:
    secret = os.getenv('JWT_SECRET_KEY')
    if not secret:
        raise RuntimeError('JWT_SECRET_KEY must be set in the environment.')
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    return UUID(payload['sub'])
