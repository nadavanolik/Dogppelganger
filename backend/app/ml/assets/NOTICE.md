# Vendored model

`yunet_face_detection_2023mar.onnx` — YuNet face detector, from
[OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet),
licensed Apache-2.0. Author: Shiqi Yu and Yuantao Feng.

Committed rather than downloaded because it is 232KB — small enough that
vendoring beats a network fetch that could fail on a fresh VM, and unlike the
226MB dog corpus it costs the repository nothing meaningful.

Loaded by `app/ml/faces.py` via `cv2.FaceDetectorYN`.
