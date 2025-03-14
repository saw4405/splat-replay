import os
import cv2

import pytest

from src.analyzer import Analyzer


@pytest.fixture(scope="module")
def analyzer():
    return Analyzer()


@pytest.fixture
def load_image():
    def _load(filename: str):
        base_path = os.path.join(os.getcwd(), "tests",
                                 "fixtures", "sample_images")
        image_path = os.path.join(base_path, filename)
        image = cv2.imread(image_path)
        if image is None:
            pytest.skip(f"画像ファイルが存在しないか読み込めません: {image_path}")
        return image
    return _load


@pytest.mark.parametrize("filename,expected", [
    ("result_1.png", (10, 8, 3)),
    ("result_2.png", (0, 1, 0)),
    ("result_3.png", (9, 9, 2)),
    ("result_fes.png", None),   # 現状、フェスには対応していない
    ("result_not_lose.png", (11, 7, 3)),
])
def test_kill_record(analyzer, load_image, filename, expected):
    image = load_image(filename)
    result = analyzer.kill_record(image)
    assert result == expected
