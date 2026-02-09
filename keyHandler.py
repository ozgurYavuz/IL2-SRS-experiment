import threading
import time
import select
from evdev import InputDevice, list_devices, ecodes

class KeyHandler:
    """
    Manages input device monitoring for Push-to-Talk (PTT) keys.

    This class scans for specified input devices and monitors them in a background
    thread for key presses and releases, triggering callbacks when PTT events occur.
    It reads directly from /dev/input/event* devices, making it compatible with
    both X11 and Wayland.
    """
    def __init__(self, ptt1_callback: callable, ptt2_callback: callable, keybinds: dict, verbose: bool = False):
        """
        Initializes the KeyHandler.

        Args:
            ptt1_callback: Function to call with True (pressed) or False (released) for PTT1.
            ptt2_callback: Function to call with True (pressed) or False (released) for PTT2.
            keybinds: A dictionary containing the keybind settings from the config.
            verbose: If True, print all received input events for debugging.
        """
        self.ptt1_callback = ptt1_callback
        self.ptt2_callback = ptt2_callback
        self.keybinds = keybinds
        self.ptt1_key_code = self._parse_key(keybinds.get('ptt1'))
        self.ptt2_key_code = self._parse_key(keybinds.get('ptt2'))
        self.verbose = verbose

        self.monitored_devices = []
        self.is_running = False
        self.monitor_thread = None

    def _parse_key(self, key_string: str):
        """
        Parses a key string (e.g., 'KEY_J', 'BTN_TRIGGER') into an evdev key code.
        """
        if not key_string:
            return None
        try:
            # ecodes.ecodes is a dictionary mapping names to codes
            return ecodes.ecodes[key_string]
        except KeyError:
            print(f"Warning: Key '{key_string}' not recognized by evdev. Ignoring.")
            return None

    def start_monitoring(self):
        """
        Starts the background thread to monitor input devices.
        """
        if self.is_running:
            print("Key monitoring is already running.")
            return

        print("Starting key monitoring...")
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """
        Stops the input device monitoring thread.
        """
        if not self.is_running:
            return
        print("Stopping key monitoring...")
        self.is_running = False
        # The thread will exit on its own. We can join if we need to wait for cleanup.
        if self.monitor_thread:
            self.monitor_thread.join()

    def _monitor_loop(self):
        """
        The main loop for the monitoring thread. It scans for devices and listens for events.
        """
        # Use poll() for robustness, as it has no file descriptor limit like select().
        poller = select.poll()
        monitored_devices = {}  # A map of {file_descriptor: InputDevice}

        while self.is_running:
            try:
                # --- Device Discovery ---
                # Periodically rescan to find newly connected devices.
                device_paths = list_devices()
                current_device_paths = {dev.path for dev in monitored_devices.values()}

                for path in device_paths:
                    if path not in current_device_paths:
                        try:
                            dev = InputDevice(path)
                            print(f"Now monitoring: {dev.name} ({dev.path})")
                            # Register the device's file descriptor for input events.
                            poller.register(dev.fd, select.POLLIN)
                            monitored_devices[dev.fd] = dev
                        except (OSError, IOError):
                            # This can happen if a device is unplugged right as we try to open it.
                            continue

                if not monitored_devices:
                    print("No input devices found. Waiting...")
                    time.sleep(5)
                    continue

                # --- Event Polling ---
                # Wait for an event on any registered device, with a 1-second timeout.
                # The timeout allows the loop to check self.is_running and rescan for devices.
                events = poller.poll(1000)  # 1000ms timeout

                for fd, _ in events:
                    device = monitored_devices[fd]
                    try:
                        for event in device.read():
                            # --- Verbose Logging for Debugging ---
                            if self.verbose:
                                print(f"[{device.name}] Event: type={event.type}, code={event.code}, value={event.value}")

                            # We only care about press (1) and release (0) events.
                            # 'hold' events (value 2) are ignored to prevent repeated callbacks.
                            if event.value in [0, 1]:
                                is_pressed = event.value == 1
                                # Check for the PTT key codes directly, regardless of event type (e.g., EV_KEY, EV_MSC).
                                # This adds robustness for devices like Steam Controllers that might use different event types for virtual buttons.
                                if event.code == self.ptt1_key_code:
                                    self.ptt1_callback(is_pressed)
                                elif event.code == self.ptt2_key_code:
                                    self.ptt2_callback(is_pressed)
                    except (OSError, IOError):
                        # Device was unplugged. Unregister and remove it.
                        print(f"Device disconnected: {device.name}")
                        poller.unregister(fd)
                        device.close()
                        del monitored_devices[fd]

            except PermissionError:
                print("\nFATAL: Permission denied to read from /dev/input/*.")
                print("Please add your user to the 'input' group:")
                print("  sudo usermod -a -G input $USER")
                print("Then, log out and log back in for the change to take effect.")
                self.is_running = False
                break
            except Exception as e:
                print(f"Error in key monitor loop: {e}")
                time.sleep(5) # Avoid spamming errors

if __name__ == '__main__':
    # Example usage for testing
    print("Testing KeyHandler. Press 'j' or 'k'. Press Ctrl+C to exit.")
    
    def ptt1(pressed): print(f"PTT1 {'pressed' if pressed else 'released'}")
    def ptt2(pressed): print(f"PTT2 {'pressed' if pressed else 'released'}")

    # Use evdev key names. You can find them with the `evtest` command-line tool.
    test_binds = {'ptt1': 'KEY_J', 'ptt2': 'KEY_K'}
    
    handler = KeyHandler(ptt1, ptt2, test_binds, verbose=True)
    handler.start_monitoring()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        handler.stop_monitoring()
    print("Test finished.")