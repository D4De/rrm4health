from time import sleep
import zmq
import threading
import queue
import json
import numpy as np
import pickle
import logging
from Config import ZMQ_RECV_SLEEP, ZMQ_LINGER_TIMEOUT, THREAD_JOIN_TIMEOUT

logger = logging.getLogger(__name__)

class NumpyArrayEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

class ChannelManager:
    def __init__(self):
        self.context = zmq.Context()
        self.in_channels = []   
        self.out_channels = {}    # name -> zmq.Socket
        self.threads = []         # receiver threads
        self._closing = threading.Event()  # Signal to stop threads cleanly

    def add_input_channel(self, bind_addr):
        q = queue.Queue()
        socket = self.context.socket(zmq.PULL)
        socket.bind(bind_addr)
        self.in_channels.append((socket, q))

        # Start receiver thread
        def recv_loop():
            while not self._closing.is_set():
                try:
                    msg = socket.recv(zmq.NOBLOCK)
                    q.put(pickle.loads(msg))
                except zmq.Again:
                    # TODO: consider using zmq.Poller for better efficiency or putting it in config
                    sleep(ZMQ_RECV_SLEEP)
                except zmq.ZMQError:
                    break  # socket closed

        t = threading.Thread(target=recv_loop, daemon=True)
        t.start()
        self.threads.append(t)

    def add_output_channel(self, name, connect_addr):
        socket = self.context.socket(zmq.PUSH)
        socket.connect(connect_addr)
        self.out_channels[name] = socket

    def recv(self, running):
        while running.is_set() and not self._closing.is_set():
            for _, q in self.in_channels:
                if not running.is_set() or self._closing.is_set():
                    return None
                try:
                    msg = q.get(timeout=0.1)  # Shorter timeout for faster response
                    q.task_done()
                    return msg
                except queue.Empty:
                    continue
        return None

    def send(self, name, data):
        # sends data to the specified channel
        sock = self.out_channels.get(name)
        if sock:
            logger.debug(f"Send msg: {data} to {sock.getsockopt(zmq.LAST_ENDPOINT)}")
            sock.send(pickle.dumps(data))

    def close(self):
        # Signal all threads to stop
        self._closing.set()
        
        # Close all the sockets and terminate the context
        for sock, _ in self.in_channels:
            sock.setsockopt(zmq.LINGER, ZMQ_LINGER_TIMEOUT)
            sock.close()
            
        for sock in self.out_channels.values():
            sock.setsockopt(zmq.LINGER, ZMQ_LINGER_TIMEOUT)
            sock.close()
        
        # Wait for threads to finish (they should exit quickly now)
        for t in self.threads:
            t.join(timeout=THREAD_JOIN_TIMEOUT)
        
        # Use destroy instead of term for immediate cleanup
        self.context.destroy(linger=ZMQ_LINGER_TIMEOUT)
