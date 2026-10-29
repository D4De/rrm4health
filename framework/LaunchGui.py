#!/usr/bin/env python3
"""
Launch script for RRM GUI interface
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import json
from core.communication.ChannelManagerClient import ChannelManagerClient
import core.Utils as Utils
from core.communication.Message import GUIListApplications, GUIListNodesStatus, GUIRegister, GUIStartApplication, GUIStopApplication, GUIListPolicies, GUISetPolicy,GUIListAvailableApplications, message_factory
from core.communication.MessageTypes import MessageTypes
from core.rrm_global.RRMGlobal import RRM_GLOBAL_IP, RRM_GLOBAL_PORT


def find_gui_configs(app_name):
    """Prefer installed presets, falling back to the local application sources."""
    framework_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = (
        os.path.join(framework_dir, "applications", app_name, "gui_config"),
        os.path.join(os.path.dirname(framework_dir), "applications_repo", app_name, "gui_config"),
    )
    for config_dir in candidates:
        try:
            configs = sorted(
                os.path.join(config_dir, name)
                for name in os.listdir(config_dir)
                if name.endswith(".json") and os.path.isfile(os.path.join(config_dir, name))
            )
        except OSError:
            continue
        if configs:
            return configs
    return []


class RRM_GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RRM Control GUI")
        self.geometry("600x750")
        self.minsize(650, 650)

        self.client = None
        self.user_arg_entries = {}
        self.user_arg_placeholders = {}  # Track which entries have placeholders
        self.running_apps = []
        self.available_policies = []
        self.current_policy = None
        self.current_app_name = None  # Track currently selected app
        self.available_configs = []  # Track available config files
        # descriptors fetched from RRM; each is {"appID":..., "manifest":...}
        self.available_descriptors = []
        self.nodes_status = []

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Connection Frame
        conn_frame = ttk.LabelFrame(main_frame, text="Connection Management", padding="10")
        conn_frame.pack(fill=tk.X, pady=5)

        conn_frame.columnconfigure(1, weight=3)
        conn_frame.columnconfigure(3, weight=1)
        conn_frame.columnconfigure(6, weight=2)

        ttk.Label(conn_frame, text="RRM Global IP:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.ip_entry = ttk.Entry(conn_frame)
        self.ip_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.ip_entry.insert(0, RRM_GLOBAL_IP)

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.port_entry = ttk.Entry(conn_frame)
        self.port_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        self.port_entry.insert(0, RRM_GLOBAL_PORT)

        self.connect_button = ttk.Button(conn_frame, text="Connect", command=self.connect_to_rrm)
        self.connect_button.grid(row=0, column=4, padx=5, pady=5)

        self.disconnect_button = ttk.Button(conn_frame, text="Disconnect", command=self.disconnect_from_rrm)
        self.disconnect_button.grid(row=0, column=5, padx=5, pady=5)
        self.disconnect_button.config(state=tk.DISABLED)

        self.status_label = ttk.Label(conn_frame, text="Status: Disconnected", foreground="red")
        self.status_label.grid(row=0, column=6, padx=10, pady=5, sticky="ew")

        # Policy Frame
        policy_frame = ttk.LabelFrame(main_frame, text="Policy Management", padding="10")
        policy_frame.pack(fill=tk.X, pady=5)

        policy_frame.columnconfigure(1, weight=1)

        ttk.Label(policy_frame, text="Current Policy:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.current_policy_label = ttk.Label(policy_frame, text="Not connected", foreground="gray")
        self.current_policy_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(policy_frame, text="Select Policy:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.selected_policy = tk.StringVar()
        self.policy_dropdown = ttk.OptionMenu(policy_frame, self.selected_policy, "Select a policy")
        self.policy_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.policy_dropdown.config(state=tk.DISABLED)

        self.change_policy_button = ttk.Button(policy_frame, text="Change Policy", command=self.change_policy)
        self.change_policy_button.grid(row=1, column=2, padx=5, pady=5)
        self.change_policy_button.config(state=tk.DISABLED)

        # Application Frame
        app_frame = ttk.LabelFrame(main_frame, text="Application Launcher", padding="10")
        app_frame.pack(fill=tk.X, pady=10)

        ttk.Label(app_frame, text="Select Application:").pack(fill=tk.X, padx=5, pady=5)
        self.app_names = self.get_descriptor_apps()
        self.selected_app = tk.StringVar()
        # Note: trace will be registered at end of __init__ after all widgets are created
        self.app_dropdown = ttk.OptionMenu(app_frame, self.selected_app, "Select an app", *self.app_names)
        self.app_dropdown.pack(fill=tk.X, padx=5, pady=5)

        # Keep a large parameter list inside a bounded, scrollable area so the
        # launcher buttons and the remaining interface stay reachable.
        user_args_container = ttk.Frame(app_frame)
        user_args_container.pack(fill=tk.X, pady=5)

        frame_background = ttk.Style().lookup("TFrame", "background") or self.cget("background")
        self.user_args_canvas = tk.Canvas(
            user_args_container,
            height=1,
            highlightthickness=0,
            background=frame_background,
        )
        self.user_args_scrollbar = ttk.Scrollbar(
            user_args_container,
            orient="vertical",
            command=self.user_args_canvas.yview,
        )
        self.user_args_frame = ttk.Frame(self.user_args_canvas, padding="10")
        self.user_args_window = self.user_args_canvas.create_window(
            (0, 0),
            window=self.user_args_frame,
            anchor="nw",
        )

        self.user_args_frame.bind(
            "<Configure>",
            lambda _event: self.user_args_canvas.configure(
                scrollregion=self.user_args_canvas.bbox("all")
            ),
        )
        self.user_args_canvas.bind(
            "<Configure>",
            lambda event: self.user_args_canvas.itemconfigure(
                self.user_args_window,
                width=event.width,
            ),
        )
        self.user_args_canvas.configure(yscrollcommand=self.user_args_scrollbar.set)
        self.user_args_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.user_args_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._bind_vertical_scroll(self.user_args_canvas, self.user_args_canvas)
        self._bind_vertical_scroll(self.user_args_frame, self.user_args_canvas)

        # Button frame for Load Config and Start Application
        button_frame = ttk.Frame(app_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.load_config_button = ttk.Button(button_frame, text="Load Configuration", command=self.load_configuration)
        self.load_config_button.pack(side=tk.LEFT, padx=5)
        self.load_config_button.config(state=tk.DISABLED)

        self.start_app_button = ttk.Button(button_frame, text="Start Application", command=self.start_application)
        self.start_app_button.pack(side=tk.RIGHT, padx=5)
        self.start_app_button.config(state=tk.DISABLED)

        # Running Apps Frame
        running_frame = ttk.LabelFrame(main_frame, text="Running Applications", padding="10")
        running_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Scrollable frame for running apps with Stop buttons
        self.running_apps_canvas = tk.Canvas(running_frame)
        self.running_apps_scrollbar = ttk.Scrollbar(running_frame, orient="vertical", command=self.running_apps_canvas.yview)
        self.running_apps_frame = ttk.Frame(self.running_apps_canvas)

        self.running_apps_frame.bind(
            "<Configure>",
            lambda e: self.running_apps_canvas.configure(scrollregion=self.running_apps_canvas.bbox("all"))
        )

        self.running_apps_canvas.create_window((0, 0), window=self.running_apps_frame, anchor="nw")
        self.running_apps_canvas.configure(yscrollcommand=self.running_apps_scrollbar.set)

        self.running_apps_canvas.pack(side="left", fill="both", expand=True)
        self.running_apps_scrollbar.pack(side="right", fill="y")

        # Nodes status frame
        nodes_frame = ttk.LabelFrame(main_frame, text="Nodes Status", padding="10")
        nodes_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.nodes_canvas = tk.Canvas(nodes_frame)
        self.nodes_scrollbar = ttk.Scrollbar(nodes_frame, orient="vertical", command=self.nodes_canvas.yview)
        self.nodes_status_frame = ttk.Frame(self.nodes_canvas)

        self.nodes_status_frame.bind(
            "<Configure>",
            lambda e: self.nodes_canvas.configure(scrollregion=self.nodes_canvas.bbox("all"))
        )

        self.nodes_canvas.create_window((0, 0), window=self.nodes_status_frame, anchor="nw")
        self.nodes_canvas.configure(yscrollcommand=self.nodes_scrollbar.set)

        self.nodes_canvas.pack(side="left", fill="both", expand=True)
        self.nodes_scrollbar.pack(side="right", fill="y")

        # Register trace callback AFTER all widgets are initialized
        # so that on_app_select has access to all UI elements
        self.selected_app.trace('w', self._on_app_selected_trace)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def get_descriptor_apps(self):
        # Prefer using descriptors previously fetched from RRM Global if available.
        if hasattr(self, 'available_descriptors') and self.available_descriptors:
            return [d.get('appID', '') for d in self.available_descriptors]

        descriptor_dir = os.path.join(os.path.dirname(__file__), "applications")
        
        if not os.path.isdir(descriptor_dir):
            messagebox.showerror("Error", f"Descriptors directory not found: {descriptor_dir}")
            return []

        try:
            files = os.listdir(descriptor_dir)
            return [
                os.path.splitext(f)[0]
                for f in files
                if f.endswith(".json") and f != "DevicePerformancePerPartition.json"
            ]
        except Exception as e:
            messagebox.showerror("Error", f"Error reading descriptor files: {e}")
            return []

    def _on_app_selected_trace(self, *args):
        """Wrapper for trace callback with error handling"""
        try:
            selected = self.selected_app.get()
            self.on_app_select(selected)
        except Exception as e:
            messagebox.showerror("Error", f"Error selecting application: {e}")

    def on_app_select(self, selected_app_name):
        for widget in self.user_args_frame.winfo_children():
            widget.destroy()
        self.user_args_canvas.configure(height=1)
        self.user_args_canvas.yview_moveto(0)
        self.user_arg_entries = {}
        self.user_arg_placeholders = {}
        self.current_app_name = selected_app_name
        self.available_configs = []

        if not selected_app_name or selected_app_name == "Select an app":
            self.load_config_button.config(state=tk.DISABLED)
            return

        # try to find descriptor entry from previously received list
        descriptor_entry = None
        for d in getattr(self, 'available_descriptors', []):
            if d.get('appID') == selected_app_name:
                descriptor_entry = d
                break

        if descriptor_entry is not None:
            # we only received parameters section over the wire
            params = descriptor_entry.get('parameters', {})
        else:
            # fallback to local descriptors folder (offline mode)
            descriptor_dir = os.path.join(os.path.dirname(__file__), "applications")
            filepath = os.path.join(descriptor_dir, f"{selected_app_name}.json")

            if not os.path.isfile(filepath):
                messagebox.showerror("Error", f"Descriptor file for '{selected_app_name}' not found.")
                self.load_config_button.config(state=tk.DISABLED)
                return

            with open(filepath, 'r') as f:
                manifest = json.load(f)
            params = manifest.get("executable", {}).get("parameters", {})

        self.available_configs = find_gui_configs(selected_app_name)
        self.load_config_button.config(
            state=tk.NORMAL if self.available_configs else tk.DISABLED
        )

        # manifest variable already populated earlier (remote or local)
        try:
            # params variable may already be set from descriptor_entry above
            userargs_set = []
            userarg_descriptions = {}

            for key, val in params.items():
                # Check if it's a user parameter (has {{}} template)
                if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
                    # Extract the placeholder text from {{PLACEHOLDER}}
                    placeholder = val.strip("{}").strip()
                    userargs_set.append((key, placeholder, None))  # (param_name, placeholder_text, default_value)

                elif isinstance(val, str):
                    # It's a default value without {{}}
                    userargs_set.append((key, None, val))  # (param_name, placeholder_text, default_value)

            if userargs_set:
                ttk.Label(self.user_args_frame, text="User Arguments:", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 2))

            for param_name, placeholder_text, default_value in userargs_set:
                self.create_entry_widget(self.user_args_frame, param_name, placeholder_text, default_value, self.user_arg_entries)
                if placeholder_text:
                    self.user_arg_placeholders[param_name] = placeholder_text

            self.user_args_frame.update_idletasks()
            content_height = self.user_args_frame.winfo_reqheight()
            self.user_args_canvas.configure(height=min(content_height, 220))

        except Exception as e:
            messagebox.showerror("Error", f"Could not load descriptor: {e}")
            self.load_config_button.config(state=tk.DISABLED)

    def create_entry_widget(self, parent, arg_name, placeholder_text, default_value, entry_dict):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)

        label = ttk.Label(frame, text=f"{arg_name}:")
        label.pack(side=tk.LEFT, padx=5)

        # Use tk.Entry instead of ttk.Entry for better foreground color control
        entry = tk.Entry(frame)
        entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        # If there's a placeholder text (from {{}}), use it as hint
        if placeholder_text:
            entry.insert(0, placeholder_text)
            entry.config(foreground='gray')
            
            # Add focus-in handler to clear placeholder
            def on_focus_in(event):
                current_fg = entry.cget('foreground')
                if entry.get() == placeholder_text and current_fg == 'gray':
                    entry.delete(0, tk.END)
                    entry.config(foreground='black')
            
            # Add focus-out handler to restore placeholder if empty
            def on_focus_out(event):
                if not entry.get():
                    entry.insert(0, placeholder_text)
                    entry.config(foreground='gray')
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
        
        # If there's a default value (no {{}}), insert it as actual value
        elif default_value:
            entry.insert(0, default_value)
            entry.config(foreground='black')
        
        entry_dict[arg_name] = entry

        if parent is self.user_args_frame:
            for widget in (frame, label, entry):
                self._bind_vertical_scroll(widget, self.user_args_canvas)

    @staticmethod
    def _bind_vertical_scroll(widget, canvas):
        """Scroll ``canvas`` with the mouse wheel while hovering its contents."""
        def on_mousewheel(event):
            if getattr(event, "num", None) == 4:
                units = -1
            elif getattr(event, "num", None) == 5:
                units = 1
            else:
                delta = getattr(event, "delta", 0)
                units = -1 if delta > 0 else 1
            canvas.yview_scroll(units, "units")
            return "break"

        widget.bind("<MouseWheel>", on_mousewheel, add="+")
        widget.bind("<Button-4>", on_mousewheel, add="+")
        widget.bind("<Button-5>", on_mousewheel, add="+")

    def load_configuration(self):
        """Load configuration from a JSON file and populate user arg fields"""
        if not self.available_configs:
            messagebox.showinfo("No Configurations", "No configuration files available for this application.")
            return
        
        # Create a dialog to select configuration
        config_dialog = tk.Toplevel(self)
        config_dialog.title("Select Configuration")
        config_dialog.geometry("500x400")
        config_dialog.transient(self)
        config_dialog.grab_set()
        
        ttk.Label(config_dialog, text="Available Configurations:", font=("TkDefaultFont", 10, "bold")).pack(pady=10, padx=10, anchor="w")
        
        # Create a frame for the configuration list with scrollbar
        list_frame = ttk.Frame(config_dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        config_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        config_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=config_listbox.yview)
        
        # Load config file info and populate listbox
        config_info = []
        for config_path in self.available_configs:
            try:
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    name = config_data.get("name", os.path.basename(config_path))
                    description = config_data.get("description", "No description")
                    config_info.append((config_path, name, description, config_data))
                    config_listbox.insert(tk.END, name)
            except Exception as e:
                print(f"Error loading config {config_path}: {e}")
        
        # Info label for selected config description
        info_frame = ttk.LabelFrame(config_dialog, text="Description", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        description_label = ttk.Label(info_frame, text="Select a configuration to view details", wraplength=450)
        description_label.pack(anchor="w")
        
        def on_select(event):
            selection = config_listbox.curselection()
            if selection:
                idx = selection[0]
                if idx < len(config_info):
                    description_label.config(text=config_info[idx][2])
        
        config_listbox.bind('<<ListboxSelect>>', on_select)
        
        # Buttons
        button_frame = ttk.Frame(config_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def apply_config():
            selection = config_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a configuration.")
                return
            
            idx = selection[0]
            if idx >= len(config_info):
                return
                
            config_path, name, description, config_data = config_info[idx]
            userargs = config_data.get("userargs", {})
            
            if not userargs:
                messagebox.showwarning("Empty Configuration", "This configuration has no user arguments defined.")
                return
            
            # Populate the entry fields
            for key, value in userargs.items():
                if key in self.user_arg_entries:
                    entry = self.user_arg_entries[key]
                    # Clear the entry
                    entry.delete(0, tk.END)
                    # Insert the new value
                    entry.insert(0, str(value))
                    # Set the foreground color to black (not placeholder)
                    entry.config(foreground='black')
            
            config_dialog.destroy()
        
        def cancel():
            config_dialog.destroy()
        
        ttk.Button(button_frame, text="Apply", command=apply_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=5)
        
        # Center the dialog
        config_dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (config_dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (config_dialog.winfo_height() // 2)
        config_dialog.geometry(f"+{x}+{y}")

    def handler(self, msg):
        try:
            msg = message_factory(msg)
        except ValueError as e:
            print(f"Error decoding message: {e}")
            return

        if msg.type == MessageTypes.GLOBAL_REGISTER_RESPONSE:
            print(f"Registered with RRM Global: {msg.status}")
            # Set current policy from registration response
            if msg.current_policy:
                self.current_policy = msg.current_policy
                self.current_policy_label.config(text=self.current_policy, foreground="blue")
            # After registration, request the list of available policies
            self.client.send_message(GUIListPolicies())
            # also ask for available applications so the dropdown can be populated
            self.client.send_message(GUIListAvailableApplications())

        elif msg.type == MessageTypes.GLOBAL_LIST_POLICIES_RESPONSE:
            self.available_policies = msg.policy_list
            # Update the policy dropdown menu
            menu = self.policy_dropdown["menu"]
            menu.delete(0, "end")
            for policy in self.available_policies:
                menu.add_command(label=policy, command=lambda p=policy: self.selected_policy.set(p))
            if self.available_policies:
                # If we know the current policy, set it as selected; otherwise use the first one
                if self.current_policy and self.current_policy in self.available_policies:
                    self.selected_policy.set(self.current_policy)
                else:
                    self.selected_policy.set(self.available_policies[0])

        elif msg.type == MessageTypes.GLOBAL_SET_POLICY_RESPONSE:
            if msg.status == "OK":
                # Update current policy display
                self.current_policy = self.selected_policy.get()
                self.current_policy_label.config(text=self.current_policy, foreground="blue")
                messagebox.showinfo("Success", f"Policy changed to {self.current_policy}")
            else:
                messagebox.showerror("Policy Change Failed", f"Failed to change policy.\n\nReason: {msg.status}")

        elif msg.type == MessageTypes.GLOBAL_START_APPLICATION_RESPONSE:
            if msg.status == "OK":
                messagebox.showinfo("Success", f"Application {msg.appID} started successfully.")
            else:
                messagebox.showerror("Application Start Failed", f"Failed to start application {msg.appID}.\n\nReason: {msg.status}")

        elif msg.type == MessageTypes.GLOBAL_STOP_APPLICATION_RESPONSE:
            if msg.status == "OK":
                messagebox.showinfo("Success", f"Application {msg.appID} stopped successfully.")
            else:
                messagebox.showerror("Application Stop Failed", f"Failed to stop application {msg.appID}.\n\nReason: {msg.status}")

        elif msg.type == MessageTypes.GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE:
            # store descriptor list for later UI use
            self.available_descriptors = msg.descriptors if msg.descriptors is not None else []
            # populate application dropdown with received names
            names = [d.get('appID','') for d in self.available_descriptors]
            if names:
                menu = self.app_dropdown['menu']
                menu.delete(0, 'end')
                for name in names:
                    # IMPORTANT: Must use command lambda to set StringVar when item is selected
                    # This triggers the .trace() callback registered on self.selected_app
                    menu.add_command(label=name, command=lambda n=name: self.selected_app.set(n))
                self.app_names = names
            # if running disconnected or not connected will just ignore
        elif msg.type == MessageTypes.GLOBAL_LIST_APPLICATIONS_RESPONSE:
            self.running_apps = msg.applications

            # Clear previous widgets in running apps frame
            for widget in self.running_apps_frame.winfo_children():
                widget.destroy()

            for app in self.running_apps:
                app_id = app['appID']
                partitions = app.get('partitions', [])

                # Extract partition and node information from the clean partition mapping
                partition_to_node = {}

                for partition in partitions:
                    partition_id = partition.get('partitionID')
                    node_ip = partition.get('node_ip')
                    node_port = partition.get('node_port')
                    
                    if partition_id and node_ip and node_port:
                        node_endpoint = f"{node_ip}:{node_port}"
                        partition_to_node[partition_id] = node_endpoint

                # Count unique nodes from partition locations
                total_partitions = len(partition_to_node)
                total_nodes = len(set(partition_to_node.values()))
                
                display_text = f"{app_id} - {total_partitions} partition{'s' if total_partitions != 1 else ''} on {total_nodes} node{'s' if total_nodes != 1 else ''}"
                
                # Create expandable frame for app details
                app_frame = ttk.LabelFrame(self.running_apps_frame, text=display_text, padding="5")
                app_frame.pack(fill=tk.X, pady=2, padx=5)

                # Top row with stop button
                top_row = ttk.Frame(app_frame)
                top_row.pack(fill=tk.X, pady=2)

                stop_btn = ttk.Button(top_row, text="Stop", command=lambda app_id=app_id: self.stop_application(app_id))
                stop_btn.pack(side=tk.RIGHT, padx=5)

                # Details section
                details_frame = ttk.Frame(app_frame)
                details_frame.pack(fill=tk.X, pady=2)

                # Partition mapping only
                if partition_to_node:
                    ttk.Label(details_frame, text="Partition Locations:", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
                    for partition, node in sorted(partition_to_node.items()):
                        partition_info = f"  • {partition} → {node}"
                        ttk.Label(details_frame, text=partition_info, font=("TkDefaultFont", 8)).pack(anchor="w", padx=10)

        elif msg.type == MessageTypes.GLOBAL_LIST_NODES_STATUS_RESPONSE:
            self.nodes_status = msg.nodes if msg.nodes is not None else []

            for widget in self.nodes_status_frame.winfo_children():
                widget.destroy()

            if not self.nodes_status:
                ttk.Label(self.nodes_status_frame, text="No nodes connected", foreground="gray").pack(anchor="w", padx=5, pady=5)
            else:
                for node in self.nodes_status:
                    node_id = node.get("node_id", "unknown")
                    status = str(node.get("status", "UNKNOWN")).upper()
                    board_id = node.get("board_id", "")
                    online = bool(node.get("online", False))

                    color = "green" if online else "red"
                    card = ttk.LabelFrame(self.nodes_status_frame, text=node_id, padding="5")
                    card.pack(fill=tk.X, pady=2, padx=5)

                    ttk.Label(card, text=f"Status: {status}", foreground=color).pack(anchor="w")
                    if board_id:
                        ttk.Label(card, text=f"Board ID: {board_id}").pack(anchor="w")

        elif msg.type == MessageTypes.GLOBAL_SHUTDOWN:
            print("Received GlobalShutdown message from RRM Global. Disconnecting...")
            self.disconnect_from_rrm()
            messagebox.showinfo("RRM Shutdown", "RRM Global has initiated shutdown. GUI has been disconnected.")

        elif msg.type == MessageTypes.GLOBAL_GUI_NOTIFICATION:
            severity = str(getattr(msg, "severity", "info") or "info").lower()
            category = str(getattr(msg, "category", "generic") or "generic")
            app_id = str(getattr(msg, "appID", "") or "")
            node_id = str(getattr(msg, "nodeID", "") or "")
            text = str(getattr(msg, "message", "") or "")

            details = []
            if category:
                details.append(f"Category: {category}")
            if app_id:
                details.append(f"App: {app_id}")
            if node_id:
                details.append(f"Node: {node_id}")
            details_block = "\n".join(details)
            dialog_text = text if not details_block else f"{text}\n\n{details_block}"

            print(f"[GUI NOTIFICATION][{severity.upper()}] {dialog_text}")
            if severity == "error":
                messagebox.showerror("Framework Notification", dialog_text)
            elif severity == "warning":
                messagebox.showwarning("Framework Notification", dialog_text)
            else:
                messagebox.showinfo("Framework Notification", dialog_text)

        else:
            print(f"Received unknown message type: {msg.type}")

    def connect_to_rrm(self):
        ip = self.ip_entry.get()
        port = self.port_entry.get()
        if not ip or not port:
            messagebox.showerror("Error", "IP and Port cannot be empty.")
            return

        try:
            port = int(port)
            self.client = ChannelManagerClient(ip=Utils.get_local_ip(), port=Utils.get_free_port(), rrmIp=ip, rrmPort=port, handler=self.handler)
            self.client.start()
            self.client.send_message(GUIRegister())
            # once registered we'll receive a GLOBAL_REGISTER_RESPONSE, and handler will
            # request policies; also request descriptor list explicitly here in case
            # we want to display apps right away
            self.client.send_message(GUIListAvailableApplications())
            self.status_label.config(text="Status: Connected", foreground="green")
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.start_app_button.config(state=tk.NORMAL)
            self.policy_dropdown.config(state=tk.NORMAL)
            self.change_policy_button.config(state=tk.NORMAL)
            self.start_monitoring()

        except Exception as e:
            messagebox.showerror("Connection Failed", f"Could not connect to RRM Global.\n{e}")
            self.client = None

    def disconnect_from_rrm(self):
        if self.client:
            self.client.close()
        self.client = None

        self.status_label.config(text="Status: Disconnected", foreground="red")
        self.connect_button.config(state=tk.NORMAL)
        self.disconnect_button.config(state=tk.DISABLED)
        self.start_app_button.config(state=tk.DISABLED)
        self.policy_dropdown.config(state=tk.DISABLED)
        self.change_policy_button.config(state=tk.DISABLED)
        self.current_policy_label.config(text="Not connected", foreground="gray")

        # Clear running apps list
        for widget in self.running_apps_frame.winfo_children():
            widget.destroy()

        for widget in self.nodes_status_frame.winfo_children():
            widget.destroy()

    def start_application(self):
        app_name = self.selected_app.get()
        if not app_name or app_name == "Select an app":
            messagebox.showerror("Error", "Please select an application to start.")
            return

        # Collect args and validate placeholder fields are filled
        args = {}
        unfilled_fields = []
        
        for key, entry in self.user_arg_entries.items():
            value = entry.get()
            # Check if it's a placeholder field
            if key in self.user_arg_placeholders:
                placeholder = self.user_arg_placeholders[key]
                # Check if user left the placeholder or didn't fill it
                if not value or value == placeholder:
                    unfilled_fields.append(key)
                else:
                    args[key] = value
            else:
                args[key] = value  # Include default values or user-entered values
        
        # If there are unfilled placeholder fields, show error
        if unfilled_fields:
            fields_list = "\n".join([f"  • {field}" for field in unfilled_fields])
            messagebox.showerror(
                "Missing Required Fields", 
                f"Please fill in the following required fields:\n\n{fields_list}"
            )
            return

        try:
            start_msg = GUIStartApplication(appID=app_name, args=args)
            self.client.send_message(start_msg)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to send start command.\n{e}")

    def stop_application(self, app_id):
        try:
            stop_msg = GUIStopApplication(appID=app_id)
            self.client.send_message(stop_msg)
            messagebox.showinfo("Info", f"Stop command for {app_id} sent.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send stop command.\n{e}")

    def change_policy(self):
        policy_name = self.selected_policy.get()
        if not policy_name or policy_name == "Select a policy":
            messagebox.showerror("Error", "Please select a policy to change to.")
            return

        if policy_name == self.current_policy:
            messagebox.showinfo("Info", f"Already using policy: {policy_name}")
            return

        try:
            set_policy_msg = GUISetPolicy(policy_name=policy_name)
            self.client.send_message(set_policy_msg)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send policy change command.\n{e}")

    def start_monitoring(self):
        if self.client:
            self.client.send_message(GUIListApplications())
            self.client.send_message(GUIListNodesStatus())
            self.after(5000, self.start_monitoring)

    def on_closing(self):
        if self.client:
            self.client.close()
        self.destroy()

if __name__ == "__main__":
    app = RRM_GUI()
    app.mainloop()
