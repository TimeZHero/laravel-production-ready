#!/bin/sh
set -eu

# An empty volume mounted over storage/ hides the folders Laravel expects
mkdir -p storage/app/private storage/app/public storage/framework/cache/data \
    storage/framework/sessions storage/framework/testing storage/framework/views storage/logs

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
    pending=0
    php artisan migrate:status --pending=2 || pending=$?
    case "$pending" in
        0)
            # Nothing to migrate: skip the lock, so a stale one cannot block scaling
            ;;
        2)
            # 75 only means another container holds the migration lock: wait here,
            # because a restart would count toward Convox's crashRestartLimit
            until php artisan migrate --force --isolated=75; do
                status=$?
                [ "$status" -eq 75 ] || exit "$status"
                sleep 2
            done
            ;;
        *)
            # No migrations table yet: nothing to lock against
            php artisan migrate --force
            ;;
    esac
fi

# Production environment
if [ "${APP_ENV:-production}" = "production" ]; then
    php artisan optimize --quiet
    # Uncomment if you use Filament (https://filamentphp.com)
    # php artisan filament:optimize --quiet
fi

php artisan about || true

exec "$@"