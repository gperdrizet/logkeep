#!/bin/sh
# Process the Alertmanager config template with environment variables
envsubst < /etc/alertmanager/alertmanager.yml.template > /etc/alertmanager/alertmanager.yml

# Start Alertmanager with the processed config
exec /bin/alertmanager "$@"
