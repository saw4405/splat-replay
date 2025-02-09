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

Credentials = Union[google.auth.external_account_authorized_user.Credentials,
                    google.oauth2.credentials.Credentials]
PrivacyStatus = Literal['public', 'private', 'unlisted']

logger = logging.getLogger(__name__)


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
        if not os.path.exists(self.TOKEN_FILE):
            return None

        with open(self.TOKEN_FILE, 'rb') as token_file:
            return pickle.load(token_file)

    def _save_credentials(self, credentials: Credentials):
        with open(self.TOKEN_FILE, 'wb') as token_file:
            pickle.dump(credentials, token_file)

    def _get_credentials(self) -> Credentials:
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

    def upload(self, path: str, title: str, description: str, category: int = 20, privacy_status: PrivacyStatus = 'private') -> Optional[str]:
        media_file = None
        try:
            # Specify the file to upload
            media_file = MediaFileUpload(
                path, mimetype='video/*', resumable=True)

            # Call the API's videos.insert method to upload the video
            request = self._youtube.videos().insert(
                part="snippet,status",
                body={
                    'snippet': {
                        'title': title,
                        'description': description,
                        'categoryId': category  # 20 for Gaming
                    },
                    'status': {
                        'privacyStatus': privacy_status  # 'public', 'private', or 'unlisted'
                    }
                },
                media_body=media_file
            )

            # Upload the video
            response = request.execute()

            logger.info(f'Video "{title}" uploaded successfully!')
            logger.info(f'Video ID: {response["id"]}')
            return response["id"]
        except google.auth.exceptions.GoogleAuthError as e:
            logger.info(f"Authentication failed: {e}")
            return None
        except Exception as e:
            logger.info(f"An error occurred: {e}")
            return None
        finally:
            if media_file:
                del media_file
                gc.collect()

    def set_thumbnail(self, video_id: str, image_path: str) -> bool:
        media_file = None
        try:
            # Specify the file to upload
            media_file = MediaFileUpload(image_path)

            # Call the API's thumbnails.set method to upload the thumbnail
            request = self._youtube.thumbnails().set(
                videoId=video_id,
                media_body=media_file
            )

            # Upload the thumbnail
            request.execute()

            logger.info(f'Thumbnail uploaded successfully!')
            return True
        except google.auth.exceptions.GoogleAuthError as e:
            logger.info(f"Authentication failed: {e}")
            return False
        except Exception as e:
            logger.info(f"An error occurred: {e}")
            return False
        finally:
            if media_file:
                del media_file
                gc.collect()

    def insert_caption(self, video_id: str, caption_path: str, language: str = "ja") -> bool:
        media_file = None
        try:
            # Specify the file to upload
            media_file = MediaFileUpload(caption_path)

            # Call the API's captions.insert method to upload the caption
            request = self._youtube.captions().insert(
                part="snippet",
                body={
                    'snippet': {
                        'videoId': video_id,
                        'language': language,
                        'name': f'Caption for {language}',
                    }
                },
                media_body=media_file
            )

            # Upload the caption
            request.execute()

            logger.info(f'Caption for "{language}" uploaded successfully!')
            return True
        except google.auth.exceptions.GoogleAuthError as e:
            logger.info(f"Authentication failed: {e}")
            return False
        except Exception as e:
            logger.info(f"An error occurred: {e}")
            return False
        finally:
            if media_file:
                del media_file
                gc.collect()
