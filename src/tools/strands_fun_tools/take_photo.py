"""Take photos using camera with multi-camera support"""

from typing import Dict, Any, List, Optional
import cv2
import os
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from strands import tool


def _discover_cameras(max_check: int = 10) -> List[int]:
    """Discover all available cameras by checking indices."""
    available_cameras = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available_cameras.append(i)
            cap.release()
    return available_cameras


def _capture_from_camera(
    camera_id: int, save_dir: Path, detect_faces: bool, delay: float, face_cascade
) -> Dict[str, Any]:
    """Capture a single photo from a specific camera."""
    try:
        cam = cv2.VideoCapture(camera_id)
        if not cam.isOpened():
            return {
                "camera_id": camera_id,
                "status": "error",
                "message": "Failed to open camera",
            }

        # Warmup and delay
        time.sleep(delay)
        ret, frame = cam.read()
        cam.release()

        if not ret:
            return {
                "camera_id": camera_id,
                "status": "error",
                "message": "Failed to capture frame",
            }

        # Detect faces if enabled
        faces_found = 0
        if detect_faces and face_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            faces_found = len(faces)
            for x, y, w, h in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

        # Save photo with meaningful filename
        timestamp = int(time.time())
        meaningful_part = f"face-{faces_found}" if detect_faces else "capture"
        filename = f"photo-{timestamp}-cam{camera_id}-{meaningful_part}.jpg"
        filepath = save_dir / filename
        cv2.imwrite(str(filepath), frame)

        # Get file info
        height, width = frame.shape[:2]
        file_size = os.path.getsize(filepath)

        return {
            "camera_id": camera_id,
            "status": "success",
            "filepath": str(filepath),
            "resolution": f"{width}x{height}",
            "faces_found": faces_found,
            "file_size": file_size,
        }

    except Exception as e:
        return {"camera_id": camera_id, "status": "error", "message": str(e)}


@tool
def take_photo(
    camera_ids: Optional[List[int]] = None,
    num_photos: int = 1,
    delay: float = 3.0,
    detect_faces: bool = True,
    save_path: str = None,
    discover: bool = False,
) -> Dict[str, Any]:
    """Capture photos using computer's camera(s) with multi-camera support

    Args:
        camera_ids: List of camera IDs to use (e.g., [0, 1, 2]). If None, uses camera 0
        num_photos: Number of photos to take per camera (1-10)
        delay: Delay before capturing in seconds
        detect_faces: Use face detection
        save_path: Directory to save photos (defaults to current directory)
        discover: If True, discover and list all available cameras without capturing

    Returns:
        Dict with status and content
    """
    try:
        # Discovery mode
        if discover:
            cameras = _discover_cameras()
            if not cameras:
                return {
                    "status": "error",
                    "content": [{"text": "❌ No cameras detected"}],
                }

            result_info = [
                "🔍 **Camera Discovery Results:**",
                f"Found {len(cameras)} camera(s): {cameras}",
                "",
                "Use `camera_ids=[0, 1, 2]` to capture from specific cameras",
            ]
            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        # Setup save directory
        save_dir = Path(save_path).expanduser() if save_path else Path.cwd()
        save_dir.mkdir(parents=True, exist_ok=True)

        # Load face detector if needed
        face_cascade = None
        if detect_faces:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)

        # Determine which cameras to use
        if camera_ids is None:
            camera_ids = [0]  # Default to camera 0

        # Validate cameras exist
        available = _discover_cameras()
        for cam_id in camera_ids:
            if cam_id not in available:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"❌ Camera {cam_id} not available. Available: {available}"
                        }
                    ],
                }

        all_results = []
        successful_captures = 0

        # Multi-camera parallel capture
        if len(camera_ids) > 1:
            print(f"📸 Capturing from {len(camera_ids)} cameras in parallel...")

            with ThreadPoolExecutor(max_workers=len(camera_ids)) as executor:
                futures = []
                for cam_id in camera_ids:
                    for photo_num in range(num_photos):
                        future = executor.submit(
                            _capture_from_camera,
                            cam_id,
                            save_dir,
                            detect_faces,
                            delay,
                            face_cascade,
                        )
                        futures.append(future)

                for future in as_completed(futures):
                    result = future.result()
                    all_results.append(result)
                    if result["status"] == "success":
                        successful_captures += 1

        # Single camera sequential capture
        else:
            cam_id = camera_ids[0]
            for i in range(num_photos):
                print(f"📸 Taking photo {i+1}/{num_photos} from camera {cam_id}...")
                result = _capture_from_camera(
                    cam_id, save_dir, detect_faces, delay, face_cascade
                )
                all_results.append(result)
                if result["status"] == "success":
                    successful_captures += 1

        # Format results
        result_info = [
            "📸 **Photo Capture Results:**",
            f"✅ Success: {successful_captures}/{len(all_results)} photos",
            f"📁 Save directory: `{save_dir}`",
            "",
        ]

        for result in all_results:
            if result["status"] == "success":
                result_info.append(
                    f"✅ **Camera {result['camera_id']}**: {result['resolution']} "
                    f"({result['faces_found']} faces, {result['file_size']:,} bytes)"
                )
                result_info.append(f"   📄 `{result['filepath']}`")
            else:
                result_info.append(
                    f"❌ **Camera {result['camera_id']}**: {result['message']}"
                )

        return {
            "status": "success" if successful_captures > 0 else "error",
            "content": [{"text": "\n".join(result_info)}],
        }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
