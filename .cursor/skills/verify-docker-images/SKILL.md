---
name: verify-docker-images
description: Build and validate all Docker image variants (fpm, roadrunner, swoole, frankenphp x production, development). Creates a fresh Laravel project, applies this repo's Docker configs, builds all 8 images, starts containers, and verifies a comprehensive checklist of assertions via docker exec and HTTP requests. Use when the user says "run tests", "verify images", "validate docker", "check everything works", or after making changes to Dockerfiles, confs/, or scripts/.
---

# Verify Docker Images

Replaces the traditional test suite with agent-driven verification. Scaffolds a fresh Laravel project, builds all Docker image variants, starts containers, and validates each one against a strict checklist.

## Prerequisites

- Docker daemon running locally
- At least 10 GB free disk space
- No containers named `lpr-test-*` already running

## Workflow

**Read [REFERENCE.md](REFERENCE.md) immediately** — it contains the exact setup procedure, every verification check, and the expected values.

High-level steps:

1. **Clean up** — Remove any stale `lpr-test-*` containers and images from previous runs
2. **Scaffold** — Create a fresh Laravel project in a temp directory via a `composer` Docker container
3. **Prepare** — Copy both Dockerfiles + confs/ + scripts/ + editor/.dockerignore, install packages, patch start-container.sh
4. **Build** — Build all 8 Docker images (fpm/roadrunner/swoole via `Dockerfile`, frankenphp via `Dockerfile.frankenphp`)
5. **Start** — Run all 8 containers with the correct env vars and volume mounts (dev containers need bind-mount)
6. **Wait** — Poll each container until its health check passes (up to 120 seconds each)
7. **Verify** — Execute **every single check** from the REFERENCE.md checklist, recording PASS or FAIL
8. **Report** — Print a summary table grouped by container, with total pass/fail counts
9. **Clean up** — Stop and remove all containers, remove images, delete the temp directory

## Rules

- You **MUST** run every check listed in REFERENCE.md. Do not skip any.
- For each check, record the actual value observed alongside PASS/FAIL.
- If a container fails to start, mark all its checks as FAIL with reason "container failed to start" and continue with the remaining containers.
- If a single check fails, continue running all other checks — do not stop early.
- Always clean up at the end, even if checks fail.
- Use `docker exec CONTAINER_NAME CMD` for in-container checks.
- Use `curl -s` for HTTP checks against `http://127.0.0.1:PORT`.
- Report the final summary as a markdown table.
