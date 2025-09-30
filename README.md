# OpenRouter Free Model Retry Pipe

This is an Open WebUI pipe that includes enhanced retry logic for problematic free model providers from OpenRouter.ai with status summaries, filtering to only show free models, improved error handling, and artifact filtering.

## New Features in v0.1.15

### 📊 Enhanced Logging and Notifications
- **Structured logging**: Console logs now include user:model context and error details (e.g., `user:model - Attempt 29/60: ERROR: 429` or `user:model - Attempt 29: SUCCESS`)
- **Multi-colored UI notifications**: Toast messages use appropriate colors for different states:
  - 🔴 **Error** (red): Final failures and critical errors
  - 🟡 **Warning** (yellow): Burst/cycle failures and retry warnings
  - 🔵 **Info** (blue): Retry summaries and progress updates
  - 🟢 **Success** (green): Successful responses after retries
- **Improved UI notifications**: Toast messages show concise, formatted status without injecting content into chat responses
- **Backend-only**: All notifications use OpenWebUI's event emitter system, no frontend changes required

### 🔧 Implementation Improvements
- **Aiohttp-optional**: Graceful fallback to synchronous requests if aiohttp is unavailable (e.g., pip install fails in containers)
- **Model name normalization**: Free models display as "OR-Free/Model Name (Retry)" without redundant prefixes
- **Robust user valve handling**: Safely extracts API keys whether user valves are dicts or Pydantic objects

## Previous Features in v0.1.12

### 🐛 Bug Fixes
- **Server Lockup Fix**: Converted to asynchronous implementation to prevent blocking the entire Open WebUI server during retries
- **Image Rendering Fix**: Removed markdown formatting from retry summaries to prevent interference with image rendering in responses
- **Content Parsing**: Retry summaries now use plain text formatting to avoid conflicts with markdown content

## Previous Features in v0.1.9

### 🎯 Free Models Only
- **Filtered Model List**: Only displays models that end with "(free)" from OpenRouter's API
- **Alphabetical Sorting**: Free models are sorted alphabetically for easier browsing
- **Reduced Clutter**: Eliminates paid models from the interface for users focused on free options

### 📢 Retry Status Summaries
- **Response Integration**: Retry information is included directly in the chat response when retries occur
- **Detailed Summaries**: Shows attempt count, success/failure status, and error details
- **Non-Intrusive**: Status appears as part of the response content without UI notifications

### 🔧 Enhanced Retry Logic
- **Asynchronous Implementation**: Non-blocking retries that don't lock up the Open WebUI server
- **Response Content Integration**: Retry summaries are prepended to successful responses
- **Improved Error Handling**: Better detection and reporting of different error types

### 🔁 Retry Scheduler Improvements (v0.1.12)
- **Burst-based retries**: Fast retry bursts to recover quickly from transient 429s:
  - attempts_per_burst (default 10) with 2–4s spacing between attempts
  - bursts_before_long_pause (default 3)
  - burst pause between bursts: 15–30s
  - cycles (default 2) with a long pause (default 60s) between cycles
- **Structured final error**: If all attempts are exhausted the pipe returns a structured error:
  {"error": {"message": "..."},"retry_info": {"attempts": N, "success": false, "errors": [...]}}
- **Notifications**: Optional ENABLE_NOTIFICATIONS valve (default true) emits status events to the OpenWebUI event emitter on retries, bursts, cycles, success and final failure.
- **Non-blocking**: All waits use asyncio so the server remains responsive.

## Installation

### Method 1: Install via Open WebUI Admin Panel (Recommended)

1. Navigate to your Open WebUI Admin Panel
2. Go to **Functions**
3. Click **Upload Function**
4. Select the `openrouter-retry.py` file from this directory
5. Click **Install**

### Method 2: Manual Installation

1. Copy the `openrouter-retry.py` file to your Open WebUI functions directory:
    ```
    cp openrouter-retry.py /path/to/open-webui/functions/pipes/openrouter_retry/
    ```

2. If you're using Docker, you can mount the file as a volume:
    ```bash
    docker run -d -p 3000:8080 \
      --add-host=host.docker.internal:host-gateway \
      -v ./functions/pipes/openrouter_retry:/app/functions/pipes/openrouter_retry \
      -v open-webui:/app/backend/data \
      --name open-webui \
      --restart always \
      ghcr.io/open-webui/open-webui:main
    ```

## Dependencies

This pipe uses aiohttp for non-blocking HTTP I/O.

- If you run Open WebUI in Docker (container name may vary):
  ```
  docker exec -it open-webui pip install --no-cache-dir aiohttp
  # or if pip is not found
  docker exec -it open-webui pip3 install --no-cache-dir aiohttp
  ```
- If you run Open WebUI on the host:
  ```
  pip install aiohttp
  # or
  pip3 install aiohttp
  ```

Note: After installing the dependency, restart the Open WebUI process/container.

## Configuration

After installation, configure the pipe through the Open WebUI Admin Panel:

1. Navigate to **Admin Panel > Functions**
2. Find the "OpenRouter Free Model Retry Pipe" in the list
3. Click the **Configure** button (gear icon)
4. Set the following options:

| Option | Description | Default Value |
|--------|-------------|---------------|
| `OPENROUTER_API_BASE_URL` | The base URL for OpenRouter API endpoints | `https://openrouter.ai/api/v1` |
| `OPENROUTER_API_KEY` | Required API key to retrieve the model list | `""` |
| `ENABLE_NOTIFICATIONS` | Emit status events to OpenWebUI event emitter (if available) | `True` |
| `attempts_per_burst` | Number of attempts per fast retry burst | `10` |
| `attempt_delay_min` | Minimum delay between attempts within a burst (seconds) | `2.0` |
| `attempt_delay_max` | Maximum delay between attempts within a burst (seconds) | `4.0` |
| `bursts_before_long_pause` | Number of bursts before a longer pause | `3` |
| `burst_pause_min` | Minimum pause between bursts (seconds) | `15.0` |
| `burst_pause_max` | Maximum pause between bursts (seconds) | `30.0` |
| `cycles` | Number of cycles (each cycle consists of bursts_before_long_pause bursts) | `2` |
| `long_pause` | Long pause between cycles (seconds) | `60.0` |

## How It Works

This version is asynchronous and non-blocking. While the pipe is waiting between retries, the server event loop remains responsive and other requests continue to be served. Retry attempt messages (e.g., "Received 429 error... Waiting X seconds...") are printed to the server logs immediately, one attempt at a time.


### Model Filtering
1. Fetches all available models from OpenRouter API
2. Filters to only include models ending with "(free)"
3. Sorts the filtered models alphabetically
4. Presents only the free models in the OpenWebUI interface

### Retry Logic with Status Summaries
1. When a 429 error occurs, the pipe automatically retries with a burst-based timing strategy
2. For streaming responses, retry information is prepended to the final response stream
3. For non-streaming responses, a retry summary appears at the beginning of the response
4. When retries exhaust, the pipe returns a structured error containing the provider error and retry_info; a final error notification is emitted so the UI can unblock

### Status Summary Examples
```
OpenRouter Retry Summary: 3 attempts, Success
```

For failed retries:
```
OpenRouter Retry Summary: 31 attempts, Failed
Last Error: Max retry attempts (31) exceeded for OpenRouter request.
```

## Usage

1. After installing and configuring the pipe, restart your Open WebUI instance
2. Only free models ending with "(free)" will appear in the model selector
3. When using these models, 429 errors will be automatically retried with live status updates
4. Monitor the retry progress through the status messages in the UI

## Troubleshooting

### Issue: Status messages not appearing
**Solution**: Ensure you're using a compatible version of OpenWebUI that supports the event emitter system.

### Issue: No free models showing
**Solution**:
1. Verify your OpenRouter API key has access to free models
2. Check the OpenRouter API status
3. Ensure the API key is correctly configured

### Issue: Retries not working
**Solution**:
1. Check that the model being used ends with "(free)"
2. Verify the retry configuration values
3. Check Open WebUI logs for any error messages

## Migration from Previous Version

If you're upgrading from the original version:

1. The pipe now only shows free models - if you need paid models, use the original version
2. Status messages are now real-time during retries instead of only in error responses
3. The pipe is now asynchronous and non-blocking; Open WebUI continues serving other users while retries sleep via asyncio without blocking the event loop
4. Event emission is handled gracefully with fallback support for older OpenWebUI versions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
