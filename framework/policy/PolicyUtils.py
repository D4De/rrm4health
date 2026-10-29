from policy.Policy import GlobalPolicyBase
from policy.Policy import LocalPolicyBase

# Include new policies subclasses here
from policy.PolicySymmetricDistribution import PolicySymmetricDistributionGlobal, PolicySymmetricDistributionLocal
from policy.PolicyMaximizeBatteryLife import PolicyMaximizeBatteryLifeGlobal, PolicyMaximizeBatteryLifeLocal

def get_policy_names() -> list:
    """
    Returns a list of available policy names.
    :return: A list of strings representing the names of available policies.
    """
    return [cls.name() for cls in GlobalPolicyBase.__subclasses__()]

def load_policy_by_name_global(name: str) -> GlobalPolicyBase:
    """
    Loads a global policy instance by its readable name defined in the class method `name()`.
    
    :param name: The custom name of the policy (from cls.name()).
    :return: An instance of the matching policy class.
    :raises ValueError: If the name does not match any known policy.
    """
    for cls in GlobalPolicyBase.__subclasses__():
        if hasattr(cls, "name") and cls.name() == name:
            return cls()
    
    available = [cls.name() for cls in GlobalPolicyBase.__subclasses__() if hasattr(cls, "name")]
    raise ValueError(f"Unknown policy: '{name}'. Available policies: {available}")

def load_policy_by_name_local(name: str) -> LocalPolicyBase:
    """
    Loads a local policy instance by its readable name defined in the class method `name()`.
    
    :param name: The custom name of the policy (from cls.name()).
    :return: An instance of the matching policy class.
    :raises ValueError: If the name does not match any known policy.
    """
    for cls in LocalPolicyBase.__subclasses__():
        if hasattr(cls, "name") and cls.name() == name:
            return cls()
    
    available = [cls.name() for cls in LocalPolicyBase.__subclasses__() if hasattr(cls, "name")]
    raise ValueError(f"Unknown policy: '{name}'. Available policies: {available}")

