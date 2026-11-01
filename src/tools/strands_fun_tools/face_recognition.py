"""Face recognition using AWS Rekognition"""

from typing import Dict, Any, Optional
import cv2
import boto3
import io
import time
from strands import tool


@tool
def face_recognition(
    action: str,
    collection_id: Optional[str] = None,
    external_image_id: Optional[str] = None,
    face_id: Optional[str] = None,
    similarity_threshold: float = 90.0,
    max_faces: int = 10,
) -> Dict[str, Any]:
    """Face recognition with AWS Rekognition

    Args:
        action: Action (capture, index_face, search_faces, list_faces, delete_face, create_collection, list_collections)
        collection_id: AWS Rekognition Collection ID
        external_image_id: Identifier for face image
        face_id: Face ID for operations
        similarity_threshold: Similarity threshold (0-100)
        max_faces: Max faces to return

    Returns:
        Dict with status and content
    """
    try:
        rekognition = boto3.client("rekognition")

        if action == "create_collection":
            if not collection_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ collection_id required"}],
                }
            rekognition.create_collection(CollectionId=collection_id)
            return {
                "status": "success",
                "content": [{"text": f"✅ Created collection: {collection_id}"}],
            }

        elif action == "list_collections":
            response = rekognition.list_collections()
            collections = response.get("CollectionIds", [])
            return {
                "status": "success",
                "content": [{"text": f"✅ Collections: {', '.join(collections)}"}],
            }

        elif action == "capture":
            # Capture from camera
            cam = cv2.VideoCapture(0)
            if not cam.isOpened():
                return {
                    "status": "error",
                    "content": [{"text": "❌ Could not open camera"}],
                }

            print("📸 Capturing face in 3 seconds...")
            time.sleep(3)
            ret, frame = cam.read()
            cam.release()

            if not ret:
                return {
                    "status": "error",
                    "content": [{"text": "❌ Could not capture image"}],
                }

            # Convert to bytes
            _, buffer = cv2.imencode(".jpg", frame)
            image_bytes = io.BytesIO(buffer).getvalue()

            return {"status": "success", "content": [{"text": "✅ Image captured"}]}

        elif action == "index_face":
            if not collection_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ collection_id required"}],
                }

            # Capture and index
            cam = cv2.VideoCapture(0)
            ret, frame = cam.read()
            cam.release()

            _, buffer = cv2.imencode(".jpg", frame)
            image_bytes = buffer.tobytes()

            response = rekognition.index_faces(
                CollectionId=collection_id,
                Image={"Bytes": image_bytes},
                ExternalImageId=external_image_id or f"face_{int(time.time())}",
                DetectionAttributes=["ALL"],
            )

            face_records = response.get("FaceRecords", [])
            return {
                "status": "success",
                "content": [{"text": f"✅ Indexed {len(face_records)} faces"}],
            }

        elif action == "search_faces":
            if not collection_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ collection_id required"}],
                }

            # Capture and search
            cam = cv2.VideoCapture(0)
            ret, frame = cam.read()
            cam.release()

            _, buffer = cv2.imencode(".jpg", frame)
            image_bytes = buffer.tobytes()

            response = rekognition.search_faces_by_image(
                CollectionId=collection_id,
                Image={"Bytes": image_bytes},
                FaceMatchThreshold=similarity_threshold,
                MaxFaces=max_faces,
            )

            matches = response.get("FaceMatches", [])
            result = []
            for match in matches:
                similarity = match["Similarity"]
                face_id = match["Face"]["FaceId"]
                external_id = match["Face"].get("ExternalImageId", "Unknown")
                result.append(f"Match: {external_id} (Similarity: {similarity:.2f}%)")

            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Found {len(matches)} matches:\n" + "\n".join(result)}
                ],
            }

        elif action == "list_faces":
            if not collection_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ collection_id required"}],
                }

            response = rekognition.list_faces(
                CollectionId=collection_id, MaxResults=max_faces
            )
            faces = response.get("Faces", [])
            result = [
                f"Face: {f['FaceId']} ({f.get('ExternalImageId', 'No ID')})"
                for f in faces
            ]

            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Found {len(faces)} faces:\n" + "\n".join(result)}
                ],
            }

        elif action == "delete_face":
            if not collection_id or not face_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ collection_id and face_id required"}],
                }

            rekognition.delete_faces(CollectionId=collection_id, FaceIds=[face_id])
            return {
                "status": "success",
                "content": [{"text": f"✅ Deleted face: {face_id}"}],
            }

        return {
            "status": "error",
            "content": [{"text": f"❌ Unknown action: {action}"}],
        }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
