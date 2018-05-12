import json
import logging
import sys
import os
import subprocess
from queue import Queue, Empty
from threading import Thread

import paho.mqtt.client as mqtt


class MqttMessage:
    def __init__(self, topic, data):
        self.data = data
        self.topic = topic


RTL_COMMAND = ['rtl_433', '-q', '-f', '433920000', '-F', 'json', '-R', '12']
MQTT_TOPIC_PREFIX = os.environ['MQTT_TOPIC_PREFIX']
MQTT_HOST = os.environ['MQTT_HOST']
MQTT_PORT = int(os.environ['MQTT_PORT'])
MQTT_LOGIN = os.environ['MQTT_LOGIN']
MQTT_PASS = os.environ['MQTT_PASS']

SENSOR_IDS = ["THN132N2501"]


def on_connect(client, userdata, flags, rc):
    logging.info("CNNACK received with code %d." % (rc))


def on_publish(client, userdata, mid):
    logging.info("mid: " + str(mid))


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.info("start")

mqttc = mqtt.Client("rtl_433")
mqttc.username_pw_set(username=MQTT_LOGIN, password=MQTT_PASS)
mqttc.connect(MQTT_HOST, port=MQTT_PORT)
mqttc.loop_start()
logging.info("main loop")


def enqueue_output(src, out, queue):
    for line in iter(out.readline, b''):
        print("Received: {}".format(line))
        queue.put((src, line))
    out.close()


def process_data(payload):
    try:
        device_id = "{}{}".format(payload['model'], payload['id'])
        if 'channel' in payload:
            device_id = "{}{}".format(device_id, payload['channel'])
        if device_id in SENSOR_IDS:
            print("{}: {}".format(device_id, payload))
            return MqttMessage(device_id, payload)
        else:
            return None
    except ValueError:
        print("WARNING: Received non-json data from rtl_433: {}".format(payload))


def publish_mqtt_message(mqtt_message):
    (rc, mid) = mqttc.publish("{}/{}".format(MQTT_TOPIC_PREFIX, mqtt_message.topic), json.dumps(mqtt_message.data))
    logging.debug("rc=%s, mid=%s" % (rc, mid))
    mqttc.loop(2)  # timeout = 2s
    logging.debug("published")


def start():
    proc = subprocess.Popen(RTL_COMMAND, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    q = Queue()

    t = Thread(target=enqueue_output, args=('stdout', proc.stdout, q))

    t.daemon = True  # thread dies with the program
    t.start()

    pulse = 0
    while True:
        try:
            _, line = q.get(timeout=40)
        except Empty:
            pulse += 1
        else:  # got line
            pulse -= 1
            try:
                payload = json.loads(line.decode("utf-8"))
                print (payload)

                mqtt_message = process_data(payload)
                if mqtt_message != None:
                    publish_mqtt_message(mqtt_message)
                else:
                    logging.debug("mqtt_message is None")
            except json.JSONDecodeError:
                logging.error(line)


if __name__ == '__main__':
    print("INFO: Starting command: {}".format(RTL_COMMAND))
    start()
