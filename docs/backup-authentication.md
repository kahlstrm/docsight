# Backup authentication

When an administrator password is configured, backup downloads, scheduled backup
requests, backup listing and deletion, restore and restore validation, and
server-side directory browsing require an authenticated browser session.
API bearer tokens do not grant access to these operations. Integrations that used
a bearer token for backups must use the administrator session workflow instead.

Initial setup without an administrator password remains available. Configure an
administrator password and restrict management access before exposing the service.
