"""
title: OpenRouter Free Model Retry Pipe
author: tamarindmonkey
author_url: https://github.com/tamarindmonkey
funding_url: https://github.com/tamarindmonkey
version: 0.1.9
"""

import time
from pydantic import BaseModel, Field
from typing import Optional, Union, Generator, Iterator
import requests
import json


class Pipe:
    class Valves(BaseModel):
        NAME_PREFIX: str = Field(
            default="OpenRouter/",
            description="The prefix applied before the model names.",
        )
        OPENROUTER_API_BASE_URL: str = Field(
            default="https://openrouter.ai/api/v1",
            description="The base URL for OpenRouter API endpoints.",
        )
        OPENROUTER_API_KEY: str = Field(
            default="",
            description="Required API key to retrieve the model list.",
        )
        # Retry configuration
        first_retry_delay: float = Field(
            default=3.0, description="Delay in seconds for the first retry"
        )
        short_retry_count: int = Field(
            default=10, description="Number of short retries"
        )
        short_retry_delay: float = Field(
            default=2.0, description="Delay in seconds for short retries"
        )
        long_retry_count: int = Field(
            default=20, description="Number of long retries"
        )
        long_retry_delay: float = Field(
            default=4.0, description="Delay in seconds for long retries"
        )
        fallback_delay: float = Field(
            default=60.0,
            description="Delay in seconds before fallback retry sequence",
        )
        pass

    class UserValves(BaseModel):
        OPENROUTER_API_KEY: str = Field(
            default="",
            description="User-specific API key for accessing OpenRouter services.",
        )

    def __init__(self):
        self.type = "manifold"
        self.valves = self.Valves()
        pass

    def pipes(self):
        """Return list of available models, filtered to only include free models and sorted alphabetically"""
        if self.valves.OPENROUTER_API_KEY:
            try:
                headers = {}
                headers["Authorization"] = f"Bearer {self.valves.OPENROUTER_API_KEY}"
                headers["Content-Type"] = "application/json"

                r = requests.get(
                    f"{self.valves.OPENROUTER_API_BASE_URL}/models", headers=headers
                )

                models = r.json()

                # Filter to only include models that end with "(free)" and sort alphabetically
                free_models = []
                for model in models["data"]:
                    model_name = model.get("name", model.get("id", ""))
                    if model_name.endswith("(free)"):
                        free_models.append({
                            "id": model["id"],  # Return the actual OpenRouter model ID
                            "name": f'{self.valves.NAME_PREFIX}{model_name} (Retry)',
                        })

                # Sort alphabetically by the model identifier part (after the first "/")
                def sort_key(model_dict):
                    name = model_dict["name"]
                    # Extract the part after "OpenRouter/" for sorting
                    if "/" in name:
                        return name.split("/", 1)[1].lower()
                    return name.lower()

                free_models.sort(key=sort_key)

                return free_models

            except Exception as e:
                print(f"Error: {e}")
                return [
                    {
                        "id": "error",
                        "name": "Could not fetch models from OpenRouter, please update the API Key in the valves.",
                    },
                ]
        else:
            return [
                {
                    "id": "error",
                    "name": "Global API Key not provided.",
                },
            ]

    def get_retry_delay(self, attempt: int) -> float:
        """Calculate delay based on retry attempt number"""
        # First retry: 1 second wait
        if attempt == 1:
            return self.valves.first_retry_delay

        # Next 10 retries: 0.5 second waits
        if attempt <= 1 + self.valves.short_retry_count:
            return self.valves.short_retry_delay

        # Next 20 retries: 0.1 second waits
        if attempt <= 1 + self.valves.short_retry_count + self.valves.long_retry_count:
            return self.valves.long_retry_delay

        # If all fail: wait 60 seconds, then repeat sequence
        return self.valves.fallback_delay

    def make_openrouter_request(self, url: str, headers: dict, payload: dict, stream: bool = False) -> dict:
        """Make an HTTP request to OpenRouter API"""
        try:
            r = requests.post(
                url=url,
                json=payload,
                headers=headers,
                timeout=30.0,
                stream=stream,
            )

            # For streaming requests, we return the response object directly
            if stream:
                return {
                    "status_code": r.status_code,
                    "response": r
                }

            # For non-streaming requests, try to parse JSON response
            try:
                response_data = r.json()
            except json.JSONDecodeError:
                response_data = {"text": r.text}

            return {
                "status_code": r.status_code,
                "data": response_data
            }
        except Exception as e:
            return {
                "error": str(e),
                "status_code": None
            }

    def retry_openrouter_request(self, url: str, headers: dict, payload: dict, stream: bool = False, attempt: int = 1) -> tuple:
        """Retry the OpenRouter request with the specified timing strategy"""
        # Check if we've exceeded maximum attempts
        max_attempts = 1 + self.valves.short_retry_count + self.valves.long_retry_count

        if attempt > max_attempts * 2:  # Allow one fallback cycle
            # If still failing after all retries, return error
            error_response = {
                "error": {
                    "message": f"Max retry attempts ({max_attempts}) exceeded for OpenRouter request. Please try again later.",
                    "type": "max_retries_exceeded",
                    "code": "max_retries_exceeded"
                }
            }
            retry_info = {"attempts": attempt, "success": False, "errors": [], "max_retries_exceeded": True}
            return error_response, retry_info

        # Make the request
        response = self.make_openrouter_request(url, headers, payload, stream)

        # Check if we need to retry
        if response.get("status_code") == 429:
            print(f"Received 429 error on attempt {attempt}, retrying...")

            # Calculate delay
            delay = self.get_retry_delay(attempt)

            # Wait for the specified delay
            print(f"Waiting {delay} seconds before retry attempt {attempt + 1}")
            time.sleep(delay)

            # Retry with next attempt
            return self.retry_openrouter_request(url, headers, payload, stream, attempt + 1)
        elif "error" in response:
            print(f"Received error on attempt {attempt}: {response['error']}")

            # For connection errors, we might want to retry
            if "timeout" in str(response["error"]).lower() or "connect" in str(response["error"]).lower():
                # Calculate delay
                delay = self.get_retry_delay(attempt)

                # Wait for the specified delay
                print(f"Waiting {delay} seconds before retry attempt {attempt + 1}")
                time.sleep(delay)

                # Retry with next attempt
                return self.retry_openrouter_request(url, headers, payload, stream, attempt + 1)

            # For other errors, return the error
            retry_info = {"attempts": attempt, "success": False, "errors": [response["error"]]}
            return response, retry_info
        else:
            # Success, return the response
            print(f"Request successful on attempt {attempt}")
            retry_info = {"attempts": attempt, "success": True, "errors": []}
            return response, retry_info

    def stream_response(self, response) -> Generator:
        """Stream the response from OpenRouter, filtering out processing artifacts"""
        try:
            for line in response.iter_lines():
                if line:
                    # Decode bytes to string for processing
                    line_str = line.decode('utf-8', errors='ignore') if isinstance(line, bytes) else str(line)

                    # Remove OpenRouter processing artifacts by replacing the exact string
                    # This is safer than skipping lines as it preserves legitimate content
                    cleaned_line = line_str.replace(": OPENROUTER PROCESSING", "")

                    # Only yield if there's content left after cleaning
                    if cleaned_line.strip():
                        # Yield the cleaned line (encode back to bytes if original was bytes)
                        if isinstance(line, bytes):
                            yield cleaned_line.encode('utf-8')
                        else:
                            yield cleaned_line
        except Exception as e:
            yield f"data: {{\"error\": {{\"message\": \"Error streaming response: {str(e)}\"}}}}\n\n".encode()

    def format_retry_summary(self, retry_info: dict) -> str:
        """Format retry information into a readable summary"""
        attempts = retry_info.get("attempts", 1)
        success = retry_info.get("success", False)
        errors = retry_info.get("errors", [])

        if attempts <= 1:
            return ""  # No retry summary needed for single attempts

        status = "✅ Success" if success else "❌ Failed"
        summary = f"🔄 **OpenRouter Retry Summary**: {attempts} attempts, {status}"

        if not success and errors:
            summary += f"\n**Last Error**: {errors[-1].get('message', 'Unknown error')}"

        return summary

    def stream_response_with_retry_info(self, response, retry_info: dict) -> Generator:
        """Stream the response with retry information prepended for streaming responses"""
        try:
            # First, yield the retry summary if there were retries
            if retry_info and retry_info.get("attempts", 0) > 1:
                retry_summary = self.format_retry_summary(retry_info)
                if retry_summary:
                    # Send retry summary as a data message
                    yield f"data: {{\"choices\": [{{\"delta\": {{\"content\": \"{retry_summary}\\n\\n\"}}}}]}}\n\n".encode()

            # Then stream the actual response, filtering artifacts safely
            for line in response.iter_lines():
                if line:
                    # Decode bytes to string for processing
                    line_str = line.decode('utf-8', errors='ignore') if isinstance(line, bytes) else str(line)

                    # Remove OpenRouter processing artifacts by replacing the exact string
                    cleaned_line = line_str.replace(": OPENROUTER PROCESSING", "")

                    # Only yield if there's content left after cleaning
                    if cleaned_line.strip():
                        # Yield the cleaned line (encode back to bytes if original was bytes)
                        if isinstance(line, bytes):
                            yield cleaned_line.encode('utf-8')
                        else:
                            yield cleaned_line
        except Exception as e:
            yield f"data: {{\"error\": {{\"message\": \"Error streaming response: {str(e)}\"}}}}\n\n".encode()

    def pipe(self, body: dict, __user__: dict) -> Union[str, Generator, Iterator]:
        """Process the pipe request"""
        print(f"pipe:{__name__}")
        print(__user__)

        user_valves = __user__.get("valves")

        # Use user's API key if available, otherwise use global
        api_key = ""
        if user_valves and user_valves.OPENROUTER_API_KEY:
            api_key = user_valves.OPENROUTER_API_KEY
        else:
            api_key = self.valves.OPENROUTER_API_KEY

        if not api_key:
            raise Exception("OPENROUTER_API_KEY not provided.")

        headers = {}
        headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"
        # Add referer header for OpenRouter analytics
        headers["HTTP-Referer"] = "https://openwebui.com"
        headers["X-Title"] = "Open WebUI"

        # Extract model ID (remove prefix added by OpenWebUI)
        model_id = body["model"]
        # Find the first "." and take everything after it
        if "." in model_id:
            model_id = model_id[model_id.find(".") + 1:]

        # Create payload with correct model ID
        payload = {**body, "model": model_id}
        print(f"Payload: {payload}")

        try:
            # Check if this is a streaming request
            is_streaming = body.get("stream", False)

            # Make the request with retry logic
            response, retry_info = self.retry_openrouter_request(
                url=f"{self.valves.OPENROUTER_API_BASE_URL}/chat/completions",
                headers=headers,
                payload=payload,
                stream=is_streaming
            )

            # Handle response
            if "error" in response:
                error = response["error"]
                return f"Error: {error.get('message', 'Unknown error')}"
            elif is_streaming:
                # For streaming requests, return a generator that streams the response
                r = response.get("response")
                if r:
                    return self.stream_response_with_retry_info(r, retry_info)
                else:
                    return f"data: {{\"error\": {{\"message\": \"Error streaming response\"}}}}\n\n"
            else:
                # For non-streaming requests, prepend retry info to the response
                response_data = response.get("data", {})
                if retry_info and retry_info.get("attempts", 0) > 1:
                    # Add retry summary to the response content
                    retry_summary = self.format_retry_summary(retry_info)
                    if "choices" in response_data and response_data["choices"]:
                        content = response_data["choices"][0].get("message", {}).get("content", "")
                        response_data["choices"][0]["message"]["content"] = f"{retry_summary}\n\n{content}"

                return response_data
        except Exception as e:
            print(f"Exception in pipe: {e}")
            return f"Error: {e}"