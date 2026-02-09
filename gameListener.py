import socket
import struct

# Constants based on the C# code and IL-2 SRS documentation
UDP_PORT = 4322
SRS_ADDRESS_MSG_TYPE = 12
CLIENT_DATA_MSG_TYPE = 13


def find_srs_data_from_packet(data: bytes):
    """
    Parses a raw UDP packet from IL-2
        finds SRS address and pilot name

    Args:
        data: The raw bytes received from the UDP socket.

    Returns:
        A tuple containing (srs_address, pilot_name). Either can be None
        if not found in the packet.
    """
    try:
        # In C#, a MemoryStream is used. In Python, we can simply track our
        # position in the byte array with an 'offset' variable.

        # C#: stream.Seek(10, SeekOrigin.Current);
        # The first 10 bytes are a header we can skip.
        offset = 10

        # C#: int indicatorCount = stream.ReadByte();
        # The next byte tells us how many "indicator structs" there are.
        indicator_count, = struct.unpack_from('<B', data, offset)
        offset += 1

        # This loop skips over all the indicator data blocks.
        for _ in range(indicator_count):
            # C#: stream.Seek(2, SeekOrigin.Current);
            offset += 2
            # C#: uint indicators = (uint) stream.ReadByte();
            indicators, = struct.unpack_from('<B', data, offset)
            offset += 1
            # C#: stream.Seek(4*indicators, SeekOrigin.Current);
            offset += (4 * indicators)

        # C#: int eventCount = stream.ReadByte();
        # Now we've reached the event data. This byte tells us how many events follow.
        event_count, = struct.unpack_from('<B', data, offset)
        offset += 1

        srs_address = None
        pilot_name = None

        # Loop through each event to find the one we want.
        for _ in range(event_count):
            # C#: int msgTypeInt = BitConverter.ToUInt16(new[] {part1, part2}, 0);
            # The message type is a 2-byte unsigned short (little-endian).
            msg_type, = struct.unpack_from('<H', data, offset)
            offset += 2

            # C#: uint eventSize = (uint) stream.ReadByte();
            # The event size is a 1-byte unsigned integer.
            event_size, = struct.unpack_from('<B', data, offset)
            offset += 1

            if msg_type == SRS_ADDRESS_MSG_TYPE:
                # We found it! The payload of this event is the address string.
                payload_bytes = data[offset : offset + event_size]
                # The string is ASCII and terminated by a null character (\x00).
                srs_address = payload_bytes.split(b'\x00', 1)[0].decode('ascii')
            if msg_type == CLIENT_DATA_MSG_TYPE:
                # We found it!
                """struct STClientData{
                        long nClientID, //User's ClientID
                        nServerClientID; //Server's ClientID
                        char sPlayerName[32];
                };"""
                #payload_bytes = data[offset +8 : offset + event_size]
                # The format is two 4-byte signed longs and a 32-byte char array.
                # '<' for little-endian, 'l' for signed long, '32s' for 32-byte string.
                client_id, server_client_id, pilot_name_bytes = struct.unpack_from('<ll32s', data, offset)
                
                # Decode the name and strip any trailing null bytes.
                pilot_name = pilot_name_bytes.split(b'\x00', 1)[0].decode('ascii', 'ignore')

            # If it's not the message we want, skip its data to get to the next event.
            offset += event_size
            
    except (struct.error, IndexError):
        # This can happen if we receive a packet that is malformed or not from the game.
        # We just ignore it and wait for the next one.
        return None

    return srs_address, pilot_name

def listen_for_game_data():
    """
    Opens a UDP socket and listens for game data from IL-2.

    This function binds to the standard IL-2 UDP port and continuously
    listens for packets. Each packet is passed to the parser function.
    Once the SRS address is successfully found and parsed, the function
    returns the address.

    Returns:
        A tuple (srs_address, pilot_name) once both have been found.
    """
    # Create a UDP socket (AF_INET for IPv4, SOCK_DGRAM for UDP)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # Bind the socket to all available network interfaces on the specified port.
        try:
            sock.bind(("", UDP_PORT))
            print("socket bound")
        except OSError as e:
            print(f"FATAL: Could not bind to UDP port {UDP_PORT}.")
            print(f"Error: {e}")
            print("\nThis usually means another program (like another SRS client) is already running.")
            print("Please close any other SRS applications and try again.")
            return None

        print(f"Listening for IL-2 game data on UDP port {UDP_PORT}...")
        found_srs_address = None
        found_pilot_name = None

        while not (found_srs_address and found_pilot_name):
            # Wait and receive a packet. 2048 is a safe buffer size.
            data, _ = sock.recvfrom(2048)
            
            srs_address, pilot_name = find_srs_data_from_packet(data)

            if srs_address and not found_srs_address:
                found_srs_address = srs_address
                print(f"Success! Found SRS Server Address: {found_srs_address}")
            
            if pilot_name and not found_pilot_name:
                found_pilot_name = pilot_name
                print(f"Success! Found Pilot Name: {found_pilot_name}")
        
        return found_srs_address, found_pilot_name

if __name__ == '__main__':
    # This block allows you to test the listener by running the file directly.
    print("gameListener.py started")
    listen_for_game_data()