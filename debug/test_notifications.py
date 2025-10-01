#!/usr/bin/env python3
"""
Test script to verify different toast notification types work in OpenWebUI.

This creates a simple pipe that emits different types of notifications when called.
Install this as a pipe and call it to test if warning, info, and success toasts work.
You can select each type from the models menu in a chat after enabling the function.

Expected behavior:
- error: red background toast
- warning: yellow background toast
- info: blue background toast
- success: green background toast
"""

import asyncio
from pydantic import BaseModel, Field
from typing import Optional, Union, Generator, Iterator, AsyncGenerator, Any


class Pipe:
    class Valves(BaseModel):
        TEST_TYPE: str = Field(
            default="all",
            description="Type of notification to test: 'all', 'error', 'warning', 'info', 'success'"
        )

    class UserValves(BaseModel):
        pass

    def __init__(self):
        self.type = "manifold"
        self.id = "test_notifications"
        self.name = "Test Notifications"
        self.valves = self.Valves()

    def pipes(self):
        """Return test models"""
        return [
            {
                "id": "test_notifications",
                "name": "🧪 Test Notifications (All Types)"
            },
            {
                "id": "test_error",
                "name": "🔴 Test Error Notification"
            },
            {
                "id": "test_warning",
                "name": "🟡 Test Warning Notification"
            },
            {
                "id": "test_info",
                "name": "🔵 Test Info Notification"
            },
            {
                "id": "test_success",
                "name": "🟢 Test Success Notification"
            }
        ]

    async def _send_notification(
        self,
        event_emitter,
        message: str,
        level: str = "info",
        title: Optional[str] = None,
        timeout: Optional[float] = None,
        meta: Optional[dict] = None,
    ):
        """Send notification to UI event emitter if available"""
        if not event_emitter:
            return

        payload = {
            "type": level,
            "title": title or "Test Notification",
            "content": message,
            "timeout": timeout,
            "meta": meta or {},
        }

        # Handle both object with .emit method and callable function
        if event_emitter:
            if hasattr(event_emitter, 'emit'):
                # Object with .emit method
                try:
                    res = event_emitter.emit("notification", payload)
                    if asyncio.iscoroutine(res):
                        await res
                    return
                except Exception:
                    pass
            else:
                # Try as callable function
                try:
                    res = event_emitter({"type": "notification", "data": payload})
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

    async def pipe(self, body: dict, __user__: Optional[dict] = None, __event_emitter__: Optional[Any] = None) -> Union[str, AsyncGenerator, Iterator]:
        """Test different notification types"""

        model_id = body.get("model", "")
        test_type = "all"

        # Determine which test to run based on model ID
        if "error" in model_id:
            test_type = "error"
        elif "warning" in model_id:
            test_type = "warning"
        elif "info" in model_id:
            test_type = "info"
        elif "success" in model_id:
            test_type = "success"

        # Emit test notifications
        if test_type == "all" or test_type == "error":
            await self._send_notification(
                __event_emitter__,
                "🔴 This is a RED ERROR notification (should have red background)",
                "error",
                title="Error Test",
                timeout=5
            )
            await asyncio.sleep(1)  # Small delay between notifications

        if test_type == "all" or test_type == "warning":
            await self._send_notification(
                __event_emitter__,
                "🟡 This is a YELLOW WARNING notification (should have yellow background)",
                "warning",
                title="Warning Test",
                timeout=5
            )
            await asyncio.sleep(1)

        if test_type == "all" or test_type == "info":
            await self._send_notification(
                __event_emitter__,
                "🔵 This is a BLUE INFO notification (should have blue background)",
                "info",
                title="Info Test",
                timeout=5
            )
            await asyncio.sleep(1)

        if test_type == "all" or test_type == "success":
            await self._send_notification(
                __event_emitter__,
                "🟢 This is a GREEN SUCCESS notification (should have green background)",
                "success",
                title="Success Test",
                timeout=5
            )

        # Return a simple response
        return {
            "choices": [
                {
                    "message": {
                        "content": f"✅ Test completed! Check the notifications above.\n\nTest type: {test_type}\n\nIf you see different colored toast notifications (red, yellow, blue, green), then all notification types are working correctly!"
                    }
                }
            ]
        }