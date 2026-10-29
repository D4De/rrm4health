#!/usr/bin/env python3
"""
Launcher script for RRMLocal.
This script initializes and starts the local RRM instance.
"""
import argparse
import ipaddress
import sys
import os

# Add Framework directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logging_config import setup_logging, LEVEL_INFO, LEVEL_DEBUG, LEVEL_WARNING, LEVEL_ERROR
from core.rrm_local.RRMLocal import RRMLocal
from core.rrm_global.RRMGlobal import RRM_GLOBAL_IP, RRM_GLOBAL_PORT
import core.Utils as Utils


def valid_ip(address):
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid IP address: '{address}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the local RRM")
    parser.add_argument('--global_ip', type=valid_ip, required=False, help='IP address of the global RRM', default=RRM_GLOBAL_IP)
    parser.add_argument('--global_port', type=int, required=False, help='Which port to use for the global RRM', default=RRM_GLOBAL_PORT)
    parser.add_argument('--board_info_file', type=str, required=False, help='Optional explicit board-info JSON file (override)', default=None)
    parser.add_argument('--node_id', type=str, required=False, help='Logical node_id in node_inventory.json', default=None)
    parser.add_argument('--log_level', type=str, default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level: DEBUG (all details), INFO (normal), WARNING (warnings only), ERROR (errors only). Default: INFO')
    parser.add_argument('--log_file', type=str, default=None, help='Optional path to log file (logs will also go to console)')
    args = parser.parse_args()

    # Configure logging
    level_map = {'DEBUG': LEVEL_DEBUG, 'INFO': LEVEL_INFO, 'WARNING': LEVEL_WARNING, 'ERROR': LEVEL_ERROR}
    setup_logging(level=level_map[args.log_level], log_file=args.log_file)
  
    rrm = RRMLocal(
        port=Utils.get_free_port(),
        global_ip=args.global_ip,
        global_port=args.global_port,
        board_info_file=args.board_info_file,
        node_id=args.node_id,
    )
    rrm.running_loop()  # Start the RRM local loop
