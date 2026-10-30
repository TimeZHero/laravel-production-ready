#!/bin/sh
set -eu

# Development environment
if [ "${APP_ENV:-production}" = "local" ]; then
    if [ ! -f "vendor/autoload.php" ]; then
        composer install --no-interaction
    fi

    if [ ! -d "node_modules" ]; then
        npm install
    fi

    if [ "${OCTANE_SERVER:-}" = "roadrunner" ] && [ -f "vendor/bin/rr" ] && [ ! -f "rr" ]; then
        ./vendor/bin/rr get-binary --no-interaction --no-config
        chmod +x rr
    fi
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    if php artisan migrate:status >/dev/null; then
        php artisan migrate --force --isolated=1
    else
        php artisan migrate --force
    fi
fi

# Production environment
if [ "${APP_ENV:-production}" = "production" ]; then
    php artisan optimize --quiet
    # Uncomment if you use Filament (https://filamentphp.com)
    # php artisan filament:optimize --quiet
fi

php artisan about || true

exec "$@"