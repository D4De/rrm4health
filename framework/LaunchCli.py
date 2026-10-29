#!/usr/bin/env python3
"""
Launch script for RRM CLI interface
"""
import argparse
import ipaddress
from core.communication.ChannelManagerClient import ChannelManagerClient
import core.Utils as Utils
import json
from core.communication.Message import GUIRegister, GUIStartApplication, GUIStopApplication, GUIListPolicies, GUISetPolicy, GUIListAvailableApplications, message_factory
from core.rrm_global.RRMGlobal import RRM_GLOBAL_IP, RRM_GLOBAL_PORT

def message_handler(msg_dict):
    try:
        msg = message_factory(msg_dict)
        print(f"[RECEIVED]: {msg}")
    except ValueError as e:
        print(f"Error decoding message: {e}")

def cli(client):
    client.send_message(GUIRegister())
    print("Simple RRM CLI")
    print("1. Start App")
    print("2. Stop App")
    print("3. Get Policy List")
    print("4. Change Policy")
    print("5. List Available Descriptors")
    print("6. Exit")

    while True:
        choice = input("\nChoose an option: ")
        if choice == "1":
            app_id = input("Enter App ID: ")
            user_args_str = input("Enter user arguments as a JSON string (e.g., {\"key\": \"value\"}) or leave empty: ")
            user_args = {}
            if user_args_str:
                try:
                    user_args = json.loads(user_args_str)
                except json.JSONDecodeError:
                    print("Error: Invalid JSON format for user arguments. Please try again.")
                    continue

            client.send_message(GUIStartApplication(appID=app_id, args=user_args))
            print(f"Sent START_APP for {app_id}")
        elif choice == "2":
            input_str = input("Enter App ID: ")
            app_id = (input_str.split(",")[0], int(input_str.split(",")[1])) 
            client.send_message(GUIStopApplication(appID=app_id))
            print(f"Sent STOP_APP for {app_id}")
        elif choice == "3":
            client.send_message(GUIListPolicies())
            print("Sent request for policy list")
        elif choice == "4":
            policy = input("Enter new policy name: ")
            client.send_message(GUISetPolicy(policy_name=policy))
            print(f"Sent policy change to {policy}")
        elif choice == "5":
            client.send_message(GUIListAvailableApplications())
            print("Sent request for available application descriptors")
        elif choice == "6":
            print("Exiting...")
            client.close()
            break
        else:
            print("Invalid choice")

def valid_ip(address):
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid IP address: '{address}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the RRM CLI interface")
    parser.add_argument('--global_ip', type=valid_ip, required=False, help='IP address of the global RRM', default=RRM_GLOBAL_IP)
    parser.add_argument('--global_port', type=int, required=False, help='Port of the global RRM', default=RRM_GLOBAL_PORT)
    args = parser.parse_args()

    # Configuration
    ip = Utils.get_local_ip()
    port = Utils.get_free_port()
    rrm_ip = args.global_ip
    rrm_port = args.global_port
    
    print(f"Using local IP: {ip}, port: {port}")
    print(f"Connecting to RRM Global at {rrm_ip}:{rrm_port}")
    
    client = ChannelManagerClient(ip, port, rrm_ip, rrm_port, message_handler)
    client.start()

    try:
        cli(client)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        client.close()
