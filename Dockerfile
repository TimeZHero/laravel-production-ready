ARG ALPINE_VERSION=3.23
ARG PHP_VERSION=84
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
ARG WWWUSER=1000

ENV SUPERVISOR_AUTORESTART=false
ENV USER=${USER}

WORKDIR /app

# https://laravel.com/docs/master/deployment#server-requirements
RUN apk add --no-cache \
    curl \
    nginx \
    npm \
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
    php${PHP_VERSION}-opcache \
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

# - Install Composer
# - Fix permissions
# - Create user with UID matching host user (for file permission compatibility)
# - Create group and user only if they don't already exist
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/bin/ --filename=composer; \
    getent group ${USER} || addgroup ${USER}; \
    getent passwd ${USER} || adduser -u ${WWWUSER} -G ${USER} -D -h /home/${USER} ${USER}; \
    chown -R ${USER}:${USER} /app /run /var/lib/nginx /var/log/nginx

# Supervisord
COPY --link confs/supervisor.d/supervisord.conf /etc/supervisord.conf
# Configure Nginx
COPY --link confs/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --link confs/nginx/server-common.conf /etc/nginx/server-common.conf
COPY --link confs/supervisor.d/nginx.conf /etc/supervisor.d/nginx.conf
# Configure PHP
COPY --link confs/php.ini /etc/php${PHP_VERSION}/conf.d/app.ini
# Entrypoint
COPY --link --chmod=755 scripts/start-container.sh /usr/local/bin/start-container

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

COPY --link composer.* packages .

RUN composer install --no-cache --optimize-autoloader --no-interaction --no-dev --no-scripts --prefer-dist

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

ENV OCTANE_HTTPS=true

# Production-specific nginx config
COPY --link confs/nginx/enable-sendfile.conf /etc/nginx/conf.d/enable-sendfile.conf

# Copy pre-built vendor from dependencies
COPY --link --chown=${USER}:${USER} --from=dependencies /app/vendor vendor

# Copy application source
COPY --link --chown=${USER}:${USER} . .

# Download RoadRunner binary (only if engine is roadrunner)
RUN if [ "${ENGINE}" = "roadrunner" ]; then \
        ./vendor/bin/rr get-binary --no-interaction --no-config --quiet; \
    fi

# Finalize: build frontend, run composer scripts, cleanup
RUN npm ci; \
    npm run build; \
    rm -rf node_modules; \
    composer dump-autoload --optimize --classmap-authoritative

# Switch to non-root user for runtime
USER ${USER}

# =============================================================================
# Development
# =============================================================================
FROM ${ENGINE} AS development

ARG ENGINE
ARG PHP_VERSION
ARG USER

ENV SUPERVISOR_AUTORESTART=true
ENV OPCACHE_VALIDATE_TIMESTAMPS=1
ENV OCTANE_HTTPS=false
ENV OCTANE_OPTIONS="--watch"

# Install dev-only packages
RUN apk --no-cache add \
    bash \
    php${PHP_VERSION}-dev \
    php${PHP_VERSION}-xdebug

# Enable xdebug
COPY --link confs/xdebug.ini /etc/php${PHP_VERSION}/conf.d/50_xdebug.ini

# Copy supervisor programs for development
COPY --link confs/supervisor.d/queue.conf /etc/supervisor.d/queue.conf
COPY --link confs/supervisor.d/scheduler.conf /etc/supervisor.d/scheduler.conf

# Switch to non-root user for runtime
USER ${USER}

# =============================================================================
# Default target
# =============================================================================
FROM production
