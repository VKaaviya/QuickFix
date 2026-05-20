import hmac
import hashlib
import json


def payload_bytes(payload):
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode()
    return json.dumps(payload, separators=(",", ":")).encode()


def generate_signature(payload, secret):
    signature = hmac.new(
        secret.encode(),
        payload_bytes(payload),
        hashlib.sha256
    ).hexdigest()

    return signature


def generate(payload,secret):
    return generate_signature(payload, secret)

