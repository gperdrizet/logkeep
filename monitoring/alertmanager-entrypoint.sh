#!/bin/sh
# Process the Alertmanager config template with environment variables
# Escape special characters for sed
SMTP_PASSWORD_ESCAPED=$(echo "$SMTP_PASSWORD" | sed 's/[&/\$]/\\&/g')

sed -e "s/\${SMTP_HOST}/${SMTP_HOST}/g" \
    -e "s/\${SMTP_PORT}/${SMTP_PORT}/g" \
    -e "s/\${SMTP_USER}/${SMTP_USER}/g" \
    -e "s|\${SMTP_PASSWORD}|${SMTP_PASSWORD_ESCAPED}|g" \
    -e "s/\${ALERT_EMAIL}/${ALERT_EMAIL}/g" \
    /etc/alertmanager/alertmanager.yml.template > /etc/alertmanager/alertmanager.yml

# Start Alertmanager with the processed config
exec /bin/alertmanager "$@"
