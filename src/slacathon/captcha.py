import base64
import json
import logging
from fastapi import HTTPException
from altcha.v1 import create_challenge as _create, verify_solution, ChallengeOptions
from .settings import settings

logger = logging.getLogger(__name__)


def create_challenge() -> dict:
    challenge = _create(ChallengeOptions(hmac_key=settings.altcha_hmac_key))
    return {
        "algorithm": challenge.algorithm,
        "challenge": challenge.challenge,
        "salt": challenge.salt,
        "signature": challenge.signature,
    }


def verify_captcha(payload: str):
    if not payload:
        raise HTTPException(status_code=400, detail="CAPTCHA solution missing")
    try:
        decoded = base64.b64decode(payload).decode()
        solution = json.loads(decoded)
    except Exception:
        raise HTTPException(status_code=400, detail="CAPTCHA payload malformed")

    ok, _ = verify_solution(solution, settings.altcha_hmac_key)
    if not ok:
        logger.warning("Altcha verification failed")
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed")
