# LLM Summarization Retry Implementation

## Overview

This implementation adds automatic retry logic for failed LLM summarizations. When the Ollama container is offline or unreachable, summarization attempts are deferred and retried automatically at increasing intervals.

## Changes Made

### 1. Database Schema
**File**: `src/models/link.py`
- Added `summary_last_retry_at` field to track last retry timestamp
- Enables time-based retry scheduling with progressive backoff

**Migration**: `migrations/add_summary_last_retry_at.py`
- Run with: `python -m alembic upgrade head`

### 2. Processing Logic
**File**: `src/services/processor.py`
- **Old behavior**: Immediate retry with exponential backoff (blocking)
- **New behavior**: Single attempt on submission, failures marked for deferred retry
- No longer blocks background task with sleep delays
- Sets `summary_last_retry_at` timestamp on failure

### 3. Retry Service
**File**: `src/services/retry_summarization.py`

**Key Features**:
- Progressive backoff intervals: 15min → 30min → 1hr → 2hr → 4hr
- Only retries LLM service failures (not content extraction failures)
- Batch processes up to 50 links per run
- Re-extracts content (handles URL changes)
- Respects `llm_max_retries` limit

**Query Conditions**:
```python
- status == COMPLETED (content extraction succeeded)
- summary IS NULL (no summary yet)
- summary_error contains "unavailable", "timeout", or "service"
- summary_retry_count < max_retries
- Sufficient time elapsed since last retry
```

### 4. Scheduler Integration
**File**: `src/main.py`
- Imported `APScheduler` for periodic tasks
- Runs `retry_summarizations()` every 20 minutes
- Only active when `LLM_ENABLED=true`
- Graceful shutdown on app termination

### 5. Manual Trigger
**File**: `src/cli/admin.py`
- New command: `python src/cli/admin.py retry-summaries`
- Useful for testing or immediate retry

### 6. Dependencies
**File**: `requirements.txt`
- Added `APScheduler==3.10.4`

## Retry Intervals

| Attempt | Wait Time | Total Elapsed |
|---------|-----------|---------------|
| 1st     | 15 min    | 15 min        |
| 2nd     | 30 min    | 45 min        |
| 3rd     | 1 hour    | 1h 45min      |
| 4th     | 2 hours   | 3h 45min      |
| 5th     | 4 hours   | 7h 45min      |

After max retries, link is marked with permanent error.

## Error Types

**Will Retry** (LLM service issues):
- "Summarization service unavailable"
- "Timeout while generating summary"
- "HTTP error from Ollama"

**Will NOT Retry** (content issues):
- "Article content unavailable"
- "Content not suitable for summarization"
- "Unable to extract article text"

## Usage

### Automatic (Production)
- Runs every 20 minutes automatically
- No configuration needed
- Logs to standard application logs

### Manual Testing
```bash
# Trigger retry task immediately
python src/cli/admin.py retry-summaries

# View links needing retry
python src/cli/admin.py view-failed-links

# Reset retry counts for testing
python src/cli/admin.py reset-summary-retries <username>
```

### Monitoring
Check logs for:
```
"Found N link(s) needing summarization retry"
"Link ID summarized successfully on retry"
"Summarization retry task completed: X succeeded, Y failed"
```

## Configuration

Existing settings in `.env`:
```bash
LLM_ENABLED=true              # Enable/disable LLM features
LLM_MAX_RETRIES=5             # Maximum retry attempts
LLM_BASE_URL=http://ollama:11434
```

## Deployment

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run migration:
   ```bash
   python -m alembic upgrade head
   ```

3. Restart application:
   ```bash
   docker-compose restart logkeep-green
   ```

## Benefits

1. **No blocking**: Background tasks complete quickly
2. **Resilient**: Handles temporary Ollama outages
3. **User-friendly**: No manual intervention required
4. **Efficient**: Progressive backoff reduces load
5. **Transparent**: Clear logging and status tracking
