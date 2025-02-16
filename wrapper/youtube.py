import os
import gc
import logging
import pickle
from typing import Optional, Union, Literal

import google.auth
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.auth.exceptions
import google.auth.external_account_authorized_user
import google.oauth2.credentials

from utility.result import Result, Ok, Err

Credentials = Union[google.auth.external_account_authorized_user.Credentials,
                    google.oauth2.credentials.Credentials]
PrivacyStatus = Literal['public', 'private', 'unlisted']


class Youtube:
    def __init__(self):
        self.TOKEN_FILE = 'token.pickle'
        self.CLIENT_SECRET_FILE = 'client_secrets.json'
        self.API_NAME = 'youtube'
        self.API_VERSION = 'v3'
        self.SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
                       'https://www.googleapis.com/auth/youtube.force-ssl']

        credentials = self._get_credentials()
        self._youtube = build(
            self.API_NAME, self.API_VERSION, credentials=credentials)

    def _load_credentials(self) -> Optional[Credentials]:
        """ 認証情報をファイルからロードする

        Returns:
            Optional[Credentials]: 認証情報が存在する場合はCredentials、それ以外はNone
        """
        if not os.path.exists(self.TOKEN_FILE):
            return None

        with open(self.TOKEN_FILE, 'rb') as token_file:
            return pickle.load(token_file)

    def _save_credentials(self, credentials: Credentials):
        """ 認証情報をファイルに保存する

        Args:
            credentials (Credentials): 保存する認証情報
        """
        with open(self.TOKEN_FILE, 'wb') as token_file:
            pickle.dump(credentials, token_file)

    def _get_credentials(self) -> Credentials:
        """ 認証情報を取得する

        Returns:
            Credentials: 取得した認証情報
        """
        credentials = self._load_credentials()
        if credentials:
            try:
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    self._save_credentials(credentials)
                return credentials
            except:
                pass

        flow = InstalledAppFlow.from_client_secrets_file(
            self.CLIENT_SECRET_FILE, self.SCOPES)
        credentials = flow.run_local_server(port=8080)
        self._save_credentials(credentials)
        return credentials

    def upload(self, path: str, title: str, description: str, category: int = 20, privacy_status: PrivacyStatus = 'private') -> Result[str, str]:
        """ 動画をアップロードする

        Args:
            path (str): アップロードする動画のパス
            title (str): 動画のタイトル
            description (str): 動画の説明
            category (int, optional): 動画のカテゴリー. Defaults to 20.
            privacy_status (PrivacyStatus, optional): 動画の公開範囲. Defaults to 'private'.

        Returns:
            Result[str, str]: 成功した場合はOkに動画IDが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        media_file = None
        try:
            media_file = MediaFileUpload(
                path, mimetype='video/*', resumable=True)
            request = self._youtube.videos().insert(
                part="snippet,status",
                body={
                    'snippet': {
                        'title': title,
                        'description': description,
                        'categoryId': category
                    },
                    'status': {
                        'privacyStatus': privacy_status
                    }
                },
                media_body=media_file
            )
            response = request.execute()
            return Ok(response["id"])

        except google.auth.exceptions.GoogleAuthError as e:
            return Err(f"認証に失敗しました: {e}")
        except Exception as e:
            return Err(f"アップロードに失敗しました: {e}")
        finally:
            if media_file:
                del media_file
                gc.collect()

    def set_thumbnail(self, video_id: str, image_path: str) -> Result[None, str]:
        """ 動画のサムネイルを設定する

        Args:
            video_id (str): 動画ID
            image_path (str): サムネイルの画像パス

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        media_file = None
        try:
            media_file = MediaFileUpload(image_path)
            request = self._youtube.thumbnails().set(
                videoId=video_id,
                media_body=media_file
            )
            request.execute()
            return Ok(None)

        except google.auth.exceptions.GoogleAuthError as e:
            return Err(f"認証に失敗しました: {e}")
        except Exception as e:
            return Err(f"アップロードに失敗しました: {e}")
        finally:
            if media_file:
                del media_file
                gc.collect()

    def insert_caption(self, video_id: str, caption_path: str, caption_name: str, language: str = "ja") -> Result[None, str]:
        """ 動画に字幕を設定する

        Args:
            video_id (str): 動画ID
            caption_path (str): 字幕ファイルのパス
            caption_name (str): 字幕の名前
            language (str, optional): 字幕の言語. Defaults to "ja".

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        media_file = None
        try:
            media_file = MediaFileUpload(caption_path)
            request = self._youtube.captions().insert(
                part="snippet",
                body={
                    'snippet': {
                        'videoId': video_id,
                        'language': language,
                        'name': caption_name,
                    }
                },
                media_body=media_file
            )
            request.execute()
            return Ok(None)

        except google.auth.exceptions.GoogleAuthError as e:
            return Err(f"認証に失敗しました: {e}")
        except Exception as e:
            return Err(f"アップロードに失敗しました: {e}")
        finally:
            if media_file:
                del media_file
                gc.collect()
