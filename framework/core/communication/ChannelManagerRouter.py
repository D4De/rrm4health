import json
import queue
import threading
import zmq
import logging
from core.communication.Message import Message, message_factory
from Config import ZMQ_POLL_TIMEOUT

logger = logging.getLogger(__name__)


class ChannelManagerRouter():
    def __init__(self, ip, port, handler):
        self.__ip = ip
        self.__port = port
        self.__handler = handler

        self.__context = zmq.Context()
        self.__socket = self.__context.socket(zmq.ROUTER)
        self.__socket.bind(f"tcp://*:{self.__port}")
        self.__running = True

        logger.info(f"ChannelManagerRouter initialized on {self.__ip}:{self.__port}")

        self.__send_queue = queue.Queue()

        self.io_thread = threading.Thread(target=self._io_loop, daemon=True)
        self.io_thread.start()

    def _io_loop(self):
        """Handle both directions from the sole socket-owning thread."""
        poller = zmq.Poller()
        poller.register(self.__socket, zmq.POLLIN)
        while self.__running or not self.__send_queue.empty():
            try:
                while True:
                    try:
                        client_id, msg_dict = self.__send_queue.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        logger.debug(f"[{self.__ip}:{self.__port}] Channel manager sending message to {client_id}: {msg_dict}")
                        self.__socket.send_multipart([client_id, json.dumps(msg_dict).encode('utf-8')])
                    finally:
                        self.__send_queue.task_done()

                socks = dict(poller.poll(timeout=min(ZMQ_POLL_TIMEOUT, 50)))
                if self.__socket in socks and socks[self.__socket] == zmq.POLLIN:
                    client_id, raw_msg = self.__socket.recv_multipart()
                    msg_dict = json.loads(raw_msg.decode('utf-8'))
                    logger.debug(f"[{self.__ip}:{self.__port}] Router received: {msg_dict} from {client_id}")
                    if self.__handler:
                        self.__handler(client_id, msg_dict)
            except zmq.ZMQError as e:
                logger.error(f"ZMQ Error in ChannelManagerRouter loop [{self.__ip}:{self.__port}]: {e}")
                break
            except Exception as exc:
                logger.exception(
                    "Unexpected error in ChannelManagerRouter loop [%s:%s]: %s",
                    self.__ip,
                    self.__port,
                    exc,
                )


    def send_message(self, client_id: bytes, message: Message):
        if not isinstance(message, Message):
            raise TypeError("Message must be an instance of Message dataclass.")
        self.__send_queue.put((client_id, message.to_dict()))
         # We expect an OK message from the client TODO check if it is implementable for all clients apps included, for now we remove the unknown messages from the handlers

    def close(self):
        self.__running = False
        current_thread = threading.current_thread()
        if self.io_thread.is_alive() and self.io_thread != current_thread:
            self.io_thread.join()
        self.__socket.close()
        self.__context.term()
        logger.info(f"ChannelManagerRouter closed on {self.__ip}:{self.__port}")
