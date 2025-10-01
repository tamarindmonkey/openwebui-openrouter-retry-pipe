"""
title: OpenRouter Automatic Retry Pipe
version: 0.1.19
description: Unified automatic retry handler for OpenRouter with consistent notifications for streaming and non-streaming requests
author: tamarindmonkey
author_url: https://github.com/tamarindmonkey
funding_url: https://github.com/tamarindmonkey
"""

import asyncio
import logging
import random
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Union, Generator, Iterator, AsyncGenerator, Any

# aiohttp is optional in environments where pip install is not available.
# If aiohttp is missing, the pipe will fall back to using requests in a thread.
try:
    import aiohttp  # type: ignore
    AIOHTTP_AVAILABLE = True
except Exception:
    aiohttp = None
    AIOHTTP_AVAILABLE = False
import requests
import json

logger = logging.getLogger(__name__)


class Pipe:
    class Valves(BaseModel):
        NAME_PREFIX: str = Field(
            default="OR-Free/",
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
        ENABLE_NOTIFICATIONS: bool = Field(
            default=True,
            description="Emit status notifications to the OpenWebUI event emitter when available.",
        )
        ENABLE_IN_CHAT_ERRORS: bool = Field(
            default=True,
            description="Include structured in-chat error messages (meta.ui) on final failures.",
        )
        IN_CHAT_EVENT_NAME: str = Field(
            default="message",
            description="Event name to use when emitting in-chat message events (fallback to 'message').",
        )
        attempts_per_burst: int = Field(
            default=10,
            description="Number of attempts per burst for fast retry bursts",
        )
        attempt_delay_min: float = Field(
            default=2.0,
            description="Minimum delay between attempts within a burst (seconds)",
        )
        attempt_delay_max: float = Field(
            default=4.0,
            description="Maximum delay between attempts within a burst (seconds)",
        )
        bursts_before_long_pause: int = Field(
            default=3,
            description="Number of bursts before a longer pause",
        )
        burst_pause_min: float = Field(
            default=15.0,
            description="Minimum pause between bursts (seconds)",
        )
        burst_pause_max: float = Field(
            default=30.0,
            description="Maximum pause between bursts (seconds)",
        )
        cycles: int = Field(
            default=2,
            description="Number of cycles (each cycle consists of bursts_before_long_pause bursts)",
        )
        long_pause: float = Field(
            default=60.0,
            description="Long pause between cycles (seconds)",
        )

    class UserValves(BaseModel):
        OPENROUTER_API_KEY: str = Field(
            default="",
            description="User-specific API key for accessing OpenRouter services.",
        )

    def __init__(self):
        self.type = "manifold"
        self.id = "openrouter_automatic_retry_pipe"
        self.name = ""
        self.valves = self.Valves()

    def pipes(self):
        """Return list of available models, filtered to only include free models and sorted alphabetically"""
        if self.valves.OPENROUTER_API_KEY:
            try:
                headers = {}
                headers["Authorization"] = f"Bearer {self.valves.OPENROUTER_API_KEY}"
                headers["Content-Type"] = "application/json"

                # synchronous fetch for model list (non-blocking in normal usage)
                r = requests.get(
                    f"{self.valves.OPENROUTER_API_BASE_URL}/models",
                    headers=headers,
                    timeout=15,
                )
                models = r.json()

                # Filter to only include models that end with "(free)" and sort alphabetically
                free_models = []
                for model in models.get("data", []):
                    model_name = model.get("name", model.get("id", ""))
                    if model_name.endswith("(free)"):
                        # Normalize display name by stripping any provider prefix (e.g., "OpenRouter/")
                        display_name = model_name.split("/", 1)[-1] if "/" in model_name else model_name
                        free_models.append(
                            {
                                "id": model["id"],  # Return the actual OpenRouter model ID
                                "name": f'{self.valves.NAME_PREFIX}{display_name} (Auto-Retry)',
                            }
                        )

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
                logger.exception(f"Error fetching models: {e}")
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

    async def make_openrouter_request(
        self,
        session: Optional["aiohttp.ClientSession"],
        url: str,
        headers: dict,
        payload: dict,
        stream: bool = False,
    ) -> dict:
        """Make an HTTP request to OpenRouter API.

        Uses aiohttp when available. If aiohttp is not installed in the environment
        (e.g., pip cannot be run inside the container), falls back to `requests`
        running in a thread for non-blocking behavior in the async context.
        Streaming is only supported when aiohttp is available; otherwise streaming
        requests will fall back to a non-streaming request and return the full response.
        """
        # If aiohttp available, prefer that (supports streaming)
        if AIOHTTP_AVAILABLE and aiohttp is not None:
            try:
                if stream:
                    # keep response open for streaming; no context manager here
                    r = await session.post(
                        url=url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=None),
                    )
                    return {"status_code": r.status, "response": r, "stream": True}

                # Non-streaming
                async with session.post(
                    url=url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30.0),
                ) as r:
                    try:
                        response_data = await r.json()
                    except json.JSONDecodeError:
                        response_data = {"text": await r.text()}

                    return {"status_code": r.status, "data": response_data, "stream": False}
            except Exception as e:
                return {"error": str(e), "status_code": None}

        # Fallback using requests in a thread (no true streaming support)
        try:
            def sync_post():
                try:
                    if stream:
                        # perform a normal (non-streaming) request when aiohttp unavailable
                        r = requests.post(url, json=payload, headers=headers, timeout=30)
                        try:
                            return {"status_code": r.status_code, "data": r.json(), "stream": False}
                        except Exception:
                            return {"status_code": r.status_code, "data": {"text": r.text}, "stream": False}
                    else:
                        r = requests.post(url, json=payload, headers=headers, timeout=30)
                        try:
                            return {"status_code": r.status_code, "data": r.json(), "stream": False}
                        except Exception:
                            return {"status_code": r.status_code, "data": {"text": r.text}, "stream": False}
                except requests.exceptions.Timeout:
                    return {"error": "Request timeout", "status_code": 408}
                except requests.exceptions.ConnectionError:
                    return {"error": "Connection error", "status_code": 503}
                except Exception as e:
                    return {"error": str(e), "status_code": 500}

            return await asyncio.to_thread(sync_post)
        except Exception as e:
            return {"error": str(e), "status_code": None}

    async def _send_status(
        self,
        event_emitter,
        description: str,
        done: bool = False,
        hidden: bool = False,
    ):
        """Emit a status update to the UI event emitter if available (async-safe)."""
        if not getattr(self.valves, "ENABLE_NOTIFICATIONS", False):
            return
        if not event_emitter:
            return

        # Handle both object with .emit method and callable function
        if event_emitter:
            if hasattr(event_emitter, 'emit'):
                # Object with .emit method
                try:
                    res = event_emitter.emit("status", {
                        "description": description,
                        "done": done,
                        "hidden": hidden,
                    })
                    if asyncio.iscoroutine(res):
                        await res
                    return
                except Exception:
                    pass
            elif callable(event_emitter):
                # Callable function (like in current OpenWebUI)
                try:
                    res = event_emitter({
                        "type": "status",
                        "data": {
                            "description": description,
                            "done": done,
                            "hidden": hidden,
                        }
                    })
                    if asyncio.iscoroutine(res):
                        await res
                    return
                except Exception:
                    pass
            else:
                pass


    async def _send_notification(
        self,
        event_emitter,
        message: str,
        level: str = "info",
        title: Optional[str] = None,
        timeout: Optional[float] = None,
        meta: Optional[dict] = None,
    ):
        """Emit a notification to the UI event emitter if available (async-safe).

        Backwards-compatible: older callers may pass only (event_emitter, message, level).
        Newer callers may pass `title`, `timeout`, and `meta` for richer notifications.
        """
        if not getattr(self.valves, "ENABLE_NOTIFICATIONS", False):
            return
        if not event_emitter:
            return

        payload = {
            "type": level,
            "title": title or "OpenRouter",
            "content": message,
            "timeout": timeout,
            "meta": meta or {},
            "timestamp": datetime.now().isoformat(),
        }

        # Handle both object with .emit method and callable function
        if event_emitter:
            if hasattr(event_emitter, 'emit'):
                # Object with .emit method (like in alt file)
                try:
                    # Try status event first
                    res = event_emitter.emit("status", payload)
                    if asyncio.iscoroutine(res):
                        await res
                    return
                except Exception:
                    try:
                        # Fallback to message event
                        res = event_emitter.emit("message", {"content": f"[{level.upper()}] {message}"})
                        if asyncio.iscoroutine(res):
                            await res
                        return
                    except Exception:
                        pass
            elif callable(event_emitter):
                # Callable function (like in current OpenWebUI)
                try:
                    res = event_emitter({"type": "notification", "data": payload})
                    if asyncio.iscoroutine(res):
                        await res
                    return
                except Exception:
                    pass
            else:
                pass

    async def retry_openrouter_request(
        self,
        url: str,
        headers: dict,
        payload: dict,
        stream: bool = False,
        event_emitter: Optional[Any] = None,
        user: Optional[dict] = None,
        model: str = "",
    ) -> tuple:
        """Retry the OpenRouter request using burst-based scheduling.

        Strategy:
          - attempts_per_burst attempts per burst (2-4s between attempts)
          - bursts_before_long_pause bursts per cycle (15-30s between bursts)
          - cycles cycles total (long_pause between cycles)
        Returns: (response, retry_info)
        """
        start_time = asyncio.get_event_loop().time()
        max_attempts = (
            self.valves.attempts_per_burst
            * self.valves.bursts_before_long_pause
            * self.valves.cycles
        )
        attempts = 0
        errors = []
        user_name = user.get("name", user.get("id", "unknown")) if user else "unknown"
        model_id = model or "unknown"


        for cycle in range(self.valves.cycles):
            for burst in range(self.valves.bursts_before_long_pause):
                for attempt_in_burst in range(self.valves.attempts_per_burst):
                    attempts += 1

                    # Send attempt status (each new status marks previous as done)
                    await self._send_status(
                        event_emitter,
                        f"Attempt {attempts}/{max_attempts} in progress...",
                        done=False,
                        hidden=False,
                    )

                    # Create new session for each attempt to avoid connection issues
                    attempt_session = aiohttp.ClientSession()
                    try:
                        response = await self.make_openrouter_request(
                            attempt_session, url, headers, payload, stream
                        )
                    except Exception as e:
                        # If request fails, close session and continue
                        try:
                            await attempt_session.close()
                        except Exception:
                            pass
                        # Treat as error response
                        response = {"error": str(e), "status_code": None}

                    status = response.get("status_code")
                    # Rate limited - retry
                    if status == 429:
                        logger.info(f"{user_name}:{model_id} - Attempt {attempts}/{max_attempts}: ERROR: {status}")
                        errors.append({"attempt": attempts, "error": status})
                        # close streaming response object if present to avoid leaks
                        resp_obj = response.get("response")
                        try:
                            if resp_obj and hasattr(resp_obj, "close"):
                                resp_obj.close()
                        except Exception:
                            pass
                        # close the attempt session to prevent unclosed session warnings
                        try:
                            await attempt_session.close()
                        except Exception:
                            pass
                        delay = random.uniform(
                            self.valves.attempt_delay_min, self.valves.attempt_delay_max
                        )
                        await asyncio.sleep(delay)
                        if attempts >= max_attempts:
                            break
                        continue

                    if "error" in response:
                        err_str = str(response["error"])
                        logger.info(f"{user_name}:{model_id} - Attempt {attempts}/{max_attempts}: ERROR: {status or 'unknown'} - {err_str}")
                        errors.append({"attempt": attempts, "error": err_str})
                        if "timeout" in err_str.lower() or "connect" in err_str.lower():
                            await self._send_notification(
                                event_emitter,
                                f"{status or 'unknown'} error after {attempts} attempts. Retrying in {random.uniform(self.valves.burst_pause_min, self.valves.burst_pause_max):.0f} seconds",
                                "error",
                            )
                            # Send error status (each new status marks previous as done)
                            await self._send_status(
                                event_emitter,
                                f"Attempt {attempts}/{max_attempts}: {status or 'unknown'} error - Retrying in {random.uniform(self.valves.attempt_delay_min, self.valves.attempt_delay_max):.0f}s",
                                done=False,
                                hidden=False,
                            )
                            # close the attempt session to prevent unclosed session warnings
                            try:
                                await attempt_session.close()
                            except Exception:
                                pass
                            delay = random.uniform(
                                self.valves.attempt_delay_min, self.valves.attempt_delay_max
                            )
                            await asyncio.sleep(delay)
                            if attempts >= max_attempts:
                                break
                            continue
                        retry_info = {"attempts": attempts, "success": False, "errors": errors}
                        try:
                            await attempt_session.close()
                        except Exception:
                            pass
                        return response, retry_info, None

                    # HTTP error (non-429)
                    if status and status >= 400:
                        logger.info(f"{user_name}:{model_id} - Attempt {attempts}/{max_attempts}: ERROR: {status}")
                        data = response.get("data") or {}
                        err_obj = data.get("error") if isinstance(data, dict) else None
                        if not err_obj:
                            err_obj = {"message": f"HTTP {status} error"}
                        errors.append({"attempt": attempts, "error": err_obj})
                        retry_info = {"attempts": attempts, "success": False, "errors": errors}
                        try:
                            await attempt_session.close()
                        except Exception:
                            pass
                        return {"error": err_obj}, retry_info, None

                    # Success
                    if status and 200 <= status < 300:
                        elapsed_time = asyncio.get_event_loop().time() - start_time
                        elapsed_str = f"{int(elapsed_time // 60)}m{int(elapsed_time % 60)}s"
                        logger.info(f"{user_name}:{model_id} - Attempt {attempts} ({elapsed_str}): SUCCESS")
                        retry_info = {"attempts": attempts, "success": True, "errors": errors, "elapsed_time": elapsed_time}

                        # For non-streaming, close the session
                        if not stream:
                            try:
                                await attempt_session.close()
                            except Exception:
                                pass

                        # Return response and session (for streaming)
                        return response, retry_info, attempt_session if stream else None

                # After a burst finishes without success, wait before next burst (unless we're done or this is the last burst in the cycle)
                if attempts >= max_attempts:
                    break
                # Skip burst pause if this is the last burst in the current cycle (cycle pause will handle the delay)
                is_last_burst_in_cycle = (burst == self.valves.bursts_before_long_pause - 1)
                if not is_last_burst_in_cycle:
                    burst_pause = random.uniform(
                        self.valves.burst_pause_min, self.valves.burst_pause_max
                    )
                    logger.info(f"{user_name}:{model_id} - Burst completed without success; waiting {burst_pause:.1f}s")
                    await self._send_notification(
                        event_emitter, f"Burst of {self.valves.attempts_per_burst} attempts failed. Waiting {burst_pause:.0f} seconds before next burst", "warning"
                    )
                    # Send visible burst transition status
                    await self._send_status(
                        event_emitter, f"Burst {burst+1}/{self.valves.bursts_before_long_pause} completed ({attempts}/{max_attempts} attempts). Waiting {burst_pause:.0f}s before next burst", done=False, hidden=False
                    )
                    await asyncio.sleep(burst_pause)

            # After bursts in a cycle, long pause before next cycle
            if attempts >= max_attempts:
                break
            if cycle < self.valves.cycles - 1:
                logger.info(f"{user_name}:{model_id} - Cycle {cycle+1} completed; waiting {self.valves.long_pause}s")
                await self._send_notification(
                    event_emitter, f"Cycle {cycle+1} of {self.valves.cycles} completed without success. Waiting {self.valves.long_pause:.0f} seconds before next cycle", "warning"
                )
                # Send visible cycle transition status
                await self._send_status(
                    event_emitter, f"Cycle {cycle+1}/{self.valves.cycles} completed ({attempts}/{max_attempts} attempts). Waiting {self.valves.long_pause:.0f}s before next cycle", done=False, hidden=False
                )
                await asyncio.sleep(self.valves.long_pause)

        # Exhausted attempts
        elapsed_time = asyncio.get_event_loop().time() - start_time
        elapsed_str = f"{int(elapsed_time // 60)}m{int(elapsed_time % 60)}s"
        last_error = errors[-1] if errors else {}
        error_code = last_error.get("error", "unknown") if isinstance(last_error, dict) else str(last_error)
        error_message = last_error.get("message", str(last_error)) if isinstance(last_error, dict) else str(last_error)
        final_err = {"message": f"Max retry attempts ({max_attempts}) exceeded for OpenRouter request."}
        retry_info = {"attempts": attempts, "success": False, "errors": errors, "max_retries_exceeded": True, "elapsed_time": elapsed_time}
        logger.error(f"{user_name}:{model_id} - Attempt {attempts}/{max_attempts} ({elapsed_str}): ERROR: {error_code} - {error_message}")
        await self._send_notification(event_emitter, f"All {attempts} attempts failed. Final error: {error_code} - {error_message}", "error")
        # Send final failure status (visible and marked as done)
        await self._send_status(event_emitter, f"All {attempts} attempts failed. Final error: {error_code}", done=True, hidden=False)
        return {"error": final_err}, retry_info, None

    async def stream_response(
        self, response: aiohttp.ClientResponse, session: aiohttp.ClientSession
    ) -> AsyncGenerator[bytes, None]:
        """Stream the response from OpenRouter, filtering out processing artifacts"""
        try:
            while True:
                line = await response.content.readline()
                if not line:
                    break

                # Decode bytes to string for processing
                line_str = (
                    line.decode("utf-8", errors="ignore")
                    if isinstance(line, (bytes, bytearray))
                    else str(line)
                )

                # Remove OpenRouter processing artifacts by replacing the exact string
                cleaned_line = line_str.replace(": OPENROUTER PROCESSING", "")

                # Only yield if there's content left after cleaning
                if cleaned_line.strip():
                    yield cleaned_line.encode("utf-8")
        except Exception as e:
            yield f'data: {{"error": {{"message": "Error streaming response: {str(e)}"}}}}\n\n'.encode()
        finally:
            try:
                response.close()
            finally:
                await session.close()

    def format_retry_summary(self, retry_info: dict) -> str:
        """Format retry information into a readable summary"""
        attempts = retry_info.get("attempts", 1)
        success = retry_info.get("success", False)
        errors = retry_info.get("errors", [])

        if attempts <= 1:
            return ""  # No retry summary needed for single attempts

        status = "Success" if success else "Failed"
        summary = f"Retry Summary: {attempts} attempts, {status}"

        if not success and errors:
            # errors may be list of strings or dicts
            last_err = errors[-1]
            last_msg = (
                last_err.get("message", "Unknown error")
                if isinstance(last_err, dict)
                else str(last_err)
            )
            summary += f"\nLast Error: {last_msg}"

        return summary

    async def stream_response_with_retry_info(
        self, response: aiohttp.ClientResponse, retry_info: dict, session: aiohttp.ClientSession
    ) -> AsyncGenerator[bytes, None]:
        """Stream the response. Retry information is communicated via notifications only."""
        async for chunk in self.stream_response(response, session):
            yield chunk

    async def pipe(self, body: dict, __user__: Optional[dict] = None, __event_emitter__: Optional[Any] = None) -> Union[str, AsyncGenerator, Iterator]:
        """Process the pipe request with unified retry logic for both streaming and non-streaming"""

        # Use the parameters directly as passed by OpenWebUI
        user = __user__
        event_emitter = __event_emitter__

        # Extract user's valves safely (supports dict or object)
        user_valves = None
        api_key = ""
        if user:
            if isinstance(user, dict):
                user_valves = user.get("valves")
            else:
                user_valves = getattr(user, "valves", None)

        if user_valves:
            if isinstance(user_valves, dict):
                api_key = user_valves.get("OPENROUTER_API_KEY", "") or ""
            else:
                api_key = getattr(user_valves, "OPENROUTER_API_KEY", "") or ""

        if not api_key:
            api_key = self.valves.OPENROUTER_API_KEY

        if not api_key:
            return {"error": {"message": "OPENROUTER_API_KEY not provided."}}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openwebui.com",
            "X-Title": "Open WebUI",
        }

        # Extract model ID (remove prefix added by OpenWebUI)
        model_id = body.get("model", "")
        if "." in model_id:
            model_id = model_id.split(".", 1)[1]

        # Create payload with correct model ID
        payload = {**body, "model": model_id}

        try:
            # Determine if this is a streaming request
            is_streaming = body.get("stream", False)

            # If aiohttp is unavailable, streaming cannot be supported in this environment;
            # fall back to non-streaming mode and notify the UI.
            if is_streaming and not AIOHTTP_AVAILABLE:
                try:
                    await self._send_notification(
                        event_emitter,
                        "Streaming requests are unavailable in this environment (aiohttp not installed). Falling back to non-streaming.",
                        "warning",
                        title="OpenRouter Notice",
                        timeout=6,
                    )
                except Exception:
                    pass
                is_streaming = False

            url = f"{self.valves.OPENROUTER_API_BASE_URL}/chat/completions"

            # UNIFIED retry logic - same for both streaming and non-streaming
            response, retry_info, success_session = await self.retry_openrouter_request(
                url=url,
                headers=headers,
                payload=payload,
                stream=is_streaming,
                event_emitter=event_emitter,
                user=user,
                model=model_id,
            )

            # Handle errors with unified notifications
            if "error" in response:
                error = response["error"]
                await self._send_notification(
                    event_emitter,
                    error.get("message", "OpenRouter request failed"),
                    "error",
                    title="OpenRouter Error",
                    timeout=None,
                    meta={"retry_info": retry_info, "error": error},
                )

                # Emit chat:message:error so frontend shows in-chat error box
                if event_emitter:
                    try:
                        if callable(event_emitter):
                            await event_emitter({"type": "chat:message:error", "data": {"error": error}})
                        else:
                            emit = getattr(event_emitter, "emit", None)
                            if callable(emit):
                                res = emit("chat:message:error", {"error": error})
                                if asyncio.iscoroutine(res):
                                    await res
                    except Exception:
                        pass

                try:
                    await session.close()
                except Exception:
                    pass
                return {"error": error, "retry_info": retry_info}

            # SUCCESS - send notifications and status update, format response
            if retry_info.get("success"):
                    # Extract provider name from model_id (e.g., "anthropic/claude-3" -> "Anthropic")
                    provider_name = "Unknown"
                    if "/" in model_id:
                        provider_prefix = model_id.split("/")[0].lower()
                        provider_map = {
                            "anthropic": "Anthropic",
                            "openai": "OpenAI",
                            "google": "Google",
                            "meta": "Meta",
                            "mistral": "Mistral",
                            "cohere": "Cohere",
                            "together": "Together AI",
                            "huggingface": "Hugging Face",
                            "replicate": "Replicate",
                            "perplexity": "Perplexity",
                        }
                        provider_name = provider_map.get(provider_prefix, provider_prefix.title())
                    elapsed_time = retry_info.get("elapsed_time", 0)
                    elapsed_str = f"{int(elapsed_time // 60)}m{int(elapsed_time % 60)}s"

                    # Success notification
                    attempts = retry_info.get('attempts', 1)
                    if attempts > 1:
                        # Multiple attempts - show retry success
                        await self._send_notification(
                            event_emitter,
                            f"Response received after {attempts} attempt(s)",
                            "success",
                            timeout=10
                        )

                        # Retry summary notification (info level)
                        retry_summary = self.format_retry_summary(retry_info)
                        if retry_summary:
                            await self._send_notification(
                                event_emitter,
                                retry_summary,
                                "info",
                                title="OpenRouter Retry Summary",
                                timeout=10,
                                meta={"retry_info": retry_info},
                            )

                    # Show final success status
                    await self._send_status(
                        event_emitter,
                        f"Response received from {provider_name} after {elapsed_str} ({retry_info.get('attempts')} attempts)",
                        done=True,
                        hidden=False
                    )

                    # Add retry summary to chat message for non-streaming (only for multiple attempts)
                    if attempts > 1:
                        retry_summary = self.format_retry_summary(retry_info)
                        if retry_summary and not is_streaming:
                            # Prepend retry summary to the response content
                            if "choices" in response_data and response_data["choices"]:
                                content = response_data["choices"][0].get("message", {}).get("content", "")
                                response_data["choices"][0]["message"]["content"] = f"{retry_summary}\n\n{content}"

            if is_streaming:
                # Streaming response - add retry summary to chat if retries occurred
                attempts = retry_info.get("attempts", 1)
                if attempts > 1:
                    retry_summary = self.format_retry_summary(retry_info)
                    if retry_summary:
                        await event_emitter({
                            "type": "message",
                            "data": {"content": f"{retry_summary}\n\n"}
                        })

                # Streaming response - use the success session
                r = response.get("response")
                if r and success_session:
                    # Don't close the session here - stream_response_with_retry_info will handle it
                    return self.stream_response_with_retry_info(r, retry_info, success_session)
                else:
                    try:
                        await session.close()
                    except Exception:
                        pass
                    err_payload = {"error": {"message": "Error streaming response"}}
                    await self._send_status(event_emitter, "Error streaming response", done=True, hidden=False)
                    return f"data: {json.dumps(err_payload)}\n\n"
            else:
                # Non-streaming response
                try:
                    await session.close()
                except Exception:
                    pass

                response_data = response.get("data", {})

                return response_data

        except Exception as e:
            logger.exception(f"Exception in pipe: {e}")
            await self._send_notification(event_emitter, f"Internal pipe exception: {str(e)}", "error")
            return {"error": {"message": str(e)}}