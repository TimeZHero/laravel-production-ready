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
use Illuminate\Support\Facades\App;
use Illuminate\Support\ServiceProvider;

class DevServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        if (! App::isLocal()) {
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

Append a scheduled task to `$TMPDIR/routes/console.php`, used by the boot
output checks (section R):

```php
Illuminate\Support\Facades\Schedule::command('inspire')->hourly();
```

Append a slow route to `$TMPDIR/routes/web.php`, used by the graceful-shutdown
checks (section P):

```php
Route::get('/slow', function () {
    sleep(10);

    return 'slow-done';
});
```

Append the feature routes used by the hardened-runtime checks (section T). Each
one writes where a real app writes:

```php
Route::prefix('check')->group(function () {
    Route::get('/view', fn () => view('check'));
    Route::get('/session', function () {
        session(['visits' => session('visits', 0) + 1]);

        return (string) session('visits');
    });
    Route::get('/cache', function () {
        Illuminate\Support\Facades\Cache::store('file')->put('check', 'cache-ok', 60);

        return Illuminate\Support\Facades\Cache::store('file')->get('check');
    });
    Route::get('/local-disk', function () {
        Illuminate\Support\Facades\Storage::disk('local')->put('check.txt', 'local-ok');

        return Illuminate\Support\Facades\Storage::disk('local')->get('check.txt');
    });
    Route::get('/public-disk', function () {
        Illuminate\Support\Facades\Storage::disk('public')->put('check.txt', 'public-ok');

        return Illuminate\Support\Facades\Storage::disk('public')->get('check.txt');
    });
    Route::post('/upload', fn (Illuminate\Http\Request $request) => $request->file('file')->store('uploads') ? 'upload-ok' : 'upload-failed')
        ->withoutMiddleware(Illuminate\Foundation\Http\Middleware\PreventRequestForgery::class);
    Route::get('/log', function () {
        Illuminate\Support\Facades\Log::channel('single')->info('check-log-line');

        return str_contains(file_get_contents(storage_path('logs/laravel.log')), 'check-log-line') ? 'log-ok' : 'log-missing';
    });
    Route::get('/tmp', fn () => file_put_contents(tempnam(sys_get_temp_dir(), 'check'), 'x') ? 'tmp-ok' : 'tmp-failed');
    Route::get('/mail', function () {
        Illuminate\Support\Facades\Mail::raw('check', fn ($message) => $message->to('check@example.com'));

        return 'mail-ok';
    });
    Route::get('/queue', function () {
        App\Jobs\CheckJob::dispatch();

        return 'queued';
    });
});
```

Create `$TMPDIR/resources/views/check.blade.php` (compiled on first render):

```blade
<x-check-badge label="view-ok" />
```

Create `$TMPDIR/resources/views/components/check-badge.blade.php`:

```blade
@props(['label'])
<span>{{ $label }}</span>
```

Create `$TMPDIR/app/Jobs/CheckJob.php`:

```php
<?php

namespace App\Jobs;

use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Support\Facades\Storage;

class CheckJob implements ShouldQueue
{
    use Queueable;

    public function handle(): void
    {
        Storage::disk('local')->put('job.txt', 'job-ok');
    }
}
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

Make the build also write outside `public/build`, the way an Inertia SSR
bundle does, so S6 can check that every build output reaches production:

```bash
docker run --rm -v "$TMPDIR:/app" -w /app node:24-alpine \
    npm pkg set scripts.build="vite build && mkdir -p bootstrap/ssr && echo built > bootstrap/ssr/marker.txt"
```

### 10. Patch start-container.sh

In `$TMPDIR/scripts/start-container.sh`, make these replacements so the container doesn't fail on missing DB or missing Filament (these tests run with `DB_CONNECTION=null`, so `migrate:status` fails and the unlocked branch hits an unreachable connection; the locked loop is patched too, in case a branch changes):

| Original                                   | Replacement                                                       |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `    php artisan migrate:status --pending=2 \|\| pending=$?` | `    php artisan migrate:status --pending=2 2>/dev/null \|\| pending=$?` |
| `            until php artisan migrate --force --isolated=75; do` | `            until php artisan migrate --force --isolated=75 2>/dev/null \|\| true; do` |
| `            php artisan migrate --force` (inside the `*)` branch) | `            php artisan migrate --force 2>/dev/null \|\| true` |
| `php artisan filament:optimize`             | `php artisan filament:optimize 2>/dev/null \|\| true`                |

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
| F5 | PHP memory limit defaults to 128M | all 4 production images | `docker run --rm ENV_FLAGS lpr-test:ENGINE-production php -r 'echo ini_get("memory_limit");'` | Output ends with `128M` |
| F6 | `PHP_MEMORY_LIMIT` overrides it | all 4 production images | Same, with `-e PHP_MEMORY_LIMIT=256M` | Output ends with `256M` |
| F7 | PHP stops a worker before the pod limit does | all 4 production images | `docker run --name lpr-test-oom -m 320m ENV_FLAGS -e PHP_MEMORY_LIMIT=256M lpr-test:ENGINE-production php artisan tinker --execute='$chunks = []; while (true) { $chunks[] = str_repeat("x", 8 * 1024 * 1024); }'`, then `docker inspect -f '{{.State.OOMKilled}}' lpr-test-oom` and `docker rm lpr-test-oom` | Output contains `Allowed memory size of 268435456`; `OOMKilled` is `false`. The `queue` service's `scale.memory` (320) must stay above its `PHP_MEMORY_LIMIT` (256M) plus the PHP runtime |

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
| H2 | RoadRunner config flag set by its stage only | roadrunner-production, swoole-production | `docker exec CONTAINER sh -c 'ps -o args \| grep [o]ctane:start'` | roadrunner: contains `--rr-config=.rr.yaml`; swoole: does not |

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
| J2 | Code is root-owned | all 4 production containers | `docker exec CONTAINER stat -c '%u %n' /app /app/app /app/vendor /app/public/build /app/storage /app/bootstrap/cache` | `0` for the first four; `65534` for `storage` and `bootstrap/cache` |
| J3 | App user cannot write code | all 4 production containers | `docker exec CONTAINER sh -c 'touch /app/x; touch /app/public/x; touch /app/vendor/x' 2>&1` | Three `Permission denied` |
| J4 | App user writes storage | all 4 production containers | `docker exec CONTAINER sh -c 'touch storage/x bootstrap/cache/x && echo ok'` | `ok` |
| J5 | Runs as the image's `nobody` | all 4 production containers | `docker exec CONTAINER id` | `uid=65534(nobody) gid=65534(nobody)`; FrankenPHP shows `gid=65534(nogroup)` |
| J6 | Image scripts are read-only | all 8 containers | `docker exec CONTAINER stat -c '%a %u %n' /usr/local/bin/start-container` (FrankenPHP: add `/usr/local/bin/php`) | `555 0` on every line |

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

### S. Build Tools — Development Only

Git, Node/npm and Composer are build and development tools. Production images
get the built assets and the optimized autoloader from the `build` stage, not
the tools that made them.

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| S1 | No build tools | all 4 production containers | `docker exec CONTAINER sh -c 'for tool in git node npm composer; do command -v $tool >/dev/null && echo "present: $tool"; done; true'` | Empty output |
| S2 | Build tools present | all 4 development containers | `docker exec CONTAINER sh -c 'git --version && npm --version && composer --version'` | Exit code 0 |
| S3 | Built assets shipped | all 4 production containers | `docker exec CONTAINER sh -c 'test -f public/build/manifest.json && echo ok'` | `ok` |
| S4 | Optimized autoloader shipped | all 4 production containers | `docker exec CONTAINER grep -c "setClassMapAuthoritative(true)" vendor/composer/autoload_real.php` | `1` or more |
| S5 | Package manifest shipped | all 4 production containers | `docker exec CONTAINER test -f bootstrap/cache/packages.php` | Exit code 0 |
| S6 | Output outside `public/build` shipped | all 4 production containers | `docker exec CONTAINER cat bootstrap/ssr/marker.txt` | `built` (written by the step 9 build script, like an SSR bundle) |
| S7 | No `node_modules` | all 4 production containers | `docker exec CONTAINER test -e node_modules` | Non-zero exit code |

---

### O. Startup — Migration Policy

Migrations are controlled by the explicit `RUN_MIGRATIONS` environment variable,
which defaults to `true`.

The built images carry the step 10 entrypoint, which discards migration output
and failures, so these checks mount the repo's own script over it. With
`DB_CONNECTION=null`, an attempted migration fails, and that failure must stop
the boot before the command runs. Run them for each of the 4 production images,
in bash (`$O_RUN` relies on word splitting, which zsh does not do).

```bash
REPO=/path/to/laravel-production-ready
mkdir -p "$TMPDIR/o"
# The script is 644 in git (the Dockerfiles add the exec bit), so mount an executable copy
install -m 755 "$REPO/scripts/start-container.sh" "$TMPDIR/o/start-container.sh"
O_RUN="docker run --rm \
    -v $TMPDIR/o/start-container.sh:/usr/local/bin/start-container:ro \
    -e APP_ENV=testing -e APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU= \
    -e DB_CONNECTION=null -e LOG_CHANNEL=stderr -e CACHE_STORE=array"
```

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| O1 | Migrations run by default | all 4 production images | `$O_RUN lpr-test:ENGINE-production php artisan --version 2>&1; echo "exit=$?"` | Contains `Undefined array key "driver"` (`DB_CONNECTION=null` reads as a real null, so Laravel gets the whole connections array); does **not** contain `Laravel Framework`; exit not `0` |
| O2 | Disabled migrations are skipped | all 4 production images | `$O_RUN -e RUN_MIGRATIONS=false lpr-test:ENGINE-production php artisan --version 2>&1; echo "exit=$?"` | Contains `Laravel Framework`; does **not** contain `Undefined array key`; `exit=0` |

---

### V. Startup — Migration Lock Wait

A container that loses the migration lock must wait in the entrypoint, not
exit: on Convox every exit is a restart, and `crashRestartLimit: 1` rolls the
deploy back on the second one. A migration that really fails must still exit.

These checks need a real database and the **unpatched** entrypoint (step 10
makes migration failures harmless), so they mount the repo's own script over
the image's. Run them for each of the 4 production images.

```bash
REPO=/path/to/laravel-production-ready
docker network create lpr-test-v
docker run -d --name lpr-test-v-db --network lpr-test-v \
    -e MARIADB_ROOT_PASSWORD=secret mariadb:11
mkdir -p "$TMPDIR/v"
# The script is 644 in git (the Dockerfiles add the exec bit), so mount an executable copy
install -m 755 "$REPO/scripts/start-container.sh" "$TMPDIR/v/start-container.sh"
cat > "$TMPDIR/v/slow.php" <<'PHP'
<?php
use Illuminate\Database\Migrations\Migration;
return new class extends Migration {
    public function up(): void { sleep(20); }
};
PHP
cat > "$TMPDIR/v/broken.php" <<'PHP'
<?php
use Illuminate\Database\Migrations\Migration;
return new class extends Migration {
    public function up(): void { throw new RuntimeException('broken migration'); }
};
PHP
```

Per engine, recreate the database (`docker exec lpr-test-v-db mariadb -psecret
-e 'DROP DATABASE IF EXISTS v; CREATE DATABASE v'`) and define:

```bash
V_RUN="docker run --network lpr-test-v \
    -v $TMPDIR/v/start-container.sh:/usr/local/bin/start-container:ro \
    -e APP_ENV=testing -e APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU= \
    -e LOG_CHANNEL=stderr -e CACHE_STORE=database \
    -e DB_CONNECTION=mariadb -e DB_HOST=lpr-test-v-db -e DB_DATABASE=v \
    -e DB_USERNAME=root -e DB_PASSWORD=secret"
SLOW="-v $TMPDIR/v/slow.php:/app/database/migrations/2099_01_01_000000_slow.php:ro"
BROKEN="-v $TMPDIR/v/broken.php:/app/database/migrations/2099_01_01_000001_broken.php:ro"
# Not yet run when V6 starts (SLOW already ran in step 2)
SLOW2="-v $TMPDIR/v/slow.php:/app/database/migrations/2099_01_01_000002_slow.php:ro"
```

1. Bootstrap the schema: `$V_RUN --rm lpr-test:ENGINE-production php artisan --version` (exit 0).
2. `$V_RUN -d --name lpr-test-v-a $SLOW lpr-test:ENGINE-production`; wait until its log contains `Running migrations.` (the migration's own line has no newline until it finishes, so Docker only logs it after the lock is free).
3. `$V_RUN -d --name lpr-test-v-b $SLOW lpr-test:ENGINE-production`.
4. Run V1–V3, then `docker rm -f lpr-test-v-a lpr-test-v-b`.
5. Run V4.
6. Leave a stale lock, as a migrating container killed mid-run would: `$V_RUN --rm -e RUN_MIGRATIONS=false lpr-test:ENGINE-production php artisan tinker --execute="Cache::lock('framework/command-migrate', 3600)->get() or exit(1);"` (exit 0). Then run V5 and V6.

| # | Check | Command | Expected |
|---|-------|---------|----------|
| V1 | Loser waits instead of exiting | 10s after step 3: `docker inspect -f '{{.State.Running}}' lpr-test-v-b` and `docker logs lpr-test-v-b 2>&1` | `true`; log contains `The [migrate] command is already running.` |
| V2 | Loser boots once the lock frees | Poll `docker inspect -f '{{.State.Health.Status}}'` on both, up to 60s | Both `healthy`; `lpr-test-v-b` never exited (`RestartCount` and exit code untouched, `.State.StartedAt` unchanged) |
| V3 | Loser did not run the migration | `docker logs lpr-test-v-b 2>&1` | Does **not** contain a `2099_01_01_000000_slow` line with `DONE` |
| V4 | Broken migration still exits | `timeout 60 $V_RUN --rm $BROKEN lpr-test:ENGINE-production php artisan --version; echo $?` | Exit code `1` (not `124`: it did not hang); output contains `broken migration` |
| V5 | Nothing pending skips the lock | `timeout 60 $V_RUN --rm lpr-test:ENGINE-production php artisan --version; echo $?` | Exit code `0`; output contains `No pending migrations` and `Laravel Framework`; does **not** contain `already running` |
| V6 | Pending migration waits on the stale lock | `$V_RUN -d --name lpr-test-v-c $SLOW2 lpr-test:ENGINE-production`; after 15s `docker inspect -f '{{.State.Running}}' lpr-test-v-c` and its logs; then `docker rm -f lpr-test-v-c` | `true`; log contains `already running` and no `2099_01_01_000002_slow` line with `DONE` |

Clean up after the last engine: `docker rm -f lpr-test-v-db && docker network rm lpr-test-v`.

---

### R. Startup — Scheduler Command

The app prints `php artisan about` at boot. The scheduler's `convox.yml`
command prints `php artisan schedule:list` first, then `exec`s
`schedule:work`. Run it from the production image with the runtime env vars
from step 12, but `APP_ENV=production`, exactly as Convox passes it (split into
arguments, no shell). `APP_ENV=testing` makes Laravel's `runningUnitTests()`
true, which turns off every `trap()` signal handler: the scheduler then ignores
SIGTERM and R4 fails for a reason production never has.

```bash
docker run -d --name lpr-test-boot-scheduler ENV_FLAGS -e APP_ENV=production -e RUN_MIGRATIONS=false lpr-test:ENGINE-production sh -c "php artisan schedule:list && exec php artisan schedule:work --whisper"
sleep 10
docker logs lpr-test-boot-scheduler > /tmp/lpr-boot-scheduler.log 2>&1
docker exec lpr-test-boot-scheduler cat /proc/1/cmdline | tr '\0' ' '
START=$(date +%s); docker stop -t 30 lpr-test-boot-scheduler; echo "stop took $(( $(date +%s) - START ))s"
docker rm -f lpr-test-boot-scheduler
```

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| R1 | App prints `about` | all 4 production containers | `docker logs CONTAINER 2>&1` | Contains `Laravel Version` |
| R2 | Scheduler prints the schedule | all 4 production images | `cat /tmp/lpr-boot-scheduler.log` | Contains `inspire` |
| R3 | `schedule:work` is PID 1 | all 4 production images | `cmdline` line above | Contains `schedule:work`; does **not** start with `sh` |
| R4 | SIGTERM reaches the scheduler | all 4 production images | `stop took` line | Under `5` seconds. `30` means the signal was lost: `sh` is PID 1 (the `exec` is missing) or the container ran with `APP_ENV=testing` |

---

### Q. Static Assets — Caching and Access Log

Vite writes content-hashed files to `public/build/assets/`, so each URL always
serves the same bytes. nginx marks them `immutable` and leaves successful hits
out of the access log. Failed requests under the same path are still logged.
Production images only, since development serves assets from the Vite dev server.

Pick a built asset first:

```bash
ASSET=$(docker exec CONTAINER sh -c 'ls /app/public/build/assets | head -1')
```

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| Q1 | Hashed asset is immutable | nginx-based production (3 containers) | `curl -s -D - -o /dev/null http://127.0.0.1:PORT/build/assets/$ASSET` | Status `200`; exactly one `Cache-Control` header, equal to `public, max-age=31536000, immutable` |
| Q2 | Security headers kept on assets | nginx-based production (3 containers) | Same curl | `X-Frame-Options: SAMEORIGIN` and `X-Content-Type-Options: nosniff` present |
| Q3 | Manifest is not immutable | nginx-based production (3 containers) | `curl -s -D - -o /dev/null http://127.0.0.1:PORT/build/manifest.json` | No `immutable` in any `Cache-Control` header |
| Q4 | Missing asset is not cacheable | nginx-based production (3 containers) | `curl -s -D - -o /dev/null http://127.0.0.1:PORT/build/assets/missing-0000.js` | Status `404`; no `immutable` in any `Cache-Control` header |
| Q5 | Dotfiles still denied under assets | nginx-based production (3 containers) | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:PORT/build/assets/.env` | `403` |
| Q6 | Successful asset hits are not logged | nginx-based production (3 containers) | Request the asset (200), then again with `-H 'If-None-Match: <its ETag>'` (304); then `docker logs CONTAINER 2>&1 \| grep "GET /build/assets/$ASSET"` | No output |
| Q7 | Failed asset requests are logged | nginx-based production (3 containers) | After Q4 and Q5: `docker logs CONTAINER 2>&1 \| grep -E 'GET /build/assets/(missing-0000.js\|\.env)' \| grep -v '\[error\]'` (nginx's error log names the same request) | Two access-log lines, with status `404` and `403` |
| Q8 | Traversal out of assets is logged | nginx-based production (3 containers) | `curl -s --path-as-is -o /dev/null http://127.0.0.1:PORT/build/assets/../manifest.json`, then `docker logs CONTAINER 2>&1 \| grep 'assets/../manifest.json'` | One line (nginx normalizes the URI to `/build/manifest.json`, outside the skipped path) |

---

### T. Hardened Runtime — Read-Only Root

Runs each production image the way the hardened `convox.yml` runs it: read-only
root, `nobody` (65534), no capabilities, no privilege escalation, and writable mounts
only where the `emptyDir` volumes go. Docker's `--tmpfs` stands in for
`emptyDir` (`exec` because `emptyDir` is not `noexec`). The app runs in
`production` with real drivers so every write path is exercised.

```bash
HARDEN="--read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,exec,mode=1777 --tmpfs /app/storage:rw,exec,mode=1777 \
  --tmpfs /app/bootstrap/cache:rw,exec,mode=1777 --tmpfs /home/nobody:rw,exec,mode=1777"
# frankenphp only: Caddy's config and data
HARDEN_FRANKENPHP="--tmpfs /config:rw,exec,mode=1777 --tmpfs /data:rw,exec,mode=1777"
APPENV="-e APP_NAME=LaravelTest -e APP_ENV=production -e APP_DEBUG=false \
  -e APP_KEY=base64:dGVzdGtleWZvcnRlc3RpbmcxMjM0NTY3ODkwYWJjZGU= \
  --network lpr-test-net -e DB_CONNECTION=mariadb -e DB_HOST=lpr-test-db \
  -e DB_DATABASE=laravel -e DB_USERNAME=laravel -e DB_PASSWORD=laravel \
  -e SESSION_DRIVER=file -e CACHE_STORE=file -e QUEUE_CONNECTION=database \
  -e LOG_CHANNEL=stderr -e MAIL_MAILER=log"
# The images ship pdo_mysql only, like production, so the checks use MariaDB
docker network create lpr-test-net
docker run -d --name lpr-test-db --network lpr-test-net -e MARIADB_DATABASE=laravel \
  -e MARIADB_USER=laravel -e MARIADB_PASSWORD=laravel -e MARIADB_ROOT_PASSWORD=root mariadb:11
docker run -d --name lpr-test-ENGINE-hardened -p 8080 $HARDEN [$HARDEN_FRANKENPHP] $APPENV lpr-test:ENGINE-production
```

Remove `lpr-test-db` and `lpr-test-net` in the cleanup step.

Wait for `healthy` as in step 13. `URL` is the mapped port; `C` the container.

| # | Check | Command | Expected |
|---|-------|---------|----------|
| T1 | Boots healthy | step 13 poll | `healthy` |
| T2 | No write errors at boot | `docker logs C 2>&1 \| grep -Ei 'read-only file system\|permission denied'` | No output |
| T3 | Config cached at boot | `docker logs C 2>&1 \| grep -E 'Config +\.+ +CACHED'` | One line |
| T4 | Blade view and component compile | `curl -s URL/check/view` | Contains `view-ok` |
| T5 | File sessions | `curl -s -c jar -b jar URL/check/session` twice | `1`, then `2` |
| T6 | File cache | `curl -s URL/check/cache` | `cache-ok` |
| T7 | Local disk | `curl -s URL/check/local-disk` | `local-ok` |
| T8 | Public disk | `curl -s URL/check/public-disk` | `public-ok` |
| T9 | Multipart upload | `curl -s -F file=@/etc/hosts URL/check/upload` | `upload-ok` |
| T10 | File log channel | `curl -s URL/check/log` | `log-ok` |
| T11 | System temp dir | `curl -s URL/check/tmp` | `tmp-ok` |
| T12 | Mail (log mailer) | `curl -s URL/check/mail` | `mail-ok` |
| T13 | Queued job | `curl -s URL/check/queue`, then `docker exec C php artisan queue:work --once`, then `docker exec C cat storage/app/private/job.txt` | `queued`, exit 0, `job-ok` |
| T14 | Scheduled task | `docker exec C php artisan schedule:test --name=inspire` | Exit 0 |
| T15 | Tinker, one-shot | `docker exec C php artisan tinker --execute="echo 'tinker-ok';" 2>&1` | Contains `tinker-ok`; no `read-only` or `not writable` |
| T16 | Tinker, interactive session | `echo "echo 'tinker-ok';" \| docker exec -i C php artisan tinker 2>&1` | Same as T15. FrankenPHP fails with `cli_set_process_title()`, with or without hardening (README Quirks): record, don't fail |
| T17 | Maintenance mode | `docker exec C php artisan down`, `curl` `/` , `docker exec C php artisan up`, `curl` `/` | `503`, then `200` |
| T18 | Rebuild caches at runtime | `docker exec C sh -c 'php artisan optimize:clear && php artisan optimize'` | Exit 0 |
| T19 | Everyday artisan | `docker exec C sh -c 'php artisan route:list && php artisan migrate:status && php artisan view:cache && php artisan event:cache'` | Exit 0 |
| T20 | Octane control | octane engines: `docker exec C php artisan octane:status` and `php artisan octane:reload` | `running`; exit 0 |
| T21 | No write errors after T4–T20 | Same as T2 | No output |
| T22 | Public disk served through `public/storage` | `curl -s URL/storage/check.txt` (written by T8) | `public-ok` |
| T23 | App options don't drop the RoadRunner flag | roadrunner only: rerun the hardened container with `-e OCTANE_OPTIONS=--workers=2`, then T1 and T2 | `healthy`; no output |

The image ships the `public/storage` link, so `php artisan storage:link` is not
needed (it fails on the read-only root). The `public` disk is per pod and lost on
restart; production stores public files on S3, see the README.

---

### U. Convox Local Rack (optional)

Section T approximates Kubernetes with Docker flags. To check the real thing,
deploy the scaffolded app to a Convox local rack. Run it with nothing else
building: a starved minikube node goes `NotReady` and fails unrelated checks.

```bash
minikube start --driver=docker --kubernetes-version=v1.35.0 --cpus=6 --memory=8g \
  --insecure-registry=registry.lpr.macdev.convox.cloud
minikube addons enable ingress && minikube addons enable ingress-dns
convox rack install local lpr -v <latest 3.25.x> os=mac
```

- **Reaching the rack:** `*.macdev.convox.cloud` resolves to `127.0.0.1`, and
  port 443 is usually taken by the local caddy-docker-proxy. Forward the ingress
  instead, `kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 9443:443`,
  and point the CLI at it with `RACK_URL` (the URL from `terraform output -raw api`
  in `~/Library/Preferences/convox/racks/lpr`, with `:9443` after the host).
  `RACK_URL` also keeps every command off any organization rack the CLI is
  logged into.
- **After `minikube stop`/`start`:** deploys roll back with
  `failed calling webhook "validate.nginx.ingress.kubernetes.io"` (the admission
  webhook's certificate no longer verifies). On the throwaway cluster:
  `kubectl delete validatingwebhookconfiguration ingress-nginx-admission`.
- **The app:** a copy of the scaffold with this repo's `convox.yml`, minus
  `domain:`. Set `APP_KEY`, `DB_CONNECTION=mariadb`, `CACHE_STORE=redis`,
  `QUEUE_CONNECTION=redis` and dummy values for the other required variables.
  Deploy each engine with `convox deploy --build-args ENGINE=<engine>`;
  FrankenPHP needs `manifest: Dockerfile.frankenphp` and the `/config` and
  `/data` `emptyDir`s.

Check against `https://app.<app>.lpr.macdev.convox.cloud:9443` (`curl -k --resolve`)
and with `kubectl exec`:

| # | Check | Expected |
|---|-------|----------|
| U1 | Pods of `app`, `queue`, `scheduler` | Running; `securityContext` and the `emptyDir` mounts present in the pod spec |
| U2 | `touch /app/public/x` in each service | Fails (read-only) |
| U3 | The T4–T13 routes, T22, the queue job picked up by the `queue` service | Same as section T |
| U4 | Tinker via `kubectl exec`, one-shot and interactive | `tinker-ok` (FrankenPHP: interactive fails, known) |
| U5 | `convox run app --use-service-volume php artisan tinker` (with a TTY) and `... php artisan about` | Works |
| U6 | `convox run app php artisan --version` without the flag | Fails: `convox run` drops `volumeOptions`, so nothing is writable |
| U7 | `convox exec <pid> php artisan tinker --execute=...` | `tinker-ok` |
| U8 | A Timer on the `scheduler` service | Pod succeeds; it has the `emptyDir` mounts |
| U9 | `down`/`up`, `optimize:clear && optimize`, `octane:status`/`octane:reload` | `503`/`200`, exit 0, `running` |
| U10 | Logs of all services | No `Read-only file system` or `Permission denied` |

---

### P. Shutdown — In-Flight Requests

A deploy stops the container while requests are still running. The stop signal
must drain them instead of dropping them. These checks **stop the container**,
so run them last, after every other check on that container.

Start a 10-second request, stop the container two seconds into it, and time the
stop:

```bash
curl -s -m 60 -o /tmp/lpr-slow-CONTAINER.txt -w '%{http_code}' http://127.0.0.1:PORT/slow > /tmp/lpr-slow-CONTAINER.code &
CURL_PID=$!
sleep 2
START=$(date +%s)
docker stop -t 90 CONTAINER
echo "stop took $(( $(date +%s) - START ))s"
wait $CURL_PID
cat /tmp/lpr-slow-CONTAINER.code /tmp/lpr-slow-CONTAINER.txt
```

| # | Check | Applies to | Command | Expected |
|---|-------|-----------|---------|----------|
| P1 | In-flight request completes | nginx-based production (3 containers) | See script above | Status `200` and body `slow-done` |
| P2 | Stop waits for the request, not the timeout | nginx-based production (3 containers) | Same script, `stop took` line | Between `5` and `30` seconds: long enough to have waited for the request, far below the 90-second kill |
| P3 | Stop signal reaches Octane | frankenphp-production | Same script, `stop took` line | Under `5` seconds. `90` means bash swallowed SIGTERM (the `php` wrapper lost its `exec`) |

FrankenPHP is expected to drop the in-flight request (curl exit `52`): on
SIGTERM, Octane asks Caddy to stop and then exits at once, killing the server
([laravel/octane#970](https://github.com/laravel/octane/issues/970)). Production
covers this with the `preStop` sleep in `convox.yml`, so do not record it as a
failure.

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

# Section V leftovers
docker rm -f lpr-test-v-a lpr-test-v-b lpr-test-v-c lpr-test-v-db 2>/dev/null || true
docker network rm lpr-test-v 2>/dev/null || true

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
