import datetime
from pathlib import Path
import time
import json
import openai
import os
from openai import AzureOpenAI
import requests
import re
import logging
from dotenv import load_dotenv
import math
from pydub import AudioSegment
import tempfile

class TranscriptionService:

    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        

    def convert_media_to_mp3(self, filename: str):

        file_path = Path(filename)
        media_extensions = [".mp4", ".mpeg", ".m4a", ".wav", ".webm"]

        if file_path.suffix.lower() in media_extensions:
            logging.info(
                f"Detected video file ({file_path.suffix}). Converting to MP3 format.")
            try:
                # Create a temporary MP3 file for the conversion result
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_wav:
                    mp3_filename = tmp_wav.name
                # Ensure ffmpeg is correctly set (update the path as needed)
                AudioSegment.converter = r"C:\Users\scrutz\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
                # Load the video file (pydub will extract the audio track)
                audio = AudioSegment.from_file(filename)
                # Reduce audio quality to minimize file size
                # Convert to mono (1 channel)
                audio = audio.set_channels(1)
                # Reduce sample rate to 16kHz (sufficient for speech recognition)
                audio = audio.set_frame_rate(16000)
                # Export with reduced quality settings
                audio.export(mp3_filename, format="mp3", bitrate="32k")
                logging.info("Conversion to MP3 successful.")
                # Return the new WAV file
                return mp3_filename
            except Exception as e:
                logging.error(f"Conversion to MP3 failed: {e}")
            raise Exception("Conversion to MP3 failed")

        # Return the original filename if not a video file
        return filename

    async def get_transcription(self, filename, max_retries=5):
        # Store original filename
        original_filename = filename
        files_to_delete = []

        try:
            # Configure OpenAI with Azure settings
            openai.api_type = "azure"
            openai.api_base = os.environ['AOAI_WHISPER_ENDPOINT']
            openai.api_key = os.environ['AOAI_WHISPER_KEY']
            openai.api_version = "2023-09-01-preview"

            deployment_id = os.environ['AOAI_WHISPER_MODEL']

            transcript = ''

            client = AzureOpenAI(
                api_key=os.environ['AOAI_WHISPER_KEY'],
                azure_endpoint=os.environ['AOAI_WHISPER_ENDPOINT'],
                api_version="2024-02-01"
            )

            # Convert video to MP3
            converted_filename = self.convert_media_to_mp3(filename)
            if converted_filename != original_filename:
                files_to_delete.append(converted_filename)

            filename = converted_filename

            # Check the file size
            file_size = os.path.getsize(filename)
            max_size = 25 * 1024 * 1024  # 25 MB in bytes

            if file_size > max_size:
                logging.info(
                    f"File {filename} is {file_size / (1024 * 1024):.2f} MB, exceeding the 20 MB limit. Splitting into chunks.")

                try:
                    AudioSegment.converter = r"C:\Users\scrutz\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"  # Needed for Windows
                    audio = AudioSegment.from_file(filename)
                except Exception as e:
                    logging.error(f"Failed to load audio file: {e}")
                    raise Exception(f"Failed to load audio file for chunking: {e}")

                # Preserve original file extension for export (will be '.wav' if converted)
                file_extension = os.path.splitext(filename)[1]

                # Calculate number of chunks needed (aiming for ~20MB chunks)
                target_chunk_size = 20 * 1024 * 1024  # 20 MB
                num_chunks = max(1, math.ceil(file_size / target_chunk_size))
                chunk_duration = len(audio) / num_chunks

                logging.info(
                    f"Audio duration: {len(audio)/1000:.2f} seconds, splitting into {num_chunks} chunks of {chunk_duration/1000:.2f} seconds each")

                transcript_chunks = []

                for i in range(num_chunks):
                    start_time = int(i * chunk_duration)
                    end_time = int(min(len(audio), (i + 1) * chunk_duration))

                    logging.info(
                        f"Processing chunk {i+1}/{num_chunks}: {start_time/1000:.2f}s to {end_time/1000:.2f}s")

                    # Extract the chunk from the audio
                    chunk = audio[start_time:end_time]

                    # Save the chunk to a temporary file using the original format
                    with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                        temp_filename = temp_file.name
                        chunk.export(temp_filename, format=file_extension)

                    try:
                        chunk_transcribed = False
                        retry_count = 0
                        while not chunk_transcribed and retry_count < max_retries:
                            try:
                                with open(temp_filename, "rb") as audio_file:
                                    result = client.audio.transcriptions.create(
                                        file=audio_file,
                                        model=deployment_id
                                      )
                                chunk_transcript = result.text
                                chunk_transcribed = True
                                logging.info(
                                    f"Successfully transcribed chunk {i+1}/{num_chunks}")
                            except Exception as e:
                                if 'Maximum content size limit' in str(e):
                                    raise e
                                retry_count += 1
                                logging.error(
                                    f"Error transcribing chunk {i+1}/{num_chunks}: {e} (Attempt {retry_count}/{max_retries})")
                                if retry_count >= max_retries:
                                    raise Exception(f"Max retries ({max_retries}) reached while transcribing chunk {i+1}")
                                time.sleep(10)
                        transcript_chunks.append(chunk_transcript)
                    finally:
                        # Clean up the temporary chunk file
                        if os.path.exists(temp_filename):
                            try:
                                os.remove(temp_filename)
                            except Exception as e:
                                logging.warning(
                                    f"Failed to remove temporary file {temp_filename}: {e}")

                # Combine the transcriptions from each chunk
                transcript = " ".join(transcript_chunks)
                logging.info(
                    f"Successfully combined {len(transcript_chunks)} transcript chunks.")
            else:
                transcribed = False
                retry_count = 0
                while not transcribed and retry_count < max_retries:
                    try:
                        with open(filename, "rb") as f:
                            result = client.audio.transcriptions.create(
                                file=f, model=deployment_id)
                        transcript = result.text
                        transcribed = True
                    except Exception as e:
                        if 'Maximum content size limit' in str(e):
                            raise e
                        retry_count += 1
                        logging.error(f"Error during transcription: {e} (Attempt {retry_count}/{max_retries})")
                        if retry_count >= max_retries:
                            raise Exception(f"Max retries ({max_retries}) reached while transcribing file")
                        time.sleep(10)

            if len(transcript) > 0:
                return transcript

            raise Exception("No transcript generated")

        finally:
            # Clean up files
            files_to_delete.append(original_filename)

            # Using set to avoid duplicates
            for file_to_delete in set(files_to_delete):
                if os.path.exists(file_to_delete):
                    try:
                        os.remove(file_to_delete)
                        logging.info(f"Deleted file: {file_to_delete}")
                    except Exception as e:
                        logging.warning(
                            f"Failed to delete file {file_to_delete}: {e}") 