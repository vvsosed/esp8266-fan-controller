# Throwaway MQTT broker for testing the board's MQTT support: plain TCP, no TLS, nothing kept
# between runs. Not for permanent use.
#
#   docker build -t fan-mqtt mqtt-broker
#   docker run --rm --name fan-mqtt -p 1883:1883 fan-mqtt                                    # anyone may connect
#   docker run --rm --name fan-mqtt -p 1883:1883 -e MQTT_USER=fan -e MQTT_PASS=secret fan-mqtt   # login required
#   docker exec fan-mqtt mosquitto_sub -t '#' -v                                             # watch (add -u/-P with a login)
FROM eclipse-mosquitto:2.0.22
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["sh", "/entrypoint.sh"]
CMD ["/usr/sbin/mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
