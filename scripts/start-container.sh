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
        
        echo "building assets..."
        npm run build
    fi
fi

# --isolated uses cache locks; fall back to non-isolated if the cache table doesn't exist yet
echo "running migrations..."
php artisan migrate --force --isolated 2>/dev/null || php artisan migrate --force

# Production environment
if [ "${APP_ENV:-production}" = "production" ]; then
    echo "clearing cache..."
    php artisan optimize:clear

    echo "optimizing..."
    php artisan optimize
    php artisan filament:optimize
fi

echo ">> Startup complete. Launching application..."
exec "$@"