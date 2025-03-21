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


    async def get_transcription(self, filename: str):
        # Configure OpenAI with Azure settings
        openai.api_type = "azure"
        openai.api_base = os.environ['AOAI_WHISPER_ENDPOINT']
        openai.api_key = os.environ['AOAI_WHISPER_KEY']
        openai.api_version = "2023-09-01-preview"

        # Specify the model and deployment ID for the transcription
        #model_name = os.environ['AOAI_WHISPER_MODEL_TYPE']  # "whisper-1"
        deployment_id = os.environ['AOAI_WHISPER_MODEL']

        # Specify the language of the audio
        #audio_language = "en"

        # Initialize an empty string to store the transcript
        transcript = ''

        client = AzureOpenAI(
            api_key=os.environ['AOAI_WHISPER_KEY'], azure_endpoint=os.environ['AOAI_WHISPER_ENDPOINT'], api_version="2024-02-01"
       )

        # Check the file size
        file_size = os.path.getsize(filename)
        max_size = 20 * 1024 * 1024  # 25 MB in bytes

        if file_size > max_size:
            logging.info(f"File {filename} is {file_size / (1024 * 1024):.2f} MB, exceeding the 25 MB limit. Splitting into chunks.")
            
            # Load the audio file
            try:
                AudioSegment.converter = r"C:\Users\scrutz\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe" #Needed to run local with Windows
                audio = AudioSegment.from_mp3(filename)
            except Exception as e:
                logging.error(f"Failed to load audio file: {e}")
                raise Exception(f"Failed to load audio file for chunking: {e}")
            
            # Get original file extension for format preservation
            file_extension = os.path.splitext(filename)[1]
            if not file_extension:
                file_extension = ".mp3"  # Default to mp3 if no extension found
            
            # Remove the dot from extension for format parameter
            export_format = file_extension[1:] if file_extension.startswith('.') else file_extension
            
            # Calculate number of chunks needed (aim for ~20MB chunks to be safe)
            target_chunk_size = 20 * 1024 * 1024  # 20 MB
            num_chunks = max(1, math.ceil(file_size / target_chunk_size))
            chunk_duration = len(audio) / num_chunks
            
            logging.info(f"Audio duration: {len(audio)/1000:.2f} seconds, splitting into {num_chunks} chunks of {chunk_duration/1000:.2f} seconds each")
            
            # Process in chunks
            transcript_chunks = []
            
            for i in range(num_chunks):
                start_time = int(i * chunk_duration)
                end_time = int(min(len(audio), (i + 1) * chunk_duration))
                
                logging.info(f"Processing chunk {i+1}/{num_chunks}: {start_time/1000:.2f}s to {end_time/1000:.2f}s")
                
                # Extract chunk
                chunk = audio[start_time:end_time]
                
                # Save chunk to temporary file using original format
                with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                    temp_filename = temp_file.name
                    chunk.export(temp_filename, format=export_format)
                
                try:
                    # Process chunk with OpenAI
                    chunk_transcript = ""
                    chunk_transcribed = False
                    
                    while not chunk_transcribed:
                        try:
                            with open(temp_filename, "rb") as audio_file:
                                result = client.audio.transcriptions.create(
                                    file=audio_file, 
                                    model=deployment_id
                                )
                            chunk_transcript = result.text
                            chunk_transcribed = True
                            logging.info(f"Successfully transcribed chunk {i+1}/{num_chunks}")
                        except Exception as e:
                            if 'Maximum content size limit' in str(e):
                                raise e
                            logging.error(f"Error transcribing chunk {i+1}/{num_chunks}: {e}")
                            time.sleep(10)
                    
                    transcript_chunks.append(chunk_transcript)
                finally:
                    # Clean up temporary file
                    if os.path.exists(temp_filename):
                        try:
                            os.remove(temp_filename)
                        except Exception as e:
                            logging.warning(f"Failed to remove temporary file {temp_filename}: {e}")
            
            # Combine all transcriptions
            transcript = " ".join(transcript_chunks)
            logging.info(f"Successfully combined {len(transcript_chunks)} transcript chunks.")
        else:
            # For files under 25 MB
            transcribed = False
            while not transcribed:
                try:
                    result = client.audio.transcriptions.create(file=open(filename, "rb"), model=deployment_id)
                    transcript = result.text
                    transcribed = True
                except Exception as e:
                    if 'Maximum content size limit' in str(e):
                        raise e
                    logging.error(e)
                    time.sleep(10)
                    pass

        # If a transcript was generated, return it
        if len(transcript) > 0:
           return transcript

        # If no transcript was generated, raise an exception
        raise Exception("No transcript generated")
