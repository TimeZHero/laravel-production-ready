#!/bin/sh
set -eu

echo ">> Container startup"

# Development environment
if [ "${APP_ENV:-production}" = "local" ]; then
    if [ ! -f "vendor/autoload.php" ]; then
        echo "vendor not found, running composer install..."
        composer install --no-interaction
    fi

    if [ ! -d "node_modules" ]; then
        echo "node_modules not found, running npm install..."
        npm install
    fi

    if [ "${OCTANE_SERVER:-}" = "roadrunner" ] && [ -f "vendor/bin/rr" ] && [ ! -f "rr" ]; then
        echo "downloading RoadRunner binary..."
        ./vendor/bin/rr get-binary --no-interaction --no-config --quiet
        chmod +x rr
    fi
fi

echo "running migrations..."
if php artisan migrate:status >/dev/null; then
    php artisan migrate --force --isolated=1
else
    # No migrations table yet: nothing exists to lock against, isolation is moot.
    php artisan migrate --force
fi

# Production environment
if [ "${APP_ENV:-production}" = "production" ]; then
    echo "optimizing..."
    php artisan optimize
    # Uncomment if you use Filament (https://filamentphp.com)
    # php artisan filament:optimize
fi

echo ">> Startup complete. Launching application..."
exec "$@"