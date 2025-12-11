# Privacy Policy

**Last Updated**: December 2025

## Overview

RAG Assistant is designed with privacy in mind. This document outlines what data we collect, how we use it, and your rights.

## Data We Collect

### Personal Information
- **Email Address**: Used for authentication and account identification
- **Account Credentials**: Hashed passwords (bcrypt) - we never store plaintext passwords
- **Usage Data**: Query history, document uploads, and API usage statistics

### Technical Data
- **IP Addresses**: Stored in logs for security and rate limiting (retention depends on your log rotation policy)
- **Redis Operational Data**: Rate-limit buckets (`ratelimit:<key>`) and revoked JWT IDs (`revoked:{jti}`) with automatic expiration (no long-term session store)
- **Uploaded Documents**: Supported text/PDF/CSV/Markdown and (optionally) Office formats when enabled by the operator

## How We Use Your Data

- **Authentication**: Email and passwords for secure account access
- **Service Delivery**: Process queries, index documents, generate responses
- **Analytics**: Aggregate usage statistics (non-identifiable)
- **Security**: Fraud detection, abuse prevention, rate limiting
- **Compliance**: Legal obligations and security incident response

## Data Storage and Retention

| Data Type | Retention Period | Storage Location |
|-----------|------------------|------------------|
| Email & Credentials | Until account deletion | Database (encrypted at rest*) |
| Query History | Operator-controlled (no automatic TTL) | Database |
| Uploaded Documents | Until manual deletion | Gemini File Search Store |
| Application Logs  | Operator-configured (no built-in TTL) | Server filesystem |
| Redis Operational Data | Rate limit buckets <= 2 minutes, revoked tokens <= 15 minutes | Redis (in-memory) |

\* *Encryption at rest is operator-configurable and depends on your deployment setup*

Log retention is controlled by the deployment environment (e.g. log rotation,
cloud logging). The application does not enforce a fixed retention period.
If you need a hard retention cap (e.g., 90 days), configure database cleanup
jobs (e.g., a cron that deletes `chat_history` and `query_logs` older than 90 days). A helper script `python -m scripts.cleanup_tmp` is available to purge stale upload temp files from `TMP_DIR`.

> Redis is only used for short-lived operational data. Rate-limit counters expire automatically within ~120 seconds, and revoked JWT entries are removed as soon as the token lifetime (default 15 minutes) elapses.

## Third-Party Services

### Gemini API (Google)
- We send your queries and uploaded documents to Gemini API for processing
- Subject to [Google's Privacy Policy](https://policies.google.com/privacy)
- Documents are stored in Gemini File Search stores under your API key

### Public Branding Settings
- `/api/settings` is publicly readable to deliver theme/branding; do not store sensitive values there.

### No Other Tracking
- We do **NOT** use analytics trackers (Google Analytics, etc.)
- We do **NOT** sell or share your data with third parties
- We do **NOT** use your data for advertising

## Your Rights

### Data Access
Contact us to request a copy of your personal data.

### Data Deletion
- **Account Deletion**: Contact support to delete your account and associated data
- **Document Deletion**: Delete documents via the UI or API
- **Future**: Self-service data export and deletion (roadmap)

### Data Portability
You can export your query history and document metadata (feature in development).

## Security Measures

- **JWT Secrets**: 256-bit cryptographically random keys
- **Password Hashing**: bcrypt with salt
- **Rate Limiting**: Prevent abuse and brute-force attacks
- **HTTPS**: All data in transit is encrypted (operator must configure SSL)
- **File Upload Validation**: Magic number checks to prevent malicious files

## Encryption at Rest

RAG Assistant **does not** enforce encryption at rest by default. Operators can enable it:
- **PostgreSQL**: Enable TDE (Transparent Data Encryption) at the database level
- **SQLite**: Use SQLCipher or filesystem-level encryption
- **Redis**: Use encrypted volumes or RedisCrypt

### Session Tokens

RAG Assistant uses short-lived JWT access tokens for authentication.

- Tokens are stored in browser **sessionStorage** by the default frontend.
- Thread titles are stored in **localStorage** for convenience.
- Chat threads and citations may be cached locally in **IndexedDB** to speed up UI loading; this cache is not automatically cleared by the app.
- Tokens are sent to the backend in the `Authorization: Bearer <token>` header.
- HTTP-only cookies are not used by default; TLS provides transport security.
- Operators may choose to deploy an alternate frontend that stores tokens
  differently (e.g., in cookies), but that is outside the default distribution.

Client-side caches (sessionStorage, localStorage, IndexedDB) follow the browser's lifetime semantics.
Users can clear them via their browser settings; operators can customize the frontend to clear local data on logout if required.

### Uploaded Files and Metadata
- Filenames and content types may be logged for troubleshooting (you can adjust logging as needed).
- When `GCS_ARCHIVE_BUCKET` is configured, a GCS URI is stored in `documents.gcs_uri`.

## Children's Privacy

RAG Assistant is not intended for users under 13 years of age. We do not knowingly collect data from children.

## Changes to This Policy

We will notify users of material changes via:
1. Email notification (if we have your email)
2. Notice in the application
3. Update to this document with new "Last Updated" date

## Contact Us

For privacy-related questions or data requests:
- **Email**: info@sapphirebridge.de
- **Security Issues**: See SECURITY.md for vulnerability reporting

---

**Note for Self-Hosted Operators**: If you deploy RAG Assistant yourself, you are the data controller and responsible for compliance with applicable privacy laws (GDPR, CCPA, etc.). This document serves as a template; customize it for your deployment.
