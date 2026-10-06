"""
Purpose: Per-staff browser logins for the WhatsApp inbox (/waha/wa-chats/) — the nginx htpasswd file behind that one location.
Used by: workforce.views.staff_roles_list / staff_waha_access (the "WAHA Inbox" column on Staff Roles)
Notes: Inbox only. The raw /waha/ API proxy injects the WAHA key, so it keeps the root-owned /etc/nginx/.htpasswd (admin only).
       Lines are `username:$apr1$…` (nginx verifies apr1 itself); writes are locked and atomic; passwords are never stored or logged.
"""
import fcntl
import os
import re
import secrets
import subprocess
import tempfile
from contextlib import contextmanager

from django.conf import settings

# No look-alikes (0/O, 1/l/I) — the password is read off a screen and typed on a phone.
_ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_USERNAME_RE = re.compile(r'[^\s:]{1,150}')


class InboxAccessError(Exception):
    """The password file could not be read or written."""


def path():
    return settings.WAHA_INBOX_HTPASSWD


def _entries():
    """[(username, hash)] in file order; a missing file is an empty list."""
    try:
        with open(path(), encoding='utf-8') as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    except OSError as e:
        raise InboxAccessError(f'Cannot read {path()}: {e}') from e
    out = []
    for line in lines:
        user, sep, hashed = line.strip().partition(':')
        if sep and user:
            out.append((user, hashed))
    return out


def usernames():
    return {user for user, _ in _entries()}


def has_access(username):
    return username in usernames()


@contextmanager
def _locked():
    folder = os.path.dirname(path())
    try:
        # 0711: nginx (www-data) may reach the file but not list the folder.
        os.makedirs(folder, mode=0o711, exist_ok=True)
        lock = open(path() + '.lock', 'a')
    except OSError as e:
        raise InboxAccessError(f'Cannot open {folder}: {e}') from e
    with lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _write(entries):
    folder = os.path.dirname(path())
    try:
        fd, tmp = tempfile.mkstemp(dir=folder, prefix='.htpasswd-')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(''.join(f'{user}:{hashed}\n' for user, hashed in entries))
        # nginx workers run as www-data; apr1 hashes of random passwords are safe to expose.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path())
    except OSError as e:
        raise InboxAccessError(f'Cannot write {path()}: {e}') from e


def _apr1(password):
    try:
        done = subprocess.run(['openssl', 'passwd', '-apr1', '-stdin'], input=password,
                              capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        raise InboxAccessError(f'Cannot hash the password: {e}') from e
    return done.stdout.strip()


def new_password():
    return '-'.join(''.join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3))


def set_password(username):
    """Give `username` inbox access with a fresh password (replacing any old one); returns it."""
    if not _USERNAME_RE.fullmatch(username or ''):
        raise InboxAccessError('That username cannot be used for a browser login.')
    password = new_password()
    hashed = _apr1(password)
    with _locked():
        entries = [(u, h) for u, h in _entries() if u != username]
        entries.append((username, hashed))
        _write(entries)
    return password


def revoke(username):
    """Remove `username` from the file; True when there was an entry."""
    with _locked():
        entries = _entries()
        kept = [(u, h) for u, h in entries if u != username]
        if len(kept) == len(entries):
            return False
        _write(kept)
    return True


def nginx_wired():
    """True when the nginx site config points at this file (else edits here change nothing yet)."""
    try:
        with open(settings.NGINX_SITE_CONF, encoding='utf-8') as f:
            return path() in f.read()
    except OSError:
        return False
