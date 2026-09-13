# Purpose: Single source of truth for whether a task may close without proof of delivery.
# Used by: ezzy_api/views.py (driver_complete_task), fleet/views.py (partial delivery), the driver PWA card attrs.
# Notes: Proof lands in two stores — DeliveryProof (fleet upload endpoint) and TaskDocument
#        (the /complete/ multipart post) — so every check reads both or it passes wrongly.

from django.db.models import Q

# The outcomes a client can demand evidence for. 'partial_delivery' rides on the
# delivered rule: goods changed hands, so the same contract applies.
DELIVERED_OUTCOMES = ('delivered', 'partial_delivery')
FAILED_OUTCOMES = ('failed',)

PHOTO = 'photo'
SIGNATURE = 'signature'
BOTH = 'both'

_KIND_PARTS = {
    PHOTO: (PHOTO,),
    SIGNATURE: (SIGNATURE,),
    BOTH: (PHOTO, SIGNATURE),
}

_LABEL = {PHOTO: 'a delivery photo', SIGNATURE: "the customer's signature"}


def business_for(task):
    """The client this task bills to. DeliveryTask.business is nullable on old rows."""
    return getattr(task, 'business', None) or getattr(getattr(task, 'order', None), 'business', None)


def requirement_for(task, outcome):
    """What this client demands before `outcome` may be written: 'photo', 'signature',
    'both', or None when nothing is required.

    A failed attempt always resolves to a photo. There is no customer standing there
    to sign for a parcel they did not take, so a signature requirement would be
    impossible to satisfy and drivers would be stuck on the doorstep.
    """
    business = business_for(task)
    if not business:
        return None
    if outcome in DELIVERED_OUTCOMES and business.pod_required_delivered:
        return business.pod_kind or PHOTO
    if outcome in FAILED_OUTCOMES and business.pod_required_failed:
        return PHOTO
    return None


def existing_kinds(task):
    """Proof kinds already filed against this task, across both stores.

    Keeps a retry after a dropped connection from being blocked by the upload its
    own first attempt already made.
    """
    from ezzy_api import models as ezzy_api_models

    kinds = set()
    for proof_type in task.delivery_proofs.values_list('proof_type', flat=True):
        if proof_type == SIGNATURE:
            kinds.add(SIGNATURE)
        elif proof_type == PHOTO:
            kinds.add(PHOTO)
    doc_types = ezzy_api_models.TaskDocument.objects.filter(
        Q(task=task), document_type__in=('delivery_proof', 'photo', 'signature'),
    ).values_list('document_type', flat=True)
    for doc_type in doc_types:
        kinds.add(SIGNATURE if doc_type == SIGNATURE else PHOTO)
    return kinds


def missing(task, outcome, supplied=()):
    """Error message for the driver, or None when the task may close.

    `supplied` is the proof kinds arriving with this request — pass the keys of the
    uploaded files, not the files themselves.
    """
    kind = requirement_for(task, outcome)
    if not kind:
        return None

    have = set(supplied) | existing_kinds(task)
    lacking = [part for part in _KIND_PARTS[kind] if part not in have]
    if not lacking:
        return None

    business = business_for(task)
    name = getattr(business, 'business_name', None) or 'This client'
    needed = ' and '.join(_LABEL[part] for part in lacking)
    return f'{name} requires proof of delivery. Capture {needed} before submitting.'


def supplied_kinds(files):
    """Map an upload dict (request.FILES) onto proof kinds."""
    kinds = set()
    if 'delivery_proof' in files or PHOTO in files:
        kinds.add(PHOTO)
    if SIGNATURE in files:
        kinds.add(SIGNATURE)
    return kinds
