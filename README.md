# Automatic Retry Pipe

<<<<<<< HEAD
This is an Open WebUI pipe that includes enhanced retry logic for problematic free model providers from OpenRouter.ai with status summaries, filtering to only show free models, improved error handling, and artifact filtering.
=======
**Version 0.1.20**
>>>>>>> c673140 (linted. New README.md)

A sophisticated retry mechanism for Open WebUI that automatically handles API failures with intelligent backoff strategies, real-time status updates, and seamless integration.

## Overview

The Automatic Retry Pipe enhances Open WebUI by providing robust automatic retry functionality for OpenRouter API requests. When API calls fail due to rate limits, timeouts, or temporary errors, the pipe intelligently retries requests using a burst-based scheduling strategy while keeping users informed through real-time status updates.

## Key Features

### 🔄 Intelligent Retry Logic

- **Burst-based retries**: Fast retry bursts (default 10 attempts) with short delays (2-4 seconds)
- **Progressive backoff**: Longer pauses between retry cycles (15-30 seconds between bursts, 60 seconds between cycles)
- **Configurable limits**: Configurable cycles (default 2) with configurable burst count (default 3) within each cycle
- **Smart error handling**: Distinguishes between retryable and permanent errors

### 📊 Real-Time Status Updates

- **Live progress tracking**: See attempt-by-attempt progress in the chat interface
- **Visual status indicators**: Color-coded notifications (success green, warning yellow, error red)
- **Detailed summaries**: Complete retry history with timing and error information
- **Non-blocking UI**: Status updates don't interfere with chat functionality

### 🔧 Advanced Configuration

- **Per-user settings**: Individual API keys and preferences
- **Valve-based controls**: Fine-tune retry behavior through Open WebUI's valve system
- **Notification toggles**: Enable/disable different types of notifications
- **Provider detection**: Automatic provider name recognition for status messages

### 🚀 Performance Optimizations

- **Asynchronous processing**: Non-blocking retry logic using asyncio
- **Session isolation**: Fresh HTTP connections for each attempt to prevent corruption
- **Memory management**: Proper cleanup of HTTP sessions and connections
- **Streaming support**: Full compatibility with streaming responses

## Installation

### Method 1: Install via Open WebUI Admin Panel (Recommended)

1. Navigate to your Open WebUI Admin Panel
2. Go to **Functions**
3. Click **Upload Function**
4. Select the `automatic_retry.py` file
5. Click **Install**

### Method 2: Manual Installation

1. Copy `automatic_retry.py` to your Open WebUI functions directory:

   ```bash
   cp automatic_retry.py /path/to/open-webui/functions/pipes/
   ```

2. If using Docker, mount the file as a volume:

   ```bash
   docker run -d -p 3000:8080 \
     --add-host=host.docker.internal:host-gateway \
     -v ./automatic_retry.py:/app/functions/pipes/automatic_retry.py \
     -v open-webui:/app/backend/data \
     --name open-webui \
     --restart always \
     ghcr.io/open-webui/open-webui:main
   ```

## Dependencies

The pipe requires `aiohttp` for optimal performance:

- **Docker installation**:

  ```bash
  docker exec -it open-webui pip install --no-cache-dir aiohttp
  ```

- **Host installation**:

  ```bash
  pip install aiohttp
  ```

**Note**: Restart Open WebUI after installing dependencies. If aiohttp is unavailable, the pipe falls back to synchronous requests.

## Configuration

Configure the pipe through Open WebUI's Admin Panel > Functions > Automatic Retry Pipe > Configure:

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| `NAME_PREFIX` | Model name prefix | "OR-Free/" | String |
| `OPENROUTER_API_BASE_URL` | OpenRouter API endpoint | "https://openrouter.ai/api/v1" | URL |
| `OPENROUTER_API_KEY` | Global API key | "" | String |
| `ENABLE_NOTIFICATIONS` | Show status notifications | `true` | Boolean |
| `ENABLE_IN_CHAT_ERRORS` | Show errors in chat | `true` | Boolean |
| `attempts_per_burst` | Attempts per burst | 10 | 1-50 |
| `attempt_delay_min` | Min delay between attempts | 2.0 | 0.1-10.0 |
| `attempt_delay_max` | Max delay between attempts | 4.0 | 0.1-10.0 |
| `bursts_before_long_pause` | Bursts per cycle | 3 | 1-10 |
| `burst_pause_min` | Min pause between bursts | 15.0 | 1.0-300.0 |
| `burst_pause_max` | Max pause between bursts | 30.0 | 1.0-300.0 |
| `cycles` | Total retry cycles | 2 | 1-5 |
| `long_pause` | Pause between cycles | 60.0 | 10.0-600.0 |

### User-Specific Configuration

Users can override the global API key through their personal valves:

- Navigate to **Settings** > **Account** > **Automatic Retry Pipe**
- Enter personal `OPENROUTER_API_KEY`

## Usage

### Basic Usage

1. **Install and configure** the pipe as described above
2. **Select a model** with "Auto-Retry" in the name (e.g., "OR-Free/DeepSeek V3 (Auto-Retry)")
3. **Send messages normally** - retries happen automatically on failures
4. **Monitor progress** through status updates in the chat interface

### Model Selection

The pipe automatically filters and displays only free OpenRouter models with:

- "OR-Free" (default) prefixed (configurable)
- "(Auto-Retry)" appended

```
OR-Free/Anthropic: Claude 3.5 Sonnet (free) (Auto-Retry)
OR-Free/Meta: Llama 3.1 405B (free) (Auto-Retry)
OR-Free/Mistral: Mixtral 8x7B (free) (Auto-Retry)
```

### Status Monitoring

During retries, you'll see real-time updates:

```
Attempt 1/60 in progress...
Attempt 2/60 in progress...
Attempt 3/60 in progress...
Burst 1/3 completed (10/60 attempts). Waiting 18s before next burst
Attempt 11/60 in progress...
...
Response received from DeepSeek after 2m45s (23 attempts)
```

### Notification Types

- **🟢 Success**: Green notifications for successful responses after retries
- **🟡 Warning**: Yellow notifications for retry cycle transitions
- **🔴 Error**: Red notifications for final failures or critical errors
- **🔵 Info**: Blue notifications for retry summaries and progress updates

## How It Works

### Retry Strategy

The pipe uses a **hierarchical retry strategy**:

```
Cycles (2 total)
├── Cycle 1
│   ├── Burst 1: 10 attempts (2-4s delays)
│   ├── Burst 2: 10 attempts (2-4s delays)
│   └── Burst 3: 10 attempts (2-4s delays) → 15-30s pause
└── Cycle 2
    ├── Burst 1: 10 attempts (2-4s delays)
    ├── Burst 2: 10 attempts (2-4s delays)
    └── Burst 3: 10 attempts (2-4s delays) → 60s pause
```

**Total**: Up to 60 attempts over ~4-5 minutes

### Error Classification

- **Retryable errors** (429 rate limits, timeouts, connection errors):
  - Trigger immediate retry with burst scheduling
  - Show attempt-by-attempt status updates

- **Permanent errors** (400-499 HTTP codes except 429):
  - Fail immediately without retries
  - Show error notification

### Status Event System

The pipe communicates progress through Open WebUI's event system:

```javascript
// Status updates
{"type": "status", "data": {
  "description": "Attempt 5/60 in progress...",
  "done": false,
  "hidden": false
}}

// Notifications
{"type": "notification", "data": {
  "type": "success",
  "title": "OpenRouter",
  "content": "Response received after 3 attempts",
  "timeout": 10
}}
```

### Session Management

- **Fresh sessions**: Each retry attempt uses a new HTTP session
- **Automatic cleanup**: Sessions are properly closed in all code paths
- **Memory safety**: Prevents connection leaks and session corruption

### Streaming Compatibility

- **Full streaming support**: Works with real-time streaming responses
- **Retry summary injection**: Adds retry information to streaming chats
- **Session preservation**: Maintains streaming connections across retries

## Troubleshooting

### Common Issues

#### No free models showing

- Verify your OpenRouter API key has access to free models
- Check OpenRouter API status
- Ensure the API key is correctly configured

#### Status messages not appearing

- Confirm you're using a compatible Open WebUI version
- Check that `ENABLE_NOTIFICATIONS` is set to `true`
- Verify the pipe is properly installed

#### Retries not working

- Ensure you're using a model with "(Auto-Retry)" in the name
- Check retry configuration values
- Review Open WebUI logs for error messages

#### Unclosed session warnings

- This is normal and indicates proper session cleanup
- The warnings appear when sessions are garbage collected
- They don't affect functionality

### Log Analysis

Monitor Open WebUI logs for detailed retry information:

```
INFO - John:deepseek/deepseek-chat-v3-0324:free - Attempt 1/60: ERROR: 429
INFO - John:deepseek/deepseek-chat-v3-0324:free - Attempt 2/60: ERROR: 429
INFO - John:deepseek/deepseek-chat-v3-0324:free - Attempt 3/60 (0m27s): SUCCESS
```

### Performance Tuning

**For faster retries:**

- Reduce `attempt_delay_max` and `burst_pause_max`
- Increase `attempts_per_burst`

**For more patience:**

- Increase `cycles` and `long_pause`
- Add more `bursts_before_long_pause`

**For less intrusive notifications:**

- Set `ENABLE_NOTIFICATIONS` to `false`
- Keep only essential error notifications

## Migration from Previous Versions

If upgrading from earlier versions:

- **Status events replace chat injection**: Retry information now appears as status updates instead of being injected into chat responses
- **Improved session management**: Better HTTP connection handling prevents corruption
- **Enhanced error classification**: More intelligent retry vs. fail decisions
- **Real-time progress**: Live status updates during retry attempts

## Contributing

Contributions are welcome! The pipe is designed to be extensible and well-documented.

## License

This project is licensed under the MIT License.
