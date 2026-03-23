# Production-Ready Docker Images for Laravel

Stateless, performant Docker images designed for Kubernetes — deployed via [Convox](https://convox.com/).

Compatible with [Laravel Sail](https://github.com/laravel/sail) for local development.

---

## Table of Contents

- [Local Setup](#local-setup)
- [Usage](#usage)
  - [Editor Files](#editor-files)
  - [Local Packages](#local-packages)
  - [Docker Compose & Convox](#docker-compose--convox)
  - [Redis](#redis)
  - [Vite](#vite)
- [Environment Variables](#environment-variables)
- [Things to Review](#things-to-review)
- [FrankenPHP](#frankenphp)
  - [Key Differences](#key-differences)
  - [Quirks](#quirks)
  - [Docker Compose Volumes](#docker-compose-volumes)
  - [What's Not Included](#whats-not-included)
- [TODO](#todo)
- [Additional Notes](#additional-notes)
- [Special Thanks & Inspirations](#special-thanks--inspirations)

---

## Local Setup

1. Install [Laravel Sail](https://laravel.com/docs/12.x/sail) in your project and publish the assets.

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

---

## Usage

This repository is **not interactive**. All operations are done through copy-paste and by reviewing configuration files for your specific use case.

Copy the `Dockerfile` (or `Dockerfile.frankenphp`) into your project and adjust as needed.

### Editor Files

The `editor/` folder contains starter versions of `.dockerignore`, `.gitignore`, and `.gitattributes`. These are **not used by this repository itself** — they are provided as a starting point for your project. Copy them into your project root and tweak them to fit your needs.

### Local Packages

If you maintain local Composer packages committed in the same repository, place them inside a `packages/` folder at the root of your project. The Docker build already accounts for this.

### Docker Compose & Convox

Both `docker-compose.yml` and `convox.yml` are **minimal examples** meant as a starting point. They are not meant to be used as-is — review them, adjust values, and extend them to match your project's requirements.

The two Docker Compose settings you want to configure are:

| Setting              | Possible Values                              |
|----------------------|----------------------------------------------|
| `build.target`       | `development`, `production`                  |
| `build.args.ENGINE`  | `fpm`, `swoole`, `roadrunner`, `frankenphp`  |

> **Which engine should I use?**
>
> - **Development** — I recommend `fpm` unless you specifically want to mirror your production Octane setup or need Octane features locally. Even with the `--watch` flag, Octane has a noticeable reload delay every time you save a file.
> - **Production** — Any of them works. FrankenPHP has a few rough edges and may not be mature enough for every workload yet (see the [FrankenPHP section](#frankenphp)).

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

### Vite

The program to run `npm run dev` is **not enabled by default** because of the performance overhead it introduces. Depending on your project, you may not want it running all the time.

To enable it, copy the unused Vite supervisor program from the Dockerfile's development stage into your active supervisord configs — or simply run `npm run dev` manually whenever you need it.

---

## Environment Variables

The production image exposes two environment variables:

| Variable | Build Arg | Description |
|---|---|---|
| `COMMIT_SHA` | `COMMIT_SHA` | The Git commit SHA used to build the image |
| `BRANCH` | `BRANCH` | The Git branch used to build the image |

Pass them at build time:

```bash
convox deploy --build-args "COMMIT_SHA=$CI_COMMIT_SHA" --build-args "BRANCH=$CI_COMMIT_REF_NAME"
```

At runtime they are available as regular environment variables, which makes them useful for Sentry releases:

```php
'release' => env('COMMIT_SHA'),
```

---

## Things to Review

Before deploying, make sure to review these configuration values and adjust them for your project:

**Upload & body size limits** — These three values work together and should be kept in sync. If a user uploads a file larger than any of these, the request will be rejected at that layer.

| File | Setting | Default | Notes |
|---|---|---|---|
| `confs/php.ini` | `upload_max_filesize` | `50M` | Max size of a single uploaded file |
| `confs/php.ini` | `post_max_size` | `60M` | Max size of the entire POST body (should be slightly larger than `upload_max_filesize` to account for other form fields) |
| `confs/nginx/nginx.conf` | `client_max_body_size` | `50m` | Nginx will reject requests larger than this before PHP even sees them |

**Content-Security-Policy** — In `confs/nginx/server-common.conf`, there is a commented-out `Content-Security-Policy` header. If your application uses iframes or is embedded by other domains, uncomment it and replace `*.allowed-domain.com` with your actual allowed origins:

```nginx
# Uncomment to allow framing from subdomains (and optionally remove X-Frame-Options):
# add_header Content-Security-Policy "frame-ancestors 'self' *.allowed-domain.com" always;
```

This file is included by both the PHP-FPM and Octane Nginx configs (`confs/nginx/php-fpm.conf` and `confs/nginx/octane.conf`), so the change applies everywhere.

---

## FrankenPHP

[FrankenPHP](https://frankenphp.dev/) has been a bit of a special child in this setup. It works, but there are things worth knowing before you adopt it.

**TL;DR** — FrankenPHP is in an awkward spot for the time being. Before adopting, make sure to read the [known issues](https://frankenphp.dev/docs/known-issues/) page.

### Key Differences

1. **Official image instead of Nginx proxy** — Unlike the other engines, FrankenPHP runs from the [official FrankenPHP Docker image](https://hub.docker.com/r/dunglas/frankenphp) instead of being proxied by Nginx.
2. **Port mapping** — Octane is exposed directly on port `8000`. I remapped it to `8080` for compatibility with the rest of the setup, but this breaks the silent convention that Octane runs on `8000`.
3. **No Alpine** — Alpine Linux images can't be used because [musl libc is slower with PHP ZTS mode](https://frankenphp.dev/docs/performance/#dont-use-musl).
4. **No sidecar processes in development** — Since FrankenPHP is exposed directly, the additional dev commands (queue worker, scheduler) are not run alongside it the way they are for the other engines.

### Quirks

- **Composer + `php` binary** — There's an awkward issue where PHP is not properly referenced by Composer inside the FrankenPHP image. See: [Composer scripts referencing `php`](https://frankenphp.dev/docs/known-issues/#composer-scripts-referencing-php).
- **`octane:frankenphp` vs `octane:serve`** — The FrankenPHP docs suggest running `php artisan octane:frankenphp` directly instead of `php artisan octane:serve --server=frankenphp`. While functionally identical, the former does not load configuration from the standard `config/octane.php` file.
- **Double web server debate** — [Laravel Forge](https://forge.laravel.com/) appears to run FrankenPHP behind Nginx, similar to other Octane providers. Using a double web server can mask bugs, so this project uses the [official Docker approach recommended in the Laravel docs](https://laravel.com/docs/12.x/octane#frankenphp-via-docker) instead. See also [this Octane issue](https://github.com/laravel/octane/issues/889) confirming Forge's Nginx setup.

### Docker Compose Volumes

The Caddy volumes below are **not** set by default, but they are needed in a single-server environment for HTTPS handling and other Caddy features:

```yaml
- caddy_data:/data
- caddy_config:/config
```

### What's Not Included

| Feature | Reason |
|---|---|
| [Thread pool splitting](https://frankenphp.dev/docs/performance/#splitting-the-thread-pool) | Not configured — worth exploring for high-traffic workloads |
| [X-Sendfile / large file serving](https://frankenphp.dev/docs/x-sendfile/) | Not needed in a Kubernetes setup where files are served from object storage |
| Custom Caddyfile | Not included, but can be easily added by editing the `CMD` |
| Additional Caddy modules | None are bundled in this project |

> Most performance-related configuration is handled by the Octane server itself. See: [FrankenPHP Performance docs](https://frankenphp.dev/docs/performance/).

---

## TODO

- [ ] Adopt [Pie](https://github.com/php/pie) (the new PHP extension installer) once the project matures further.
- [ ] Test whether Alpine + musl is only problematic for FrankenPHP or affects other engines too.
- [ ] Stress test to find optimal values in `convox.yml` (Kubernetes) and PHP-FPM/worker pool configurations.

---

## Additional Notes

- [Laragear Preload](https://github.com/Laragear/Preload) did not seem worth the complexity in a Kubernetes environment.

---

## Special Thanks & Inspirations

- [Laravel Sail](https://github.com/laravel/sail)
- [TrafeX/docker-php-nginx](https://github.com/TrafeX/docker-php-nginx)
- [dunglas/symfony-docker](https://github.com/dunglas/symfony-docker)
