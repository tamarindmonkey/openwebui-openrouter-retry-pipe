# OpenRouter Free Model Retry Pipe

This is a revised version of the OpenRouter pipe that includes enhanced retry logic with status summaries, filtering to only show free models, improved error handling, and artifact filtering.

## New Features in v0.1.9

### 🎯 Free Models Only
- **Filtered Model List**: Only displays models that end with "(free)" from OpenRouter's API
- **Alphabetical Sorting**: Free models are sorted alphabetically for easier browsing
- **Reduced Clutter**: Eliminates paid models from the interface for users focused on free options

### 📢 Retry Status Summaries
- **Response Integration**: Retry information is included directly in the chat response when retries occur
- **Detailed Summaries**: Shows attempt count, success/failure status, and error details
- **Non-Intrusive**: Status appears as part of the response content without UI notifications

### 🔧 Enhanced Retry Logic
- **Synchronous Implementation**: Compatible with OpenWebUI's pipeline framework
- **Response Content Integration**: Retry summaries are prepended to successful responses
- **Improved Error Handling**: Better detection and reporting of different error types

### 🧹 Response Cleaning
- **Safe Artifact Removal**: Uses targeted string replacement to remove exactly ": OPENROUTER PROCESSING" artifacts
- **Content Preservation**: Preserves all legitimate content while removing API artifacts
- **No Line Skipping**: Safer than line filtering - won't remove valid responses that happen to mention OpenRouter processing

## Installation

### Method 1: Install via Open WebUI Admin Panel (Recommended)

1. Navigate to your Open WebUI Admin Panel
2. Go to **Functions**
3. Click **Upload Function**
4. Select the `main_revision.py` file from this directory
5. Click **Install**

### Method 2: Manual Installation

1. Copy the `main_revision.py` file to your Open WebUI functions directory:
    ```
    cp main_revision.py /path/to/open-webui/functions/pipes/openrouter_retry/
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

## Configuration

After installation, configure the pipe through the Open WebUI Admin Panel:

1. Navigate to **Admin Panel > Functions**
2. Find the "OpenRouter 429 Error Retry Pipe (Fixed)" in the list
3. Click the **Configure** button (gear icon)
4. Set the following options:

| Option | Description | Default Value |
|--------|-------------|---------------|
| `OPENROUTER_API_BASE_URL` | The base URL for OpenRouter API endpoints | `https://openrouter.ai/api/v1` |
| `OPENROUTER_API_KEY` | Required API key to retrieve the model list | `""` |
| `first_retry_delay` | Delay in seconds for the first retry | `3.0` |
| `short_retry_count` | Number of short retries | `10` |
| `short_retry_delay` | Delay in seconds for short retries | `2.0` |
| `long_retry_count` | Number of long retries | `20` |
| `long_retry_delay` | Delay in seconds for long retries | `4.0` |
| `fallback_delay` | Delay in seconds before fallback retry sequence | `60.0` |

## How It Works

### Model Filtering
1. Fetches all available models from OpenRouter API
2. Filters to only include models ending with "(free)"
3. Sorts the filtered models alphabetically
4. Presents only the free models in the OpenWebUI interface

### Retry Logic with Status Summaries
1. When a 429 error occurs, the pipe automatically retries with your specified timing strategy
2. For streaming responses, retry information is prepended to the final response
3. For non-streaming responses, a retry summary appears at the beginning of the response
4. Response artifacts like ": OPENROUTER PROCESSING" are automatically filtered out

### Status Summary Examples
```
🔄 **OpenRouter Retry Summary**: 3 attempts, ✅ Success
```

For failed retries:
```
🔄 **OpenRouter Retry Summary**: 31 attempts, ❌ Failed
**Last Error**: Max retry attempts (31) exceeded for OpenRouter request.
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
3. The pipe maintains synchronous compatibility with OpenWebUI's pipeline framework
4. Event emission is handled gracefully with fallback support for older OpenWebUI versions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.