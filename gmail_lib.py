"""
Gmail API Library for MCP Server

This module provides functions to interact with Gmail API using OAuth2 authentication.
"""

import os
import json
import base64
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import mimetypes
from typing import List, Dict, Any, Optional

# Global variable to store the authorization code
auth_code = None

class AuthCodeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        
        # Parse the URL query parameters to extract the code
        query_components = parse_qs(urlparse(self.path).query)
        if 'code' in query_components:
            auth_code = query_components['code'][0]
            
            # Send a response to the browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            response_content = """
            <html>
            <head><title>Authentication Successful</title></head>
            <body>
                <h1>Authentication Successful!</h1>
                <p>You can now close this browser window and return to your application.</p>
            </body>
            </html>
            """
            self.wfile.write(response_content.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            error_content = """
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>No authorization code found in the response.</p>
            </body>
            </html>
            """
            self.wfile.write(error_content.encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress log messages
        pass

def get_credentials():
    """Get valid Gmail API credentials"""
    creds = None
    token_file = 'gmail_token.json'
    credentials_file = 'gmail_credentials.json'
    
    # Check if token file exists and load it
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Gmail credentials file '{credentials_file}' not found. "
                    "Please download it from Google Cloud Console."
                )
            
            # Start the OAuth flow
            flow = Flow.from_client_secrets_file(
                credentials_file,
                scopes=['https://www.googleapis.com/auth/gmail.readonly',
                       'https://www.googleapis.com/auth/gmail.send',
                       'https://www.googleapis.com/auth/gmail.modify']            )
              # Set up the redirect URI to match Google Cloud Console configuration
            redirect_uri = 'http://localhost:5000/oauth2callback'
            flow.redirect_uri = redirect_uri
            
            # Start a local server to handle the OAuth callback
            global auth_code
            auth_code = None
            
            server = HTTPServer(('localhost', 5000), AuthCodeHandler)
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            # Get the authorization URL
            auth_url, _ = flow.authorization_url(prompt='consent')
            
            print(f"Opening browser for Gmail authentication...")
            print(f"If the browser doesn't open automatically, visit: {auth_url}")
            
            # Open the authorization URL in the default browser
            webbrowser.open(auth_url)
            
            # Wait for the authorization code
            print("Waiting for authorization...")
            timeout = 120  # 2 minutes timeout
            start_time = time.time()
            
            while auth_code is None and (time.time() - start_time) < timeout:
                time.sleep(1)
            
            server.shutdown()
            
            if auth_code is None:
                raise TimeoutError("Authorization timed out")
            
            # Exchange the authorization code for credentials
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            
            # Save the credentials for the next run
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
            
            print("Gmail authentication successful!")
    
    return creds

def get_gmail_service():
    """Get Gmail API service object"""
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    return service

def list_messages(service, query='', max_results=10, label_ids=None):
    """List Gmail messages"""
    try:
        kwargs = {
            'userId': 'me',
            'q': query,
            'maxResults': max_results
        }
        
        if label_ids:
            kwargs['labelIds'] = label_ids
            
        result = service.users().messages().list(**kwargs).execute()
        messages = result.get('messages', [])
        
        # Get detailed message info
        detailed_messages = []
        for message in messages:
            msg_detail = service.users().messages().get(
                userId='me', 
                id=message['id'],
                format='metadata',
                metadataHeaders=['Subject', 'From', 'To', 'Date']
            ).execute()
            
            headers = {h['name']: h['value'] for h in msg_detail['payload']['headers']}
            
            detailed_messages.append({
                'id': message['id'],
                'threadId': message['threadId'],
                'subject': headers.get('Subject', ''),
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'date': headers.get('Date', ''),
                'snippet': msg_detail.get('snippet', ''),
                'labelIds': msg_detail.get('labelIds', [])
            })
        
        return detailed_messages
    except Exception as e:
        print(f"Error listing messages: {e}")
        return []

def get_message(service, message_id):
    """Get a specific Gmail message"""
    try:
        message = service.users().messages().get(
            userId='me', 
            id=message_id,
            format='full'
        ).execute()
        
        payload = message['payload']
        headers = {h['name']: h['value'] for h in payload['headers']}
        
        # Extract message body
        body = ''
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
        else:
            if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return {
            'id': message['id'],
            'threadId': message['threadId'],
            'subject': headers.get('Subject', ''),
            'from': headers.get('From', ''),
            'to': headers.get('To', ''),
            'date': headers.get('Date', ''),
            'body': body,
            'snippet': message.get('snippet', ''),
            'labelIds': message.get('labelIds', [])
        }
    except Exception as e:
        print(f"Error getting message: {e}")
        return None

def send_message(service, to, subject, body, cc=None, bcc=None):
    """Send an email"""
    try:
        # Create email message
        message_text = f"""To: {to}
Subject: {subject}
"""
        if cc:
            message_text += f"Cc: {cc}\n"
        if bcc:
            message_text += f"Bcc: {bcc}\n"
        
        message_text += f"\n{body}"
        
        raw_message = base64.urlsafe_b64encode(message_text.encode()).decode()
        
        send_message_body = {'raw': raw_message}
        
        result = service.users().messages().send(
            userId='me',
            body=send_message_body
        ).execute()
        
        return result
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

def reply_to_message(service, message_id, reply_body):
    """Reply to a specific message"""
    try:
        # Get the original message
        original_message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=['Subject', 'From', 'To', 'Message-ID']
        ).execute()
        
        headers = {h['name']: h['value'] for h in original_message['payload']['headers']}
        
        # Create reply message
        reply_text = f"""To: {headers.get('From', '')}
Subject: Re: {headers.get('Subject', '').replace('Re: ', '')}
In-Reply-To: {headers.get('Message-ID', '')}
References: {headers.get('Message-ID', '')}

{reply_body}"""
        
        raw_message = base64.urlsafe_b64encode(reply_text.encode()).decode()
        
        send_message_body = {
            'raw': raw_message,
            'threadId': original_message['threadId']
        }
        
        result = service.users().messages().send(
            userId='me',
            body=send_message_body
        ).execute()
        
        return result
    except Exception as e:
        print(f"Error replying to message: {e}")
        return None

def get_labels(service):
    """Get Gmail labels"""
    try:
        result = service.users().labels().list(userId='me').execute()
        labels = result.get('labels', [])
        
        return [{
            'id': label['id'],
            'name': label['name'],
            'type': label['type']
        } for label in labels]
    except Exception as e:
        print(f"Error getting labels: {e}")
        return []

def add_label_to_message(service, message_id, label_id):
    """Add a label to a message"""
    try:
        result = service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': [label_id]}
        ).execute()
        return result
    except Exception as e:
        print(f"Error adding label to message: {e}")
        return None

def remove_label_from_message(service, message_id, label_id):
    """Remove a label from a message"""
    try:
        result = service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': [label_id]}
        ).execute()
        return result
    except Exception as e:
        print(f"Error removing label from message: {e}")
        return None

def mark_as_read(service, message_id):
    """Mark a message as read"""
    return remove_label_from_message(service, message_id, 'UNREAD')

def mark_as_unread(service, message_id):
    """Mark a message as unread"""
    return add_label_to_message(service, message_id, 'UNREAD')

def search_messages(service, query, max_results=10):
    """Search Gmail messages with a query"""
    return list_messages(service, query=query, max_results=max_results)
