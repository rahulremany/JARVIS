# SECURITY.md

## 1. Threat Model & Defenses
**Actors:** external attacker, malware, malicious local user, stolen device, compromised OAuth token, poisoned content, voice spoofing, supply chain tampering.
**Defenses:**
- Speaker verification & anti-replay challenge
- Policy gate for all tool calls
- Signed, reproducible builds
- Localhost default, strict connector allowlist
- Hardware-backed key storage

## 2. Identity & Keys
- Per-device keypair
- User master key (hardware-backed, optional Shamir recovery)
- Secrets in OS keychain
- mTLS between devices, cert pinning
- Instant revocation & key rotation

## 3. Data Storage
- Pre-wake audio in RAM only (≤10s)
- Post-wake transcript stored only if user opts in
- Encryption domains: memories, embeddings, settings/tokens, audit logs
- Keys separate per domain, hardware-backed

## 4. Network Isolation
- Default: localhost-only
- Outbound network disabled unless user enables tools
- LAN mode: VPN + mTLS required
- Connector domain allowlist, TLS pinning

## 5. Roles & Permissions
- **Full Access (Owner):** everything; biometric for finance/locks/garage/vehicle unlock; preview for comms/calendar writes; TTL=permanent
- **Trusted Access:** daily tasks; no finance/locks/cameras/account link; TTL=90d
- **Restricted Access:** media/scenes/timers only; TTL=24h guest / permanent child
- Policy gate enforces TTL, rate limits, geofence, confirmations

## 6. Prompt Injection & Tool Safety
- LLM requests pass through schema validator
- Untrusted content sanitized (strip HTML/JS)
- Secret egress guard blocks outbound sensitive data unless confirmed

## 7. Wake & Anti-Spoof
- VAD → wake word → speaker verification (ECAPA-TDNN)
- Anti-replay challenge for risky actions
- Biometric fallback on low confidence

## 8. Supply Chain Security
- Signed, reproducible builds
- Model hash checks
- No unsigned updates

## 9. Home & Vehicle Rules
- Prefer local protocols (Matter/HomeKit)
- Vehicle: status/nav/climate ok; unlock/garage require bio+proximity; no driving controls

## 10. Safety UX
- Privacy Promise on onboarding
- Role selection + per-connector consent toggles
- Preview bubble for sends/writes; biometric only for high-risk
- Privacy dashboard with revoke/purge/export
- Live mic indicator; kill switch hotkey

## 11. Testing & Monitoring
- Red-team prompt injection, token leaks, replay attacks
- Fuzz testing of parsers
- Local anomaly detection for suspicious spikes in actions

## 12. Compliance
- Plain-English Privacy Promise
- Data handling summary
- Export/erase/revoke tools
- Third-party API compliance

---

# PRIVACY.md

## Principles
- Local-first: all inference & storage on-device unless user enables cloud
- Data minimization: store only what’s necessary, for as long as necessary
- User consent for every integration
- Full transparency: logs, receipts, and controls

## Data Handling
- **Pre-wake audio:** RAM only, auto-deleted
- **Post-wake transcript:** stored only on user request
- **Stored data:** redacted text, embeddings, connector metadata, audit log
- **Encryption:** separate keys per domain, hardware-backed, never leave device unless E2EE sync is enabled

## Roles & Access
- **Full Access:** full control; biometric for sensitive actions
- **Trusted Access:** no finance/locks/account link
- **Restricted Access:** basics only (media/scenes/timers)

## Network Policy
- Default offline after model download
- Network tools only run when user enables them
- LAN connections require VPN + mTLS

## User Controls
- Role assignment via voice or UI
- Per-connector permission toggles
- Privacy dashboard: revoke, purge, export
- Live mic indicator & kill switch
- “Record nothing” mode

## Retention & Deletion
- Memories off by default
- Audit log: 30 events or 30 days max
- One-click full wipe

## Third-Party Compliance
- OAuth sign-in only; minimal scopes
- No password storage
- Respect all API TOS (no auto-driving, finance read-only by default)

## Rights
- Export all data in human-readable format
- Erase all data instantly
- Revoke any permission instantly

