# Human Image Detection & Traffic Light Simulation

This project uses YOLOv11n for person detection and simulates a traffic light system based on the number of people detected.

## Prerequisites

- Python 3.x
- A webcam or video stream source

## Installation

1.  Clone the repository or download the source code.
2.  Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

    This will install `ultralytics` (for YOLO) and `opencv-python`.

## Usage

Run the main script to start the application:

```bash
python main.py
```

### Arguments

- `--source`: Camera index (0, 1, ...) or path/stream URL. Default is "0".
  ```bash
  python main.py --source 1
  python main.py --source http://192.168.0.10:8080/video
  ```
- `--iphone-url`: HTTP/RTSP stream URL for an iPhone camera (e.g., from an IP Camera app).
  ```bash
  python main.py --iphone-url http://192.168.1.5:8080/video
  ```

## Controls

When the application window is active:

- **`q`**: Quit the application.
- **`c`**: Switch between available local cameras.
- **`i`**: Switch between the iPhone stream (if configured) and the local camera.
