import logging
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)
signer = TimestampSigner(salt="documents.portal.security.salt")

def generate_signed_token(invoice_id, expires_in=86400):
    """Generates a secure, time-sensitive cryptographic HMAC token for an invoice."""
    # Note: TimestampSigner checks expiry automatically on unsign,
    # we just pass str(invoice_id) into the signing pipeline
    return signer.sign(str(invoice_id))


def verify_signed_token(token, invoice_id, max_age=86400):
    """Verifies if the token is authentic, untampered, and within its max age."""
    try:
        unsigned_id = signer.unsign(token, max_age=max_age)
        return unsigned_id == str(invoice_id)
    except SignatureExpired:
        logger.warning(f"Expired secure portal link token used for invoice {invoice_id}")
        return False
    except BadSignature:
        logger.error(f"Tampered or invalid token verification attempt for invoice {invoice_id}")
        return False