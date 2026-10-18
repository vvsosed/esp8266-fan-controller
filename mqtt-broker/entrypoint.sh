#!/bin/sh
# Writes the broker config, then hands over to the image's own entrypoint.
# MQTT_USER and MQTT_PASS both set: a login is required. Otherwise anyone may connect.
set -e
conf=/mosquitto/config/mosquitto.conf
passwd=/mosquitto/config/passwd

echo "listener 1883" > "$conf"            # all interfaces: mosquitto 2 serves only localhost without it
if [ -n "$MQTT_USER" ] && [ -n "$MQTT_PASS" ]; then
    mosquitto_passwd -b -c "$passwd" "$MQTT_USER" "$MQTT_PASS"
    chown mosquitto:mosquitto "$passwd"   # mosquitto warns about a password file it doesn't own
    chmod 0700 "$passwd"
    printf 'allow_anonymous false\npassword_file %s\n' "$passwd" >> "$conf"
    echo "MQTT test broker: login required, user $MQTT_USER"
else
    echo "allow_anonymous true" >> "$conf"
    echo "MQTT test broker: no login"
fi

exec /docker-entrypoint.sh "$@"
