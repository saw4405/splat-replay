import os

import pytesseract
import numpy as np


class OCR:
    def __init__(self):
        PATH = os.environ["TESSERACT_PATH"]
        pytesseract.pytesseract.tesseract_cmd = PATH

    def get_text(self, image: np.ndarray) -> str:
        return str(pytesseract.image_to_string(image))
