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

## How It Works

1. **Watch** - Monitors `videos/input/` for new video files
2. **Split** - Divides long videos into <= 60-second clips
3. **Caption** - Transcribes audio with Whisper and burns subtitles into the video
4. **Metadata** - Generates titles, descriptions, and hashtags via an LLM
5. **Schedule** - Queues shorts for upload according to your posting schedule
6. **Upload** - Publishes to YouTube as private videos with scheduled publish times

## Modes

- **Auto mode** - Automatically moves to the next video when the configured short limit is reached
- **Manual mode** - Pauses after processing one video until a new one is added

## Content Machine

A single 30-minute video can produce 30 Shorts scheduled over 30 days. Drop one video, get a month of content.
