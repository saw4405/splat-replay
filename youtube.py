import os
import pickle

import google.auth
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.auth.exceptions


class Youtube:

    def __init__(self):
        self._instance = self._authenticate()
        
    def _authenticate(self):
        TOKEN_FILE = 'token.pickle'
        CLIENT_SECRET_FILE = 'client_secrets.json'
        API_NAME = 'youtube'
        API_VERSION = 'v3'
        SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

        credentials = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token_file:
                credentials = pickle.load(token_file)

        if credentials:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES)
            credentials = flow.run_local_server(port=8080)
            with open(TOKEN_FILE, 'wb') as token_file:
                pickle.dump(credentials, token_file)
        
        youtube = build(API_NAME, API_VERSION, credentials=credentials)
        return youtube

    def upload(self, path: str, title: str, description: str, category: str = '22', privacy_status: str = 'private') -> bool:
        try:
            # Specify the file to upload
            media_file = MediaFileUpload(path, mimetype='video/*', resumable=True)
            
            # Call the API's videos.insert method to upload the video
            request = self._instance.videos().insert(
                part="snippet,status",
                body={
                    'snippet': {
                        'title': title,
                        'description': description,
                        'tags': ['example', 'video', 'upload'],
                        'categoryId': category  # 22 for People & Blogs
                    },
                    'status': {
                        'privacyStatus': privacy_status  # 'public', 'private', or 'unlisted'
                    }
                },
                media_body=media_file
            )
            
            # Upload the video
            response = request.execute()
            
            print(f'Video "{title}" uploaded successfully!')
            print(f'Video ID: {response["id"]}')
            return True
        except google.auth.exceptions.GoogleAuthError as e:
            print(f"Authentication failed: {e}")
            return False
        except Exception as e:
            print(f"An error occurred: {e}")
            return False