
# --------------------------------------------------
# STE-07: Local-development pathway access guard
# --------------------------------------------------

import os
import secrets

from fastapi import HTTPException, Request


def require_pathway_dev_access(request: Request) -> None:
    """
    Restrict saved-pathway operations to controlled
    local development.

    This is NOT student authentication. A shared
    development key cannot establish pathway ownership.

    Production multi-user deployment requires
    authenticated student accounts and per-pathway
    ownership checks.
    """

    configured_key = os.environ.get(
        "FUTUREPATH_DEV_API_KEY",
        ""
    )

    # Fail closed: private pathway operations are
    # disabled unless a sufficiently long development
    # key has been explicitly configured.
    if len(configured_key) < 32:
        raise HTTPException(
            status_code=503,
            detail=(
                "Saved pathway API operations are disabled. "
                "Local development access has not been configured."
            )
        )

    # Permit access only from a loopback client.
    # This is an additional development restriction,
    # not a production-grade authentication mechanism.
    client_host = (
        request.client.host
        if request.client is not None
        else None
    )

    if client_host not in ("127.0.0.1", "::1"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Saved pathway operations are restricted "
                "to local development."
            )
        )

    # A development key must be supplied explicitly.
    supplied_key = request.headers.get(
        "X-FuturePath-Dev-Key",
        ""
    )

    # Constant-time comparison avoids ordinary
    # string-comparison timing differences.
    if not secrets.compare_digest(
        supplied_key,
        configured_key
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid pathway development access key.",
            headers={
                "WWW-Authenticate": "Bearer"
            }
        )

    # Access check passed.
    return None
