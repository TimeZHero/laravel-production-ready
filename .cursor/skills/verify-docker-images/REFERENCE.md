# Verification Reference

Complete setup procedure and verification checklist for all Docker image variants.

---

## Naming Conventions

| Engine     | Target      | Image Tag                       | Container Name                  |
| ---------- | ----------- | ------------------------------- | ------------------------------- |
| fpm        | production  | `lpr-test:fpm-production`       | `lpr-test-fpm-production`       |
| fpm        | development | `lpr-test:fpm-development`      | `lpr-test-fpm-development`      |
| roadrunner | production  | `lpr-test:roadrunner-production`| `lpr-test-roadrunner-production`|
| roadrunner | development | `lpr-test:roadrunner-development`| `lpr-test-roadrunner-development`|
| swoole     | production  | `lpr-test:swoole-production`    | `lpr-test-swoole-production`    |
| swoole     | development | `lpr-test:swoole-development`   | `lpr-test-swoole-development`   |
| frankenphp | production  | `lpr-test:frankenphp-production`| `lpr-test-frankenphp-production`|
| frankenphp | development | `lpr-test:frankenphp-development`| `lpr-test-frankenphp-development`|

---

## Setup Procedure

### 1. Clean up stale resources

Remove any containers and images left over from a previous run:

```bash
for name in lpr-test-fpm-production lpr-test-fpm-development \
            lpr-test-roadrunner-production lpr-test-roadrunner-development \
            lpr-test-swoole-production lpr-test-swoole-development \
            lpr-test-frankenphp-production lpr-test-frankenphp-development; do
    docker rm -f "$name" 2>/dev/null || true
done

for tag in lpr-test:fpm-production lpr-test:fpm-development \
           lpr-test:roadrunner-production lpr-test:roadrunner-development \
           lpr-test:swoole-production lpr-test:swoole-development \
           lpr-test:frankenphp-production lpr-test:frankenphp-development; do
    docker rmi -f "$tag" 2>/dev/null || true
done
```

### 2. Create a temp directory

```bash
TMPDIR=$(mktemp -d -t lpr-test-XXXXXX)
echo "Scaffolding in: $TMPDIR"
```

Keep `$TMPDIR` for the rest of the procedure. All subsequent commands assume the project root is the repo directory (the one containing `Dockerfile`, `confs/`, `scripts/`).

### 3. Scaffold a fresh Laravel project

Use the official composer Docker image so no local PHP is needed:

```bash
docker run --rm -v "$TMPDIR:/app" -w /app composer:latest \
    sh -c "composer create-project --no-interaction --prefer-dist laravel/laravel ."
```

### 4. Copy Docker configs into the scaffolded project

From the repo root, copy these into `$TMPDIR`:

- `Dockerfile`
- `Dockerfile.frankenphp`
- `confs/` (entire directory, recursive)
- `scripts/` (entire directory, recursive)
- `editor/.dockerignore` → `$TMPDIR/.dockerignore`

### 5. Install Octane and RoadRunner packages

```bash
docker run --rm -v "$TMPDIR:/app" -w /app composer:latest \
    sh -c "composer require -W --ignore-platform-reqs laravel/octane spiral/roadrunner-cli spiral/roadrunner-http --no-interaction"
```

### 6. Register the dev commands

Create `$TMPDIR/app/Providers/DevServiceProvider.php` with the registrations from
the README's "Development" section:

```php
<?php

namespace App\Providers;

use Illuminate\Foundation\DevCommands;
use Illuminate\Support\ServiceProvider;

class DevServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        if (! $this->app->environment('local')) {
            return;
        }

        $engine = env('OCTANE_SERVER');

        if ($engine) {
            $port = env('OCTANE_PORT', 8000);
            DevCommands::artisan("octane:start --watch --server={$engine} --port={$port}", 'server');
        } else {
            DevCommands::register('php-fpm -F 2>&1 | cat', 'server');
        }

        DevCommands::artisan('schedule:work', 'scheduler');
    }
}
```

Then edit `$TMPDIR/bootstrap/providers.php` so it returns:

```php
<?php

return [
    App\Providers\AppServiceProvider::class,
    App\Providers\DevServiceProvider::class,
];
```

### 7. Create the .env file

Write to `$TMPDIR/.env`:

```
APP_NAME=LaravelTest
APP_ENV=testing
APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU=
APP_DEBUG=true
DB_CONNECTION=null
LOG_CHANNEL=stderr
SESSION_DRIVER=file
CACHE_STORE=array
QUEUE_CONNECTION=sync
```

### 8. Create the packages directory

```bash
mkdir -p "$TMPDIR/packages"
```

The Dockerfile's `COPY` expects this directory to exist.

### 9. Install npm dependencies

Install them **inside a Linux container**, not on the host — otherwise
`node_modules` (bind-mounted into the dev containers) contains macOS native
bindings (e.g. rolldown/esbuild) and the Vite dev server crash-loops with
"Cannot find native binding". This also mirrors real usage, where
`start-container.sh` runs `npm install` inside the container on first boot.

The libc must match the image family — one `node_modules` cannot serve both:

- **nginx-based dev containers** (Alpine/musl): install with `node:24-alpine`
- **frankenphp dev container** (Debian/glibc): install with `node:24-slim`

```bash
# For the nginx-based dev containers (default — do this one first)
docker run --rm -v "$TMPDIR:/app" -w /app node:24-alpine \
    sh -c "npm install && npm install --save-dev chokidar"
```

To verify Vite in the frankenphp development container as well, reinstall with
`node:24-slim` and restart only that container (`docker restart
lpr-test-frankenphp-development`). Reinstall with `node:24-alpine` afterwards
if further checks on the nginx-based dev containers are needed.

`chokidar` is needed for Octane's `--watch` flag in development.

### 10. Patch start-container.sh

In `$TMPDIR/scripts/start-container.sh`, make two replacements so the container doesn't fail on missing DB or missing Filament:

| Original                                  | Replacement                                              |
| ----------------------------------------- | -------------------------------------------------------- |
| `php artisan migrate --force --isolated`   | `php artisan migrate --force --isolated 2>/dev/null \|\| true` |
| `php artisan filament:optimize`            | `php artisan filament:optimize 2>/dev/null \|\| true`        |

### 11. Build all 8 images

Build nginx-based images (fpm, roadrunner, swoole) from `Dockerfile`:

```bash
for ENGINE in fpm roadrunner swoole; do
    for TARGET in production development; do
        docker build --tag "lpr-test:${ENGINE}-${TARGET}" \
                     --target "$TARGET" \
                     --build-arg "ENGINE=$ENGINE" \
                     "$TMPDIR"
    done
done
```

Build FrankenPHP images from `Dockerfile.frankenphp`:

```bash
for TARGET in production development; do
    docker build -f "$TMPDIR/Dockerfile.frankenphp" \
                 --tag "lpr-test:frankenphp-${TARGET}" \
                 --target "$TARGET" \
                 --build-arg "ENGINE=frankenphp" \
                 "$TMPDIR"
done
```

If any build fails, record it and continue building the rest.

### 12. Start all containers

**Runtime environment variables** (used for every container):

```
APP_NAME=LaravelTest
APP_ENV=testing
APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU=
APP_DEBUG=true
DB_CONNECTION=null
LOG_CHANNEL=stderr
SESSION_DRIVER=file
CACHE_STORE=array
QUEUE_CONNECTION=sync
```

**Production containers** — source code is baked into the image:

```bash
docker run -d --name "lpr-test-ENGINE-production" \
    -p 8080 \
    -e APP_NAME=LaravelTest \
    -e APP_ENV=testing \
    -e APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU= \
    -e APP_DEBUG=true \
    -e DB_CONNECTION=null \
    -e LOG_CHANNEL=stderr \
    -e SESSION_DRIVER=file \
    -e CACHE_STORE=array \
    -e QUEUE_CONNECTION=sync \
    "lpr-test:ENGINE-production"
```

**Development containers** — source code is NOT in the image, bind-mount the scaffolded project:

```bash
docker run -d --name "lpr-test-ENGINE-development" \
    -p 8080 \
    -v "$TMPDIR:/app" \
    -e APP_NAME=LaravelTest \
    -e APP_ENV=local \
    -e APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU= \
    -e APP_DEBUG=true \
    -e DB_CONNECTION=null \
    -e LOG_CHANNEL=stderr \
    -e SESSION_DRIVER=file \
    -e CACHE_STORE=array \
    -e QUEUE_CONNECTION=sync \
    -e HOME=/tmp \
    "lpr-test:ENGINE-development"
```

Note the differences for development: `APP_ENV=local`, `HOME=/tmp`, and the bind-mount volume.

### 13. Wait for containers to become healthy

Poll each container until the health check passes (the Dockerfiles define a `HEALTHCHECK`):

```bash
docker inspect --format='{{.State.Health.Status}}' CONTAINER_NAME
```

Repeat every 3 seconds, up to 120 seconds total. Expected value: `healthy`.

If a container exits or doesn't become healthy within 120 seconds, record it as failed, inspect logs with `docker logs CONTAINER_NAME`, and move on.

Known harness artifact: all development containers share the same bind-mounted
`/app`, and both RoadRunner and Swoole write their state to
`storage/framework/octane-server-state.json`. One engine's state file can make
the other engine's `octane:start` abort with "server is already running" (the
recorded pid usually exists in the other container's namespace too). Fix:
delete `storage/framework/octane-server-state.json` and restart the affected
container. Not a repo bug — real projects run a single dev container.

### 14. Get the mapped host port

Each container maps port 8080 to a random host port:

```bash
docker port CONTAINER_NAME 8080
```

Use the returned `127.0.0.1:PORT` as the base URL for HTTP checks on that container.

---

## Verification Checklist

### Legend

- **Applies to**: which containers must be checked
- **Command**: exact command to run
- **Expected**: the assertion to verify
- **"nginx-based"** = fpm, roadrunner, swoole (all 6 containers)
- **"octane"** = roadrunner, swoole (not fpm, not frankenphp-for-this-section)
- **"all"** = all 8 containers

---

### A. Reachability

These checks verify the container is serving HTTP traffic correctly.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| A1 | Health endpoint | all 8 containers | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:PORT/up` | `200` |
| A2 | Root page | all 8 containers | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:PORT/` | `200` |

---

### B. Security Headers

These checks verify security-related HTTP headers.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| B1 | X-Frame-Options | nginx-based only (6 containers) | `curl -s -D - -o /dev/null http://127.0.0.1:PORT/up` and inspect headers | Header `X-Frame-Options` equals `SAMEORIGIN` |
| B2 | X-Content-Type-Options | nginx-based only (6 containers) | Same curl, inspect headers | Header `X-Content-Type-Options` equals `nosniff` |
| B3 | No X-Powered-By | all 8 containers | Same curl, inspect headers | Header `X-Powered-By` is **absent** |
| B4 | Server hides version | nginx-based only (6 containers) | Same curl, inspect headers | Header `Server` does **not** contain a `/` character (no version exposed) |

---

### C. Dotfile and PHP Access Denial

These checks verify sensitive files are not accessible.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| C1 | .env blocked | nginx-based only (6 containers) | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:PORT/.env` | `403` |
| C2 | .git blocked | nginx-based only (6 containers) | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:PORT/.git/config` | `403` |
| C3 | Direct PHP access denied | fpm containers only (2 containers) | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:PORT/some-random-file.php` | `404` |

---

### D. Production — Nginx Configuration

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| D1 | sendfile enabled | nginx-based production (3 containers) | `docker exec CONTAINER nginx -T` | Output contains `sendfile on` |

---

### E. Development — Nginx Configuration

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| E1 | sendfile NOT enabled | nginx-based development (3 containers) | `docker exec CONTAINER nginx -T` | Output does **not** contain `sendfile on` |

---

### F. Production — PHP Configuration

For **nginx-based production** containers (fpm-production, roadrunner-production, swoole-production), use `php -i` and `php -m`:

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| F1 | opcache timestamps disabled | nginx-based production (3 containers) | `docker exec CONTAINER php -i \| grep opcache.validate_timestamps` | Value is `0` or `Off` |
| F2 | xdebug not installed | nginx-based production (3 containers) | `docker exec CONTAINER php -m` | `xdebug` (case-insensitive) is **not** in the list |

For **frankenphp-production** (1 container), use temp PHP scripts because the FrankenPHP php wrapper can interfere with `php -i` / `php -m`:

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| F3 | opcache timestamps disabled | frankenphp-production | `docker exec CONTAINER sh -c 'echo "<?php echo ini_get(\"opcache.validate_timestamps\");" > /tmp/_q.php && php /tmp/_q.php'` | Output is `0`, `Off`, or empty string |
| F4 | xdebug not installed | frankenphp-production | `docker exec CONTAINER sh -c 'echo "<?php foreach(get_loaded_extensions() as \$e) echo strtolower(\$e).PHP_EOL;" > /tmp/_q.php && php /tmp/_q.php'` | `xdebug` is **not** in the output |

---

### G. Development — PHP Configuration

For **nginx-based development** containers (fpm-development, roadrunner-development, swoole-development):

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| G1 | opcache timestamps enabled | nginx-based development (3 containers) | `docker exec CONTAINER php -i \| grep opcache.validate_timestamps` | Value is `1` or `On` |
| G2 | xdebug installed | nginx-based development (3 containers) | `docker exec CONTAINER php -m` | `xdebug` (case-insensitive) **is** in the list |

For **frankenphp-development** (1 container):

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| G3 | opcache timestamps enabled | frankenphp-development | `docker exec CONTAINER sh -c 'echo "<?php echo ini_get(\"opcache.validate_timestamps\");" > /tmp/_q.php && php /tmp/_q.php'` | Output is `1` or `On` |
| G4 | xdebug installed | frankenphp-development | `docker exec CONTAINER sh -c 'echo "<?php foreach(get_loaded_extensions() as \$e) echo strtolower(\$e).PHP_EOL;" > /tmp/_q.php && php /tmp/_q.php'` | `xdebug` **is** in the output |

---

### H. Production — Octane Environment Variables

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| H1 | OCTANE_HTTPS=true | roadrunner-production, swoole-production, frankenphp-production (3 containers) | `docker exec CONTAINER env \| grep OCTANE_HTTPS` | `OCTANE_HTTPS=true` |

---

### I. Development — Octane Environment Variables

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| I1 | OCTANE_HTTPS=false | roadrunner-development, swoole-development, frankenphp-development (3 containers) | `docker exec CONTAINER env \| grep OCTANE_HTTPS` | `OCTANE_HTTPS=false` |
| I2 | --watch flag present | roadrunner-development, swoole-development, frankenphp-development (3 containers) | `docker exec CONTAINER ps aux` (frankenphp: use the /proc command from section M) | Process list contains `octane:start --watch` |
| I3 | OCTANE_PORT declared | roadrunner-development, swoole-development (2 containers) | `docker exec CONTAINER env \| grep OCTANE_PORT` | `OCTANE_PORT=8000` |
| I4 | OCTANE_PORT declared | frankenphp-development | `docker exec CONTAINER env \| grep OCTANE_PORT` | `OCTANE_PORT=8080` |

---

### J. User Permissions

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| J1 | Non-root user | all 8 containers | `docker exec CONTAINER id` (without specifying a user, runs as the container's default) | Output does **not** contain `uid=0` |

---

### K. Processes — Nginx-Based Production

Verify using `ps aux` inside the container.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| K1 | nginx running | fpm-production, roadrunner-production, swoole-production | `docker exec CONTAINER ps aux` | Output contains `nginx` |
| K2 | Engine process running | fpm-production | Same ps output | Contains `php-fpm` |
| K3 | Engine process running | roadrunner-production, swoole-production | Same ps output | Contains `octane` |
| K4 | No queue worker | fpm-production, roadrunner-production, swoole-production | Same ps output | Does **not** contain `queue:work` |
| K5 | No scheduler | fpm-production, roadrunner-production, swoole-production | Same ps output | Does **not** contain `schedule:` |
| K6 | No dev multiplexer | fpm-production, roadrunner-production, swoole-production | Same ps output | Does **not** contain `artisan dev` |
| K7 | Engine under supervisord | fpm-production | `docker exec CONTAINER ls /etc/supervisor.d/` | Contains `php-fpm.conf` |
| K8 | Engine under supervisord | roadrunner-production, swoole-production | `docker exec CONTAINER ls /etc/supervisor.d/` | Contains `octane.conf` |

---

### L. Processes — Nginx-Based Development

In development, supervisord runs **only nginx**. The app server (php-fpm or
octane) and the sidecars (queue listener, scheduler, Vite, Pail) are all
managed by `php artisan dev` — consistent across engines.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| L1 | nginx running | fpm-development, roadrunner-development, swoole-development | `docker exec CONTAINER ps aux` | Output contains `nginx` |
| L2 | Engine process running | fpm-development | Same ps output | Contains `php-fpm` |
| L3 | Engine process running | roadrunner-development, swoole-development | Same ps output | Contains `octane` |
| L4 | Dev multiplexer running | fpm-development, roadrunner-development, swoole-development | Same ps output | Contains `artisan dev` |
| L5 | Queue listener running | fpm-development, roadrunner-development, swoole-development | Same ps output | Contains `queue:listen` |
| L6 | Scheduler running | fpm-development, roadrunner-development, swoole-development | Same ps output | Contains `schedule:work` |
| L7 | Vite dev server running | fpm-development, roadrunner-development, swoole-development | Same ps output | Contains `vite` |
| L8 | Log tailing running | fpm-development, roadrunner-development, swoole-development | Same ps output | Contains `pail` |
| L9 | No default dev server | fpm-development, roadrunner-development, swoole-development | Same ps output | Does **not** contain `artisan serve` (the provider replaces the default `server` process with the engine) |
| L10 | Engine not under supervisord | fpm-development, roadrunner-development, swoole-development | `docker exec CONTAINER ls /etc/supervisor.d/` | Contains `nginx.conf` and `dev.conf`; does **not** contain `php-fpm.conf` or `octane.conf` |

---

### M. Processes — FrankenPHP

FrankenPHP containers do not have `ps` installed. Use `/proc` to inspect running processes:

```bash
docker exec CONTAINER sh -c 'for f in /proc/[0-9]*/cmdline; do tr "\0" " " < "$f" 2>/dev/null; echo; done'
```

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| M1 | Octane/FrankenPHP running | frankenphp-production, frankenphp-development | See proc command above | Output contains `octane` or `frankenphp` |
| M2 | No nginx | frankenphp-production, frankenphp-development | Same output | Does **not** contain `nginx` |
| M3 | No supervisord | frankenphp-production, frankenphp-development | Same output | Does **not** contain `supervisord` |
| M4 | Dev multiplexer + sidecars | frankenphp-development | Same output | Contains `artisan dev`, `queue:listen` and `schedule:work` (FrankenPHP has no supervisord, so `artisan dev` is the container command and Octane itself runs as a dev process) |
| M5 | No dev multiplexer | frankenphp-production | Same output | Does **not** contain `artisan dev` |

---

### N. Node.js Version (multiplex floor)

`php artisan dev` runs through `@laravel/multiplex`, which requires Node.js
**v22.13 or later**. Verify every development image meets the floor.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| N1 | Node.js version | all 4 development containers | `docker exec CONTAINER node --version` | `v22.13.0` or higher |

---

## Cleanup

After all checks are complete (regardless of pass/fail), run:

```bash
# Stop and remove all containers
for name in lpr-test-fpm-production lpr-test-fpm-development \
            lpr-test-roadrunner-production lpr-test-roadrunner-development \
            lpr-test-swoole-production lpr-test-swoole-development \
            lpr-test-frankenphp-production lpr-test-frankenphp-development; do
    docker rm -f "$name" 2>/dev/null || true
done

# Remove all images
for tag in lpr-test:fpm-production lpr-test:fpm-development \
           lpr-test:roadrunner-production lpr-test:roadrunner-development \
           lpr-test:swoole-production lpr-test:swoole-development \
           lpr-test:frankenphp-production lpr-test:frankenphp-development; do
    docker rmi -f "$tag" 2>/dev/null || true
done

# Delete the temp directory
rm -rf "$TMPDIR"
```

---

## Results Format

Present results as a markdown table grouped by container:

```
## Results

### lpr-test-fpm-production

| #  | Check                     | Result | Actual Value         |
|----|---------------------------|--------|----------------------|
| A1 | Health endpoint           | PASS   | 200                  |
| A2 | Root page                 | PASS   | 200                  |
| B1 | X-Frame-Options           | PASS   | SAMEORIGIN           |
| ...| ...                       | ...    | ...                  |

### lpr-test-fpm-development

| #  | Check                     | Result | Actual Value         |
|----|---------------------------|--------|----------------------|
| ...| ...                       | ...    | ...                  |

...

### Summary

| Container                      | Passed | Failed | Total |
|--------------------------------|--------|--------|-------|
| lpr-test-fpm-production        | 14     | 0      | 14    |
| lpr-test-fpm-development       | 13     | 0      | 13    |
| ...                            | ...    | ...    | ...   |
| **Total**                      | **X**  | **Y**  | **Z** |
```
