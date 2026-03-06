# Security Review: AI Data Operations Platform

**Review Date:** 2026-03-06
**Scope:** Full codebase review of `ai-data-ops-platform`
**Files Reviewed:** All files in `src/`, `trigger-jobs/`, `n8n/`, `emails/`, `supabase/migrations/`, `data_quality/`, `demo/`, plus `Dockerfile`, `docker-compose.yml`, `vercel.json`, `.env.example`, `requirements.txt`, `.gitignore`, `Makefile`

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 7     |
| MEDIUM   | 8     |
| LOW      | 5     |
| **Total** | **23** |

---

## 1. Hardcoded Secrets, API Keys, Passwords

### FINDING 1.1 -- Hardcoded Default Passwords in docker-compose.yml

- **Severity:** CRITICAL
- **File:** `docker-compose.yml`, lines 10, 31, 55, 86, 91, 133, 149
- **Description:** Default fallback passwords are embedded directly in the compose file. If the `.env` file is missing or incomplete, services start with weak, well-known passwords. These defaults are also visible in version control.
- **Code Evidence:**
  ```yaml
  # Line 10
  POSTGRES_PASSWORD: ${DB_PASSWORD:-dataops_dev_password}
  # Line 31
  command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-redis_dev_password}
  # Line 55
  POSTGRES_PASSWORD: ${TEMPORAL_DB_PASSWORD:-temporal_dev_password}
  # Line 133
  PGADMIN_DEFAULT_PASSWORD: ${PGADMIN_PASSWORD:-admin}
  # Line 149
  GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
  ```
- **Fix:** Remove all default fallback values from `docker-compose.yml`. Require explicit environment variables and fail fast if they are not set. For development, use a `.env` file that is gitignored (already in `.gitignore`). Example:
  ```yaml
  POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD must be set}
  ```

### FINDING 1.2 -- Default Passwords in .env.example

- **Severity:** HIGH
- **File:** `.env.example`, lines 54, 61, 114, 117, 120
- **Description:** The `.env.example` file contains actual default password values rather than placeholder tokens. Developers who copy this file to `.env.local` without modification will run with weak credentials.
- **Code Evidence:**
  ```bash
  # Line 54
  DB_PASSWORD=dataops_dev_password
  # Line 61
  REDIS_PASSWORD=redis_dev_password
  # Line 114
  PGADMIN_PASSWORD=admin
  # Line 117
  GRAFANA_PASSWORD=admin
  # Line 120
  SECRET_KEY=your-secret-key-change-in-production
  ```
- **Fix:** Replace all default passwords in `.env.example` with clearly non-functional placeholders like `CHANGE_ME_BEFORE_USE` or empty strings with a comment. For `SECRET_KEY`, provide a command to generate one:
  ```bash
  SECRET_KEY=  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```

### FINDING 1.3 -- Snowflake Connection String with Password Interpolation

- **Severity:** MEDIUM
- **File:** `data_quality/great_expectations.yml`, line 18
- **Description:** The Snowflake connection string embeds the password directly in the URL via environment variable interpolation. While the variable itself is not hardcoded, the URL format means the password appears in connection strings, potentially logged by SQLAlchemy or Great Expectations.
- **Code Evidence:**
  ```yaml
  url: "snowflake://${SNOWFLAKE_USER}:${SNOWFLAKE_PASSWORD}@${SNOWFLAKE_ACCOUNT}/AI_DATA_OPS_DB/PUBLIC?warehouse=${SNOWFLAKE_WAREHOUSE}"
  ```
- **Fix:** Use SQLAlchemy's `create_engine` with separate `connect_args` or a Snowflake connector that accepts credentials as separate parameters rather than embedding them in the URL. Set `echo: false` (already done) and configure logging to redact connection strings.

---

## 2. Auth Vulnerabilities, Missing Auth on Endpoints

### FINDING 2.1 -- n8n Webhook Has No Authentication

- **Severity:** CRITICAL
- **File:** `n8n/annotation_quality_pipeline.json`, lines 2-16
- **Description:** The webhook trigger at `https://n8n.example.com/webhook/quality-batch` has no authentication configured. Any party who knows (or guesses) this URL can trigger the entire quality scoring pipeline, including sending emails and modifying Supabase data.
- **Code Evidence:**
  ```json
  {
    "parameters": {},
    "id": "webhook_trigger",
    "name": "Webhook Trigger",
    "type": "n8n-nodes-base.webhook",
    "typeVersion": 1,
    "webhookId": "quality-batch-webhook",
    "webhookUrl": "https://n8n.example.com/webhook/quality-batch"
  }
  ```
- **Fix:** Add authentication to the webhook. n8n supports header-based auth, Basic auth, or HMAC signature verification. At minimum:
  ```json
  "parameters": {
    "authentication": "headerAuth",
    "headerAuth": {
      "name": "X-Webhook-Secret",
      "value": "={{ $env.WEBHOOK_SECRET }}"
    }
  }
  ```

### FINDING 2.2 -- Using SUPABASE_ANON_KEY for Server-Side Write Operations

- **Severity:** HIGH
- **File:** `n8n/annotation_quality_pipeline.json`, lines 93-101, 142-150; `n8n/active_learning_trigger.json`, lines 138-146, 168-176
- **Description:** Several n8n workflow nodes that perform server-side write operations (storing quality scores, creating/updating annotation tasks) use `SUPABASE_ANON_KEY` instead of `SUPABASE_SERVICE_KEY`. The anon key is subject to Row-Level Security (RLS) policies and is designed for client-side use. Using it server-side means these operations may silently fail if RLS policies do not permit the action, or conversely, if RLS is overly permissive to accommodate this pattern, it weakens client-side security.
- **Code Evidence:**
  ```json
  // annotation_quality_pipeline.json, line 101
  "value": "Bearer {{ $env.SUPABASE_ANON_KEY }}"

  // active_learning_trigger.json, line 146
  "value": "Bearer {{ $env.SUPABASE_ANON_KEY }}"
  ```
- **Fix:** All server-side operations in n8n workflows should use `SUPABASE_SERVICE_KEY`:
  ```json
  "value": "Bearer {{ $env.SUPABASE_SERVICE_KEY }}"
  ```

### FINDING 2.3 -- No Environment Variable Validation in Trigger.dev Jobs

- **Severity:** HIGH
- **File:** `trigger-jobs/quality_scoring.ts`, lines 399-401; `trigger-jobs/active_learning.ts`, lines 63-66, 159-162, 276-279, 325-328
- **Description:** Supabase clients are created using TypeScript non-null assertions (`!`) on environment variables. If these variables are not set, the code will pass `undefined` to `createClient`, which may produce cryptic runtime errors, connect to wrong endpoints, or silently fail instead of failing fast with a clear message.
- **Code Evidence:**
  ```typescript
  // quality_scoring.ts, lines 399-401
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );

  // active_learning.ts, lines 63-66
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );
  ```
- **Fix:** Validate environment variables at job initialization and fail fast:
  ```typescript
  const SUPABASE_URL = process.env.SUPABASE_URL;
  const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;
  if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
    throw new Error("Missing required environment variables: SUPABASE_URL, SUPABASE_SERVICE_KEY");
  }
  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
  ```

---

## 3. Input Validation Issues (SQL Injection, XSS, Command Injection, Unsafe Deserialization)

### FINDING 3.1 -- Server-Side Request Forgery (SSRF) via User-Controlled URL

- **Severity:** CRITICAL
- **File:** `n8n/annotation_quality_pipeline.json`, line 19
- **Description:** The quality scoring HTTP request constructs its URL from user-supplied webhook body data (`$json.body.api_endpoint`). An attacker who can trigger the webhook (see Finding 2.1) can set `api_endpoint` to any URL, causing the n8n server to make requests to internal services, cloud metadata endpoints (e.g., `http://169.254.169.254/`), or other sensitive infrastructure.
- **Code Evidence:**
  ```json
  "url": "{{ $json.body.api_endpoint }}/quality/score-batch"
  ```
- **Fix:** Replace the user-controlled URL with a fixed, environment-variable-based endpoint:
  ```json
  "url": "{{ $env.QUALITY_API_URL }}/quality/score-batch"
  ```
  If the endpoint must be dynamic, validate it against an allowlist of permitted domains.

### FINDING 3.2 -- Cross-Site Scripting (XSS) in Email HTML Template

- **Severity:** HIGH
- **File:** `trigger-jobs/active_learning.ts`, lines 393-401
- **Description:** The inline email HTML template directly interpolates user-controlled data (`annotator.name`, `count`) without HTML escaping. If an annotator's name contains HTML/JavaScript (e.g., `<script>alert(1)</script>`), it will be rendered in the email client. While most modern email clients block script execution, HTML injection can still be used for phishing (e.g., injecting fake login forms).
- **Code Evidence:**
  ```typescript
  html: `
    <h1>New Active Learning Tasks</h1>
    <p>Hi ${annotator.name},</p>
    <p>We've selected ${count} uncertain samples from our model that need your expertise.</p>
    ...
    <p><a href="${process.env.APP_URL}/tasks">View Tasks</a></p>
  ```
- **Fix:** Use the React Email templates that already exist in the `emails/` directory (e.g., `AssignmentNotification`), which use React components for safe rendering. If inline HTML is necessary, escape all user input:
  ```typescript
  function escapeHtml(str: string): string {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
              .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  ```

### FINDING 3.3 -- Unvalidated Webhook Body Data Passed to Downstream APIs

- **Severity:** HIGH
- **File:** `n8n/annotation_quality_pipeline.json`, line 33
- **Description:** The webhook body data (`batch_id`, `annotations`, `schema_type`) is forwarded directly to the quality scoring API without any validation or sanitization in the n8n workflow. While the downstream API may validate its own input, the workflow layer should provide defense-in-depth.
- **Code Evidence:**
  ```json
  "bodyParametersJson": "{\n  \"batch_id\": \"{{ $json.body.batch_id }}\",\n  \"annotations\": {{ $json.body.annotations | stringify }},\n  \"schema_type\": \"{{ $json.body.schema_type }}\"\n}"
  ```
- **Fix:** Add a validation node (Code node or IF node) after the webhook trigger that validates:
  - `batch_id` matches UUID format
  - `schema_type` is from an allowed set
  - `annotations` is an array with expected structure
  - `api_endpoint` is removed or validated against allowlist

### FINDING 3.4 -- SQL Function Parameters Not Type-Checked at Application Level

- **Severity:** LOW
- **File:** `supabase/migrations/001_initial_schema.sql`, lines 467-486
- **Description:** The `update_task_status` function accepts `p_status` as `TEXT` rather than using the `task_status` enum type defined in the schema. While PostgreSQL will enforce constraints at the column level, using TEXT allows any string to be passed as the status parameter, which could cause unexpected behavior or errors deep in the execution.
- **Code Evidence:**
  ```sql
  CREATE OR REPLACE FUNCTION update_task_status(
      p_task_id UUID,
      p_status TEXT,
      p_annotator_id UUID DEFAULT NULL
  )
  ```
- **Fix:** Use the enum type directly:
  ```sql
  CREATE OR REPLACE FUNCTION update_task_status(
      p_task_id UUID,
      p_status task_status,
      p_annotator_id UUID DEFAULT NULL
  )
  ```

---

## 4. API Security Gaps (Rate Limiting, CORS)

### FINDING 4.1 -- No CORS Configuration

- **Severity:** MEDIUM
- **File:** `vercel.json` (entire file); no CORS configuration found anywhere in codebase
- **Description:** There is no CORS (Cross-Origin Resource Sharing) configuration defined for the API. Without explicit CORS headers, the API either defaults to same-origin only (blocking legitimate cross-origin frontend requests) or, if a permissive middleware is added later, could allow any origin to make authenticated requests.
- **Fix:** Add explicit CORS configuration. In `vercel.json`, add CORS headers:
  ```json
  {
    "source": "/api/:path*",
    "headers": [
      {
        "key": "Access-Control-Allow-Origin",
        "value": "https://yourdomain.com"
      },
      {
        "key": "Access-Control-Allow-Methods",
        "value": "GET, POST, PUT, DELETE, OPTIONS"
      },
      {
        "key": "Access-Control-Allow-Headers",
        "value": "Content-Type, Authorization"
      }
    ]
  }
  ```

### FINDING 4.2 -- Rate Limiting Configured but Not Implemented

- **Severity:** MEDIUM
- **File:** `.env.example`, lines 151-152; no implementation found
- **Description:** The `.env.example` file defines `RATE_LIMIT_REQUESTS=1000` and `RATE_LIMIT_WINDOW_SECONDS=60`, suggesting rate limiting was planned. However, no rate limiting middleware or implementation exists in the codebase. The Vercel deployment also has no rate limiting configured. The `vercel.json` function configurations allow long-running functions (up to 300s for `score-batch`) without rate limits.
- **Fix:** Implement rate limiting using Upstash Redis rate limiter for the Vercel deployment:
  ```typescript
  import { Ratelimit } from "@upstash/ratelimit";
  import { Redis } from "@upstash/redis";

  const ratelimit = new Ratelimit({
    redis: Redis.fromEnv(),
    limiter: Ratelimit.slidingWindow(1000, "60 s"),
  });
  ```

### FINDING 4.3 -- Missing Content-Security-Policy Header

- **Severity:** MEDIUM
- **File:** `vercel.json`, lines 88-109
- **Description:** The `vercel.json` includes `X-Content-Type-Options`, `X-Frame-Options`, and `X-XSS-Protection` headers (good), but is missing the `Content-Security-Policy` header, which is the most effective defense against XSS attacks. Also missing `Strict-Transport-Security` (HSTS) and `Referrer-Policy` headers.
- **Code Evidence:**
  ```json
  "headers": [
    { "key": "Content-Type", "value": "application/json" },
    { "key": "X-Content-Type-Options", "value": "nosniff" },
    { "key": "X-Frame-Options", "value": "DENY" },
    { "key": "X-XSS-Protection", "value": "1; mode=block" }
  ]
  ```
- **Fix:** Add the following headers:
  ```json
  { "key": "Content-Security-Policy", "value": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'" },
  { "key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains" },
  { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
  { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" }
  ```

### FINDING 4.4 -- Vercel Functions with Excessive maxDuration

- **Severity:** LOW
- **File:** `vercel.json`, lines 111-124
- **Description:** The `quality/score-batch.ts` function allows a maximum duration of 300 seconds (5 minutes). Combined with no rate limiting, this makes the endpoint vulnerable to resource exhaustion attacks where an attacker sends many requests to the long-running function, consuming all available serverless function slots.
- **Code Evidence:**
  ```json
  "api/quality/score-batch.ts": {
    "memory": 1024,
    "maxDuration": 300
  }
  ```
- **Fix:** Reduce `maxDuration` if possible, and implement rate limiting (see Finding 4.2). Consider adding request queuing instead of synchronous processing for long operations.

---

## 5. Data Exposure (PII in Logs, Error Messages)

### FINDING 5.1 -- PII Exposed in Database View

- **Severity:** MEDIUM
- **File:** `supabase/migrations/001_initial_schema.sql`, lines 441-460
- **Description:** The `annotator_performance` view exposes annotator email addresses alongside their performance metrics. This view may be queried by dashboard components or API endpoints accessible to project managers or other annotators, leaking PII.
- **Code Evidence:**
  ```sql
  CREATE VIEW annotator_performance AS
  SELECT
      a.id,
      a.name,
      a.email,         -- PII exposed
      a.skill_level,
      a.accuracy_score,
      a.total_annotations,
      ...
  ```
- **Fix:** Remove `email` from the view or create separate views with different access levels:
  ```sql
  CREATE VIEW annotator_performance AS
  SELECT
      a.id,
      a.name,
      -- a.email removed to prevent PII exposure
      a.skill_level,
      a.accuracy_score,
      ...
  ```

### FINDING 5.2 -- Verbose Console Logging of Operational Data

- **Severity:** LOW
- **File:** `trigger-jobs/quality_scoring.ts`, lines 397-504; `trigger-jobs/active_learning.ts`, lines 80-525
- **Description:** Both trigger jobs contain extensive `console.log` statements that output batch IDs, annotator counts, task assignment details, and other operational data. In production environments, these logs may be stored in centralized logging systems where they could be accessed by broader teams than intended.
- **Code Evidence:**
  ```typescript
  // quality_scoring.ts
  console.log(`Starting quality scoring for batch ${payload.batchId}`);
  console.log(`Checkpoint 5: Stored quality score in Supabase`);

  // active_learning.ts
  console.log(`Checkpoint 2: Found ${annotators.length} available annotators`);
  console.log(`Checkpoint 3: Created ${taskAssignments.length} assignments`);
  ```
- **Fix:** Use structured logging with configurable log levels. Replace `console.log` with a proper logger:
  ```typescript
  import { logger } from "@trigger.dev/sdk/v3";
  logger.info("Quality scoring started", { batchId: payload.batchId });
  ```

### FINDING 5.3 -- Error Messages May Leak Email Addresses

- **Severity:** LOW
- **File:** `trigger-jobs/active_learning.ts`, line 409
- **Description:** Error logging includes the annotator's email address, which could end up in error tracking systems (Sentry, etc.) accessible to the development team.
- **Code Evidence:**
  ```typescript
  console.error(`Failed to send email to ${annotator.email}:`, error);
  ```
- **Fix:** Log the annotator ID instead of the email:
  ```typescript
  console.error(`Failed to send email to annotator ${annotator.id}:`, error);
  ```

---

## 6. Infrastructure Misconfigurations

### FINDING 6.1 -- Docker Container Runs as Root

- **Severity:** HIGH
- **File:** `Dockerfile`, entire file (no `USER` directive)
- **Description:** The runtime container runs all processes as root. If the application is compromised, the attacker has full root access within the container, making container escape and lateral movement easier.
- **Code Evidence:**
  ```dockerfile
  # Line 30 - copies to root's local directory
  COPY --from=builder /root/.local /root/.local
  # Line 33
  ENV PATH=/root/.local/bin:$PATH
  # No USER directive anywhere in the file
  ```
- **Fix:** Add a non-root user:
  ```dockerfile
  # After installing runtime dependencies
  RUN groupadd -r appuser && useradd -r -g appuser appuser

  # Copy packages to app user's directory
  COPY --from=builder /root/.local /home/appuser/.local
  ENV PATH=/home/appuser/.local/bin:$PATH

  # Switch to non-root user
  USER appuser
  ```

### FINDING 6.2 -- Database and Cache Ports Exposed to Host

- **Severity:** HIGH
- **File:** `docker-compose.yml`, lines 14, 33, 61-62
- **Description:** PostgreSQL (5432), Redis (6379), and Temporal (7233, 8233) ports are mapped directly to the host machine. In environments where the host has a public IP or is on a shared network, these services become directly accessible from outside the Docker network.
- **Code Evidence:**
  ```yaml
  # Line 14
  ports:
    - "5432:5432"
  # Line 33
  ports:
    - "6379:6379"
  # Lines 61-62
  ports:
    - "7233:7233"
    - "8233:8233"
  ```
- **Fix:** Bind to localhost only, or remove port mappings entirely and rely on Docker networking:
  ```yaml
  ports:
    - "127.0.0.1:5432:5432"
  ```
  Or better, remove the `ports` directive from all internal services and only expose the application port (8000).

### FINDING 6.3 -- No Network Segmentation Between Dev Tools and Production Services

- **Severity:** MEDIUM
- **File:** `docker-compose.yml`, lines 124-159
- **Description:** pgAdmin and Grafana are on the same Docker network (`dataops-network`) as PostgreSQL, Redis, and the application. While they are behind a `dev` profile, if accidentally started in a production-like environment, they provide additional attack surface with direct access to all services.
- **Fix:** Create separate networks for dev tools:
  ```yaml
  networks:
    dataops-network:
      driver: bridge
    dev-network:
      driver: bridge

  # pgadmin and grafana use dev-network + dataops-network
  # Production services use only dataops-network
  ```

### FINDING 6.4 -- Tests Directory Copied into Production Container

- **Severity:** MEDIUM
- **File:** `Dockerfile`, line 39
- **Description:** The test directory is copied into the production container, increasing the image size and attack surface. Test files may contain mock credentials, test fixtures with PII, or other data that should not be in production.
- **Code Evidence:**
  ```dockerfile
  COPY src /app/src
  COPY tests /app/tests   # Should not be in production image
  ```
- **Fix:** Remove the tests copy from the production Dockerfile:
  ```dockerfile
  COPY src /app/src
  # Do not copy tests into production image
  ```

### FINDING 6.5 -- Source Code Mounted Read-Only but Still Present in Running Containers

- **Severity:** LOW
- **File:** `docker-compose.yml`, lines 117-118
- **Description:** The compose file mounts source and test directories as read-only volumes, which is a development convenience. However, this means the container has access to the full source code at runtime. This is acceptable for development but should not be used in production configurations.
- **Code Evidence:**
  ```yaml
  volumes:
    - ./src:/app/src:ro
    - ./tests:/app/tests:ro
  ```
- **Fix:** Remove volume mounts for production. Use a separate `docker-compose.prod.yml` that does not mount source code.

---

## 7. Dependency Vulnerabilities

### FINDING 7.1 -- psycopg2-binary Not Recommended for Production

- **Severity:** MEDIUM
- **File:** `requirements.txt`, line 9
- **Description:** The project uses `psycopg2-binary` which bundles its own version of libpq. The psycopg2 documentation explicitly warns against using the binary package in production because it may have incompatibilities with system libraries and does not receive security patches for the bundled libpq as quickly.
- **Code Evidence:**
  ```
  psycopg2-binary==2.9.9
  ```
- **Fix:** Use `psycopg2` (non-binary) in production, which compiles against the system's libpq:
  ```
  psycopg2==2.9.9
  ```
  Keep `psycopg2-binary` only in a development requirements file.

### FINDING 7.2 -- Potentially Outdated Dependencies with Known Vulnerabilities

- **Severity:** MEDIUM
- **File:** `requirements.txt`, multiple lines
- **Description:** Several dependencies are pinned to versions that may have known security vulnerabilities:
  - `aiohttp==3.9.1` -- versions prior to 3.9.4 had HTTP request smuggling vulnerabilities (CVE-2024-23334, CVE-2024-23829)
  - `boto3==1.29.7` / `botocore==1.32.7` -- significantly outdated (Dec 2023), may miss security patches
  - `opentelemetry-api==1.20.0` / `opentelemetry-sdk==1.20.0` -- outdated (Oct 2023)
- **Fix:** Update all dependencies to their latest patch versions. Run periodic dependency audits:
  ```bash
  pip install pip-audit
  pip-audit -r requirements.txt
  ```

### FINDING 7.3 -- Docker Images Using `latest` Tag

- **Severity:** LOW
- **File:** `docker-compose.yml`, lines 46, 129, 144
- **Description:** Several Docker images use the `latest` tag, which is mutable and can change unexpectedly. This makes builds non-reproducible and could introduce security vulnerabilities if a compromised image is pushed.
- **Code Evidence:**
  ```yaml
  image: temporalio/auto-setup:latest
  image: dpage/pgadmin4:latest
  image: grafana/grafana:latest
  ```
- **Fix:** Pin all Docker images to specific versions:
  ```yaml
  image: temporalio/auto-setup:1.24.2
  image: dpage/pgadmin4:8.4
  image: grafana/grafana:10.3.1
  ```

---

## Recommendations Summary (Priority Order)

### Immediate Actions (CRITICAL)

1. **Remove SSRF vulnerability** -- Replace `$json.body.api_endpoint` with a fixed environment variable in `n8n/annotation_quality_pipeline.json` (Finding 3.1)
2. **Add webhook authentication** -- Secure the n8n webhook trigger with header-based auth or HMAC signatures (Finding 2.1)
3. **Remove default passwords from docker-compose.yml** -- Use `${VAR:?error}` syntax to require explicit configuration (Finding 1.1)

### Short-Term Actions (HIGH)

4. **Run containers as non-root** -- Add `USER` directive to Dockerfile (Finding 6.1)
5. **Bind database ports to localhost** -- Prevent external access to PostgreSQL and Redis (Finding 6.2)
6. **Use SERVICE_KEY for server-side n8n operations** -- Replace ANON_KEY usage (Finding 2.2)
7. **Validate environment variables in trigger jobs** -- Replace non-null assertions with explicit checks (Finding 2.3)
8. **Fix XSS in email templates** -- Use React Email components or escape user input (Finding 3.2)
9. **Add input validation to n8n webhooks** -- Validate batch_id, schema_type, annotations structure (Finding 3.3)
10. **Remove default passwords from .env.example** -- Use non-functional placeholders (Finding 1.2)

### Medium-Term Actions (MEDIUM)

11. **Implement rate limiting** -- Use Upstash Ratelimit on API endpoints (Finding 4.2)
12. **Add CORS configuration** -- Define allowed origins explicitly (Finding 4.1)
13. **Add security headers** -- CSP, HSTS, Referrer-Policy, Permissions-Policy (Finding 4.3)
14. **Remove PII from database views** -- Drop email from annotator_performance view (Finding 5.1)
15. **Update vulnerable dependencies** -- Especially aiohttp, boto3 (Finding 7.2)
16. **Use psycopg2 non-binary in production** (Finding 7.1)
17. **Remove tests from production Docker image** (Finding 6.4)
18. **Add network segmentation for dev tools** (Finding 6.3)

### Long-Term Actions (LOW)

19. **Pin Docker image versions** (Finding 7.3)
20. **Implement structured logging** -- Replace console.log with proper logger (Finding 5.2)
21. **Redact PII from error logs** -- Log IDs instead of emails (Finding 5.3)
22. **Use enum types in SQL functions** (Finding 3.4)
23. **Protect Snowflake credentials in connection string** (Finding 1.3)

---

## Positive Security Findings

The following security practices are already in place and should be maintained:

1. **Row-Level Security (RLS)** enabled on all Supabase tables in the migration schema
2. **Multi-stage Docker build** reduces final image size and attack surface
3. **Health checks** configured for all Docker services
4. **`.gitignore` properly excludes** `.env`, `.env.local`, and other sensitive files
5. **Security headers present** in `vercel.json` (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)
6. **Environment variables used** for secrets (not hardcoded values) in n8n workflows and trigger jobs
7. **Read-only volume mounts** in docker-compose for source code
8. **Clerk authentication** configured for the frontend application
9. **React Email templates** use component-based rendering (safe from XSS) for the primary email templates
10. **Dev-only services** (pgAdmin, Grafana) behind Docker Compose profiles

---

*This review covers the codebase as of 2026-03-06. Security reviews should be performed regularly, especially after major changes to authentication, authorization, or infrastructure configuration.*
