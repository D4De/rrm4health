#!/usr/bin/env python3
"""
Launcher script for RRMGlobal.
This script initializes and starts the global RRM instance.
"""
import argparse
import sys
import os

# Add Framework directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logging_config import setup_logging, LEVEL_INFO, LEVEL_DEBUG, LEVEL_WARNING, LEVEL_ERROR
from core.rrm_global.RRMGlobal import RRMGlobal, RRM_GLOBAL_PORT
from Config import GLOBAL_SNAPSHOT_DETAIL_DEFAULT
import policy.PolicyUtils as PolicyUtils


def _parse_bool_flag(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    raise argparse.ArgumentTypeError("Expected one of: on/off, true/false, yes/no, 1/0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the Global RRM")
    parser.add_argument('--global_port', type=int, required=False, help='Which port to use for the global RRM', default=RRM_GLOBAL_PORT)
    parser.add_argument('--policy_name', type=str, choices=PolicyUtils.get_policy_names(), default="PolicySymmetricDistribution", help='Name of the policy to use')
    parser.add_argument('--log_level', type=str, default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level: DEBUG (all details), INFO (normal), WARNING (warnings only), ERROR (errors only). Default: INFO')
    parser.add_argument('--log_file', type=str, default=None, help='Optional path to log file (logs will also go to console)')
    parser.add_argument('--snapshot_detail', type=str, default=GLOBAL_SNAPSHOT_DETAIL_DEFAULT,
                        choices=['minimal', 'policy', 'full'],
                        help='Global snapshot detail level: minimal (structure+workload), policy (include policy-requested metrics), full (all available metrics).')
    parser.add_argument('--metrics_mode', type=str, default='instant', choices=['instant', 'window'],
                        help='Capabilities metrics collection mode: instant (default) or window (mean aggregation where supported).')
    parser.add_argument('--window_seconds', type=float, default=0.0,
                        help='Window duration in seconds for --metrics_mode window. Must be > 0 to enable window mode.')
    parser.add_argument('--sample_interval_seconds', type=float, default=0.5,
                        help='Sampling interval in seconds for --metrics_mode window. Must be > 0. Default: 0.5.')
    parser.add_argument('--autostart', type=_parse_bool_flag, default=False,
                        help='Enable/disable startup app launch from Framework/auto_start_applications.json (default: off).')

    args = parser.parse_args()

    # Configure logging
    level_map = {'DEBUG': LEVEL_DEBUG, 'INFO': LEVEL_INFO, 'WARNING': LEVEL_WARNING, 'ERROR': LEVEL_ERROR}
    setup_logging(level=level_map[args.log_level], log_file=args.log_file)

    print(f" available policies: {PolicyUtils.get_policy_names()}")
    
  
    rrm = RRMGlobal(
        port=args.global_port,
        policy_name=args.policy_name,
        snapshot_detail=args.snapshot_detail,
        auto_start_enabled=args.autostart,
        capabilities_mode=args.metrics_mode,
        capabilities_window_seconds=args.window_seconds,
        capabilities_sample_interval_seconds=args.sample_interval_seconds,
    )

    rrm.running_loop()  # Start the RRM global loop
