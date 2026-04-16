# YouTube Shorts Automator

A local-first Python application that automates turning long videos into scheduled YouTube Shorts. Drop a single long video into a folder and get days or weeks of scheduled content.

## Prerequisites

- **Python 3.10+**
- **ffmpeg** - for video processing and caption burn-in
- **YouTube Data API credentials** - for uploading to YouTube
- **OpenAI API key** - for metadata generation (titles, descriptions, hashtags)

### Installing ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows (via chocolatey)
choco install ffmpeg
```

## Setup

```bash
# Clone and enter the project
cd youtube-shorts-automator

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy the example config and edit it
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your API keys and preferences.

### YouTube API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project and enable the **YouTube Data API v3**
3. Create **OAuth 2.0 Client ID** credentials (Desktop application)
4. Download the client secrets JSON and save it as `client_secrets.json` in the project root
5. The first upload will open a browser window for OAuth consent

## Usage

### Start the automator

```bash
python -m src.main start
```

This launches the folder watcher and scheduler. Drop video files into `videos/input/` and the system handles the rest.

### Check status

```bash
python -m src.main status
```

### Retry a failed upload

```bash
python -m src.main retry <short_id>
```

### Reset a job for reprocessing

```bash
python -m src.main reset <job_id>
```

## Scheduling

All scheduling is controlled through the `schedule` section in `config.yaml`.

### Option 1: Post every day

Upload one Short per day at a fixed time.

```yaml
schedule:
  frequency: "daily"
  time: "10:00"
```

### Option 2: Post on specific weekdays

Upload only on the days you choose.

```yaml
schedule:
  frequency: "weekdays"
  time: "14:30"
  days:
    - "Monday"
    - "Wednesday"
    - "Friday"
```

Valid day names: `Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`, `Sunday`.

### Option 3: Custom cron expression

For full control, use a standard 5-field cron expression as the `frequency` value. The `time` field is ignored when using a cron expression since the time is embedded in the expression itself.

```yaml
schedule:
  # Every Tuesday and Thursday at 9:15 AM
  frequency: "15 9 * * TUE,THU"
  time: "09:15"  # ignored when frequency is a cron expression
```

Cron format: `minute hour day-of-month month day-of-week`

| Field         | Values              | Example      |
|---------------|---------------------|--------------|
| Minute        | 0-59                | `30`         |
| Hour          | 0-23                | `14`         |
| Day of month  | 1-31 or `*`         | `*`          |
| Month         | 1-12 or `*`         | `*`          |
| Day of week   | MON-SUN or 0-6      | `MON,WED`    |

### Common cron examples

```yaml
# Twice a day at 9 AM and 6 PM
frequency: "0 9,18 * * *"

# Every 2 hours during business hours on weekdays
frequency: "0 9-17/2 * * MON-FRI"

# Once a week on Sunday at noon
frequency: "0 12 * * SUN"

# Every day at 8 PM
frequency: "0 20 * * *"
```

### Content Machine scheduling

When you set `number_of_shorts_per_video` to a high number, the scheduler automatically spreads the uploads across future dates based on your schedule. For example:

```yaml
number_of_shorts_per_video: 30
schedule:
  frequency: "daily"
  time: "10:00"
```

This generates 30 Shorts from a single video and schedules them one per day for the next 30 days. Each Short is uploaded to YouTube as a **private** video with a `publishAt` time, so they go public automatically on schedule.

## How It Works

1. **Watch** - Monitors `videos/input/` for new video files
2. **Split** - Divides long videos into <= 60-second clips
3. **Caption** - Transcribes audio with Whisper and burns subtitles into the video
4. **Metadata** - Automatically generates titles, descriptions, and hashtags via an LLM using the transcript (no manual input needed; falls back to transcript-based defaults if no API key is set)
5. **Schedule** - Queues shorts for upload according to your posting schedule
6. **Upload** - Publishes to YouTube as private videos with scheduled publish times

## Modes

- **Auto mode** - Automatically moves to the next video when the configured short limit is reached
- **Manual mode** - Pauses after processing one video until a new one is added

## Content Machine

A single 30-minute video can produce 30 Shorts scheduled over 30 days. Drop one video, get a month of content.
