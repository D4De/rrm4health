from abc import ABC, abstractmethod
class GlobalPolicyBase(ABC):

    @classmethod
    def name(cls):
        """
        Returns the display name of the policy.
        Should be overridden by subclasses.
        """
        return cls.__name__

    def get_required_fields(self):
        """
        Returns the set of resources that the policy needs to collect.
        This can be extended to include more resources as needed.
        :return: A set of resource names.
        """
        pass

    @abstractmethod
    def get_best_placement(self, graph, manifest):
        """
        Determines the best placement for the application based on the current graph and manifest.
        returns the best placement configuration and its index.
        the best placement configuration is the partition of the manifest with the node fields filled with the nodeId of the node where the partition should be placed.
        :param graph: A dictionary representing the current state of the system, where keys are node IDs and values are node objects.
        :param manifest: The manifest.json file.
        :return: A tuple containing the best configuration compiled with nodeId where to run each partition and its index in the manifest.
        """
        pass

    @abstractmethod
    def get_next_update_time(self, new_utilization, old_utilization):
        """
        Determines the next update time for the policy based on the current and previous utilization.
        :param new_utilization: The current utilization of the node.
        :param old_utilization: The previous utilization of the node.
        :return: The next update time in seconds.
        """ 
        pass

class LocalPolicyBase(ABC):

    @abstractmethod
    def __init__(self):
        super().__init__()
        self._required_fields = []

    
    @classmethod
    def name(cls):
        return cls.__name__


    def get_required_fields(self):
        """
        Returns the set of resources that the policy needs to collect.
        This can be extended to include more resources as needed.
        :return: A set of resource names.
        """
        return self._required_fields
    
    @abstractmethod
    def update_node_status(self):
        """
        Returns the dictionary with the information of the system needed by the policy aggregating the status info (directly collected) with the old_status in a way defined by the policy.
        :param old_status: The previous status of the node.
        :param measurement_sent: A boolean indicating if the system information has been sent or not.
        :return: A dictionary containing system information.
        """
        pass

    @abstractmethod
    def reset_node_status(self):
        """
        Returns the dictionary with the information of the system needed by the policy and resets the status.
        :return: A dictionary containing system information.
        """
        pass

def safe_temperature(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
