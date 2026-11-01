"""Background YOLO object detection with continuous monitoring"""

from typing import Dict, Any, List, Optional
import cv2
import threading
import time
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from strands import tool

# Global state for background detection
_detection_thread = None
_detection_active = False
_detection_lock = threading.Lock()
_detections_history = []
_object_counts = defaultdict(int)


def _detection_worker(
    model_name: str, camera_id: int, confidence: float, save_dir: Path, interval: float
):
    """Background worker thread for continuous YOLO detection."""
    global _detection_active, _detections_history, _object_counts

    try:
        # Import YOLO (ultralytics)
        from ultralytics import YOLO

        # Load model
        print(f"🧠 Loading YOLO model: {model_name}")
        model = YOLO(model_name)

        # Open camera
        cam = cv2.VideoCapture(camera_id)
        if not cam.isOpened():
            print(f"❌ Failed to open camera {camera_id}")
            _detection_active = False
            return

        print(f"✅ YOLO detection started on camera {camera_id}")

        while _detection_active:
            start_time = time.time()

            # Capture frame
            ret, frame = cam.read()
            if not ret:
                time.sleep(0.1)
                continue

            # Run YOLO detection
            results = model(frame, conf=confidence, verbose=False)

            # Process detections
            detected_objects = []
            for result in results:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    class_name = model.names[class_id]

                    detected_objects.append(
                        {
                            "object": class_name,
                            "confidence": round(conf, 3),
                            "bbox": box.xyxy[0].tolist(),
                        }
                    )

                    # Update object counts
                    with _detection_lock:
                        _object_counts[class_name] += 1

            # Log detections if any found
            if detected_objects:
                detection_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "camera_id": camera_id,
                    "objects": detected_objects,
                    "count": len(detected_objects),
                }

                with _detection_lock:
                    _detections_history.append(detection_entry)

                    # Save to file
                    detections_file = save_dir / "detections.jsonl"
                    with open(detections_file, "a") as f:
                        f.write(json.dumps(detection_entry) + "\n")

                # Print detection summary
                objects_summary = ", ".join(
                    [
                        f"{obj['object']}({obj['confidence']:.2f})"
                        for obj in detected_objects
                    ]
                )
                print(
                    f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Detected: {objects_summary}"
                )

            # Maintain interval
            elapsed = time.time() - start_time
            if elapsed < interval:
                time.sleep(interval - elapsed)

        cam.release()
        print("👋 YOLO detection stopped")

    except ImportError:
        print("❌ ultralytics not installed. Run: pip install ultralytics")
        _detection_active = False
    except Exception as e:
        print(f"❌ Detection worker error: {e}")
        _detection_active = False


@tool
def yolo_vision(
    action: str = "status",
    model: str = "yolov8n.pt",
    camera_id: int = 0,
    confidence: float = 0.5,
    save_dir: str = "./.yolo_detections",
    interval: float = 1.0,
    limit: int = 50,
) -> Dict[str, Any]:
    """Background YOLO object detection with continuous monitoring

    Args:
        action: Action to perform
            - "start": Begin background detection
            - "stop": Stop background detection
            - "status": Check if running
            - "get_detections": Recent detection entries
            - "list_objects": All unique objects seen with counts
            - "clear": Clear detection history
        model: YOLO model to use (yolov8n.pt, yolov8s.pt, yolov8m.pt, etc.)
        camera_id: Camera device ID
        confidence: Minimum confidence threshold (0.0-1.0)
        save_dir: Directory to save detection logs
        interval: Seconds between detections
        limit: Max number of recent detections to return

    Returns:
        Dict with status and content
    """
    global _detection_thread, _detection_active, _detections_history, _object_counts

    try:
        save_path = Path(save_dir).expanduser()
        save_path.mkdir(parents=True, exist_ok=True)

        if action == "start":
            if _detection_active:
                return {
                    "status": "error",
                    "content": [{"text": "❌ YOLO detection already running"}],
                }

            # Start detection thread
            _detection_active = True
            _detection_thread = threading.Thread(
                target=_detection_worker,
                args=(model, camera_id, confidence, save_path, interval),
                daemon=True,
            )
            _detection_thread.start()

            result_info = [
                "✅ **YOLO Detection Started**",
                f"🧠 Model: {model}",
                f"📹 Camera: {camera_id}",
                f"🎯 Confidence: {confidence}",
                f"⏱️  Interval: {interval}s",
                f"💾 Save dir: `{save_path}`",
            ]

            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        elif action == "stop":
            if not _detection_active:
                return {
                    "status": "error",
                    "content": [{"text": "❌ YOLO detection not running"}],
                }

            _detection_active = False
            if _detection_thread:
                _detection_thread.join(timeout=5)

            result_info = [
                "🛑 **YOLO Detection Stopped**",
                f"📊 Total detections logged: {len(_detections_history)}",
                f"🔍 Unique objects seen: {len(_object_counts)}",
            ]

            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        elif action == "status":
            with _detection_lock:
                total_detections = len(_detections_history)
                unique_objects = len(_object_counts)
                recent_objects = []

                if _detections_history:
                    last_detection = _detections_history[-1]
                    recent_objects = [
                        obj["object"] for obj in last_detection["objects"]
                    ]

            status_icon = "🟢" if _detection_active else "🔴"
            result_info = [
                f"{status_icon} **YOLO Detection Status**",
                f"Running: {'✅ Yes' if _detection_active else '❌ No'}",
                f"📊 Total detections: {total_detections}",
                f"🔍 Unique objects: {unique_objects}",
                f"💾 Save directory: `{save_path}`",
            ]

            if recent_objects:
                result_info.append(f"🕐 Last seen: {', '.join(set(recent_objects))}")

            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        elif action == "get_detections":
            with _detection_lock:
                recent = _detections_history[-limit:] if _detections_history else []

            if not recent:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No detections logged yet"}],
                }

            result_info = [f"🔍 **Recent {len(recent)} Detections:**", ""]

            for entry in recent[-10:]:  # Show last 10
                timestamp = datetime.fromisoformat(entry["timestamp"]).strftime(
                    "%H:%M:%S"
                )
                objects = ", ".join(
                    [
                        f"{obj['object']}({obj['confidence']:.2f})"
                        for obj in entry["objects"]
                    ]
                )
                result_info.append(f"🕐 **{timestamp}**: {objects}")

            result_info.extend(
                [
                    "",
                    f"📊 Total entries: {len(recent)}",
                    f"📁 Full log: `{save_path}/detections.jsonl`",
                ]
            )

            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        elif action == "list_objects":
            with _detection_lock:
                object_list = sorted(
                    _object_counts.items(), key=lambda x: x[1], reverse=True
                )

            if not object_list:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No objects detected yet"}],
                }

            result_info = [
                f"🏆 **All Detected Objects ({len(object_list)} unique):**",
                "",
            ]

            for obj, count in object_list:
                result_info.append(f"• **{obj}**: {count} times")

            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        elif action == "clear":
            with _detection_lock:
                _detections_history.clear()
                _object_counts.clear()

            # Clear log file
            detections_file = save_path / "detections.jsonl"
            if detections_file.exists():
                detections_file.unlink()

            return {
                "status": "success",
                "content": [{"text": "✅ Detection history cleared"}],
            }

        else:
            return {
                "status": "error",
                "content": [{"text": f"❌ Unknown action: {action}"}],
            }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
