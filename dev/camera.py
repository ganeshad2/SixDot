import cv2
import threading
from datetime import datetime
from pathlib import Path

# Only check external camera indices
EXTERNAL_CAMERA_INDICES = [1, 2]

# ---------- shared state ----------
command = None
running = True

# ---------- paths ----------
CAPTURE_DIR = Path.cwd() / "captures"
CAPTURE_DIR.mkdir(exist_ok=True)

# ---------- camera selection ----------
def open_external_camera(indices):
    for idx in indices:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            # warm-up frames
            for _ in range(10):
                cap.read()
            print(f"Using external camera index: {idx}")
            return cap, idx
        cap.release()
    return None, None

# ---------- input thread ----------
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

# ---------- main ----------
def main():
    global command, running

    cap, cam_idx = open_external_camera(EXTERNAL_CAMERA_INDICES)
    if cap is None:
        print("Error: External webcam not found.")
        print("Make sure it is plugged in and not used by another application.")
        return

    threading.Thread(target=input_thread, daemon=True).start()

    last_frame = None
    window_name = f"Webcam Preview (external camera {cam_idx})"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    while running:
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
                print(f"Active external camera index: {cam_idx}")

            elif cmd == "s":
                if last_frame is None:
                    print("No frame available yet.")
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = CAPTURE_DIR / f"snapshot_cam{cam_idx}_{timestamp}.jpg"

                    success = cv2.imwrite(str(filepath), last_frame)
                    if success:
                        print("Image saved successfully.")
                        print(f"Saved to: {filepath.resolve()}")
                    else:
                        print("Error: Failed to save image.")

            elif cmd == "q":
                running = False

    cap.release()
    cv2.destroyAllWindows()
    print("Program exited cleanly.")

if __name__ == "__main__":
    main()