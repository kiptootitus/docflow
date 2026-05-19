import hashlib
import json
from django.utils import timezone
from documents.models import LedgerEvent


def create_ledger_event(user, event_type, snapshot, invoice_id=None):
    """
    Creates an append-only transaction ledger log event.
    Generates a cryptographic hash chaining to maintain systemic audit integrity.
    """
    # Fetch the last event to chain the hashes together (like a light blockchain ledger)
    last_event = LedgerEvent.objects.order_by("-created_at").first()
    last_hash = last_event.hash if last_event else "0" * 64

    # Build data layout string for uniform hashing
    serialized_snapshot = json.dumps(snapshot, sort_keys=True)
    hash_payload = f"{last_hash}:{user.id if user else 'system'}:{event_type}:{serialized_snapshot}"

    computed_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

    # Save cleanly to DB
    return LedgerEvent.objects.create(
        user=user,
        invoice_id=invoice_id,
        event_type=event_type,
        snapshot=snapshot,
        hash=computed_hash
    )