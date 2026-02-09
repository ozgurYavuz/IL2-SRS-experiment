import time
import sys
from threading import Event

import configHandler
import gameListener
from audio import AudioManager
from srsServerHandler import SrsServerClient, ReceivedVoice
from keyHandler import KeyHandler

class SrsRadioClient:
    """
    The main application class that integrates all modules.
    """
    def __init__(self):
        self.settings = None
        self.audio_manager = None
        self.srs_server_client = None
        self.key_handler = None
        self._stop_event = Event()

        self.ptt1_pressed = False
        self.ptt2_pressed = False

    def _handle_received_audio(self, voice_data: ReceivedVoice):
        """Callback for the SrsServerClient to pass received audio to the AudioManager."""
        if self.audio_manager:
            # The audio payload is raw Opus data, which is what play_audio expects.
            self.audio_manager.play_audio(voice_data.audio_payload)

    def _handle_mic_capture(self, encoded_packet: bytes):
        """Callback for the AudioManager to pass encoded mic data to the SrsServerClient."""
        if self.srs_server_client and self.srs_server_client.is_running:
            if self.ptt1_pressed:
                self.srs_server_client.send_voice_packet(encoded_packet, radio_num=1)
            if self.ptt2_pressed:
                self.srs_server_client.send_voice_packet(encoded_packet, radio_num=2)

    def _handle_ptt1(self, is_pressed: bool):
        """Callback for KeyHandler on PTT1 event."""
        self.ptt1_pressed = is_pressed
        print(f"PTT1 {'Pressed' if is_pressed else 'Released'}")

    def _handle_ptt2(self, is_pressed: bool):
        """Callback for KeyHandler on PTT2 event."""
        self.ptt2_pressed = is_pressed
        print(f"PTT2 {'Pressed' if is_pressed else 'Released'}")

    def run(self):
        """Starts and runs the client application."""
        print("--- IL-2 Linux SRS Client ---")

        # 1. Load Settings
        print("\n[Step 1/5] Loading settings...")
        self.settings = configHandler.load_settings()
        if not self.settings:
            print("FATAL: Could not load settings. Exiting.")
            return

        # 2. Wait for Game Data
        print("\n[Step 2/5] Waiting for IL-2 to start...")
        print("Please start IL-2 and join a multiplayer server.")
        game_data = gameListener.listen_for_game_data()
        if not game_data:
            print("Failed to get game data. Exiting.")
            return
        
        srs_address, pilot_name = game_data
        server_ip, server_port_str = srs_address.split(':')
        server_port = int(server_port_str)

        # Use game pilot name, but fall back to config if needed
        final_pilot_name = pilot_name or self.settings['user']['pilot_name']

        # 3. Initialize Audio Manager
        print("\n[Step 3/5] Initializing audio...")
        self.audio_manager = AudioManager(
            input_device=self.settings['audio']['input_device'],
            output_device=self.settings['audio']['output_device'],
            encoded_mic_callback=self._handle_mic_capture,
            speaker_boost_db=self.settings['audio']['speaker_boost_db']
        )

        # 4. Initialize and Connect SRS Client
        print("\n[Step 4/5] Connecting to SRS Server...")
        self.srs_server_client = SrsServerClient(
            server_address=server_ip,
            server_port=server_port,
            pilot_name=final_pilot_name,
            received_audio_callback=self._handle_received_audio
        )
        self.srs_server_client.connect()

        if not self.srs_server_client.is_running:
            print("Failed to connect to SRS server. Exiting.")
            return

        # 5. Start Audio Capture and Main Loop
        print("\n[Step 5/5] Starting audio capture. Client is now active.")
        self.audio_manager.start_capture()

        # Initialize and start key handler
        self.key_handler = KeyHandler(
            ptt1_callback=self._handle_ptt1,
            ptt2_callback=self._handle_ptt2,
            keybinds=self.settings['keybinds']
        )
        self.key_handler.start_monitoring()

        print("\nClient is running. Press Ctrl+C to exit.")
        try:
            while not self._stop_event.is_set():
                # The main loop can be used for tasks like checking keybinds.
                # For now, just keep the app alive.
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutdown signal received.")
        finally:
            print("Cleaning up...")
            if self.srs_server_client: self.srs_server_client.disconnect()
            if self.audio_manager: self.audio_manager.stop_capture()
            if self.key_handler: self.key_handler.stop_monitoring()
            print("Client has been shut down. Goodbye.")

if __name__ == '__main__':
    client = SrsRadioClient()
    client.run()