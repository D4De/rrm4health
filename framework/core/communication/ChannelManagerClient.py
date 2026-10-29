import threading
import zmq
import json
import queue
import logging
from core.communication.MessageTypes import MessageTypes
from core.communication.Message import LocalConnect, Message
from Config import ZMQ_POLL_TIMEOUT

logger = logging.getLogger(__name__)


class ChannelManagerClient():
    def __init__(self, ip, port, rrmIp, rrmPort, handler):
        self.__ip = ip
        self.__port = port
        self.__handler = handler

        self.__context = zmq.Context()
        self.__socket = self.__context.socket(zmq.DEALER)
        self.__socket.identity = f"{self.__ip}:{self.__port}".encode('utf-8')
        self.__socket.connect(f"tcp://{rrmIp}:{rrmPort}")
        self.__rrmIp = rrmIp
        self.__rrmPort = rrmPort
        self.__running = True
        self.__send_queue = queue.Queue()

        self.io_thread = threading.Thread(target=self._io_loop, daemon=True)

    def initialize_connection(self):
        """Sends a connection request to the server."""
        logger.info(f"ChannelManagerClient connecting to {self.__rrmIp}:{self.__rrmPort} from {self.__ip}:{self.__port}")
        try:
            # Send a connection request
            data = LocalConnect().to_dict()
            self.__socket.send(json.dumps(data).encode('utf-8'))
            raw_msg = self.__socket.recv()
            msg = json.loads(raw_msg.decode('utf-8'))
            if msg.get("type") != MessageTypes.GLOBAL_CONNECT_RESPONSE:
                raise ConnectionError(f"RRM '{(self.__rrmIp, self.__rrmPort)}' responded unexpectedly")

            logger.info(f"[{self.__ip}:{self.__port}] Connected to {self.__rrmIp}:{self.__rrmPort}")

            self.start()
        except zmq.ZMQError as e:
            logger.error(f"Error sending connection request: {e}")

    def start(self):
        """Start the single thread that owns the ZeroMQ socket."""
        if not self.io_thread.is_alive():
            self.io_thread.start()

    def _io_loop(self):
        """Handle both directions without sharing the socket across threads."""
        poller = zmq.Poller()
        poller.register(self.__socket, zmq.POLLIN)
        while self.__running or not self.__send_queue.empty():
            try:
                while True:
                    try:
                        msg_dict, completion, result = self.__send_queue.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        logger.debug(f"[{self.__ip}:{self.__port}] Sending message: {msg_dict}")
                        self.__socket.send(json.dumps(msg_dict).encode('utf-8'))
                        result["sent"] = True
                    except Exception as exc:
                        result["error"] = exc
                        raise
                    finally:
                        self.__send_queue.task_done()
                        if completion is not None:
                            completion.set()

                socks = dict(poller.poll(timeout=min(ZMQ_POLL_TIMEOUT, 50)))
                if self.__socket in socks and socks[self.__socket] == zmq.POLLIN:
                    raw_msg = self.__socket.recv()
                    msg = json.loads(raw_msg.decode('utf-8'))
                    print(f"[{self.__ip}:{self.__port}] Received message: {msg} from {self.__rrmIp}:{self.__rrmPort}")
                    logger.debug(f"[{self.__ip}:{self.__port}] Client received: {msg} from {self.__rrmIp}:{self.__rrmPort}")

                    if self.__handler:
                        self.__handler(msg)
            except zmq.ZMQError as e:
                logger.error(f"ZMQ Error in ChannelManagerClient loop [{self.__ip}:{self.__port}]: {e}")
                break
            except Exception as exc:
                logger.exception(
                    "Unexpected error in ChannelManagerClient loop [%s:%s]: %s",
                    self.__ip,
                    self.__port,
                    exc,
                )
    
    def send_message(self, message: Message, wait: bool = False):
        if not isinstance(message, Message):
            raise TypeError("Message must be an instance of Message dataclass.")
        completion = threading.Event() if wait else None
        result = {}
        self.__send_queue.put((message.to_dict(), completion, result))
        if not wait:
            return True

        wait_seconds = 2.0
        if not completion.wait(timeout=wait_seconds):
            raise TimeoutError("Timed out waiting for ChannelManagerClient to send message")
        if "error" in result:
            raise RuntimeError("ChannelManagerClient failed to send message") from result["error"]
        return bool(result.get("sent"))

    def close(self):
        self.__running = False
        current_thread = threading.current_thread()
        if self.io_thread.is_alive() and self.io_thread != current_thread:
            self.io_thread.join()
        self.__socket.close()
        self.__context.term()
        logger.info(f"ChannelManagerClient closed on {self.__ip}:{self.__port}")
