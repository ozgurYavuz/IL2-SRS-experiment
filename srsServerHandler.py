import socket
import threading
import time
import struct
import uuid
import json
from collections import namedtuple

# Constants for the Simple Radio Standalone (SRS) protocol.
# Based on analysis of compatible client implementations.

# Packet IDs from Server to Client
PACKET_ID_SERVER_SETTINGS = 0
PACKET_ID_CLIENT_LIST = 1
PACKET_ID_VOICE = 2

# Named tuple for received voice data for clarity. The IL-2 SRS server doesn't send sender GUID with voice.
ReceivedVoice = namedtuple('ReceivedVoice', ['audio_payload', 'sender_guid'])

# Packet IDs from Client to Server
PACKET_ID_CLIENT_VOICE = 1
PACKET_ID_CLIENT_UPDATE = 2 # Radio Info Update
PACKET_ID_CLIENT_PING = 4

# Constants for the JSON-based TCP protocol used by the C# server.
JSON_MSG_TYPE_SYNC = "SYNC"
JSON_MSG_TYPE_UPDATE = "UPDATE"
JSON_MSG_TYPE_RADIO_UPDATE = "RADIO_UPDATE"
JSON_MSG_TYPE_PING = "PING"

# This client is for the IL-2 SRS Server, not DCS.
SERVER_TYPE = "IL2-SRS"
CLIENT_VERSION = "1.0.0.0" # A dummy version to satisfy the server.

class SrsServerClient:
    """
    Manages the TCP connection and communication with an SRS server.
    """
    def __init__(self, server_address: str, server_port: int, pilot_name: str, received_audio_callback: callable):
        """
        Initializes the SRS network client.

        Args:
            server_address: The IP address of the SRS server.
            server_port: The port of the SRS server.
            pilot_name: The name of the user/client.
            received_audio_callback: A function to call with a ReceivedVoice named tuple
                                     when a voice packet is received.
        """
        self.server_address = server_address
        self.server_port = server_port
        self.pilot_name = pilot_name
        if not self.pilot_name:
            self.pilot_name = "LinuxPilot" # Added a default name
        self.received_audio_callback = received_audio_callback

        self.client_guid = str(uuid.uuid4())
        self.tcp_sock = None
        self.udp_sock = None
        self.voice_packet_id = 0 # Sequentially increasing ID for voice packets
        self.is_running = False
        self.ping_thread = None
        self.tcp_receive_thread = None
        self.udp_receive_thread = None

    def connect(self):
        """Establishes a connection to the SRS server and starts the listener thread."""
        if self.is_running:
            print("Client is already connected.")
            return

        try:
            print(f"Connecting to SRS server at {self.server_address}:{self.server_port}...")
            # Setup TCP socket for control messages
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((self.server_address, self.server_port))
            print("TCP connection successful.")

            # Setup UDP socket for voice. It binds to the same local port as the TCP socket.
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.bind(self.tcp_sock.getsockname())
            print(f"UDP socket bound to {self.tcp_sock.getsockname()}")

            self._perform_handshake()

            self.is_running = True
            # Start thread for TCP control messages
            self.tcp_receive_thread = threading.Thread(target=self._tcp_receive_loop, daemon=True)
            self.tcp_receive_thread.start()

            # Start thread for UDP voice packets
            self.udp_receive_thread = threading.Thread(target=self._udp_receive_loop, daemon=True)
            self.udp_receive_thread.start()

            self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self.ping_thread.start()

            print("SRS client started.")

        except (socket.error, OSError, OverflowError) as e:
            print(f"FATAL: Could not connect to SRS server: {e}")
            self.disconnect()

    def disconnect(self):
        """Disconnects from the server and stops the listener thread."""
        if not self.is_running:
            print("not connected")
            return

        print("Disconnecting from SRS server...")
        self.is_running = False
        if self.tcp_sock:
            self.tcp_sock.close()
            self.tcp_sock = None
        if self.udp_sock:
            self.udp_sock.close()
            self.udp_sock = None
        # No need to join daemon threads, but it can be good practice if they hold resources.

    def _send_json_message(self, msg_type: str, client_data: dict = None):
        """Constructs and sends a JSON message to the server."""
        if not self.is_running or not self.tcp_sock:
            return
        
        if msg_type == JSON_MSG_TYPE_PING:
            return

        message = {
            "MsgType": msg_type,
            "ServerType": SERVER_TYPE,
            "Version": CLIENT_VERSION,
            "Client": {
                "ClientGuid": self.client_guid,
                "Name": self.pilot_name,
                "Coalition": 0, # 0=Spectator, 1=Allies, 2=Axis
                "Seat": 0,
            }
        }
        if client_data:
            message["Client"].update(client_data)

        # The server expects a JSON string followed by a newline.
        json_string = json.dumps(message) + "\n"
        packet = json_string.encode('utf-8')
        self.tcp_sock.sendall(packet)

    def _ping_loop(self):
        """Sends a ping to the server every 10 seconds to keep the connection alive."""
        while self.is_running:
            try:
                # The server has a 5-second timeout. We send a ping, then sleep.
                # This ensures the server always receives a packet within its timeout window.
                self._send_ping()
                time.sleep(4)
            except Exception:
                # The main receive loop will handle the disconnect.
                break

    def _perform_handshake(self):
        """Sends the initial SYNC message to the server."""
        self._send_json_message(JSON_MSG_TYPE_SYNC)
        print("Handshake (SYNC) message sent.")

    def _tcp_receive_loop(self):
        """Continuously listens for data from the server."""
        buffer = bytearray()
        while self.is_running:
            try:
                # Read data from the socket and add it to our buffer
                data = self.tcp_sock.recv(4096)
                if not data:
                    print("Connection closed by server.")
                    break
                buffer.extend(data)

                # Process all complete packets in the buffer
                # The server sends newline-terminated JSON messages.
                while b'\n' in buffer:
                    packet_data, buffer = buffer.split(b'\n', 1)
                    if packet_data:
                        try:
                            # The server sends JSON, but the client's _parse_packet
                            # expects binary. This part would also need to be rewritten
                            # to handle JSON messages from the server.
                            # For now, we just print it.
                            message = json.loads(packet_data.decode('utf-8'))
                            print(f"Received JSON from server: {message}")
                            # self._parse_json_message(message) # A new method would be needed
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            print(f"Could not decode server message: {e}")
                            print(f"Raw data: {packet_data}")
                        
            # This part of the original code is for a different protocol.
            except ConnectionResetError:
                print("Connection was forcibly closed by the remote host.")
                break
            except Exception as e:
                if self.is_running:
                    print(f"Error in receive loop: {e}")
                break
        
        self.is_running = False
        print("TCP receive loop stopped.")

    def _udp_receive_loop(self):
        """Continuously listens for UDP voice packets from the server."""
        print("UDP receive loop started.")
        while self.is_running:
            try:
                # For IL-2 SRS, the UDP packet is just the raw Opus audio.
                # The header is added by the client, not the server.
                data, _ = self.udp_sock.recvfrom(4096)
                if data:
                    # The server doesn't tell us who sent the audio in the packet itself.
                    # We just receive a mix. The sender_guid is therefore None.
                    voice_data = ReceivedVoice(audio_payload=data, sender_guid=None)
                    self.received_audio_callback(voice_data)
            except Exception as e:
                if self.is_running:
                    print(f"Error in UDP receive loop: {e}")
                break
        print("UDP receive loop stopped.")

    def _parse_json_message(self, message: dict):
        """Parses an incoming JSON message from the server."""
        # This would be the new implementation to handle server responses.
        pass


    def send_voice_packet(self, encoded_opus_packet: bytes, radio_num: int):
        """
        Wraps an Opus packet in the SRS protocol format and sends it.
        Args:
            encoded_opus_packet: The Opus-encoded audio data.
            frequency: The transmission frequency.
            radio_num: The radio number being used (e.g., 1 or 2).
        """
        if not self.is_running or not self.udp_sock:
            return

        try:
            # Voice packet structure for IL-2 SRS (UDP):
            # - Packet ID (8 bytes, uint64)
            # - Client GUID (variable length string, UTF-8 encoded, null-terminated)
            # - Opus Audio (the rest of the packet)

            self.voice_packet_id += 1
            
            # Pack the header
            guid_bytes = self.client_guid.encode('utf-8') + b'\x00'
            header = struct.pack('<Q', self.voice_packet_id) + guid_bytes

            # Construct the full UDP packet
            packet = header + encoded_opus_packet

            # Send to the server using the UDP socket
            self.udp_sock.sendto(packet, (self.server_address, self.server_port))

        except Exception as e:
            print(f"Error sending voice packet: {e}")
            self.disconnect()

    def send_radio_update(self, radio1_channel: int, radio2_channel: int):
        """
        Sends the current radio channel selection to the server.
        This must be called whenever the user changes their active radio channels.

        Args:
            radio1_channel (int): The selected channel for Radio 1.
            radio2_channel (int): The selected channel for Radio 2.
        """
        if not self.is_running or not self.tcp_sock:
            return

        try:
            # The server expects radio updates via the JSON protocol.
            client_data = {
                "GameState": {
                    "radios": [
                        {"channel": radio1_channel, "freq": 0, "secFreq": 0, "retransmit": False, "volume": 1.0, "modulation": 0, "name": "Radio 1"},
                        {"channel": radio2_channel, "freq": 0, "secFreq": 0, "retransmit": False, "volume": 1.0, "modulation": 0, "name": "Radio 2"}
                    ],
                    "control": 0,
                    "onboard": False,
                    "ptt": False
                }
            }
            self._send_json_message(JSON_MSG_TYPE_RADIO_UPDATE, client_data)
            #print("Radio update sent.") # This can be noisy, commenting out.
        except Exception as e:
            print(f"Error sending radio update: {e}")
            self.disconnect()

    def _send_ping(self):
        """Sends a ping packet to the server to maintain the connection."""
        self._send_json_message(JSON_MSG_TYPE_PING)

if __name__ == '__main__':
    # This block provides a simple test utility for the SrsClient.

    def run_test_client():
        """Runs the SrsClient to test its functionality."""
        
        def audio_callback(voice_data: ReceivedVoice):
            print(f"[Test Client] Received audio from GUID: {voice_data.sender_guid}, Payload size: {len(voice_data.audio_payload)}")

        client = SrsClient(
            server_address='tacticalairwar.com',
            server_port=6002,
            pilot_name="TestPilot",
            received_audio_callback=audio_callback
        )

        try:
            client.connect()
            if not client.is_running:
                print("[Test Client] FAILED to connect.")
                return

            time.sleep(1) # Give time for threads to work
            client.send_radio_update(radio1_channel=1, radio2_channel=2)
            print("[Test Client] Sent radio update.")
            print("[Test Client] Now listening for messages from the server. Press Ctrl+C to disconnect.")

            # Keep the main thread alive to allow background threads to receive data
            while client.is_running:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n[Test Client] Keyboard interrupt received, disconnecting.")
        finally:
            if client and client.is_running:
                client.disconnect()
            print("[Test Client] Test finished.")

    # Run the test
    run_test_client()