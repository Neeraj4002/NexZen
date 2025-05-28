import os
import time
import json
import webbrowser
import httpx
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from msal import ConfidentialClientApplication

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
            <p>You have successfully authenticated. You may close this window.</p>
            </body>
            </html>
            """
            self.wfile.write(response_content.encode())
        else:
            # Send error response if code is not in the URL
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'No authorization code found in the request')

def start_server():
    server = HTTPServer(('localhost', 5000), AuthCodeHandler)
    server.handle_request()  # Handle only one request and then stop

def create_confidential_client(client_id, client_secret, authority):
    return ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
        token_cache=None  # We'll handle token caching ourselves
    )

def get_access_token(app, scopes, redirect_uri="http://localhost:5000"):
    # Look for cached token first
    cache_file = "token_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                token_cache = json.load(f)
                
            if 'access_token' in token_cache and 'expires_at' in token_cache:
                # Check if token is still valid (with a 5-minute buffer)
                if token_cache['expires_at'] > time.time() + 300:
                    print("Using cached access token")
                    return token_cache['access_token']
        except Exception as e:
            print(f"Error reading cache: {e}")
    
    # No valid cached token, start the auth flow
    global auth_code
    auth_code = None
    
    # Start local server in a separate thread
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Redirect user to the authentication page
    auth_url = app.get_authorization_request_url(
        scopes,
        redirect_uri=redirect_uri
    )
    webbrowser.open(auth_url, new=True)
    
    # Wait for the authorization code
    print("Waiting for authorization...")
    server_thread.join(timeout=60)
    
    if not auth_code:
        print("Failed to obtain authorization code")
        return None
    
    print("Authorization code obtained successfully")
    
    # Exchange the authorization code for an access token
    token_response = app.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=scopes,
        redirect_uri=redirect_uri
    )
    
    if 'access_token' in token_response:
        # Cache the token
        token_cache = {
            'access_token': token_response['access_token'],
            'expires_at': time.time() + token_response.get('expires_in', 3600)
        }
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(token_cache, f)
            print("Token cached successfully")
        except Exception as e:
            print(f"Error caching token: {e}")
            
        return token_response['access_token']
    else:
        print("Error acquiring token:", token_response.get('error'))
        print("Error description:", token_response.get('error_description'))
        return None

def get_todo_lists(access_token):
    """Get all to-do lists for the current user."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = "https://graph.microsoft.com/v1.0/me/todo/lists"
    
    response = httpx.get(url, headers=headers)
    
    if response.status_code == 200:
        todo_lists = response.json()
        return todo_lists['value']  # Return the list of todo items
    else:
        print("Error fetching Todo lists:", response.status_code, response.text)
        return []  # Return an empty list if there was an error

def create_todo_list(access_token, list_name):
    """Create a new to-do list with the given name."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = "https://graph.microsoft.com/v1.0/me/todo/lists"
    
    data = {
        "displayName": list_name
    }
    
    response = httpx.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        new_list = response.json()
        return new_list
    else:
        print("Error creating todo list:", response.status_code, response.text)
        return None

def get_tasks(access_token, list_id):
    """Get all tasks from a specific list"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
    
    # Add timeout parameter and implement retry logic
    try:
        response = httpx.get(
            url, 
            headers=headers, 
            timeout=30.0  # Increase timeout to 30 seconds
        )
        
        if response.status_code == 200:
            tasks = response.json()
            return tasks.get("value", [])
        else:
            print(f"Error fetching tasks: {response.status_code} - {response.text}")
            return []
            
    except httpx.ReadTimeout:
        print("⚠️ Microsoft Graph API request timed out. The service might be slow.")
        return {"error": "Request to Microsoft Graph API timed out. Please try again later."}
    except httpx.ConnectError:
        print("⚠️ Connection error when connecting to Microsoft Graph API.")
        return {"error": "Could not connect to Microsoft Graph API. Please check your network."}
    except Exception as e:
        print(f"⚠️ Error in get_tasks: {str(e)}")
        return {"error": f"Error fetching tasks: {str(e)}"}

def create_task(access_token, list_id, title, body_content="", due_date=""):
    """Create a new task in the specified list."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
    
    data = {
        "title": title,
        "status": "notStarted"
    }
    
    # Add optional body content if provided
    if body_content:
        data["body"] = {
            "content": body_content,
            "contentType": "text"
        }
    
    # Add due date if provided
    if due_date:
        data["dueDateTime"] = {
            "dateTime": f"{due_date}T00:00:00.0000000",
            "timeZone": "UTC"
        }
    
    response = httpx.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        new_task = response.json()
        return new_task
    else:
        print("Error creating task:", response.status_code, response.text)
        return None

def complete_task(access_token, list_id, task_id):
    """Mark a task as completed."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}"
    
    data = {
        "status": "completed"
    }
    
    response = httpx.patch(url, headers=headers, json=data)
    
    if response.status_code == 200:
        updated_task = response.json()
        return updated_task
    else:
        print("Error completing task:", response.status_code, response.text)
        return None

def update_task(access_token, list_id, task_id, title=None, body_content=None, due_date=None, status=None):
    """Update a task's properties in the specified list."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}"
    
    # Only include fields that are being updated
    data = {}
    
    if title is not None:
        data["title"] = title
    
    if body_content is not None:
        data["body"] = {
            "content": body_content,
            "contentType": "text"
        }
    
    if due_date is not None:
        if due_date == "":  # Empty string means remove the due date
            data["dueDateTime"] = None
        else:
            data["dueDateTime"] = {
                "dateTime": f"{due_date}T00:00:00.0000000",
                "timeZone": "UTC"
            }
    
    if status is not None:
        data["status"] = status
    
    # Don't make an API call if there's nothing to update
    if not data:
        return None
    
    response = httpx.patch(url, headers=headers, json=data)
    
    if response.status_code == 200:
        updated_task = response.json()
        return updated_task
    else:
        print("Error updating task:", response.status_code, response.text)
        return None

def uncomplete_task(access_token, list_id, task_id):
    """Mark a task as not started (uncomplete it)."""
    return update_task(access_token, list_id, task_id, status="notStarted")

def delete_task(access_token, list_id, task_id):
    """Delete a task."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}"
    
    response = httpx.delete(url, headers=headers)
    
    if response.status_code == 204:  # 204 No Content is the expected response
        return True
    else:
        print("Error deleting task:", response.status_code, response.text)
        return False

def delete_task_list(access_token, list_id):
    """Delete a task list."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}"
    
    response = httpx.delete(url, headers=headers)
    
    if response.status_code == 204:  # 204 No Content is the expected response
        return True
    else:
        print("Error deleting task list:", response.status_code, response.text)
        return False

# Authentication configuration
CLIENT_ID = "d5301902-9c32-451f-9b1d-0c3a3d7d11e9"
CLIENT_SECRET = "F6o8Q~hT4qKW3mH3ry7A__w-3HyHgANQd9YSCcSV"
AUTHORITY = "https://login.microsoftonline.com/consumers/"
SCOPES = ["Tasks.ReadWrite"]

# Initialize the app and get access token
app = create_confidential_client(CLIENT_ID, CLIENT_SECRET, AUTHORITY)
access_token = None

def ensure_access_token():
    """Make sure we have a valid access token"""
    global access_token, app
    if not access_token:
        access_token = get_access_token(app, SCOPES)
    return access_token
