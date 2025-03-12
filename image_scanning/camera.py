# image_scanning/camera.py
import cv2
import threading

class VideoCamera(object):
    def __init__(self):
        # Use the DirectShow backend to avoid MSMF errors on Windows.
        self.video = cv2.VideoCapture(cv2.CAP_DSHOW)
        (self.grabbed, self.frame) = self.video.read()
        threading.Thread(target=self.update, args=(), daemon=True).start()

    def __del__(self):
        self.video.release()

    def get_frame(self):
        # Get current frame and encode as JPEG.
        ret, jpeg = cv2.imencode('.jpg', self.frame)
        return jpeg.tobytes()

    def update(self):
        while True:
            (self.grabbed, self.frame) = self.video.read()

def gen(camera):
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
