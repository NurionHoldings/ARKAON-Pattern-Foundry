import unittest
from PIL import Image
from frame_motion_engine import frame

class FrameMotionTests(unittest.TestCase):
    def test_dimensions_and_no_camera_translation(self):
        src=Image.new("RGB",(320,180),(12,20,28))
        a=frame(src,60)
        b=frame(src,160)
        self.assertEqual(a.size,(320,180))
        self.assertEqual(b.size,(320,180))
        self.assertNotEqual(a.tobytes(),b.tobytes())
        # Corner outside overlay stays identical after fade-in.
        self.assertEqual(a.getpixel((0,0)),b.getpixel((0,0)))

if __name__=="__main__": unittest.main()
