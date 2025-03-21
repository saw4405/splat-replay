import os
from typing import Callable

import cv2
import numpy as np
import pytest

from src.analyzer import Analyzer


@pytest.fixture(scope="module")
def analyzer():
    return Analyzer()


@pytest.fixture
def load_image() -> Callable[[str], cv2.typing.MatLike]:
    def _load(filename: str) -> cv2.typing.MatLike:
        base_path = os.path.join(os.getcwd(), "tests",
                                 "fixtures", "sample_images")
        image_path = os.path.join(base_path, filename)
        image = cv2.imread(image_path)
        if image is None:
            pytest.skip(f"画像ファイルが存在しないか読み込めません: {image_path}")
        return image
    return _load


@pytest.mark.parametrize("filename,expected", [
    ("change_schedule_1.png", True),
    ("loading_1.png", False)
])
def test_change_schedule(analyzer: Analyzer, load_image: Callable[[str], cv2.typing.MatLike], filename: str, expected: bool):
    image = load_image(filename)
    result = analyzer.change_schedule(image)
    assert result == expected


@pytest.mark.parametrize("filename,expected", [
    ("finish_1.png", True),
    ("finish_2.png", True),
    ("finish_3.png", True),
    ("finish_4.png", True),
    ("finish_5.png", True),
    ("finish_6.png", True),
    ("finish_7.png", True),
    ("finish_8.png", True),
    ("finish_9.png", True),
    ("finish_10.png", True),
    ("finish_11.png", False),
    ("loading_1.png", False)
])
def test_battle_finish(analyzer: Analyzer, load_image: Callable[[str], cv2.typing.MatLike], filename: str, expected: bool):
    image = load_image(filename)
    result = analyzer.battle_finish(image)
    assert result == expected


@pytest.mark.parametrize("filename,expected", [
    ("result_1.png", (10, 8, 3)),
    ("result_2.png", (0, 1, 0)),
    ("result_3.png", (9, 9, 2)),
    ("result_fes.png", (4, 5, 3)),
    ("result_not_lose.png", (11, 7, 3)),
])
def test_kill_record(analyzer: Analyzer, load_image: Callable[[str], cv2.typing.MatLike], filename: str, expected: tuple[int, int, int]):
    image = load_image(filename)
    result = analyzer.kill_record(image)
    assert result == expected
