import paho.mqtt.client as mqtt
import queue
import threading
class MqttTransmissionMngr:
    def __init__(self):
        self.rawdata_queue = queue.Queue()
        self.MQTT_TOPIC_RAW = ""
        self.MQTT_BROKER = "XXX.XXX.XXX.XXX"
        self.MQTT_PORT = 0
        
    # ------------------------------
    # USER SETTERS
    # ------------------------------
    
    def set_db_mqtt(self,ip,port,topic):
        self.MQTT_BROKER = ip
        self.MQTT_PORT = port
        self.MQTT_TOPIC_RAW = topic

    # ------------------------------
    # PUBLIC METHODS
    # ------------------------------
    def start_db_mqtt(self):
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.connect(self.MQTT_BROKER, self.MQTT_PORT, 60)
        self.mqtt_client.loop_start()
        self._mqtt_thread = threading.Thread(target=self._mqtt_worker, daemon=True)
        self._mqtt_thread.start()
    
    def stop_db_mqtt(self):
        self.rawdata_queue.put((None, None))
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self._mqtt_thread.join()
        print("MQTT STOPPED")
    
    def put_row(self,csv_data_d):
        self.rawdata_queue.put((self.MQTT_TOPIC_RAW, csv_data_d))
        
    # ------------------------------
    # THREAD ENTRYPOINT
    # ------------------------------
    def _mqtt_worker(self):
        while True:
            topic, payload = self.rawdata_queue.get()
            if topic is None:
                break
            try:
                #print("MQTT publish on:", topic, " payload:",payload)
                self.mqtt_client.publish(topic, payload)
            except Exception as e:
                print("MQTT publish failed:", e)
