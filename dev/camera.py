import cv2
import os
import threading
from datetime import datetime
from pathlib import Path


DEFAULT_CAMERA_INDICES = [1, 0]


# used for threading terminal input without blocking the camera preview loop
command = None # stores the latest user command (s, q)
running = True #controls when the program should exit

CAPTURE_DIR = Path.cwd() / "captures"
CAPTURE_DIR.mkdir(exist_ok=True)

def _camera_backends():
    return [cv2.CAP_DSHOW, cv2.CAP_ANY] if os.name == "nt" else [cv2.CAP_ANY]


def discover_camera_indices(preferred_indices=None):
    if os.name == "nt":
        return list(preferred_indices or DEFAULT_CAMERA_INDICES)

    detected_indices = []
    for device in sorted(Path('/dev').glob('video[0-9]*')):
        suffix = device.name.replace('video', '')
        if suffix.isdigit():
            detected_indices.append(int(suffix))

    if not detected_indices:
        return list(preferred_indices or DEFAULT_CAMERA_INDICES)

    ordered = []
    preferred = list(preferred_indices or DEFAULT_CAMERA_INDICES)
    for idx in preferred + detected_indices:
        if idx in detected_indices and idx not in ordered:
            ordered.append(idx)
    return ordered


def open_camera_by_index(index):
    for backend in _camera_backends():
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue

        # Warm up frames and confirm the camera can actually produce an image.
        frame_ok = False
        for _ in range(10):
            ret, _ = cap.read()
            if ret:
                frame_ok = True

        if frame_ok:
            print(f"Using camera index: {index}")
            return cap, index

        cap.release()

    return None, None


def list_available_cameras(indices=None):
    available = []
    for idx in discover_camera_indices(indices):
        cap, camera_index = open_camera_by_index(idx)
        if cap is not None:
            available.append(camera_index)
            cap.release()

    return available


# camera selection and decleration
def open_external_camera(indices=None):
    for idx in discover_camera_indices(indices):
        cap, camera_index = open_camera_by_index(idx)
        if cap is not None:
            return cap, camera_index
    return None, None #fail cleanly handling


def get_camera_info(camera_index):
    return f"Active external camera index: {camera_index}"


def save_snapshot(frame, camera_index):
    if frame is None:
        return False, "No frame available yet.", None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = CAPTURE_DIR / f"snapshot_cam{camera_index}_{timestamp}.jpg"
    success = cv2.imwrite(str(filepath), frame)

    if success:
        return True, "Image saved successfully.", filepath.resolve()
    return False, "Error: Failed to save image.", None

# input thread
def input_thread():
    global command, running
    print("\nCommands:")
    print("  s = save snapshot")
    print("  q = quit")
    print("  c = camera info")
    print("  h = help\n")

    while running:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            cmd = "q"

        if cmd in ("s", "q", "c", "h"):
            command = cmd
            if cmd == "q":
                running = False
        else:
            print("Unknown command. Type 'h' for help.")

def main():
    global command, running

    cap, cam_idx = open_external_camera()
    if cap is None:
        print("Error: External webcam not found.")
        print("Make sure it is plugged in and not used by another application.")
        return

    # start the terminal input in a background thread
    threading.Thread(target=input_thread, daemon=True).start()

    # store the most recent frame
    last_frame = None
    window_name = f"Webcam Preview (external camera {cam_idx})"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    # main camera loop, runs until user quits
    while running:
        #capture one frame from the webcam
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to read frame.")
            break

        last_frame = frame
        cv2.imshow(window_name, frame)
        cv2.waitKey(1)

        if command:
            cmd = command
            command = None

            if cmd == "h":
                print("Commands: s=save snapshot, q=quit, c=camera info, h=help")

            elif cmd == "c":
                print(get_camera_info(cam_idx))

            elif cmd == "s":
                success, message, filepath = save_snapshot(last_frame, cam_idx)
                print(message)
                if success and filepath is not None:
                    print(f"Saved to: {filepath}")

            elif cmd == "q":
                running = False

    cap.release()
    cv2.destroyAllWindows()
    print("Program exited cleanly.")

EXTERNAL_CAMERA_INDICES = discover_camera_indices(DEFAULT_CAMERA_INDICES)


if __name__ == "__main__":
    main()
