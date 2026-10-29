# Security policy

## Reporting a vulnerability

Do not open a public issue. Report privately to the maintainers using the channel your organization
publishes for security reports. Include the version, the adapter involved, reproduction steps, and the
expected and actual behavior. We acknowledge reports within two business days.

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |
| 0.x (Chusky Bridge) | No |

## Security model

See [docs/security-model.md](docs/security-model.md) for threat model, controls, and the invariants
that must hold. The invariants are also listed in
[skills/chusky-bridge/references/security-invariants.md](skills/chusky-bridge/references/security-invariants.md).

## Known limitations

- Rate limiting is per process unless `CHUSKY_RATE_LIMIT_BACKEND=redis`.
- Adapter behavior against live products depends on the deployed client libraries and vendor versions. Test in a lab before production.
- The default terminal (`tn3270`) and desktop (`rpa`) drivers are best-effort and must be validated per emulator and per application version.
