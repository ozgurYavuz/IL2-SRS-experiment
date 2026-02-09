import sounddevice as sd
import numpy as np
import pyogg
import time

# Constants for audio processing. SRS uses a 48kHz sample rate.
SAMPLE_RATE = 48000
# A common block size for VoIP applications (e.g., 10ms frames for Opus codec)
# 48000 Hz * 0.010 s = 480 frames
BLOCK_SIZE = 480

class AudioManager:
    """
    Manages audio input and output streams using sounddevice.
    """
    def __init__(self, input_device: str, output_device: str, encoded_mic_callback: callable, speaker_boost_db: int = 0):
        """
        Initializes the AudioManager.

        Args:
            input_device: The name or index of the input device.
            output_device: The name or index of the output device.
            encoded_mic_callback: The function to call with Opus-encoded microphone data.
            speaker_boost_db: amount to increase or decrease speaker volume in decibels
        """
        self.input_device = input_device
        self.output_device = output_device
        self.encoded_mic_callback = encoded_mic_callback

        self.input_stream = None
        self.output_stream = None

        # Correctly initialize the encoder and decoder using pyogg's API

        _encoder = pyogg.OpusEncoder()
        _encoder.set_sampling_frequency(SAMPLE_RATE)
        _encoder.set_application('voip')
        _encoder.set_channels(1)
        self.encoder = _encoder
        _decoder = pyogg.OpusDecoder()
        _decoder.set_sampling_frequency(SAMPLE_RATE)
        _decoder.set_channels(1)
        self.decoder = _decoder
        self.speaker_boost_db = speaker_boost_db

    def _mic_callback(self, indata: np.ndarray, frames: int, time, status: sd.CallbackFlags):
        """Internal callback to handle raw audio from sounddevice."""
        if status:
            print(f"Microphone capture status: {status}")
        
        # Encode the raw audio and pass the compressed packet to the external callback
        encoded_packet = self.encoder.encode(indata.tobytes())
        self.encoded_mic_callback(encoded_packet)

    def start_capture(self):
        """Starts capturing audio from the microphone."""
        if self.input_stream:
            print("Capture already running.")
            return

        print(f"Starting microphone capture on device: {self.input_device}")
        try:
            self.input_stream = sd.InputStream(
                device=self.input_device,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype='int16', # Changed from float32 to int16 for consistency
                blocksize=BLOCK_SIZE,
                callback=self._mic_callback
            )
            self.input_stream.start()
            print("Microphone capture started successfully.")
        except Exception as e:
            print(f"FATAL: Could not start microphone capture: {e}")
            self.input_stream = None

    def stop_capture(self):
        """Stops the microphone capture stream."""
        if not self.input_stream:
            return
        self.input_stream.stop()
        self.input_stream.close()
        self.input_stream = None
        print("Microphone capture stopped.")

    def play_audio(self, encoded_packet: bytes):
        """Decodes an Opus packet and plays it on the output device."""
        # This is a simplified playback method. For a real client, we'll need a buffer.
        if not self.output_stream:
            # Start the output stream on the first playback request
            try:
                self.output_stream = sd.OutputStream(
                    device=self.output_device,
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype='int16',
                    blocksize=BLOCK_SIZE
                )
                self.output_stream.start()
            except Exception as e:
                print(f"FATAL: Could not start audio playback: {e}")
                self.output_stream = None
                return

        # Decode the packet and play it
        decoded_pcm = self.decoder.decode(encoded_packet)
        if decoded_pcm:
            # Convert the raw bytes from the decoder into a NumPy array of int16
            audio_array = np.frombuffer(decoded_pcm, dtype=np.int16)
            # Reshape the array to be 2D: (n_samples, n_channels) which is (480, 1) here.

            # Apply speaker boost
            float_array = audio_array.astype(np.float32) / 32768.0 # Normalize to -1.0 to 1.0
            float_array *= 10 ** (self.speaker_boost_db / 20) # Apply boost
            float_array = np.clip(float_array, -1.0, 1.0) # Clamp to prevent clipping
            audio_array = (float_array * 32767.0).astype(np.int16) # Denormalize and convert back

            # Reshape the array to be 2D: (n_samples, n_channels) which is (480, 1) here.
            self.output_stream.write(audio_array.reshape(-1, 1))

def list_audio_devices():
    """A utility function to print all available audio devices."""
    print("Available audio devices:")
    print(sd.query_devices())

def test_sine_wave_playback(frequency=440, duration_seconds=5):
    """
    Generates a sine wave, encodes it, decodes it, and plays it back.
    This is a deterministic test to verify the encode/decode pipeline
    without involving a microphone. A clean tone indicates the audio
    output and codec logic are correct.
    """
    print(f"\n--- Testing Sine Wave ({frequency} Hz) Playback ---")
    print("If this tone sounds clean, the audio output pipeline is working correctly.")
    print("Any remaining noise issues are likely related to microphone/input settings.")

    # 1. Generate Sine Wave data
    # We will use 'int16' as it's a very common and compatible audio format.
    # The amplitude is scaled to fit within the range of a 16-bit integer.
    amplitude = 0.2 * 32767

    # Generate a time array for the duration of the sound
    t = np.linspace(0., duration_seconds, int(SAMPLE_RATE * duration_seconds), endpoint=False)
    # Generate the sine wave data as int16
    sine_data = (amplitude * np.sin(2. * np.pi * frequency * t)).astype(np.int16)

    # 2. Setup Encoder, Decoder
    encoder = pyogg.OpusEncoder()
    encoder.set_application('voip')
    encoder.set_sampling_frequency(SAMPLE_RATE)
    encoder.set_channels(1)

    decoder = pyogg.OpusDecoder()
    decoder.set_sampling_frequency(SAMPLE_RATE)
    decoder.set_channels(1)

    try:
        # 3. Setup Output Stream
        with sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=BLOCK_SIZE) as stream:
            print(f"Playing {duration_seconds}-second tone...")
            # 4. Process the sine wave in chunks
            for i in range(0, len(sine_data), BLOCK_SIZE):
                chunk = sine_data[i:i+BLOCK_SIZE]

                # If the last chunk is smaller than BLOCK_SIZE, pad it with silence
                if len(chunk) < BLOCK_SIZE:
                    chunk = np.pad(chunk, (0, BLOCK_SIZE - len(chunk)), 'constant')

                # Encode -> Decode
                encoded_packet = encoder.encode(chunk.tobytes())
                decoded_pcm = decoder.decode(encoded_packet)

                if decoded_pcm:
                    # Prepare for playback and write to the stream
                    playback_array = np.frombuffer(decoded_pcm, dtype=np.int16)
                    stream.write(playback_array.reshape(-1, 1))
            print("Sine wave test finished.")
    except Exception as e:
        print(f"An error occurred during the sine wave test: {e}")

def test_microphone_loopback():
    """
    Captures audio from the microphone, encodes it, decodes it, and plays it back.
    This tests the full AudioManager pipeline using the corrected int16 data type.
    """
    print("\n--- Testing Microphone Loopback ---")
    print("Speak into your microphone. You should hear your own voice.")
    print("If the audio is noisy, check your OS microphone gain/boost settings.")
    print("Press Ctrl+C to stop the test.")

    # This list will act as a simple queue between our mic and speaker
    audio_queue = []

    def my_mic_handler(encoded_packet):
        """This function gets called by the AudioManager with encoded audio."""
        audio_queue.append(encoded_packet)

    # Instantiate the manager with our handler, using default devices and no boost.
    manager = AudioManager(
        input_device=None,
        output_device=None,
        encoded_mic_callback=my_mic_handler,
        speaker_boost_db=0
    )
    manager.start_capture()

    try:
        while True:
            if audio_queue:
                packet = audio_queue.pop(0)
                manager.play_audio(packet)
            # A small sleep is important to prevent this loop from consuming 100% CPU.
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("\nMicrophone loopback test stopped by user.")
    finally:
        manager.stop_capture()

if __name__ == '__main__':
    print("--- AudioManager Test Utility ---")
    list_audio_devices()

    # Run the deterministic sine wave test first to confirm the output pipeline.
    test_sine_wave_playback()

    # Now, run the full microphone loopback test.
    test_microphone_loopback()