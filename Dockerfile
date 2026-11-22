ARG ALPINE_VERSION=3.24
ARG PHP_VERSION=85
ARG ENGINE=fpm
ARG USER=nobody

# =============================================================================
# Base layer
#
# Installs supervisor, nginx, php and the packages required to run the image
# =============================================================================
FROM alpine:${ALPINE_VERSION} AS base

ARG PHP_VERSION
ARG USER
# The image's own nobody; compose builds development as sail with the host UID
ARG WWWUSER=65534

ENV USER=${USER}

WORKDIR /app

# https://laravel.com/docs/master/deployment#server-requirements
RUN apk add --no-cache \
    curl \
    nginx \
    php${PHP_VERSION} \
    php${PHP_VERSION}-cli \
    php${PHP_VERSION}-ctype \
    php${PHP_VERSION}-curl \
    php${PHP_VERSION}-dom \
    php${PHP_VERSION}-fileinfo \
    php${PHP_VERSION}-gd \
    php${PHP_VERSION}-intl \
    php${PHP_VERSION}-mbstring \
    php${PHP_VERSION}-mysqli \
    php${PHP_VERSION}-openssl \
    php${PHP_VERSION}-pdo \
    php${PHP_VERSION}-phar \
    php${PHP_VERSION}-session \
    php${PHP_VERSION}-tokenizer \
    php${PHP_VERSION}-xml \
    php${PHP_VERSION}-xmlreader \
    php${PHP_VERSION}-xmlwriter \
    supervisor \
    # Common packages
    php${PHP_VERSION}-pcntl \
    php${PHP_VERSION}-bcmath \
    php${PHP_VERSION}-simplexml \
    php${PHP_VERSION}-zip \
    php${PHP_VERSION}-iconv \
    php${PHP_VERSION}-redis \
    php${PHP_VERSION}-pecl-igbinary \
    # Database drivers
    php${PHP_VERSION}-pdo_mysql

# - Create version-agnostic php alias (Alpine only ships /usr/bin/php${PHP_VERSION})
# - Fix permissions
# - Create user with UID matching host user (for file permission compatibility)
# - Create group and user only if they don't already exist
RUN ln -sf /usr/bin/php${PHP_VERSION} /usr/bin/php; \
    ln -sf /usr/bin/php${PHP_VERSION} /usr/local/bin/php; \
    getent group ${USER} || addgroup ${USER}; \
    getent passwd ${USER} || adduser -u ${WWWUSER} -G ${USER} -D -h /home/${USER} ${USER}; \
    mkdir -p /home/${USER} && chown ${WWWUSER}:${WWWUSER} /home/${USER}; \
    chown -R ${WWWUSER}:${WWWUSER} /run /var/lib/nginx /var/log/nginx

ENV HOME=/home/${USER}
ENV RUN_MIGRATIONS=true

# Supervisord
COPY --link confs/supervisor.d/supervisord.conf /etc/supervisord.conf
# Configure Nginx
COPY --link confs/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --link confs/nginx/server-common.conf /etc/nginx/server-common.conf
COPY --link confs/nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY --link confs/supervisor.d/nginx.conf /etc/supervisor.d/nginx.conf
# Configure PHP
COPY --link confs/php.ini /etc/php${PHP_VERSION}/conf.d/app.ini
# Entrypoint
COPY --link --chmod=555 scripts/start-container.sh /usr/local/bin/start-container

# Runtime configuration
EXPOSE 8080
HEALTHCHECK --timeout=10s CMD curl --silent --fail http://127.0.0.1:8080/up
ENTRYPOINT ["start-container"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]

# =============================================================================
# Dependencies layer
#
# Local packages should be placed in the packages directory
#
# This layer keeps credentials safe
# =============================================================================
FROM base AS dependencies

ARG COMPOSER_AUTH

RUN apk add --no-cache git
COPY --link --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY --link composer.* .
COPY --link packages/ packages/

RUN --mount=type=cache,target=/tmp/composer-cache \
    COMPOSER_CACHE_DIR=/tmp/composer-cache \
    composer install --optimize-autoloader --no-interaction --no-dev --no-scripts --prefer-dist

# =============================================================================
# Build layer
# =============================================================================
FROM dependencies AS build

RUN apk add --no-cache npm

COPY --link . .

RUN --mount=type=cache,target=/tmp/npm-cache \
    npm ci --cache /tmp/npm-cache && \
    npm run build && \
    composer dump-autoload --optimize --classmap-authoritative

# =============================================================================
# Php-fpm
# =============================================================================
FROM base AS fpm

ARG PHP_VERSION

# Install php-fpm and create version-agnostic alias
RUN apk add --no-cache php${PHP_VERSION}-fpm; \
    ln -sf /usr/sbin/php-fpm${PHP_VERSION} /usr/local/bin/php-fpm

# Configure FPM
COPY --link confs/php-fpm.conf /etc/php${PHP_VERSION}/php-fpm.d/www.conf
COPY --link confs/nginx/php-fpm.conf /etc/nginx/conf.d/laravel.conf
COPY --link confs/supervisor.d/php-fpm.conf /etc/supervisor.d/php-fpm.conf

# =============================================================================
# Octane
# =============================================================================
FROM base AS octane

ARG PHP_VERSION
ARG ENGINE

ENV OCTANE_SERVER=${ENGINE}
ENV OCTANE_OPTIONS=""
# Set by the engine stage; OCTANE_OPTIONS is left to the app
ENV OCTANE_SERVER_OPTIONS=""
ENV OCTANE_PORT=8000

# Octane requires sockets and posix (for posix_kill)
RUN apk add --no-cache \
    php${PHP_VERSION}-sockets \
    php${PHP_VERSION}-posix

# Octane configs
COPY --link confs/supervisor.d/octane.conf /etc/supervisor.d/octane.conf
COPY --link confs/nginx/octane.conf /etc/nginx/conf.d/laravel.conf

# =============================================================================
# RoadRunner
# =============================================================================
FROM octane AS roadrunner

# Without --rr-config Octane touches .rr.yaml at every start, which a read-only root rejects.
# An .rr.yaml shipped by the app replaces this empty one
ENV OCTANE_SERVER_OPTIONS="--rr-config=.rr.yaml"
RUN touch .rr.yaml

# =============================================================================
# Swoole
# =============================================================================
FROM octane AS swoole

ARG PHP_VERSION

RUN apk add --no-cache php${PHP_VERSION}-pecl-swoole

# =============================================================================
# Production
# =============================================================================
FROM ${ENGINE} AS production

ARG ENGINE
ARG USER
ARG WWWUSER
ARG COMMIT_SHA
ARG GIT_TAG
ARG BRANCH

ENV COMMIT_SHA=${COMMIT_SHA}
ENV GIT_TAG=${GIT_TAG}
ENV BRANCH=${BRANCH}
ENV OCTANE_HTTPS=true

# Production-specific nginx config
COPY --link confs/nginx/enable-sendfile.conf /etc/nginx/conf.d/enable-sendfile.conf

COPY --link --from=dependencies /app/vendor vendor
COPY --link --from=build --exclude=vendor --exclude=node_modules /app .
COPY --link --from=build /app/vendor/composer vendor/composer
COPY --link --from=build /app/vendor/autoload.php vendor/autoload.php

# Code stays root-owned; the app user writes only to storage/ and bootstrap/cache.
# storage:link at build: the root filesystem is read-only at runtime
RUN chown -R ${WWWUSER}:${WWWUSER} storage bootstrap/cache && \
    ln -sfn ../storage/app/public public/storage

RUN if [ "${ENGINE}" = "roadrunner" ]; then \
        ./vendor/bin/rr get-binary --no-interaction --no-config --quiet; \
    fi

# Switch to non-root user for runtime
USER ${WWWUSER}

# =============================================================================
# Development
# =============================================================================
FROM ${ENGINE} AS development

ARG ENGINE
ARG PHP_VERSION
ARG USER

ENV OPCACHE_VALIDATE_TIMESTAMPS=1
ENV OCTANE_HTTPS=false

# Install dev-only packages
RUN apk --no-cache add \
    bash \
    git \
    npm \
    php${PHP_VERSION}-dev \
    php${PHP_VERSION}-xdebug
COPY --link --from=composer:2 /usr/bin/composer /usr/bin/composer

# Enable xdebug
COPY --link confs/xdebug.ini /etc/php${PHP_VERSION}/conf.d/50_xdebug.ini

# Engine runs under artisan dev in development
RUN rm -f /etc/supervisor.d/php-fpm.conf /etc/supervisor.d/octane.conf
COPY --link confs/supervisor.d/dev.conf /etc/supervisor.d/dev.conf

# Docker Desktop shows the bind-mounted /app as root-owned, which git refuses as dubious ownership
RUN git config --system --add safe.directory /app

# Switch to non-root user for runtime
USER ${WWWUSER}

# =============================================================================
# Default target
# =============================================================================
FROM production
