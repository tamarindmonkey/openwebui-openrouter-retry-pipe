# Frontend Integration Proposal — Toasts & In‑Chat Error Box

Overview
This document proposes minimal frontend changes to render backend-sent toast notifications (top-right) and structured in‑chat error boxes when the backend includes meta.ui in messages or sends SSE meta chunks.

Goals
- Show top-right toast notifications for retry events emitted by the backend.
- Render an in‑chat styled error box (red with icon) when the backend returns a message with message.meta.ui.variant === "error".
- Ensure streaming SSE meta chunks (choices[].delta.meta) are forwarded to the chat renderer so the box appears immediately during streaming.

Backend integration points
- Backend emits structured events via the OpenWebUI event emitter with event names "status", "notification", or "message".
- Backend includes SSE data chunks of the form: {"choices":[{"delta":{"content":"","meta":{...}}}]} for streaming flows.
- See backend implementation in [`openrouter-retry.py`](openrouter-retry.py:1).

Approach
- Add a lightweight ToastProvider (React) that listens for emitter events and shows toasts.
- Add ErrorBox component that the MessageRenderer will render when message.meta.ui.variant === "error".
- Update the SSE client to attach delta.meta to the streamed partial message object so the MessageRenderer can access it.

Files to add / modify
- [`web/src/components/ToastProvider.jsx`](web/src/components/ToastProvider.jsx:1) (new)
- [`web/src/components/ErrorBox.jsx`](web/src/components/ErrorBox.jsx:1) (new)
- [`web/src/components/MessageRenderer.jsx`](web/src/components/MessageRenderer.jsx:1) (modify)
- [`web/src/lib/sse-client.js`](web/src/lib/sse-client.js:1) (modify)
- [`web/src/styles/error-box.css`](web/src/styles/error-box.css:1) (new)

1) ToastProvider (React)
Create [`web/src/components/ToastProvider.jsx`](web/src/components/ToastProvider.jsx:1) with a simple context and a small toast stack UI. The provider listens for backend events on `window.eventEmitter` (or your app's emitter) and exposes `showToast()` for local use.

Example (minimal):
```javascript
import React, { createContext, useContext, useState, useEffect } from "react";
import "./toast.css";

const ToastContext = createContext(null);
export function useToast() { return useContext(ToastContext); }

export default function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  useEffect(() => {
    const emitter = window.eventEmitter;
    if (!emitter) return;
    const handler = (payload) => {
      // payload: { type, title, message, timeout, meta }
      setToasts((t) => [...t, { id: Date.now()+Math.random(), ...payload }]);
    };
    emitter.on?.("status", handler);
    emitter.on?.("notification", handler);
    return () => {
      emitter.off?.("status", handler);
      emitter.off?.("notification", handler);
    };
  }, []);
  const remove = (id) => setToasts((t) => t.filter((x) => x.id !== id));
  return (
    <ToastContext.Provider value={{ show: (p)=> setToasts((t)=>[...t,{id:Date.now()+Math.random(),...p}]) }}>
      {children}
      <div className="toast-portal">
        {toasts.map((td) => (
          <div key={td.id} className={`toast ${td.type || "info"}`} onClick={()=>remove(td.id)}>
            <strong>{td.title}</strong><div>{td.message}</div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
```

2) ErrorBox component
Create [`web/src/components/ErrorBox.jsx`](web/src/components/ErrorBox.jsx:1). Minimal example:
```javascript
import React from "react";
import "../styles/error-box.css";
export default function ErrorBox({ title, body }) {
  return (
    <div className="error-box" role="alert" aria-live="assertive">
      <div className="error-icon">⚠️</div>
      <div className="error-content">
        <div className="error-title">{title}</div>
        <div className="error-body">{body}</div>
      </div>
    </div>
  );
}
```

CSS (add [`web/src/styles/error-box.css`](web/src/styles/error-box.css:1))
```css
.error-box{display:flex;gap:12px;background:#ffecec;border:1px solid #f5c2c2;padding:12px;border-radius:6px;color:#7a1b1b}
.error-icon{font-size:20px}
.error-title{font-weight:700;margin-bottom:6px}
.error-body{white-space:pre-wrap}
```

3) MessageRenderer updates
Modify [`web/src/components/MessageRenderer.jsx`](web/src/components/MessageRenderer.jsx:1) so that before rendering the usual content it checks:
```javascript
if (message.meta?.ui?.variant === "error") {
  return <ErrorBox title={message.meta.ui.title} body={message.meta.ui.body} />;
}
```
If your renderer supports streaming/delta updates, ensure it passes delta.meta into the final message object.

4) SSE client changes
Modify your SSE parser (e.g., [`web/src/lib/sse-client.js`](web/src/lib/sse-client.js:1)) so that when you receive a chunk like:
`{"choices":[{"delta":{"content":"...","meta":{...}}}]}`
you attach `meta` to the partial message (or the message object you append to chat). Example:
```javascript
// pseudocode in sse message handler
const parsed = JSON.parse(data);
const delta = parsed.choices?.[0]?.delta;
if (delta) {
  currentMessage.content += delta.content || "";
  if (delta.meta) currentMessage.meta = {...(currentMessage.meta||{}), ...delta.meta};
  // re-render message
}
```

5) Immediate in-chat append via emitter
For streaming flows the backend sends an SSE meta chunk; additionally the backend emits a `message` event with the structured message object to append the error to chat immediately. The toast system will also show the status. The front-end listener in `ToastProvider` registers for `message` events if desired to append that message to chat.

6) Backwards compatibility
- If the frontend doesn't support `message.meta.ui`, the error will still be visible as `content` fallback.
- Keep the valve `ENABLE_IN_CHAT_ERRORS` on the backend to toggle this behavior.

Testing
1. Start OpenWebUI with the updated backend and frontend.
2. Trigger a 429 scenario (e.g., throttle your OpenRouter key) and watch the logs.
3. Verify toasts appear on each retry attempt (top-right) and a final error toast on exhaustion.
4. For streaming model, verify the red in-chat box appears immediately before or during the stream if the backend emits SSE meta.

Files & patch options
- I can generate a small git patch (`frontend-ui-patch.diff`) containing the exact file additions/modifications for the frontend.
- Or I can add the new files under `web/src/` in this repo if you want me to commit them here (only do this if your frontend lives in the same repo).

Next steps
- I can produce the git patch now, or create the files in `web/src/` (if you want me to add them into this repository), or just hand off these snippets for your frontend developer.

If you want the patch, reply: "git patch". To add files here, reply: "create files". To keep snippets only, reply: "snippets".

Notes
- The examples above use `window.eventEmitter` as the global emitter. If your frontend exposes the event emitter under a different global, swap the name accordingly.
- Keep the toast UI minimal and accessible; follow your app's design system for colors/icons.

End of frontend proposal