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
    TOKEN_FILE = 'token.pickle'
    CLIENT_SECRET_FILE = 'client_secrets.json'
    API_NAME = 'youtube'
    API_VERSION = 'v3'
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

    def __init__(self):
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

    def upload(self, path: str, title: str, description: str, category: int = 20, privacy_status: PrivacyStatus = 'private') -> bool:
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
