"""
title: OpenRouter Free Model Smart Retry
author: assistant
version: 1.0.0
description: Elegant retry handler for OpenRouter free models with proper streaming and notifications
"""

import time
import json
import asyncio
import logging
from typing import Optional, Union, Generator, Iterator, Dict, Any
from pydantic import BaseModel, Field
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class Pipe:
    """OpenRouter free model retry handler with clean streaming support"""
    
    class Valves(BaseModel):
        OPENROUTER_API_BASE_URL: str = Field(
            default="https://openrouter.ai/api/v1",
            description="OpenRouter API base URL"
        )
        OPENROUTER_API_KEY: str = Field(
            default="",
            description="OpenRouter API key (required)"
        )
        NAME_PREFIX: str = Field(
            default="OR-Free/",
            description="Prefix for model names"
        )
        MAX_RETRIES: int = Field(
            default=10,
            description="Maximum number of retry attempts"
        )
        BASE_DELAY: float = Field(
            default=2.0,
            description="Base delay in seconds (will use exponential backoff)"
        )
        MAX_DELAY: float = Field(
            default=30.0,
            description="Maximum delay between retries in seconds"
        )
        ENABLE_NOTIFICATIONS: bool = Field(
            default=True,
            description="Show retry notifications in UI"
        )

    class UserValves(BaseModel):
        OPENROUTER_API_KEY: str = Field(
            default="",
            description="User's personal OpenRouter API key"
        )

    def __init__(self):
        self.type = "manifold"
        self.valves = self.Valves()
        self.retry_state = {}  # Track retry state per request

    def pipes(self) -> list:
        """Return only free models from OpenRouter"""
        api_key = self.valves.OPENROUTER_API_KEY
        
        if not api_key:
            return [{
                "id": "error",
                "name": "⚠️ No API Key - Configure in Settings"
            }]
        
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.valves.OPENROUTER_API_BASE_URL}/models",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                return [{
                    "id": "error",
                    "name": f"⚠️ API Error: {response.status_code}"
                }]
            
            models = response.json()
            free_models = []
            
            # Filter and format free models
            for model in models.get("data", []):
                model_id = model.get("id", "")
                model_name = model.get("name", model_id)
                
                # Only include free models
                if model_name.endswith("(free)"):
                    free_models.append({
                        "id": model_id,
                        "name": f"{self.valves.NAME_PREFIX}{model_name}"
                    })
            
            # Sort alphabetically
            free_models.sort(key=lambda x: x["name"].lower())
            
            if not free_models:
                return [{
                    "id": "error",
                    "name": "⚠️ No free models available"
                }]
            
            return free_models
            
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return [{
                "id": "error",
                "name": f"⚠️ Error: {str(e)}"
            }]

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        if attempt == 0:
            return 0
        
        # Exponential backoff: 2^attempt * base_delay
        delay = min(
            self.valves.BASE_DELAY * (2 ** (attempt - 1)),
            self.valves.MAX_DELAY
        )
        
        # Add jitter (±20%) to prevent thundering herd
        import random
        jitter = delay * 0.2 * (2 * random.random() - 1)
        
        return max(0.1, delay + jitter)

    def _send_notification(self, __event_emitter__, message: str, level: str = "info"):
        """Send notification to UI if enabled"""
        if not self.valves.ENABLE_NOTIFICATIONS:
            return
        
        if __event_emitter__ and hasattr(__event_emitter__, 'emit'):
            try:
                # Try to emit a status event
                __event_emitter__.emit(
                    "status",
                    {
                        "type": level,
                        "message": message,
                        "timestamp": datetime.now().isoformat()
                    }
                )
            except:
                # Fallback to message event
                try:
                    __event_emitter__.emit(
                        "message",
                        {"content": f"[{level.upper()}] {message}"}
                    )
                except:
                    pass

    def _make_request(
        self,
        url: str,
        headers: dict,
        payload: dict,
        stream: bool = False,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """Make HTTP request with proper error handling"""
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                stream=stream,
                timeout=timeout
            )
            
            return {
                "status_code": response.status_code,
                "response": response,
                "stream": stream
            }
            
        except requests.exceptions.Timeout:
            return {"error": "Request timeout", "status_code": 408}
        except requests.exceptions.ConnectionError:
            return {"error": "Connection error", "status_code": 503}
        except Exception as e:
            return {"error": str(e), "status_code": 500}

    def _handle_streaming_response(self, response) -> Generator:
        """Handle streaming response without corruption"""
        try:
            for line in response.iter_lines():
                if line:
                    # Decode the line
                    line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                    
                    # Skip empty lines or OpenRouter artifacts
                    if (not line_str.strip() or 
                        ": OPENROUTER PROCESSING" in line_str or
                        line_str.strip() == "data: [DONE]"):
                        continue
                    
                    # Pass through valid SSE data
                    if line_str.startswith("data: "):
                        try:
                            # Validate it's proper JSON
                            data_part = line_str[6:]  # Remove "data: "
                            if data_part.strip() and data_part.strip() != "[DONE]":
                                json.loads(data_part)  # Validate JSON
                            yield line_str + "\n"
                        except json.JSONDecodeError:
                            # Skip malformed JSON
                            continue
                    else:
                        # Pass through other valid lines
                        yield line_str + "\n"
                        
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {{\"error\": \"Stream processing error: {str(e)}\"}}\n\n"

    def _handle_non_streaming_response(self, response) -> Dict[str, Any]:
        """Handle non-streaming response"""
        try:
            data = response.json()
            
            # Clean any artifacts from response
            if "choices" in data:
                for choice in data["choices"]:
                    if "message" in choice and "content" in choice["message"]:
                        content = choice["message"]["content"]
                        # Remove any OpenRouter artifacts
                        content = content.replace(": OPENROUTER PROCESSING", "")
                        choice["message"]["content"] = content.strip()
            
            return data
            
        except json.JSONDecodeError:
            return {"error": {"message": "Invalid JSON response"}}

    def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None
    ) -> Union[str, Generator, Iterator, dict]:
        """Main pipe handler with retry logic"""
        
        # Get API key (user's or global). Support both dict and object (Pydantic) forms.
        api_key = None
        if __user__:
            # Attempt to extract a 'valves' object whether __user__ is a dict or an object
            valves_obj = None
            if isinstance(__user__, dict):
                valves_obj = __user__.get("valves")
            else:
                valves_obj = getattr(__user__, "valves", None)
            if valves_obj:
                if isinstance(valves_obj, dict):
                    api_key = valves_obj.get("OPENROUTER_API_KEY")
                else:
                    api_key = getattr(valves_obj, "OPENROUTER_API_KEY", None)
        if not api_key:
            api_key = self.valves.OPENROUTER_API_KEY
        
        if not api_key:
            return {"error": {"message": "OpenRouter API key not configured"}}
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openwebui.com",
            "X-Title": "Open WebUI"
        }
        
        # Extract actual model ID
        model_id = body.get("model", "")
        if "." in model_id:
            model_id = model_id.split(".", 1)[1]
        
        # Update payload
        payload = {**body, "model": model_id}
        is_streaming = body.get("stream", False)
        
        # Retry logic
        url = f"{self.valves.OPENROUTER_API_BASE_URL}/chat/completions"
        attempt = 0
        last_error = None
        
        while attempt <= self.valves.MAX_RETRIES:
            if attempt > 0:
                delay = self._calculate_delay(attempt)
                
                # Log and notify about retry
                retry_msg = f"Rate limited - Retry {attempt}/{self.valves.MAX_RETRIES} in {delay:.1f}s"
                logger.info(retry_msg)
                self._send_notification(__event_emitter__, retry_msg, "warning")
                
                time.sleep(delay)
            
            # Make request
            result = self._make_request(url, headers, payload, is_streaming)
            
            # Check for errors
            if "error" in result:
                last_error = result["error"]
                attempt += 1
                continue
            
            status_code = result.get("status_code")
            response = result.get("response")
            
            # Handle 429 rate limit
            if status_code == 429:
                attempt += 1
                if attempt > self.valves.MAX_RETRIES:
                    error_msg = f"Max retries ({self.valves.MAX_RETRIES}) exceeded"
                    logger.error(error_msg)
                    self._send_notification(__event_emitter__, error_msg, "error")
                    return {"error": {"message": error_msg}}
                continue
            
            # Handle other errors
            if status_code >= 400:
                try:
                    error_data = response.json()
                    return error_data
                except:
                    return {"error": {"message": f"HTTP {status_code} error"}}
            
            # Success! Notify if we had retries
            if attempt > 0:
                success_msg = f"Successfully connected after {attempt} retries"
                logger.info(success_msg)
                self._send_notification(__event_emitter__, success_msg, "success")
            
            # Return appropriate response
            if is_streaming:
                return self._handle_streaming_response(response)
            else:
                return self._handle_non_streaming_response(response)
        
        # Max retries exceeded
        error_msg = f"Failed after {self.valves.MAX_RETRIES} retries. Last error: {last_error}"
        logger.error(error_msg)
        self._send_notification(__event_emitter__, error_msg, "error")
        return {"error": {"message": error_msg}}