# Purpose: Category suffix carried on the end of a lead's contact name — "ZyDrv" for driver
#          leads, "ZyBuz" for business leads — so a phone address book can be searched by tag.
# Used by: crm/models.py (Lead.save), crm/management/commands/tag_lead_contacts.py,
#          workforce/crm_views.py (Google Contacts CSV export), crm/services.py (outbound names).
# Notes: apply_tag is idempotent and length-safe; strip_tags removes ANY tag, so a lead that
#        switches category never ends up wearing both.

import re

CONTACT_TAGS = {
    'driver': 'ZyDrv',
    'business': 'ZyBuz',
}
ALL_TAGS = tuple(CONTACT_TAGS.values())
NAME_MAX_LEN = 100

_TAG_RE = re.compile(r'(?:\s+(?:%s))+\s*$' % '|'.join(ALL_TAGS), re.IGNORECASE)


def tag_for(category):
    """The suffix a lead of this category should carry ('' for anything unknown)."""
    return CONTACT_TAGS.get(category, '')


def strip_tags(name):
    """The human name with any trailing category tag(s) removed. Use this everywhere a
    name is spoken to the customer — nobody should be greeted as 'Ahmed ZyDrv'."""
    return _TAG_RE.sub('', (name or '').strip()).strip()


def apply_tag(name, category, max_len=NAME_MAX_LEN):
    """Name + the category tag, exactly once. An empty name stays empty — a contact
    called just 'ZyDrv' is noise, not a record."""
    base = strip_tags(name)
    tag = tag_for(category)
    if not base or not tag:
        return base
    room = max_len - len(tag) - 1
    if room < 1:
        return base[:max_len]
    return f'{base[:room].rstrip()} {tag}'


def has_tag(name, category):
    return bool(name) and name.strip().lower().endswith(tag_for(category).lower())
