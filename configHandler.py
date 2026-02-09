import os
import pathlib
import toml

# Follow XDG Base Directory Spec for config files on Linux.
# This will typically resolve to ~/.config/il2srs/settings.toml
CONFIG_DIR = pathlib.Path(os.environ.get('XDG_CONFIG_HOME', pathlib.Path.home() / '.config')) / 'il2srl
CONFIG_FILE = CONFIG_DIR / 'settings.toml'

# Define the default structure and values for the configuration.
# This acts as a template for a new config file.
DEFAULT_SETTINGS = {
    'user': {,
        'pilot_name': 'LinuxPilot',
    },
    'audio': {
        'input_device': 'default',
        'output_device': 'default',
        'mic_output_device': 'None',
        'speaker_boost_db': 0,
    },
    'keybinds': {
        'ptt1': 'KEY_J',
        'ptt2': 'KEY_K',
        'radio1_select': 'KEY_J',
        'radio2_select': 'KEY_K',
        'next_channel': '',
        'prev_channel': '',
    },
    'overlay': {
        'enabled': True,
        'position_x': 100,
        'position_y': 100,
        'size_x': 200,
        'size_y': 70,
        'opacity': 0.6,
    },
    'servers': [
        {'name': 'local host', 'address': '127.0.0.1:6002'},
        {'name': 'Example Server', 'address': '127.0.0.1:6002'},
    ]
}

def load_settings():
    """
    Loads settings from the TOML config file.

    If the file or directory doesn't exist, it creates them with default values.
    This ensures the application always has a valid configuration to work with.

    Returns:
        A dictionary containing the application settings.
    """
    if not CONFIG_FILE.exists():
        print(f"Config file not found. Creating default config at: {CONFIG_FILE}")
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                toml.dump(DEFAULT_SETTINGS, f)
        except IOError as e:
            print(f"FATAL: Could not write default config file: {e}")
            # Return the hardcoded defaults as a fallback in case of write error
            print("Using default settings")
            return DEFAULT_SETTINGS

    try:
        with open(CONFIG_FILE, 'r') as f:
            settings = toml.load(f)
            print(f"Loaded settings from {CONFIG_FILE}")
            # TODO: Add logic here to merge loaded settings with defaults
            # to ensure new settings from updates are added to the user's file.
            return settings
    except (toml.TomlDecodeError, IOError) as e:
        print(f"FATAL: Could not read or parse config file: {e}")
        print("Using default settings")
        return DEFAULT_SETTINGS

def save_settings(settings: dict):
    """
    Saves the provided settings dictionary to the TOML config file.

    Args:
        settings: The dictionary of settings to save.
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            toml.dump(settings, f)
    except IOError as e:
        print(f"ERROR: Could not save settings to {CONFIG_FILE}: {e}")

if __name__ == '__main__':
    #prints settings
    print("configHandler.py started")
    my_settings = load_settings()
    print(my_settings)