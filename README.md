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

Create a `DevServiceProvider`, register it in `bootstrap/providers.php`, and register whatever your project needs in `boot()` (`reverb:start`, `horizon:listen`, `stripe listen ...`)

The following configuration is compatible for whatever engine (PHP runtime) you decide to use. Feel free to simplify it if you do not want to support all engines in your code

```php
use Illuminate\Foundation\DevCommands;

if ($this->app->environment('local')) {
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
7. Other HTTP services (Mailpit, MinIO console, …) get plain `caddy` labels on their own service, with the hostname prefixed by the service name — e.g. on the mailpit service: `caddy: 'mailpit.${COMPOSE_PROJECT_NAME}.localhost'` + `caddy.reverse_proxy: '{{upstreams 8025}}'`. The `caddy_1`/`caddy_2` index is per-container — only needed when one service serves multiple domains, like the app container's Vite group.
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

The image ships with [igbinary](https://github.com/igbinary/igbinary) and [lz4](https://github.com/lz4/lz4) already installed. You can enable the most performant serializer and compression in your `config/database.php`:

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

---

## Environment Variables

The production image exposes the following environment variables:


| Variable     | Build Arg    | Description                                                   |
| ------------ | ------------ | ------------------------------------------------------------- |
| `COMMIT_SHA` | `COMMIT_SHA` | The Git commit SHA used to build the image                    |
| `BRANCH`     | `BRANCH`     | The Git branch used to build the image                        |
| `ENGINE`     | `ENGINE`     | The engine to use:`fpm`, `swoole`, `roadrunner`, `frankenphp` |

Pass them at build time (adjust `ENGINE` to match your chosen engine):

```bash
# Gitlab CI

convox deploy --build-args "COMMIT_SHA=$CI_COMMIT_SHA" --build-args "BRANCH=$CI_COMMIT_REF_NAME" --build-args "ENGINE=swoole"
```

At runtime they are available as regular environment variables, which makes them useful for Sentry releases:

```php
'release' => env('COMMIT_SHA'),
```

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

- **Composer + `php` binary** — There's an awkward issue where PHP is not properly referenced by Composer inside the FrankenPHP image. See: [Composer scripts referencing `php`](https://frankenphp.dev/docs/known-issues/#composer-scripts-referencing-php).
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

- Adopt [PIE](https://github.com/php/pie) (the official PHP extension installer, replacing PECL) once upstream extensions release PHP 8.5-compatible versions. As of June 2026, igbinary, phpredis, and swoole do not compile against PHP 8.5 via PIE. Only xdebug works. Alpine `apk` packages and `install-php-extensions` apply patches that PIE does not.
- Stress test to find optimal/reference values in `convox.yml` (Kubernetes) and PHP-FPM/worker pool configurations.

---

## Additional Notes

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
