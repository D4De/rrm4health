import logging
import core.communication.ChannelManagerApp as ChannelManagerApp

logger = logging.getLogger(__name__)


class ChannelSetupManager:
    """Manages channel setup for input and output communication."""
    
    def __init__(self, in_channel, out_channel):
        """
        Initialize the ChannelSetupManager.
        
        Args:
            in_channel: List of input channel configurations
            out_channel: List of output channel configurations
        """
        self.__in_channel = in_channel
        self.__out_channel = out_channel
        self.__manager = ChannelManagerApp.ChannelManager()
        self._setup_channels()
    
    def _setup_channels(self):
        """Set up input and output channels."""
        # Setup input channels - bind to receive on the destination port (listen on all interfaces)
        if self.__in_channel is not None:
            for channel in self.__in_channel:
                channel_params = channel["parameters"]
                # ZMQ PULL socket binds to all interfaces (*) on the destination port
                # This allows the sender to connect and send messages to this port
                self.__manager.add_input_channel(
                    f"{channel_params['protocol']}://*:{channel_params['port_dst']}"
                )
                logger.debug(f"Added input channel on port {channel_params['port_dst']}")
        
        # Setup output channels - send to ip_dst:port_dst
        if self.__out_channel is not None:
            for channel in self.__out_channel:
                parameters = channel["parameters"]
                self.__manager.add_output_channel(
                    channel["to_partition"],
                    f"{parameters['protocol']}://{parameters['ip_dst']}:{parameters['port_dst']}"
                )
                logger.debug(f"Added output channel to {parameters['ip_dst']}:{parameters['port_dst']}")
    
    def get_channel_manager(self):
        """Get the channel manager instance."""
        return self.__manager
    
    def get_in_channel(self):
        """Get the input channel configuration."""
        return self.__in_channel
    
    def get_out_channel(self):
        """Get the output channel configuration."""
        return self.__out_channel
    
    def close(self):
        """Close the channel manager."""
        try:
            self.__manager.close()
        except Exception as e:
            logger.error(f"Error closing channel manager: {e}")
