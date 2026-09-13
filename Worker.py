name: AutoClip Render Pipeline

on:
  repository_dispatch:
    types: [start-render]
  workflow_dispatch:
    inputs:
      youtube_url:
        description: 'YouTube Video URL'
        required: true
        default: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

jobs:
  render:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repo
        uses: actions/checkout@v4

      - name: Setup Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install FFmpeg
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg fonts-liberation

      - name: Install Dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Clipping Engine
        env:
          JOB_PAYLOAD: ${{ toJson(github.event.client_payload) }}
        run: |
          python worker.py

      - name: Upload Output Clips Artifact
        uses: actions/upload-artifact@v4
        with:
          name: autoclip-shorts
          path: output/*.mp4
          retention-days: 2

