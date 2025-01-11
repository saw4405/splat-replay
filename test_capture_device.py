import os

import cv2
import dotenv

from obs import Obs

# OBSの仮想カメラのインデックスを探すために使用してください
# OBSの仮想カメラを有効にしたときにゲーム映像が表示され、無効にしたときにゲーム映像が表示されないインデックスを環境変数に設定してください
# 通常、0がPCのカメラ、1がキャプチャボード、2がOBSの仮想カメラです


def main():
    index = int(os.environ["CAPTURE_DEVICE_INDEX"])
    width = int(os.environ["CAPTURE_WIDTH"])
    height = int(os.environ["CAPTURE_HEIGHT"])

    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        raise Exception("カメラが見つかりません")
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    while True:
        # フレームを読み込む
        ret, frame = capture.read()
        if not ret:
            print("フレームの読み込みに失敗しました。")
            break

        # 映像を表示
        cv2.imshow(f'CaptureDevice[{index}]', frame)

        # 'q'キーが押されたら終了
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # カメラリソースとウィンドウを解放
    capture.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    dotenv.load_dotenv()
    main()
