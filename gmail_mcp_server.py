"""
Gmail MCP Server

This script provides an MCP server that exposes Gmail API functionality
using the FastMCP v2 framework. It properly implements MCP tools for reading, sending,
and managing Gmail messages and labels, utilizing the gmail_lib module.
"""

import asyncio
import base64
import os
from typing import List, Optional, Dict, Any

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
import gmail_lib

# --- Server Configuration ---
SERVER_NAME = "GmailMCP"
SERVER_VERSION = "1.0.0"
MCP_PORT = 5001  # Default port, can be overridden by environment variable
MCP_HOST = "127.0.0.1" # Default host
CREDENTIALS_FILE = 'gmail_credentials.json'
SCOPES = ['https://www.googleapis.com/auth/gmail.modify'] #.modify includes read, send, compose, labels

# Initialize FastMCP
mcp = FastMCP(
    name=SERVER_NAME,
    version=SERVER_VERSION,
    description="A Model Context Protocol server for Gmail API functionality."
)

# Global variable to store the Gmail API service client
gmail_service = None

# --- Helper Functions ---

async def _ensure_service(ctx: Context):
    """
    Ensures the Gmail service is initialized.
    Returns True if service is available, False otherwise.
    """
    global gmail_service
    if gmail_service is None:
        await ctx.info("Gmail service not initialized. Attempting to authenticate and initialize...")
        try:
            # Run synchronous gmail_lib.get_gmail_service in a separate thread
            # to avoid blocking the asyncio event loop.
            loop = asyncio.get_running_loop()
            gmail_service = await loop.run_in_executor(None, gmail_lib.get_gmail_service)
            if gmail_service:
                await ctx.info("✅ Gmail service initialized successfully.")
                return True
            else:
                await ctx.error("❌ Failed to initialize Gmail service. Authentication might have failed or been cancelled.")
                return False
        except FileNotFoundError as e:
            await ctx.error(f"❌ Gmail credentials file not found: {e}. Please ensure 'gmail_credentials.json' is in the correct location.")
            return False
        except TimeoutError as e:
            await ctx.error(f"❌ Gmail authentication timed out: {e}. Please try again.")
            return False
        except Exception as e:
            await ctx.error(f"❌ An unexpected error occurred during Gmail service initialization: {str(e)}")
            return False
    return True

def _get_header_value(headers: List[Dict[str, str]], name: str) -> str:
    """Extracts a specific header value from a list of header dictionaries."""
    for header in headers:
        if header['name'].lower() == name.lower():
            return header['value']
    return ""

def _decode_body_data(data: str) -> str:
    """Decodes base64url encoded body data."""
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8')
    except Exception:
        # Fallback for data that might not be perfectly padded or encoded
        try:
            return base64.b64decode(data.replace('-', '+').replace('_', '/') + '===').decode('utf-8')
        except Exception as e:
            # If decoding fails, return a placeholder or the raw data, depending on desired behavior
            # print(f"Warning: Could not decode body data: {e}") # For server-side logging
            return "[Could not decode body content]"


def _extract_body_from_payload(payload: Dict[str, Any], preferred_mime_type: str = "text/plain") -> str:
    """
    Extracts message body content from the payload.
    Tries to find the preferred MIME type, then text/plain, then the first available text part.
    """
    body_content = ""
    if 'parts' in payload:
        parts_to_check = payload['parts']
        
        # First pass for preferred_mime_type
        for part in parts_to_check:
            if part['mimeType'] == preferred_mime_type and part.get('body', {}).get('data'):
                return _decode_body_data(part['body']['data'])
            # Recurse for multipart/*
            if part['mimeType'].startswith('multipart/') and 'parts' in part:
                nested_body = _extract_body_from_payload(part, preferred_mime_type)
                if nested_body:
                    return nested_body
        
        # Second pass for text/plain if preferred was different
        if preferred_mime_type != "text/plain":
            for part in parts_to_check:
                if part['mimeType'] == 'text/plain' and part.get('body', {}).get('data'):
                    return _decode_body_data(part['body']['data'])
                if part['mimeType'].startswith('multipart/') and 'parts' in part:
                    nested_body = _extract_body_from_payload(part, "text/plain")
                    if nested_body:
                        return nested_body

        # Third pass for any text/*
        for part in parts_to_check:
            if part['mimeType'].startswith('text/') and part.get('body', {}).get('data'):
                return _decode_body_data(part['body']['data'])
            if part['mimeType'].startswith('multipart/') and 'parts' in part: # Check nested again
                nested_body = _extract_body_from_payload(part, part['mimeType']) # pass current mime
                if nested_body: return nested_body


    elif payload.get('mimeType', '').startswith('text/') and payload.get('body', {}).get('data'):
        body_content = _decode_body_data(payload['body']['data'])
    
    return body_content


def _format_message_summary(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Formats a message for list views (summary)."""
    # gmail_lib.list_messages already returns a good summary.
    # This function can be used for consistency or minor adjustments if needed.
    return {
        "id": message_data.get('id'),
        "threadId": message_data.get('threadId'),
        "subject": message_data.get('subject', ''),
        "from": message_data.get('from', ''),
        "to": message_data.get('to', ''),
        "date": message_data.get('date', ''),
        "snippet": message_data.get('snippet', ''),
        "labelIds": message_data.get('labelIds', [])
    }

def _format_message_detail(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Formats a message for detailed view, including body."""
    payload = message_data.get('payload', {})
    headers_list = payload.get('headers', [])
    
    headers_dict = {h['name']: h['value'] for h in headers_list}

    # Extract body - try HTML first, then plain text
    body_html = _extract_body_from_payload(payload, 'text/html')
    body_plain = _extract_body_from_payload(payload, 'text/plain')
    
    body = body_html if body_html else body_plain

    # Basic attachment info (name and ID if available)
    attachments = []
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('filename') and part.get('body', {}).get('attachmentId'):
                attachments.append({
                    "filename": part['filename'],
                    "mimeType": part.get('mimeType'),
                    "size": part.get('body', {}).get('size'),
                    "attachmentId": part['body']['attachmentId'] 
                })

    return {
        "id": message_data.get('id'),
        "threadId": message_data.get('threadId'),
        "subject": headers_dict.get('Subject', ''),
        "from": headers_dict.get('From', ''),
        "to": headers_dict.get('To', ''),
        "cc": headers_dict.get('Cc', ''),
        "date": headers_dict.get('Date', ''),
        "snippet": message_data.get('snippet', ''),
        "labelIds": message_data.get('labelIds', []),
        "body": body, # This will be the plain text body from gmail_lib's get_message
        "bodyHtml": body_html, # Attempt to get HTML body
        "headers": headers_dict,        "attachments": attachments
    }

# --- Pydantic Models for Tool Parameters ---

class ListMessagesRequest(BaseModel):
    query: str = Field(default='', description="Search query (e.g., 'from:user@example.com is:unread')")
    max_results: int = Field(default=10, description="Maximum number of messages to return")
    label_ids: Optional[List[str]] = Field(default=None, description="List of label IDs to filter by (e.g., ['INBOX', 'UNREAD'])")

class SearchMessagesRequest(BaseModel):
    query: str = Field(description="The search query (e.g., 'subject:important after:2023/01/01')")
    max_results: int = Field(default=10, description="Maximum number of messages to return")

class GetMessageRequest(BaseModel):
    message_id: str = Field(description="The ID of the message to retrieve")

class SendMessageRequest(BaseModel):
    to: str = Field(description="Recipient's email address")
    subject: str = Field(description="Subject of the email")
    body: str = Field(description="Body content of the email")
    cc: Optional[str] = Field(default=None, description="CC recipients (comma-separated if multiple)")
    bcc: Optional[str] = Field(default=None, description="BCC recipients (comma-separated if multiple)")

class ReplyToMessageRequest(BaseModel):
    message_id: str = Field(description="The ID of the message to reply to")
    reply_body: str = Field(description="The content of the reply")

class LabelMessageRequest(BaseModel):
    message_id: str = Field(description="The ID of the message")
    label_id: str = Field(description="The ID of the label")

class MarkAsUnreadRequest(BaseModel):
    message_id: str = Field(description="The ID of the message to mark as unread")

class MarkAsReadRequest(BaseModel):
    message_id: str = Field(description="The ID of the message to mark as read")

# --- MCP Tools ---

@mcp.tool()
async def list_messages(
    ctx: Context, 
    query: str = '', 
    max_results: int = 10, 
    label_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Lists Gmail messages.

    Args:
        query: Search query (e.g., 'from:user@example.com is:unread').
        max_results: Maximum number of messages to return.
        label_ids: List of label IDs to filter by (e.g., ['INBOX', 'UNREAD']).
    """
    await ctx.info(f"Fetching messages with query: '{query}', max_results: {max_results}, labels: {label_ids}...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        messages_raw = await loop.run_in_executor(
            None, 
            gmail_lib.list_messages, 
            gmail_service, 
            query, 
            max_results, 
            label_ids
        )
        
        if messages_raw is None: # gmail_lib.list_messages returns [] on error, or None if service fails before call
             await ctx.error("Failed to retrieve messages. The library call returned None.")
             return {"error": "Failed to retrieve messages. Library error."}

        formatted_messages = [_format_message_summary(msg) for msg in messages_raw]
        await ctx.info(f"Found {len(formatted_messages)} messages.")
        return {"messages": formatted_messages}
    except Exception as e:
        await ctx.error(f"Error listing messages: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def get_message(ctx: Context, message_id: str) -> Dict[str, Any]:
    """
    Gets a specific Gmail message by its ID.

    Args:
        message_id: The ID of the message to retrieve.
    """
    await ctx.info(f"Fetching message with ID: {message_id}...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        # gmail_lib.get_message fetches 'full' format by default
        message_raw = await loop.run_in_executor(None, gmail_lib.get_message, gmail_service, message_id)
        
        if not message_raw:
            await ctx.error(f"Message with ID '{message_id}' not found or failed to retrieve.")
            return {"error": f"Message '{message_id}' not found or error in retrieval."}
        
        formatted_message = _format_message_detail(message_raw)
        await ctx.info(f"Successfully retrieved message ID: {message_id}.")
        return {"message": formatted_message}
    except Exception as e:
        await ctx.error(f"Error getting message '{message_id}': {str(e)}")
        return {"error": f"An unexpected error occurred while fetching message '{message_id}': {str(e)}"}

@mcp.tool()
async def search_messages(ctx: Context, request: SearchMessagesRequest) -> Dict[str, Any]:
    """
    Searches Gmail messages using a query string.

    Args:
        request: The search request containing query and max_results.
    """
    await ctx.info(f"Searching messages with query: '{request.query}', max_results: {request.max_results}...")
    # This is essentially the same as list_messages but named for clarity in MCP tool list
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}
    
    try:
        loop = asyncio.get_running_loop()
        messages_raw = await loop.run_in_executor(
            None,
            gmail_lib.search_messages, # gmail_lib has a dedicated search_messages
            gmail_service,
            request.query,
            request.max_results
        )

        if messages_raw is None:
             await ctx.error("Search messages call returned None.")
             return {"error": "Failed to search messages. Library error."}

        formatted_messages = [_format_message_summary(msg) for msg in messages_raw]
        await ctx.info(f"Search found {len(formatted_messages)} messages.")
        return {"messages": formatted_messages}
    except Exception as e:
        await ctx.error(f"Error searching messages: {str(e)}")
        return {"error": f"An unexpected error occurred during search: {str(e)}"}

@mcp.tool()
async def send_message(
    ctx: Context, 
    to: str, 
    subject: str, 
    body: str, 
    cc: Optional[str] = None, 
    bcc: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sends an email.

    Args:
        to: Recipient's email address.
        subject: Subject of the email.
        body: Body content of the email.
        cc: CC recipients (comma-separated if multiple).
        bcc: BCC recipients (comma-separated if multiple).
    """
    await ctx.info(f"Attempting to send email to: {to} with subject: '{subject}'...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            gmail_lib.send_message, 
            gmail_service, 
            to, 
            subject, 
            body, 
            cc, 
            bcc
        )
        
        if result and 'id' in result:
            await ctx.info(f"Email sent successfully. Message ID: {result['id']}")
            return {"success": True, "messageId": result['id'], "threadId": result.get('threadId')}
        else:
            await ctx.error("Failed to send email. No result or ID returned from library.")
            # Log the actual result for debugging if it's not None but lacks 'id'
            if result:
                await ctx.info(f"send_message raw result from lib: {result}")
            return {"success": False, "error": "Failed to send email."}
    except Exception as e:
        await ctx.error(f"Error sending email: {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def reply_to_message(ctx: Context, message_id: str, reply_body: str) -> Dict[str, Any]:
    """
    Replies to a specific Gmail message.

    Args:
        message_id: The ID of the message to reply to.
        reply_body: The content of the reply.
    """
    await ctx.info(f"Attempting to reply to message ID: {message_id}...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            gmail_lib.reply_to_message, 
            gmail_service, 
            message_id, 
            reply_body
        )
        
        if result and 'id' in result:
            await ctx.info(f"Reply sent successfully. Message ID: {result['id']}")
            return {"success": True, "messageId": result['id'], "threadId": result.get('threadId')}
        else:
            await ctx.error("Failed to send reply. No result or ID returned from library.")
            if result:
                await ctx.info(f"reply_to_message raw result from lib: {result}")
            return {"success": False, "error": "Failed to send reply."}
    except Exception as e:
        await ctx.error(f"Error replying to message '{message_id}': {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def mark_message_as_read(ctx: Context, message_id: str) -> Dict[str, Any]:
    """Marks a message as read (removes the 'UNREAD' label)."""
    await ctx.info(f"Marking message ID: {message_id} as read...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, gmail_lib.mark_as_read, gmail_service, message_id)
        if result and 'id' in result: # modify usually returns the message resource
            await ctx.info(f"Message '{message_id}' marked as read. Current labels: {result.get('labelIds')}")
            return {"success": True, "messageId": result['id'], "labelIds": result.get('labelIds')}
        else:
            await ctx.error(f"Failed to mark message '{message_id}' as read.")
            return {"success": False, "error": "Failed to mark as read."}
    except Exception as e:
        await ctx.error(f"Error marking message '{message_id}' as read: {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def mark_message_as_unread(ctx: Context, message_id: str) -> Dict[str, Any]:
    """Marks a message as unread (adds the 'UNREAD' label)."""
    await ctx.info(f"Marking message ID: {message_id} as unread...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, gmail_lib.mark_as_unread, gmail_service, message_id)
        if result and 'id' in result:
            await ctx.info(f"Message '{message_id}' marked as unread. Current labels: {result.get('labelIds')}")
            return {"success": True, "messageId": result['id'], "labelIds": result.get('labelIds')}
        else:
            await ctx.error(f"Failed to mark message '{message_id}' as unread.")
            return {"success": False, "error": "Failed to mark as unread."}
    except Exception as e:
        await ctx.error(f"Error marking message '{message_id}' as unread: {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def add_label_to_message(ctx: Context, message_id: str, label_id: str) -> Dict[str, Any]:
    """
    Adds a label to a message. Use list_labels to find available label IDs.
    Common system label IDs: 'IMPORTANT', 'STARRED', 'SPAM', 'TRASH'. For custom labels, use their full ID.
    """
    await ctx.info(f"Adding label '{label_id}' to message ID: {message_id}...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, gmail_lib.add_label_to_message, gmail_service, message_id, label_id)
        if result and 'id' in result:
            await ctx.info(f"Label '{label_id}' added to message '{message_id}'. Current labels: {result.get('labelIds')}")
            return {"success": True, "messageId": result['id'], "labelIds": result.get('labelIds')}
        else:
            await ctx.error(f"Failed to add label '{label_id}' to message '{message_id}'.")
            return {"success": False, "error": f"Failed to add label '{label_id}'."}
    except Exception as e:
        await ctx.error(f"Error adding label '{label_id}' to message '{message_id}': {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def remove_label_from_message(ctx: Context, message_id: str, label_id: str) -> Dict[str, Any]:
    """Removes a label from a message. Use list_labels to find available label IDs."""
    await ctx.info(f"Removing label '{label_id}' from message ID: {message_id}...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, gmail_lib.remove_label_from_message, gmail_service, message_id, label_id)
        if result and 'id' in result:
            await ctx.info(f"Label '{label_id}' removed from message '{message_id}'. Current labels: {result.get('labelIds')}")
            return {"success": True, "messageId": result['id'], "labelIds": result.get('labelIds')}
        else:
            await ctx.error(f"Failed to remove label '{label_id}' from message '{message_id}'.")
            return {"success": False, "error": f"Failed to remove label '{label_id}'."}
    except Exception as e:
        await ctx.error(f"Error removing label '{label_id}' from message '{message_id}': {str(e)}")
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def list_labels(ctx: Context) -> Dict[str, Any]:
    """Lists all Gmail labels for the authenticated user."""
    await ctx.info("Fetching Gmail labels...")
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        labels = await loop.run_in_executor(None, gmail_lib.get_labels, gmail_service)
        
        if labels is None: # gmail_lib.get_labels returns [] on error, or None if service fails
            await ctx.error("Failed to retrieve labels. The library call returned None.")
            return {"error": "Failed to retrieve labels. Library error."}

        await ctx.info(f"Found {len(labels)} labels.")
        return {"labels": labels} # gmail_lib.get_labels already formats them well
    except Exception as e:
        await ctx.error(f"Error listing labels: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

# --- MCP Resources ---

@mcp.resource("gmail://messages")
async def get_messages_resource(ctx: Context) -> Dict[str, Any]:
    """Resource to get all Gmail messages"""
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        messages = await loop.run_in_executor(None, gmail_lib.list_messages, gmail_service)
        
        if messages is None:
            await ctx.error("Failed to retrieve messages. The library call returned None.")
            return {"error": "Failed to retrieve messages. Library error."}

        formatted_messages = [_format_message_summary(msg) for msg in messages]
        return {"messages": formatted_messages}
    except Exception as e:
        await ctx.error(f"Error getting messages: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.resource("gmail://messages/{message_id}")
async def get_message_resource(ctx: Context, message_id: str) -> Dict[str, Any]:
    """Resource to get a specific Gmail message"""
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        message = await loop.run_in_executor(None, gmail_lib.get_message, gmail_service, message_id)
        
        if not message:
            await ctx.error(f"Message with ID '{message_id}' not found or failed to retrieve.")
            return {"error": f"Message '{message_id}' not found or error in retrieval."}
        
        formatted_message = _format_message_detail(message)
        return {"message": formatted_message}
    except Exception as e:
        await ctx.error(f"Error getting message: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.resource("gmail://labels")
async def get_labels_resource(ctx: Context) -> Dict[str, Any]:
    """Resource to get all Gmail labels"""
    if not await _ensure_service(ctx):
        return {"error": "Gmail service not available."}

    try:
        loop = asyncio.get_running_loop()
        labels = await loop.run_in_executor(None, gmail_lib.get_labels, gmail_service)
        
        if labels is None:
            await ctx.error("Failed to retrieve labels. The library call returned None.")
            return {"error": "Failed to retrieve labels. Library error."}

        return {"labels": labels}
    except Exception as e:
        await ctx.error(f"Error getting labels: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

# --- Server Setup and Main Execution ---

def setup_server_initialization_message():
    """Optional: Print initial server setup messages."""
    print(f"⚙️  Initializing {SERVER_NAME} v{SERVER_VERSION}...")
    if not os.path.exists('gmail_credentials.json'):
        print("⚠️  Warning: 'gmail_credentials.json' not found. Gmail authentication will fail if not created.")
    else:
        print("✅ 'gmail_credentials.json' found.")
    print("🔑 Gmail authentication will be triggered on first API call if needed.")

if __name__ == "__main__":
    setup_server_initialization_message()
    
    print(f"\n🚀 Starting {SERVER_NAME}...")
    print(f"ℹ️  Ensure '{CREDENTIALS_FILE}' is present and correctly configured from Google Cloud Console.")
    print("✨ If browser doesn't open for auth, check console for URL.")
    print("⏹️  Press Ctrl+C to stop the server.")
    
    # Determine host and port from environment variables
    host = os.getenv("MCP_HOST", MCP_HOST)
    port = int(os.getenv("MCP_PORT", MCP_PORT))
    
    try:
        # Run with HTTP transport by default
        print(f"🌐 Starting server on {host}:{port}")
        mcp.run(transport="streamable-http", host=host, port=port)
    except Exception as e:
        print(f"❌ Critical server error: {e}")
        import traceback
        traceback.print_exc()
