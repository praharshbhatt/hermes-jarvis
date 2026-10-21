# Security policy

Please report vulnerabilities privately through GitHub's "Report a vulnerability" (Security tab of this repository)
instead of a public issue. Include what you found, how to reproduce it, and what it could allow. You will get a reply within
a few days.

Things we consider in scope: the admin UI's authentication and request checks, handling of keys and the device key,
the device adoption flow, the speech clip server, the firmware configuration, and the container image.

Context for reports is in [docs/security-privacy.md](docs/security-privacy.md): the admin UI is off by default and local by
default, and the adoption step is plaintext on the local network by design.
