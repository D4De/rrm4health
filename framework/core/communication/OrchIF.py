import zmq
import threading
import time
import json
import logging
import queue
from typing import List, Dict, Any
from Config import ZMQ_SEND_TIMEOUT, ZMQ_LINGER_TIMEOUT, THREAD_JOIN_TIMEOUT

logger = logging.getLogger(__name__)


class OrchIF(threading.Thread):
    
    def __init__(self,RRM_port):
        super().__init__()
        self.__booleans_tasks = {}
        self.__context = zmq.Context()
        self.__socket = self.__context.socket(zmq.DEALER)  # Invia e riceve indipendentemente
        #Variables for the neighbors
        self.__lock_neighbors = threading.Event()
        self.__neighbors = []       
        #Variables for the Ip request of a swapper
        self.__lock_IP_swap = threading.Event()
        self.__IP_swap = ""
        #Variables for the configuration
        self.__lock_configuration = threading.Event()
        self.__param_s = ""
        self.__channels_src = ""

        self._RRM_port = RRM_port
        self._stop_event = threading.Event()  # Add stop event for clean shutdown
        self.__send_queue = queue.Queue()
        self.__socket.setsockopt(zmq.SNDTIMEO, ZMQ_SEND_TIMEOUT)
        self.__registration_info = {}
        
    
    def connect(self, registration_info=None):
        logger.info("Connecting...")
        self.__registration_info = (
            dict(registration_info) if isinstance(registration_info, dict) else {}
        )
        self.__socket.connect("tcp://localhost:" + str(self._RRM_port))
        message = compose_message("REGISTER_PART", "", self.__registration_info, "")
        self.send_message(message)

    def run(self):
        logger.info("Server listening...")
        poller = zmq.Poller()
        poller.register(self.__socket, zmq.POLLIN)

        while not self._stop_event.is_set() or not self.__send_queue.empty():
            try:
                self._flush_send_queue()
                socks = dict(poller.poll(timeout=50))
                if self.__socket in socks and socks[self.__socket] == zmq.POLLIN:
                    message = self.__socket.recv()
                    logger.debug(f"Client: ricevuto -> {message.decode()}")
                    self.handle_message(json.loads(message.decode()))
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Error in OrchIF run loop: {e}")
                break
        self._flush_send_queue()
        logger.info("OrchIF thread stopped")  

    def _flush_send_queue(self):
        """Send queued messages from the socket-owning thread."""
        while True:
            try:
                payload, completion, result = self.__send_queue.get_nowait()
            except queue.Empty:
                return

            try:
                self.__socket.send(payload)
                result["sent"] = True
            except Exception as exc:
                result["error"] = exc
                logger.error("Error sending message: %s", exc)
            finally:
                self.__send_queue.task_done()
                if completion is not None:
                    completion.set()
            
    def handle_message(self,message):
        if message["action"] == "RESPONSE_OBTAIN_NODES":
                self.__neighbors = message["h_constraints"]["nodes"]
                self.__lock_neighbors.set()
                return     
        elif message["action"] =="UPDATE_CONFIGURATION":
            self.__param_s = message["h_constraints"]
            self.__channels_src = message["o_functions"]
            self.__lock_configuration.set()
            return            
        else:
            return            
            
    def notify_disconnect_part(self, disconnect_info=None):
        """Send DISCONNECT_PART without shutting down transport."""
        h_constraints = disconnect_info if isinstance(disconnect_info, dict) else ""
        message = compose_message("DISCONNECT_PART", "", h_constraints, "")
        return self.send_message(message, wait=True)

    def disconnect(self, disconnect_info=None, send_disconnect=True):
        logger.info("Disconnecting...")
        # Signal the thread to stop first
        
        try:
            # Send disconnect message if socket is still available
            if send_disconnect:
                self.notify_disconnect_part(disconnect_info=disconnect_info)
        except Exception as e:
            logger.error(f"Error sending disconnect message: {e}")
        
        # Give a brief moment for the message to be sent, but don't block long
        time.sleep(0.1)  
        self._stop_event.set()
        
        # Wait for the thread to finish (with timeout)
        if self.is_alive():
            self.join(timeout=THREAD_JOIN_TIMEOUT)
            if self.is_alive():
                logger.warning("OrchIF thread did not stop within timeout, forcing shutdown")
        
        # Close socket and destroy context
        try:
            # Set linger to 0 to avoid hanging on close
            self.__socket.setsockopt(zmq.LINGER, ZMQ_LINGER_TIMEOUT)
            self.__socket.close()
        except Exception as e:
            logger.error(f"Error closing socket: {e}")
            
        try:
            self.__context.term()  # Use term() for faster cleanup
        except Exception as e:
            logger.error(f"Error terminating context: {e}")      

    def send_message(self, message, wait=False):
        if self._stop_event.is_set():
            logger.warning("OrchIF is shutting down, message not sent")
            return False

        message_str = json.dumps(message) if isinstance(message, dict) else message
        payload = message_str.encode('utf-8')

        # Before the I/O thread starts (REGISTER_PART), direct access is safe.
        if not self.is_alive() or threading.current_thread() is self:
            try:
                self.__socket.send(payload)
                return True
            except Exception as exc:
                logger.error("Error sending message: %s", exc)
                if wait:
                    raise
                return False

        completion = threading.Event() if wait else None
        result = {}
        self.__send_queue.put((payload, completion, result))
        if not wait:
            return True

        wait_seconds = max(1.0, (ZMQ_SEND_TIMEOUT / 1000.0) + 1.0)
        if not completion.wait(timeout=wait_seconds):
            raise TimeoutError("Timed out waiting for OrchIF to send message")
        if "error" in result:
            raise RuntimeError("OrchIF failed to send message") from result["error"]
        return bool(result.get("sent"))
      
    def task_is_on(self,name):
        return self.__booleans_tasks[name]              
    
    def what_nodes_there_are(self):
        message = compose_message("OBTAIN_NODES","","","")
        self.send_message(message)
        self.__lock_neighbors.wait()
        return self.__neighbors
    
    def advert_OK_configuration(self,Id_partition):
        configuration_info = dict(self.__registration_info)
        configuration_info["Id_partition"] = Id_partition
        message = compose_message("ADVERT_OK_CONFIGURATION", "", configuration_info, "")
        return self.send_message(message, wait=True)
        
def compose_message(action, action_description, h_constraints, o_functions):
        logger.debug("Composing message")
        """
        Crea un messaggio JSON a partire dai parametri forniti.

        Parameters:
        - action: L'azione da compiere.
        - action_description: La descrizione dell'azione.
        - h_constraints: Le restrizioni sull'azione (può essere un dizionario, lista, etc).
        - o_functions: Le funzioni operative da applicare all'azione.

        Returns:
        - message: Il messaggio JSON serializzato come stringa pronto per essere inviato tramite ZMQ.
        """
        
        # Creiamo il dizionario che rappresenta il messaggio
        message_dict = {
            "action": action,
            "action_description": action_description,
            "h_constraints": h_constraints,
            "o_functions": o_functions
        }

        # Convertiamo il dizionario in formato JSON
        message_json = json.dumps(message_dict)

        return message_json
