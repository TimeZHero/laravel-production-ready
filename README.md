# Production-Ready Docker Images for Laravel

Stateless, performant Laravel images designed for Kubernetes and deployed via [Convox](https://convox.com/).

Includes an ideal local environment by leveraging [Laravel Sail](https://github.com/laravel/sail) and tries to address its known minor issues.

**Local development is opinionated towards MacOS**, optimized for both simplicity and parity with the production environment.

---

## Table of Contents

- [Usage](#usage)
  - [Development](#development)
  - [Editor Files](#editor-files)
  - [Local Packages](#local-packages)
  - [Compose & Convox](#compose--convox)
  - [Redis](#redis)
- [Environment Variables](#environment-variables)
- [Trusted Proxies](#trusted-proxies)
- [Application Safeguards](#application-safeguards)
- [Scheduler](#scheduler)
- [Container Startup](#container-startup)
- [Timeouts & Shutdown](#timeouts--shutdown)
  - [Web Requests](#web-requests)
  - [App Shutdown](#app-shutdown)
  - [Queue Workers](#queue-workers)
- [Things to Review](#things-to-review)
- [Swoole](#swoole)
- [FrankenPHP](#frankenphp)
  - [Key Differences](#key-differences)
  - [Quirks](#quirks)
  - [Compose Volumes](#compose-volumes)
  - [What's Not Included](#whats-not-included)
- [TODO](#todo)
- [Additional Notes](#additional-notes)
- [Special Thanks & Inspirations](#special-thanks--inspirations)

---

## Usage

This repository is **not interactive**. All operations are done through copy-paste and by reviewing configuration files for your specific use case.

Copy the `Dockerfile` (or `Dockerfile.frankenphp`) into your project and adjust as needed.

### Development

#### Sail Setup

1. Install [Laravel Sail](https://laravel.com/framework/docs/master/sail) in your project and publish the assets.
2. Publish the Sail binary. This lets new developers skip running `composer install` right after cloning just to get Sail working. It should be updated every time the Sail version is updated.

```bash
php artisan vendor:publish --provider="Laravel\\Sail\\SailServiceProvider" --tag=sail-bin
chmod +x sail
```

3. Add this to your `composer.json` to automate updating the binary on every `composer update`:

```json
{
    "scripts": {
        "post-update-cmd": [
            "@php artisan vendor:publish --provider=\"Laravel\\Sail\\SailServiceProvider\" --tag=sail-bin --force 2>/dev/null || true",
            "chmod +x sail 2>/dev/null || true"
        ]
    }
}
```

4. Update the alias in your shell config (`~/.zshrc` for Zsh, `~/.bashrc` for Bash) so it picks up the local binary when available:

```bash
alias sail='bash $([ -f sail ] && echo sail || echo vendor/bin/sail)'
```

#### Dev Processes

The dev command is [`php artisan dev`](https://laravel.com/docs/artisan#the-dev-command), automatically running queue, scheduler, Vite dev server and Pail log tailing.

Use Laravel **13.36 or newer**. `php artisan dev` itself runs from 13.16, and 13.25 selects inline output when the process has no TTY. 13.36 is the floor for this guide: [Application Safeguards](#application-safeguards) sets `Worker::$flushStickyConnections`, which does not exist before that release.

Create a `DevServiceProvider`, register it in `bootstrap/providers.php`, and register whatever your project needs in `boot()` (`reverb:start`, `horizon:listen`, `stripe listen ...`)

The following configuration is compatible for whatever engine (PHP runtime) you decide to use. Feel free to simplify it if you do not want to support all engines in your code

```php
use Illuminate\Foundation\DevCommands;
use Illuminate\Support\Facades\App;

if (App::isLocal()) {
    $engine = env('OCTANE_SERVER');

    if ($engine) {
        $port = env('OCTANE_PORT', 8000);
        DevCommands::artisan("octane:start --watch --server={$engine} --port={$port}", 'server');
    } else {
        // | cat: php-fpm can't open /dev/stderr when stderr is a socket (multiplex)
        DevCommands::register('php-fpm -F 2>&1 | cat', 'server');
    }

    DevCommands::artisan('schedule:work', 'scheduler');
}
```

The `server` registration overrides the framework's default single-threaded `php artisan serve`.

#### Local Domains & HTTPS

The app will use a real domain with HTTPS via a single shared [caddy-docker-proxy](https://github.com/lucaslorentz/caddy-docker-proxy) per machine. We prefer this over the nginx one due to ease of SSL cert.

Always use `.localhost` over other domains due to free local host resolution

1. Add the following to your `~/.zshrc` / `~/.bashrc`. **This may collide with the local Caddy CLI if you have it installed**

```bash
caddy() {
    case "$1" in
        create)
            docker network create caddy 2>/dev/null
            docker run -d --name caddy --restart unless-stopped --network caddy \
                -p 80:80 -p 443:443 -p 443:443/udp \
                -e CADDY_INGRESS_NETWORKS=caddy \
                -v /var/run/docker.sock:/var/run/docker.sock \
                -v caddy_data:/data \
                -l caddy=proxy.localhost -l caddy.respond=OK \
                lucaslorentz/caddy-docker-proxy:ci-alpine
            ;;
        trust)
            docker cp caddy:/data/caddy/pki/authorities/local/root.crt /tmp/caddy-root.crt \
                && security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db /tmp/caddy-root.crt \
                && rm /tmp/caddy-root.crt
            ;;
        *)
            docker "$@" caddy
            ;;
    esac
}
```

2. Once per machine: `caddy create`, then `caddy trust` to trust the root certificate. Any other command (`caddy start`, `caddy stop`, `caddy logs`) is proxied over to the docker container. You only need to start it once per machine, not per-project.
3. Merge this repo's `compose.yaml` example into your project's compose file and **delete the `ports` mappings** — the proxy replaces them. `APP_URL`, `SESSION_DOMAIN` and `VITE_DEV_SERVER_URL` are injected from the project folder name; container env wins over `.env`, so there's nothing to set.
4. Point Vite at the injected URL in `vite.config.js` — without it the `hot` file defaults to `http://localhost:5173`, which is no longer published:

```js
server: { origin: process.env.VITE_DEV_SERVER_URL },
```

5. `sail up -d` — then open `https://<folder>.localhost`. 🎉
6. Multiple subdomains support: add them to the `caddy` label separated by `', '` (Caddy rejects a comma without space) and point the compose `APP_URL` line at the canonical one.
7. Other HTTP services (Mailpit, MinIO/RustFS console, …) get plain `caddy` labels on their own service, with the hostname prefixed by the service name — e.g. on the mailpit service: `caddy: 'mailpit.${COMPOSE_PROJECT_NAME}.localhost'` + `caddy.reverse_proxy: '{{upstreams 8025}}'`. The `caddy_1`/`caddy_2` index is per-container — only needed when one service serves multiple domains, like the app container's Vite group.
   - **Object storage (MinIO, RustFS, …):** proxying only the console UI is not enough for browser-to-bucket uploads (presigned PUT/POST, multipart, etc.). Those hit the S3 API port (typically `9000`), not the console (`9001`). Add a second label group for the API — e.g. `caddy_1: 'minio.${COMPOSE_PROJECT_NAME}.localhost'` + `caddy_1.reverse_proxy: '{{upstreams 9000}}'` alongside the console on `caddy` / `9001` — and point the app's public disk URL / `AWS_ENDPOINT` (or equivalent) at that API hostname. Same split applies to RustFS. Container-to-container traffic can keep using the project-network alias; only the browser needs the published API host.
   - **DNS collision caveat:** joining the shared `caddy` network auto-registers the bare service name (`mailpit`) as a DNS alias on it — for every project that does this. Containers attached to both their project network and `caddy` (like the app) then resolve `mailpit` to multiple IPs round-robin, silently delivering half the mail to another project's Mailpit (SMTP returns 250 either way, so nothing logs). Fix: declare a manual alias on the project network only, and point the app at that alias — never at the bare service name:

     ```yaml
     mailpit:
         networks:
             sail:
                 aliases:
                     - mailpit.internal
             caddy:   # labels only — never declare the alias here

     laravel.test:
         environment:
             MAIL_HOST: 'mailpit.internal'   # container env wins over .env — .env stays stock
     ```

     The alias must be a *different* name: the bare service name is auto-registered on every joined network with no opt-out ([docker/compose#8223](https://github.com/docker/compose/issues/8223)), so re-declaring `mailpit` as a manual alias changes nothing. Manual aliases exist only where declared, and each project/worktree has its own `sail` network, so the alias always resolves to exactly one container. Delete mailpit's `ports` (`1025`/`8025`) too: SMTP is container-to-container and the UI goes through the proxy — this also lets parallel worktree stacks run simultaneously.
8. This is compatible with worktrees in order to quickly launch separate clone environments

### Editor Files

The `editor/` folder contains starter versions of `.dockerignore`, `.gitignore`, and `.gitattributes`. These are **not used by this repository itself** — they are provided as a starting point for your project. Copy them into your project root and tweak them to fit your needs.

### Local Packages

If you maintain local Composer packages committed in the same repository, place them inside a `packages/` folder at the root of your project. The Docker build already accounts for this.

### Compose & Convox

Both `compose.yaml` and `convox.yml` are **minimal examples** meant as a starting point. They are not meant to be used as-is — review them, adjust values, and extend them to match your project's requirements.

**Important:** The `compose.yaml` in this repository contains **only** the `laravel.test` service override — it is not a standalone Compose file. You are expected to merge its contents into your project's existing `compose.yaml` (the one generated by Laravel Sail that already defines services like MySQL, Redis, etc.). Do not copy it as-is or add other services to it here.

The two Docker Compose settings you want to configure are:


| Setting             | Possible Values                             |
| ------------------- | ------------------------------------------- |
| `build.target`      | `development`, `production`                 |
| `build.args.ENGINE` | `fpm`, `swoole`, `roadrunner`, `frankenphp` |

> **Important:** If you use an Octane engine (roadrunner, swoole, frankenphp), make sure you follow the [Octane installation instructions](https://laravel.com/framework/docs/master/octane#installation). In particular, verify that `config/octane.php` sets `'server'` to your chosen engine:
>
> ```php
> 'server' => env('OCTANE_SERVER', 'roadrunner'), // change default to match your engine
> ```
>
> If this value doesn't match the engine used by the Docker image, running `php artisan` commands inside the container can trigger unexpected behavior (e.g. downloading the wrong binary or port conflicts).

> **Which engine should I use?**
>
> - **Development** — I recommend `fpm` unless you specifically want to mirror your production Octane setup or need Octane features locally. Even with the `--watch` flag, Octane has a noticeable reload delay every time you save a file.
> - **Production** — If you don't have a strong preference, go with `roadrunner`. It's the most stable and reliable Octane driver in my experience — mature, predictable under load, and with fewer surprises than the alternatives. FrankenPHP has a few rough edges and may not be mature enough for every workload yet (see the [FrankenPHP section](#frankenphp)).

> **Why not OpenSwoole?**
>
> There were enough rough edges that I decided not to support it.

### Redis

The image ships with [igbinary](https://github.com/igbinary/igbinary) and [lz4](https://github.com/lz4/lz4) already installed. Enable them in `config/database.php`. Leave `persistent` on Laravel's env — stock config already reads it:

```php
'redis' => [
    'client' => env('REDIS_CLIENT', 'phpredis'),

    'options' => [
        'cluster'     => env('REDIS_CLUSTER', 'redis'),
        'prefix'      => env('REDIS_PREFIX', Str::slug(env('APP_NAME', 'laravel'), '_') . '_database_'),
        'persistent'  => env('REDIS_PERSISTENT', false),
        'serializer'  => Redis::SERIALIZER_IGBINARY,
        'compression' => Redis::COMPRESSION_LZ4,
    ],
],
```

`compose.yaml` and `convox.yml` set `REDIS_PERSISTENT=true`. Container env wins over `.env`, so a stock app picks this up with no config change, including when `config:cache` runs at container start. Each FPM child or Octane worker reuses one socket per named connection (`default`, `cache`, …) instead of paying a TCP and TLS handshake on every request. The kernel closes that socket when the process exits, so a deploy, a worker restart, and a crash all drop it. ElastiCache Serverless still caps concurrent clients at 65,000, and that cap does not grow with ECPUs, but a web fleet (pods × workers × Laravel's named connections) stays far under it. Skipping the handshake also saves ECPUs, which is what serverless Redis bills.

---

## Environment Variables

The production image exposes the following environment variables:


| Variable     | Build Arg    | Description                                                    |
| ------------ | ------------ | -------------------------------------------------------------- |
| `COMMIT_SHA` | `COMMIT_SHA` | The Git commit SHA used to build the image                     |
| `GIT_TAG`    | `GIT_TAG`    | The Git tag used to build the image. Empty on a branch deploy  |
| `BRANCH`     | `BRANCH`     | The Git branch used to build the image                         |
| `ENGINE`     | `ENGINE`     | The engine to use:`fpm`, `swoole`, `roadrunner`, `frankenphp`  |

Pass them at build time (adjust `ENGINE` to match your chosen engine):

```bash
# Gitlab CI

convox deploy --build-args "COMMIT_SHA=$CI_COMMIT_SHA" --build-args "GIT_TAG=$CI_COMMIT_TAG" --build-args "BRANCH=$CI_COMMIT_REF_NAME" --build-args "ENGINE=swoole"
```

`CI_COMMIT_TAG` is only set when the pipeline itself was triggered by a tag. A deploy from `master` leaves `GIT_TAG` empty, even if some older commit on that branch is tagged. That is what you want: the release should name the code you built, and a branch tip usually has no tag of its own.

Copy [`stubs/config/deployment.php`](stubs/config/deployment.php) to `config/deployment.php` in the app. It turns those variables into one release string: `package@version` when `GIT_TAG` is set (a leading `v` is stripped, so `v1.4.0` becomes `myapp@1.4.0`), and the bare commit SHA otherwise. For Sentry, use `config('deployment.release')`.

`env()` inside a config file is resolved when `config:cache` runs and then baked in, so it works in production. `env()` anywhere else returns `null` once the config is cached, which is why the release is read back through `config()`.

---

## Trusted Proxies

Both the local Caddy proxy and Convox's load balancer terminate TLS and forward the original scheme, host and client IP in `X-Forwarded-*` headers. Laravel ignores them until proxies are trusted. Containers are only ever reachable through the proxy, so we suggest trusting all proxies, locally and in Kubernetes:

```php
// bootstrap/app.php
->withMiddleware(function (Middleware $middleware) {
    $middleware->trustProxies(at: '*');
})
```

On Convox, the real client IP additionally requires PROXY protocol — otherwise `X-Forwarded-For` carries the load balancer's IP:

```bash
# One time command on the Convox rack

convox rack params set proxy_protocol=true -r <rack>
```

---

## Application Safeguards

Infrastructure settings like a fixed `scale.count` only cover the services defined in *this repo's* `convox.yml`, and rolling deploys briefly run old and new Processes side by side. For safety that travels with the application regardless of how it's hosted, enforce the guarantees inside `AppServiceProvider::boot()`.

This section isn't scheduler-specific — it's a home for any cross-cutting, multi-replica safeguard the app should enforce on its own, independent of the infrastructure running it:

```php
<?php

namespace App\Providers;

use Illuminate\Queue\Worker;
use Illuminate\Support\Facades\Schedule;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        Schedule::alwaysOnOneServer();

        Worker::$flushStickyConnections = true;
    }
}
```

On each database connection in `config/database.php` (`mysql`, `pgsql`, …), also read your own writes for the rest of that process:

```php
'sticky' => true,
```

- **`Schedule::alwaysOnOneServer()`** locks every task so only one Process runs it per tick, including the deploy overlap and any later scale-up.
  - `CACHE_STORE` must be shared (`redis` or `database`). `file` and `array` are per container, so every container takes its own lock and runs the task.
  - Maintenance mode and queue/schedule pauses use the same store: `convox.yml` leaves `APP_MAINTENANCE_STORE` empty, which falls back to `CACHE_STORE`.
  - Name every closure (`->name('...')`). Unnamed ones are skipped and run on every server.
- **`'sticky' => true`** sends later reads on that connection to the write host after a write, so the same process sees the row it just wrote. It only changes routing when the connection has a separate read host; with a single host it is a no-op. Octane clears the flag before every HTTP request.
- **`Worker::$flushStickyConnections = true`** (Laravel 13.36+) clears that same flag before every queued job. `queue:work` is one long-lived process, so without the reset a single job that writes sends every later job on that worker to the primary until the process is recycled — a deploy, `--max-jobs`, or a crash. A job that must read a row an earlier job just wrote belongs in a chain or a batch: once more than one worker is running, landing on the same process is not an ordering guarantee. The static property does not exist before 13.36, and assigning it fatals.

---

## Scheduler

Laravel's scheduler needs `php artisan schedule:run` invoked continuously. There are three ways to wire that up in Kubernetes/Convox, from least to most complex:

| Option                                                        | Mechanism                                                                   | Container cost                             | Complexity | Used by this repo |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------- | ---------- | ------------------ |
| **Service running `schedule:work`**                           | One long-lived Process loops in-memory and forks `schedule:run` every minute | One container, boots once                   | Low        | ✅ default          |
| **Timer running `schedule:run`**                               | A Convox Timer (Kubernetes `CronJob`) boots a fresh container every minute  | One container boot per minute (1,440/day)   | Medium     | —                   |
| **One Timer per task, generated from `schedule:list`**         | Each scheduled task becomes its own `CronJob`, bypassing the scheduler entirely | One container boot per task, per occurrence | High       | —                   |

All three are viable. The service is what's configured in this repo's `convox.yml` because it's the cheapest and has the fewest moving parts.

Whichever option you use, schedule jobs, not synchronous work. A task should dispatch onto the queue (`Schedule::job(...)`) and return; the `queue` service runs it. A command that does the work itself holds the scheduler for as long as it runs.

Don't use `runInBackground()`. A timer's `schedule:run` exits immediately and the container takes the background process with it. Under `schedule:work`, a deploy stops the scheduler without waiting for that process.

### Option 1 — Service running `schedule:work` (default)

```yaml
scheduler:
  build:
    manifest: Dockerfile
  command: php artisan schedule:work --whisper
  internal: true
  health:
    disable: true
  termination:
    grace: 45
  resources:
    - db
    - redis
  scale:
    count: 1
    cpu: 120
    memory: 256
```

- `schedule:work` runs in the foreground and spawns `schedule:run` as a child process once a minute — this is also what makes sub-minute schedules (`everySecond()`, `everyTenSeconds()`, …) possible. A Timer-based approach can't go below one minute.
- No `singleton: true`. It stops the old Process before starting the new one, so a minute boundary falling in that gap is skipped for good — the scheduler has no catch-up. The default rolling update starts the new Process first, so both run briefly; `Schedule::alwaysOnOneServer()` (see [Application Safeguards](#application-safeguards)) makes that overlap harmless by letting only one of them run each due task. `scale.count: 1` keeps it at one Process at rest.
- `--whisper` suppresses the "No scheduled commands are ready to run." line that `schedule:run` otherwise logs every single minute — most ticks have nothing due, and that line adds no value to a log aggregator.
- `schedule:work` also accepts `--run-output-file=<path>`, which redirects `schedule:run`'s output to a file instead of stdout. **Don't use it here** — this setup keeps all process output on stdout/stderr so container logs stay the single source of truth (see `LOG_CHANNEL=stderr`); writing to a file inside an ephemeral container just makes that output unreachable.
- Sized smaller than the `queue` service: it only ever runs short-lived `schedule:run` children, never a persistent job-processing loop.

### Option 2 — Timer running `schedule:run`

```yaml
timers:
  scheduler:
    command: php artisan schedule:run
    schedule: "* * * * *"
    service: app
    concurrency: Forbid
```

- Convox v3 timers map to Kubernetes `CronJob`s and support `concurrency: Allow | Forbid | Replace`. `Forbid` is the one worth setting here — it stops a new `schedule:run` invocation from starting while the previous minute's is still finishing.
- No long-lived scheduler process exists, so this only makes sense if every scheduled task finishes well within a minute, and sub-minute schedules can't be used at all.
- Every tick pays a full container boot (framework bootstrap, cached config loading, etc.), 1,440 times a day, for a command that most of the time does nothing. Reasonable if the platform/billing model favors short-lived Jobs over an always-on Process, but strictly more expensive than Option 1 for the same outcome.

### Option 3 — One Timer per task, generated from `schedule:list`

`php artisan schedule:list --json` dumps every defined task with its resolved cron expression. That output can drive a build-time script that emits one Convox `timers:` entry per task, each invoking its command directly on its own schedule — bypassing `schedule:run`/`schedule:work` (and Laravel's own due-check) entirely.

This is the most complex option and only worth it for very large or heterogeneous schedules:

- Every task gets its own `CronJob`, independently visible (`kubectl get cronjobs`) and independently sized/resourced.
- The source of truth for cron expressions moves outside `routes/console.php` into generated `convox.yml` entries, which have to be regenerated and redeployed whenever the schedule changes — a schedule change becomes a deploy, not just code picked up by the next `schedule:work` tick.
- `onOneServer()` / `alwaysOnOneServer()` lose most of their purpose, since each task already gets one `Job` per schedule tick from Kubernetes — but `withoutOverlapping()` is still relevant for tasks whose own duration can exceed their interval.

Not implemented in this repo — documented here as the natural next step if Option 1 ever becomes a bottleneck.

---

## Container Startup

`scripts/start-container.sh` is the entrypoint for every image. It installs dependencies in local only, runs migrations when `RUN_MIGRATIONS=true`, then warms the caches in production before handing off to the image's `CMD`. The Dockerfiles default `RUN_MIGRATIONS=true`, preserving ordinary Docker and Sail behavior. The Convox example makes the policy explicit: `app` enables it; `queue` and `scheduler` set it to `false`.

### Migrations

```sh
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    if php artisan migrate:status >/dev/null; then
        php artisan migrate --force --isolated=1
    else
        php artisan migrate --force
    fi
fi
```

`--isolated` takes a cache lock so concurrently booting containers don't migrate at the same time. The container that loses the lock **skips** the migration and exits with the value you pass. `1` makes the entrypoint fail and the orchestrator restart it, so the retry is the wait. A bare `--isolated` exits `0`, and that container would boot against a database still mid-migration.

`1` is also what a failed migration returns. Both cases should stop the boot, so there is nothing to tell apart, and there is no fallback to an unlocked `migrate` on that path — retrying a genuinely failed migration without the lock is worse than a crash loop.

The `migrate:status` check exists for one narrow case: a brand-new database has no `migrations` table yet, so there is also nothing for `--isolated` to lock against — taking the lock itself fails, regardless of cache store. `migrate:status` exits non-zero exactly when that table is missing, so the entrypoint falls back to a plain `migrate --force` only then, bootstrapping the schema (including the `cache`/`cache_locks` tables, if `CACHE_STORE=database`) in one unlocked pass. Every later boot finds the table and takes the isolated path. This keeps first boot zero-config for local dev and fresh deploys alike, with one caveat: if the very first deploy itself starts with more than one replica, both can see the same missing table and race on the same bootstrap migration — deploy the first release with a single replica.

Running migrations at container start keeps this repo dependency-free, but every booting app container attempts them. For stricter control, run them once per release from CI (`convox build` → `convox run app php artisan migrate --force` → `convox releases promote`) and set `RUN_MIGRATIONS=false` for every service.

A normal deploy migrates while the previous release is still serving. That overlap is fine when the migration only adds something the old code ignores. When the migration rewrites data the old code is still reading or writing, take the application down first and bring it back once the new release is the one serving:

```bash
convox run app php artisan down --render="errors::503"
# deploy the release that contains the migration
convox run app php artisan up
```

`convox.yml` sets `APP_MAINTENANCE_DRIVER=cache` and leaves `APP_MAINTENANCE_STORE` empty, so the flag lives on `CACHE_STORE`. One `down` and one `up` cover every app, queue, and scheduler container.

`--render` renders the view once, at the moment you run `down`, and stores the HTML. Later requests return that HTML. The view is not rendered again while the migration is changing the schema, which is when rendering it fails and the visitor gets a broken error page instead of the maintenance page. Pass `errors::503` — `resources/views/errors/503.blade.php` when that file exists, Laravel's own 503 view otherwise — or the view you designed for maintenance mode.

Run `down` on the release that is currently serving, before the migration starts, so the view is rendered by code that still matches the database. Run `up` only after the new release is handling traffic.

While the flag is up, `queue:work` stops taking new jobs (a job already running finishes) and the scheduler skips tasks that are not marked `evenInMaintenanceMode()`. `/up` stays reachable, so the probes in `convox.yml` do not replace pods for being down.

### Caches

`php artisan optimize` runs in production for every role. It writes `bootstrap/cache/*.php` on the container's **own** filesystem — it has nothing to do with `CACHE_STORE`, so there is no shared state to inherit and every app, queue, and scheduler container has to run it for itself.

`optimize:clear` is deliberately **not** run first. It includes `cache:clear`, and for the Redis store that is a `FLUSHDB` on the cache connection, not a prefix-aware delete — every booting pod would wipe the whole logical Redis database mid-rollout. Freshly written caches don't need clearing anyway, since the container starts with an empty `bootstrap/cache`.

> Stock Laravel keeps cache on the `cache` Redis connection (`REDIS_CACHE_DB=1`) and locks on `default` (`REDIS_DB=0`), which limits the blast radius. ElastiCache with cluster mode enabled only has database `0` (Valkey 9 can enable more, but only if `cluster-databases` was set when the cluster was created). On that setup a `cache:clear` also takes sessions, queued jobs and locks.

---

## Timeouts & Shutdown

Every time limit here sits inside a longer one. When an inner limit is longer than the layer around it, the outer layer cuts the work off first: the user gets a generic gateway error instead of Laravel's, a deploy kills a request mid-way, or a job runs twice. When you change one value, re-check its neighbours.

### Web Requests

| Layer   | Setting                                              | Value |
| ------- | ---------------------------------------------------- | ----- |
| PHP     | `max_execution_time` (`confs/php.ini`)               | 60    |
| php-fpm | `request_terminate_timeout` (`confs/php-fpm.conf`)   | 60s   |
| Octane  | `max_execution_time` (your app's `config/octane.php`) | 30    |
| nginx   | `fastcgi_read_timeout` (nginx default)               | 60s   |
| Convox  | `timeout` on the `app` service                       | 60    |

On Linux, `max_execution_time` only counts time spent running PHP code. A request waiting on the database or an HTTP call can outlive it, so `request_terminate_timeout` is the wall-clock limit that actually ends a php-fpm request. The Octane engines use Octane's own `max_execution_time` instead; nginx's `proxy_read_timeout` in front of them is 3600 to keep WebSockets open, so the Octane setting is the only request limit there.

To allow longer requests, raise these together, then raise the shutdown values below so a deploy still waits for them.

### App Shutdown

On a deploy or scale-down, Kubernetes runs the `preStop` hook, then sends SIGTERM, then sends SIGKILL once `termination.grace` has passed. The grace period counts from the start, `preStop` included.

```yaml
app:
  lifecycle:
    preStop: "sleep 5"
  termination:
    grace: 75
```

1. **`preStop: sleep 5`** — the pod keeps serving while the ingress stops routing to it. Without it, requests that arrive in the first seconds after SIGTERM hit a closed port and get a 502. Five seconds covers the ingress catching up in a normal cluster.
2. **SIGTERM** — supervisord stops nginx first, then the app server (programs stop in reverse `priority` order). nginx and php-fpm get `QUIT` (`stopsignal=QUIT`): they stop accepting connections and finish the requests already running. `TERM`, supervisord's default, makes both drop them. Octane keeps `TERM`, which it handles by draining its own server. `stopwaitsecs=65` is the most supervisord waits per program before SIGKILL: longer than the 60-second request limit, so a request is ended by its own limit (with Laravel's error), never by the shutdown.
3. **`termination.grace: 75`** — covers the 5-second sleep plus the 65 seconds supervisord may wait. nginx only finishes once its proxied requests do, so the app server behind it has nothing left to drain and stops at once.

The rule: request limit < `stopwaitsecs`, and `preStop` + `stopwaitsecs` < `termination.grace`.

**Deploy time.** The grace period is a ceiling, not a wait. An idle pod is gone about 5 seconds after the deploy starts replacing it (the sleep, then an immediate stop), and a pod in the middle of a request waits only for that request. With Convox's default `deployment.maximum: 200`, a full set of new pods starts beside the old ones and the old ones stop together, so on a normal deploy the shutdown adds those ~5 seconds once, not per pod. Only a request running close to the 60-second limit stretches it toward 75. Lower `stopwaitsecs`, `grace` and the request limits together if that ceiling is too high for you.

**FrankenPHP** has no supervisord. On SIGTERM, Octane asks Caddy to stop and exits right away, which kills requests still running ([laravel/octane#970](https://github.com/laravel/octane/issues/970)). The `preStop` sleep is what protects it: anything shorter than the sleep finishes before SIGTERM arrives. Requests longer than 5 seconds that are running when the pod stops are dropped; raise the sleep only if those matter, since it adds to every deploy.

### Queue Workers

| Setting             | Where                                                | Value |
| ------------------- | ---------------------------------------------------- | ----- |
| `--timeout`         | `queue` command in `convox.yml`                      | 60    |
| `termination.grace` | `queue` service in `convox.yml`                      | 70    |
| `retry_after`       | `config/queue.php` (Laravel default)                 | 90    |
| `--max-time`        | `queue` command in `convox.yml`                      | 86400 |
| `--max-jobs`        | `queue` command in `convox.yml`                      | 1000  |

On SIGTERM, `queue:work` finishes the job it is running and then exits. These are Laravel's own defaults (`--timeout` 60, `retry_after` 90), so only the grace period needs setting.

- `termination.grace` must be longer than `--timeout`. Otherwise Kubernetes kills a job that Laravel would still let finish.
- `retry_after` is how long the queue waits before handing a reserved job to another worker. It must also be longer than `--timeout`, or a slow job runs twice at the same time. Raise it with `DB_QUEUE_RETRY_AFTER` / `REDIS_QUEUE_RETRY_AFTER` if you raise `--timeout`. On SQS the queue's visibility timeout plays this role and is set on the queue itself.
- A job's own `$timeout` property overrides `--timeout`; keep it inside the same limits.

Like the app, the grace period is a ceiling: an idle worker exits immediately, and a deploy waits at most for the job in progress, 60 seconds in the worst case.

`--max-time=86400` and `--max-jobs=1000` recycle the process. Neither one interrupts the job already running. After that job finishes, or after an idle sleep, the worker checks the clock and the job count. Past either limit it returns exit code 0. `start-container.sh` `exec`s the command, so that process is PID 1: the container stops, and Convox starts a new one, which runs `optimize` again and then `queue:work`. Jobs waiting in the broker stay there.

That restart is the useful part. `queue:work` keeps the framework loaded for the life of the process, and PHP does not reliably hand memory back to the OS. `--max-jobs` covers a busy worker. `--max-time` covers a quiet one that would otherwise live until the next deploy. A day is long enough that the boot gap is rare. Replicas from the same deploy share a start time, so they reach the limit together; the sample runs one, so that is a single gap of one container boot.

`--timeout` is the other clock: an alarm around the current job. On Laravel 13 that alarm kills the worker (exit 1) after marking the job failed, and Convox restarts the container the same way. The 70-second grace period and the 90-second `retry_after` sit outside that 60 seconds, so a deploy can still finish the job and a second worker does not start it early.

The scheduler keeps `grace: 45`: its tasks should dispatch jobs and return (see [Scheduler](#scheduler)), so it never has long work to finish.

**Jobs longer than the grace period** should stop early instead of raising the grace period to match. Implement `Interruptible` (Laravel 13.7+): when the worker receives SIGTERM it calls `interrupted()` on the running job. The call is cooperative: the job sets a flag, its loop checks it, and it releases itself back onto the queue so the next worker continues from the saved progress.

```php
use Illuminate\Contracts\Queue\Interruptible;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;

class ImportUsers implements ShouldQueue, Interruptible
{
    use Queueable;

    private bool $interrupted = false;

    public function handle(): void
    {
        foreach ($this->pendingRows() as $row) {
            if ($this->interrupted) {
                $this->release();

                return;
            }

            $this->import($row);
        }
    }

    public function interrupted(int $signal): void
    {
        $this->interrupted = true;
    }
}
```

A release counts as an attempt against `--tries`. `queue:restart` never calls `interrupted()` (it lets the current job finish), and `queue:work --once` installs no signal handlers at all; on Convox every deploy sends SIGTERM to the worker daemon, which is the case this covers.

---

## Things to Review

Before deploying, make sure to review these configuration values and adjust them for your project:

**Upload & body size limits** — These three values work together and should be kept in sync. If a user uploads a file larger than any of these, the request will be rejected at that layer.


| File                     | Setting                | Default | Notes                                                                                                                   |
| ------------------------ | ---------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------- |
| `confs/php.ini`          | `upload_max_filesize`  | `50M`   | Max size of a single uploaded file                                                                                      |
| `confs/php.ini`          | `post_max_size`        | `60M`   | Max size of the entire POST body (should be slightly larger than`upload_max_filesize` to account for other form fields) |
| `confs/nginx/nginx.conf` | `client_max_body_size` | `50m`   | Nginx will reject requests larger than this before PHP even sees them                                                   |

**Content-Security-Policy** — In `confs/nginx/server-common.conf`, there is a commented-out `Content-Security-Policy` header. If your application uses iframes or is embedded by other domains, uncomment it and replace `*.allowed-domain.com` with your actual allowed origins:

```nginx
# Uncomment to allow framing from subdomains (and optionally remove X-Frame-Options):
# add_header Content-Security-Policy "frame-ancestors 'self' *.allowed-domain.com" always;
```

This file is included by both the PHP-FPM and Octane Nginx configs (`confs/nginx/php-fpm.conf` and `confs/nginx/octane.conf`), so the change applies everywhere.

---

## Swoole

I recommend extending the octane command to set up a desired amount of workers.
Auto mode will base itself on the machine's CPU availability, colliding with whatever sizing you prepared for the container.

Issues of timeouts may appear especially on small machines due to extreme CPU splitting

---

## FrankenPHP

[FrankenPHP](https://frankenphp.dev/) has been a bit of a special child in this setup. It works, but there are things worth knowing before you adopt it.

**TL;DR** — FrankenPHP is in an awkward spot for the time being. Before adopting, make sure to read the [known issues](https://frankenphp.dev/docs/known-issues/) page.

### Key Differences

1. **Official image instead of Nginx proxy** — Unlike the other engines, FrankenPHP runs from the [official FrankenPHP Docker image](https://hub.docker.com/r/dunglas/frankenphp) instead of being proxied by Nginx.
2. **Port mapping** — Octane is exposed directly on port `8000`. I remapped it to `8080` for compatibility with the rest of the setup, but this breaks the silent convention that Octane runs on `8000`.
3. **No Alpine** — Alpine Linux images can't be used because [musl libc is slower with PHP ZTS mode](https://frankenphp.dev/docs/performance/#dont-use-musl). This only affects FrankenPHP because it requires ZTS (thread-safe) PHP. The other engines (FPM, RoadRunner, Swoole) run NTS (non-thread-safe) PHP, where musl's threading overhead is irrelevant.
4. **No supervisord** — Since FrankenPHP is exposed directly, there is no nginx and no process supervisor in the image. Development works exactly like the other engines minus nginx: `php artisan dev` is the container command and runs Octane plus the sidecars.
5. **Node.js from the official image** — Debian 13 (trixie) apt pins Node at 20.x, but `@laravel/multiplex` (which runs `php artisan dev`) requires ≥ 22.13. The image copies Node 24 from `node:24-trixie-slim` instead of installing the apt package.

### Quirks

- **Composer + `php` binary** — There's an awkward issue where PHP is not properly referenced by Composer inside the FrankenPHP image. See: [Composer scripts referencing `php`](https://frankenphp.dev/docs/known-issues/#composer-scripts-referencing-php). The image installs that wrapper as `php`, with one change from the docs: it `exec`s FrankenPHP. The container command runs through it (`php artisan ...`), so without `exec` bash would be PID 1, ignore SIGTERM, and every stop would wait for the SIGKILL.
- **`octane:frankenphp` vs `octane:serve`** — The FrankenPHP docs suggest running `php artisan octane:frankenphp` directly instead of `php artisan octane:serve --server=frankenphp`. While functionally identical, the former does not load configuration from the standard `config/octane.php` file.
- **Double web server debate** — [Laravel Forge](https://forge.laravel.com/) appears to run FrankenPHP behind Nginx, similar to other Octane providers. Using a double web server can mask bugs, so this project uses the [official Docker approach recommended in the Laravel docs](https://laravel.com/framework/docs/master/octane#frankenphp-via-docker) instead. See also [this Octane issue](https://github.com/laravel/octane/issues/889) confirming Forge's Nginx setup.
- **Tinker does not work** — `php artisan tinker` cannot run inside the FrankenPHP image. FrankenPHP embeds PHP as a library (ZTS build) and replaces the standard `php` binary with its own wrapper, which is incompatible with PsySH's interactive REPL.

### Compose Volumes

The Caddy volumes below are **not** set by default, but they are needed in a single-server environment for HTTPS handling and other Caddy features. They persist the FrankenPHP container's **own** Caddy state (certs, ACME account) — unrelated to the local dev proxy, whose `caddy_data` volume the `caddy create` command already sets up. On Convox the load balancer terminates TLS, so they're unnecessary there.

```yaml
- caddy_data:/data
- caddy_config:/config
```

### What's Not Included


| Feature                                                                                     | Reason                                                                      |
| ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| [Thread pool splitting](https://frankenphp.dev/docs/performance/#splitting-the-thread-pool) | Not configured — worth exploring for high-traffic workloads                |
| [X-Sendfile / large file serving](https://frankenphp.dev/docs/x-sendfile/)                  | Not needed in a Kubernetes setup where files are served from object storage |

> Most performance-related configuration is handled by the Octane server itself. See: [FrankenPHP Performance docs](https://frankenphp.dev/docs/performance/).

---

## TODO

- **PIE stays out of the Dockerfiles** (on hold). [PIE 1.5](https://thephp.foundation/blog/2026/10/07/pie-1-5-released/) (October 2026) installs several third-party extensions in one command and publishes a build-time binary image (`ghcr.io/php/pie:bin`). The old PHP 8.5 compile gap is also gone: `phpredis` 6.3, `swoole/swoole`, igbinary, and xdebug all publish PIE packages for 8.5. PIE still only installs Packagist `php-ext` packages. Bundled extensions (`ctype`, `curl`, `gd`, `intl`, `mbstring`, `pdo_mysql`, `zip`, FPM, and the rest of the Laravel set) stay on Alpine `apk` or FrankenPHP's `install-php-extensions`. Handing redis, igbinary, swoole, and xdebug to PIE beside that leaves two installers for four extensions, and on Alpine it throws away the prebuilt packages. Revisit only when one installer covers the whole set. `install-php-extensions` has not switched over ([mlocati/docker-php-extension-installer#1125](https://github.com/mlocati/docker-php-extension-installer/issues/1125) is still open).
- **Composer dependency cooldown** (on hold until Composer 2.11). The setting is `config.policy.cooldown.period` (for example `"7 days"`). The clock is Packagist's registry-owned `published-time`, which package authors cannot backdate; that field has been live since [packagist#1765](https://github.com/composer/packagist/pull/1765) (June 2026). The Composer side merged in [composer#12692](https://github.com/composer/composer/pull/12692) on 1 October 2026 and ships in 2.11, which is not released. Stable is 2.10.3 (27 August 2026). These images install Composer from getcomposer.org, so they get stable, and the key is not available there yet. A plugin that reads the author-controlled `time` field is the bypass `published-time` exists to close, so it is not a stand-in.
- Stress test to find optimal/reference values in `convox.yml` (Kubernetes) and PHP-FPM/worker pool configurations.

---

## Additional Notes

- **Process supervision & restarts** — In the nginx-based images, supervisord manages each process with `autorestart=true`, `startsecs=1` and `startretries=10`. A process that crashes after running normally is restarted immediately and indefinitely. A process that keeps dying within a second of starting is retried 10 times with growing delays (1s, 2s, 3s…, about 55s total) and then left in `FATAL`. `stopasgroup` (nginx, php-fpm, dev) and `killasgroup` (all) send the stop and kill signals to the whole process group, so workers die with their master instead of keeping the socket or port. Octane gets `killasgroup` only: it stops its own workers on `TERM`, and a group-wide `TERM` would kill them mid-request. Stop signals and wait times are covered in [Timeouts & Shutdown](#app-shutdown).

  Those two settings work together and both are needed: `startretries` only counts crashes that happen inside `startsecs`, so the old `startretries=0` sent a process to `FATAL` on its first fast crash — a brief database outage could kill a process permanently while the container stayed up and the orchestrator saw nothing wrong.

  Reaching `FATAL` is intentional rather than a dead end. In production the `liveness` probe in `convox.yml` stops getting a healthy `/up` and Kubernetes replaces the pod, applying its own exponential backoff. Locally, `restart: unless-stopped` in `compose.yaml` covers the container exiting (which is how FrankenPHP fails, since it has no supervisord); a `FATAL` program under supervisord stays down until you restart the container, with the reason in the logs.

- **OPcache & FPM in production** — When running FPM in production, OPcache is enabled. This means that code changes made at runtime (e.g. via `docker exec`, even though you really should not do this) will not be reflected because PHP serves the cached opcodes. To force a full reload, gracefully restart the FPM master process:

```bash
kill -USR2 $(pgrep -o php-fpm)
```

This kills all FPM workers and respawns them with a clean OPcache state.

- [Laragear Preload](https://github.com/Laragear/Preload) did not seem worth the complexity in a Kubernetes environment.

---

## Special Thanks & Inspirations

- [Laravel Sail](https://github.com/laravel/sail)
- [TrafeX/docker-php-nginx](https://github.com/TrafeX/docker-php-nginx)
- [dunglas/symfony-docker](https://github.com/dunglas/symfony-docker)
