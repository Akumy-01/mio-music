FROM php:8.3-cli-alpine
RUN apk add --no-cache ca-certificates \
    && apk add --no-cache --virtual .build-deps $PHPIZE_DEPS curl-dev \
    && docker-php-ext-install curl \
    && apk add --no-cache libcurl \
    && apk del .build-deps
WORKDIR /app
COPY . /app
RUN addgroup -S mio && adduser -S -G mio mio
USER mio
EXPOSE 8080
CMD ["php", "-d", "display_errors=Off", "-d", "log_errors=On", "-S", "0.0.0.0:8080", "-t", "api"]
