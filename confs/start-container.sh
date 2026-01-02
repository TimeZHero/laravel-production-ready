#!/bin/sh
set -eu

echo ">> Container startup"

if [ "${APP_ENV:-production}" != "production" ]; then
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

echo "running migrations..."
php artisan migrate --force --isolated

if [ "${APP_ENV:-production}" = "production" ]; then
    echo "clearing cache..."
    php artisan optimize:clear

    echo "optimizing..."
    php artisan optimize
    php artisan filament:optimize
fi

echo ">> Startup complete. Launching application..."
exec "$@"
