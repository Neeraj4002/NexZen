#!/usr/bin/env python3

"""
Microsoft To Do MCP Server

This script provides an MCP server that exposes Microsoft To Do API functionality
using the   MCP v2 framework. It properly implements MCP tools for interacting
with Microsoft To Do APIs through the msgraph_todo_lib module.
"""

from fastmcp import FastMCP, Context
from typing import List, Optional, Dict, Any
import msgraph_todo_lib as todo_lib
import httpx

# Create the FastMCP server instance with proper metadata
mcp = FastMCP(
    name="Microsoft To Do",
    description="MCP server for interacting with Microsoft To Do API",
    version="1.0.0"
)

# ---- Task Lists Tools ----

@mcp.tool()
async def list_task_lists(ctx: Context) -> Dict[str, Any]:
    """
    Lists all Microsoft To Do task lists
    
    Returns:
        A dictionary containing a list of all task lists from Microsoft To Do
    """
    await ctx.info("Fetching your Microsoft To Do task lists...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Get task lists
    task_lists = todo_lib.get_todo_lists(access_token)
    
    # Format the response
    formatted_lists = []
    for task_list in task_lists:
        formatted_lists.append({
            "id": task_list["id"],
            "name": task_list["displayName"],
            "isShared": task_list["isShared"],
            "isOwner": task_list["isOwner"],
            "wellKnownListName": task_list["wellknownListName"] if "wellknownListName" in task_list else ""
        })
    
    await ctx.info(f"Found {len(formatted_lists)} task lists")
    return {"taskLists": formatted_lists}

@mcp.tool()
async def create_task_list(ctx: Context, name: str) -> Dict[str, Any]:
    """
    Creates a new task list in Microsoft To Do
    
    Args:
        name: The name for the new task list
    
    Returns:
        Information about the newly created task list
    """
    await ctx.info(f"Creating new task list: '{name}'...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Create new task list
    new_list = todo_lib.create_todo_list(access_token, name)
    
    if not new_list:
        await ctx.error("Failed to create task list")
        return {"error": "Failed to create task list"}
    
    await ctx.info(f"Successfully created task list: '{name}'")
    return {
        "success": True,
        "taskList": {
            "id": new_list["id"],
            "name": new_list["displayName"]
        }
    }

# ---- Tasks Tools ----

@mcp.tool()
async def list_tasks(ctx: Context, list_id: str) -> Dict[str, Any]:
    """
    Lists all tasks in a task list
    
    Args:
        list_id: The ID of the task list
    
    Returns:
        A dictionary containing a list of tasks from the specified task list
    """
    await ctx.info(f"Fetching tasks for list ID: {list_id}...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Get tasks from the list
    tasks = todo_lib.get_tasks(access_token, list_id)
    
    # Format the response
    formatted_tasks = []
    for task in tasks:
        task_data = {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"]
        }
        
        # Add optional fields if they exist
        if "dueDateTime" in task:
            task_data["dueDate"] = task["dueDateTime"]["dateTime"][:10]  # Extract YYYY-MM-DD
        
        if "body" in task and task["body"]["content"]:
            task_data["description"] = task["body"]["content"]
            
        formatted_tasks.append(task_data)
    
    await ctx.info(f"Found {len(formatted_tasks)} tasks")
    return {"tasks": formatted_tasks}

@mcp.tool()
async def create_task(
    ctx: Context, 
    list_id: str, 
    title: str, 
    description: str = "", 
    due_date: str = ""
) -> Dict[str, Any]:
    """
    Creates a new task in a task list
    
    Args:
        list_id: The ID of the task list
        title: The title of the task
        description: The description of the task (optional)
        due_date: The due date in YYYY-MM-DD format (optional)
    
    Returns:
        Information about the newly created task
    """
    await ctx.info(f"Creating new task '{title}' in list {list_id}...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Create the task
    new_task = todo_lib.create_task(access_token, list_id, title, description, due_date)
    
    if not new_task:
        await ctx.error("Failed to create task")
        return {"error": "Failed to create task"}
    
    # Format the response
    task_data = {
        "id": new_task["id"],
        "title": new_task["title"],
        "status": new_task["status"]
    }
    
    # Add optional fields if they exist
    if "dueDateTime" in new_task:
        task_data["dueDate"] = new_task["dueDateTime"]["dateTime"][:10]
    
    if "body" in new_task and new_task["body"]["content"]:
        task_data["description"] = new_task["body"]["content"]
    
    await ctx.info(f"Successfully created task: '{title}'")
    return {
        "success": True,
        "task": task_data
    }

@mcp.tool()
async def complete_task(ctx: Context, list_id: str, task_id: str) -> Dict[str, Any]:
    """
    Marks a task as completed
    
    Args:
        list_id: The ID of the task list
        task_id: The ID of the task to mark as completed
    
    Returns:
        Information about the updated task
    """
    await ctx.info(f"Marking task {task_id} as completed...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Complete the task
    updated_task = todo_lib.complete_task(access_token, list_id, task_id)
    
    if not updated_task:
        await ctx.error("Failed to complete task")
        return {"error": "Failed to complete task"}
    
    await ctx.info(f"Successfully marked task as completed")
    return {
        "success": True,
        "task": {
            "id": updated_task["id"],
            "title": updated_task["title"],
            "status": updated_task["status"]
        }
    }

@mcp.tool()
async def delete_task(ctx: Context, list_id: str, task_id: str) -> Dict[str, Any]:
    """
    Deletes a task from a task list
    
    Args:
        list_id: The ID of the task list
        task_id: The ID of the task to delete
    
    Returns:
        Success status of the deletion
    """
    await ctx.info(f"Deleting task {task_id} from list {list_id}...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Delete the task
    success = todo_lib.delete_task(access_token, list_id, task_id)
    
    if not success:
        await ctx.error("Failed to delete task")
        return {"error": "Failed to delete task"}
    
    await ctx.info("Task deleted successfully")
    return {"success": True}

@mcp.tool()
async def update_task(
    ctx: Context, 
    list_id: str, 
    task_id: str, 
    title: str = None, 
    description: str = None, 
    due_date: str = None,
    status: str = None
) -> Dict[str, Any]:
    """
    Updates an existing task in a task list
    
    Args:
        list_id: The ID of the task list
        task_id: The ID of the task to update
        title: The new title of the task (optional)
        description: The new description of the task (optional)
        due_date: The new due date in YYYY-MM-DD format (optional, empty string to remove)
        status: The new status for the task (optional, "notStarted" or "completed")
    
    Returns:
        Information about the updated task
    """
    await ctx.info(f"Updating task {task_id} in list {list_id}...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Update the task
    updated_task = todo_lib.update_task(
        access_token, 
        list_id, 
        task_id, 
        title=title, 
        body_content=description, 
        due_date=due_date,
        status=status
    )
    
    if not updated_task:
        await ctx.error("Failed to update task")
        return {"error": "Failed to update task"}
    
    # Format the response
    task_data = {
        "id": updated_task["id"],
        "title": updated_task["title"],
        "status": updated_task["status"]
    }
    
    # Add optional fields if they exist
    if "dueDateTime" in updated_task:
        task_data["dueDate"] = updated_task["dueDateTime"]["dateTime"][:10]
    
    if "body" in updated_task and updated_task["body"]["content"]:
        task_data["description"] = updated_task["body"]["content"]
    
    await ctx.info(f"Successfully updated task")
    return {
        "success": True,
        "task": task_data
    }

@mcp.tool()
async def uncomplete_task(ctx: Context, list_id: str, task_id: str) -> Dict[str, Any]:
    """
    Marks a task as not started (uncompletes a completed task)
    
    Args:
        list_id: The ID of the task list
        task_id: The ID of the task to mark as not started
    
    Returns:
        Information about the updated task
    """
    await ctx.info(f"Marking task {task_id} as not started...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Uncomplete the task
    updated_task = todo_lib.uncomplete_task(access_token, list_id, task_id)
    
    if not updated_task:
        await ctx.error("Failed to mark task as not started")
        return {"error": "Failed to mark task as not started"}
    
    await ctx.info(f"Successfully marked task as not started")
    return {
        "success": True,
        "task": {
            "id": updated_task["id"],
            "title": updated_task["title"],
            "status": updated_task["status"]
        }
    }

@mcp.tool()
async def delete_task_list(ctx: Context, list_id: str) -> Dict[str, Any]:
    """
    Deletes a task list
    
    Args:
        list_id: The ID of the task list to delete
    
    Returns:
        Success status of the deletion
    """
    await ctx.info(f"Deleting task list {list_id}...")
    
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Delete the task list
    success = todo_lib.delete_task_list(access_token, list_id)
    
    if not success:
        await ctx.error("Failed to delete task list")
        return {"error": "Failed to delete task list"}
    
    await ctx.info("Task list deleted successfully")
    return {"success": True}

# ---- Resources ----

@mcp.resource("todo://lists")
async def get_todo_lists(ctx: Context) -> Dict[str, Any]:
    """
    Resource to get all Microsoft To Do task lists
    """
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Get task lists
    task_lists = todo_lib.get_todo_lists(access_token)
    
    # Format the response
    formatted_lists = []
    for task_list in task_lists:
        formatted_lists.append({
            "id": task_list["id"],
            "name": task_list["displayName"],
            "isShared": task_list["isShared"],
            "isOwner": task_list["isOwner"]
        })
    
    return {"taskLists": formatted_lists}

@mcp.resource("todo://lists/{list_id}/tasks")
async def get_tasks_resource(ctx: Context, list_id: str) -> Dict[str, Any]:
    """
    Resource to get all tasks in a specific task list
    
    Args:
        list_id: The ID of the task list
    """
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Get tasks from the list
    tasks = todo_lib.get_tasks(access_token, list_id)
    
    # Format the response
    formatted_tasks = []
    for task in tasks:
        task_data = {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"]
        }
        
        # Add optional fields if they exist
        if "dueDateTime" in task:
            task_data["dueDate"] = task["dueDateTime"]["dateTime"][:10]
        
        if "body" in task and task["body"]["content"]:
            task_data["description"] = task["body"]["content"]
            
        formatted_tasks.append(task_data)
    
    return {"tasks": formatted_tasks}

@mcp.resource("todo://lists/{list_id}/tasks/{task_id}")
async def get_task_resource(ctx: Context, list_id: str, task_id: str) -> Dict[str, Any]:
    """
    Resource to get a specific task in a task list
    
    Args:
        list_id: The ID of the task list
        task_id: The ID of the task
    """
    # Ensure we have a valid access token
    access_token = todo_lib.ensure_access_token()
    if not access_token:
        await ctx.error("Failed to authenticate with Microsoft Graph API")
        return {"error": "Authentication failed"}
    
    # Get tasks from the list
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}"
    
    try:
        response = httpx.get(url, headers=headers)
        
        if response.status_code == 200:
            task = response.json()
            task_data = {
                "id": task["id"],
                "title": task["title"],
                "status": task["status"]
            }
            
            # Add optional fields if they exist
            if "dueDateTime" in task:
                task_data["dueDate"] = task["dueDateTime"]["dateTime"][:10]
            
            if "body" in task and task["body"]["content"]:
                task_data["description"] = task["body"]["content"]
                
            return {"task": task_data}
        else:
            await ctx.error(f"Failed to get task: {response.status_code}")
            return {"error": f"Failed to get task: {response.status_code}"}
    except Exception as e:
        await ctx.error(f"Exception while getting task: {str(e)}")
        return {"error": f"Exception: {str(e)}"}

# ---- Prompts ----

@mcp.prompt()
async def create_task_prompt(list_name: str) -> str:
    """
    Generates a prompt to create a new task in a specific list
    
    Args:
        list_name: The name of the task list
    """
    return f"""
    Let's create a new task in your '{list_name}' list.
    
    Please provide:
    1. Task title (required)
    2. Task description (optional)
    3. Due date (optional, in YYYY-MM-DD format)
    """

# Run the server if executed directly
if __name__ == "__main__":
    # Configure the server to use the appropriate transport
    # Default is stdio, which works well for local command-line tools
    #mcp.run()
    
    # For HTTP transport, us the run_http_server.py script
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8080, path="/mcp")
    # For SSE transport, uncomment the following line:
    # mcp.run(transport="sse", host="127.0.0.1", port=8000)
