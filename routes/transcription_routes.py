from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Response
from typing import Dict
import httpx
import os
import logging
from datetime import datetime
from dependencies.auth import get_current_user
from database.models import User

router = APIRouter(tags=["transcription"])
logger = logging.getLogger(__name__)

@router.post("/audio")
async def transcribe_audio(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Transcribe audio using Deepgram API
    Returns an empty transcript if transcription fails rather than throwing an error
    """
    try:
        # Get API key from environment
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            logger.error("DEEPGRAM_API_KEY not found in environment variables")
            return {"transcript": ""}
        
        # Verify content type
        content_type = audio.content_type or "audio/wav"
        logger.info(f"Audio content type: {content_type}")
        
        # Check if content type is supported
        if not content_type.startswith("audio/"):
            logger.warning(f"Unexpected content type: {content_type}, proceeding anyway")
        
        # Read audio file content
        audio_data = await audio.read()
        if not audio_data:
            logger.warning("Empty audio file received")
            return {"transcript": ""}
        
        # Log the audio size
        logger.info(f"Received audio file: {len(audio_data)} bytes from user ID {current_user.id}")
        
        # Call Deepgram API
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Token {api_key}",
                "Content-Type": content_type
            }
            
            # Use nova-3 model with smart formatting
            url = "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true"
            
            logger.info(f"Sending request to Deepgram API: {url}")
            
            try:
                # Send request to Deepgram
                response = await client.post(
                    url=url,
                    headers=headers,
                    content=audio_data,
                    timeout=30.0  # 30 seconds timeout
                )
                
                # Check for errors
                if response.status_code != 200:
                    logger.error(f"Deepgram API error: {response.status_code} - {response.text}")
                    return {"transcript": ""}
                
                # Parse response
                result = response.json()
                
                # Extract transcription
                if result and "results" in result and "channels" in result["results"]:
                    transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]
                    logger.info(f"Successfully transcribed audio: '{transcript[:50]}{'...' if len(transcript) > 50 else ''}'")
                    return {"transcript": transcript}
                else:
                    logger.error(f"Unexpected response format: {result}")
                    return {"transcript": ""}
                    
            except Exception as request_error:
                logger.error(f"Error calling Deepgram API: {str(request_error)}")
                return {"transcript": ""}
    
    except Exception as e:
        logger.error(f"Error during transcription process: {str(e)}")
        return {"transcript": ""}
