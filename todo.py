"""
LangGraph Microsoft To-Do Agent

This agent uses LangGraph to provide natural language interaction with Microsoft To-Do
through the MCP server. It can automate todo list management, task creation, updates,
and complex multi-step workflows.
"""

import asyncio
from prompts.todo_prompt import SYSTEM_PROMPT
import json
import os
from dotenv import load_dotenv
import sys
from typing import Dict, Any, List, Optional, Annotated

# LangGraph imports
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

# MCP client import
from fastmcp import Client


load_dotenv()  # Load environment variables from .env file
class AgentState(TypedDict):
    """State for the LangGraph agent"""
    messages: Annotated[List, add_messages]
    current_list_id: Optional[str]
    current_list_name: Optional[str]
    last_operation: Optional[str]


class TodoMCPAgent:
    """LangGraph agent for Microsoft To-Do automation via MCP"""
    
    def __init__(self, server_path: str = "improved_mcp_server.py", google_api_key: str = "AIzaSyD55cr_qrFmyWOipaX8mTtT4wh0yyn5wQg"):
        """
        Initialize the Todo MCP Agent
        
        Args:
            server_path: Path to the MCP server script
            google_api_key: Google API key for the LLM
        """
        self.server_path = server_path
        self.mcp_client = None
        self.connected = False
        
        # Initialize LLM
        if not google_api_key:
            raise ValueError("Google API key is required. Set GOOGLE_API_KEY environment variable or pass it directly.")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            google_api_key=os.getenv("GOOGLE_API_KEY", google_api_key),
            
        )
        
        # Tools will be populated after MCP connection
        self.tools = []
        self.graph = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect_mcp()
        await self.setup_tools()
        self.setup_graph()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect_mcp()
        
    async def connect_mcp(self):
        """Connect to the MCP server"""
        try:
            if not self.connected:
                print("🔄 Connecting to MCP server...")
                self.mcp_client = Client("http://127.0.0.1:8080/mcp/")

                print(f"Using MCP server at: {os.path.abspath(self.server_path)}")
                await self.mcp_client.__aenter__()
                self.connected = True
                print("✅ Connected to Microsoft To-Do MCP Server")
        except Exception as e:
            print(f"❌ Failed to connect to MCP server: {str(e)}")
            print("\nTroubleshooting:")
            print("1. Check if improved_mcp_server.py exists in:", os.path.abspath(self.server_path))
            print("2. Verify your Microsoft Graph API credentials in .env")
            print("3. Make sure the MCP server dependencies are installed")
            raise RuntimeError(f"Failed to initialize MCP server: {str(e)}")

    async def disconnect_mcp(self):
        """Disconnect from the MCP server"""
        if self.connected and self.mcp_client:
            await self.mcp_client.__aexit__(None, None, None)
            self.connected = False
            print("🔌 Disconnected from MCP Server")
            
    async def call_mcp_tool(self, tool_name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call an MCP tool and parse the response"""
        try:
            if not self.connected:
                await self.connect_mcp()
                
            result = await self.mcp_client.call_tool(tool_name, params or {})
            
            if not result:
                return {"error": "No result received from MCP server"}
                
            # Extract the text content from the first result item
            text_content = result[0].text
            # Parse the JSON response
            parsed_result = json.loads(text_content)
            
            print(f"🔧 Called MCP tool '{tool_name}' - Success: {'error' not in parsed_result}")
            return parsed_result
            
        except Exception as e:
            error_msg = f"Error calling MCP tool {tool_name}: {str(e)}"
            print(f"❌ {error_msg}")
            return {"error": error_msg}

    async def setup_tools(self):
        """Setup LangGraph tools that wrap MCP server functionality"""
        
        @tool
        async def list_task_lists() -> str:
            """Get all Microsoft To-Do task lists for the user."""
            result = await self.call_mcp_tool("list_task_lists")
            if "error" in result:
                return f"Error: {result['error']}"
            
            task_lists = result.get("taskLists", [])
            if not task_lists:
                return "No task lists found."
            
            output = f"Found {len(task_lists)} task lists:\n"
            for i, task_list in enumerate(task_lists, 1):
                shared_info = " (Shared)" if task_list.get("isShared", False) else ""
                output += f"{i}. {task_list['name']} (ID: {task_list['id']}){shared_info}\n"
            
            return output

        @tool
        async def create_task_list(name: str) -> str:
            """Create a new task list in Microsoft To-Do.
            
            Args:
                name: The name for the new task list
            """
            result = await self.call_mcp_tool("create_task_list", {"name": name})
            if "error" in result:
                return f"Error creating task list: {result['error']}"
            
            if result.get("success"):
                task_list = result["taskList"]
                return f"✅ Successfully created task list '{task_list['name']}' (ID: {task_list['id']})"
            
            return "Failed to create task list"

        @tool
        async def delete_task_list(list_id: str) -> str:
            """Delete a task list from Microsoft To-Do.
            
            Args:
                list_id: The ID of the task list to delete
            """
            result = await self.call_mcp_tool("delete_task_list", {"list_id": list_id})
            if "error" in result:
                return f"Error deleting task list: {result['error']}"
            
            if result.get("success"):
                return f"✅ Successfully deleted task list (ID: {list_id})"
            
            return "Failed to delete task list"

        @tool
        async def list_tasks(list_id: str) -> str:
            """Get all tasks in a specific task list.
            
            Args:
                list_id: The ID of the task list
            """
            result = await self.call_mcp_tool("list_tasks", {"list_id": list_id})
            if "error" in result:
                return f"Error listing tasks: {result['error']}"
            
            tasks = result.get("tasks", [])
            if not tasks:
                return f"No tasks found in this list (ID: {list_id})"
            
            output = f"Found {len(tasks)} tasks:\n"
            for i, task in enumerate(tasks, 1):
                status_icon = "✅" if task["status"] == "completed" else "⏳"
                due_info = f" (Due: {task['dueDate']})" if task.get("dueDate") else ""
                description_info = f" - {task['description'][:50]}..." if task.get("description") else ""
                output += f"{i}. {status_icon} {task['title']}{due_info}{description_info} (ID: {task['id']})\n"
            
            return output

        @tool
        async def create_task(list_id: str, title: str, description: str = "", due_date: str = "") -> str:
            """Create a new task in a task list.
            
            Args:
                list_id: The ID of the task list
                title: The title of the task
                description: The description of the task (optional)
                due_date: The due date in YYYY-MM-DD format (optional)
            """
            params = {
                "list_id": list_id,
                "title": title,
                "description": description,
                "due_date": due_date
            }
            
            result = await self.call_mcp_tool("create_task", params)
            if "error" in result:
                return f"Error creating task: {result['error']}"
            
            if result.get("success"):
                task = result["task"]
                due_info = f" (Due: {task['dueDate']})" if task.get("dueDate") else ""
                return f"✅ Successfully created task '{task['title']}'{due_info} (ID: {task['id']})"
            
            return "Failed to create task"

        @tool
        async def update_task(list_id: str, task_id: str, title: str = None, 
                            description: str = None, due_date: str = None, status: str = None) -> str:
            """Update an existing task in a task list.
            
            Args:
                list_id: The ID of the task list
                task_id: The ID of the task to update
                title: New title for the task (optional)
                description: New description for the task (optional)
                due_date: New due date in YYYY-MM-DD format (optional, empty string to remove)
                status: New status - "notStarted" or "completed" (optional)
            """
            params = {"list_id": list_id, "task_id": task_id}
            
            if title is not None:
                params["title"] = title
            if description is not None:
                params["description"] = description
            if due_date is not None:
                params["due_date"] = due_date
            if status is not None:
                params["status"] = status
                
            result = await self.call_mcp_tool("update_task", params)
            if "error" in result:
                return f"Error updating task: {result['error']}"
            
            if result.get("success"):
                task = result["task"]
                return f"✅ Successfully updated task '{task['title']}' (ID: {task['id']})"
            
            return "Failed to update task"

        @tool
        async def complete_task(list_id: str, task_id: str) -> str:
            """Mark a task as completed.
            
            Args:
                list_id: The ID of the task list
                task_id: The ID of the task to complete
            """
            result = await self.call_mcp_tool("complete_task", {"list_id": list_id, "task_id": task_id})
            if "error" in result:
                return f"Error completing task: {result['error']}"
            
            if result.get("success"):
                task = result["task"]
                return f"✅ Successfully completed task '{task['title']}' (ID: {task['id']})"
            
            return "Failed to complete task"

        @tool
        async def uncomplete_task(list_id: str, task_id: str) -> str:
            """Mark a completed task as not started.
            
            Args:
                list_id: The ID of the task list
                task_id: The ID of the task to mark as not started
            """
            result = await self.call_mcp_tool("uncomplete_task", {"list_id": list_id, "task_id": task_id})
            if "error" in result:
                return f"Error marking task as not started: {result['error']}"
            
            if result.get("success"):
                task = result["task"]
                return f"✅ Successfully marked task '{task['title']}' as not started (ID: {task['id']})"
            
            return "Failed to mark task as not started"

        @tool
        async def delete_task(list_id: str, task_id: str) -> str:
            """Delete a task from a task list.
            
            Args:
                list_id: The ID of the task list
                task_id: The ID of the task to delete
            """
            result = await self.call_mcp_tool("delete_task", {"list_id": list_id, "task_id": task_id})
            if "error" in result:
                return f"Error deleting task: {result['error']}"
            
            if result.get("success"):
                return f"✅ Successfully deleted task (ID: {task_id})"
            
            return "Failed to delete task"

        # Store tools for the graph
        self.tools = [
            list_task_lists, create_task_list, delete_task_list,
            list_tasks, create_task, update_task,
            complete_task, uncomplete_task, delete_task
        ]
        
        print(f"🛠️  Setup {len(self.tools)} LangGraph tools")

    def setup_graph(self):
        """Setup the LangGraph workflow"""
        
        # Bind tools to LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Create tool node
        tool_node = ToolNode(self.tools)
        
        def should_continue(state: AgentState) -> str:
            """Determine if we should continue to tools or end"""
            messages = state["messages"]
            last_message = messages[-1]
            
            # If the LLM makes a tool call, then we route to the "tools" node
            if last_message.tool_calls:
                return "tools"
            # Otherwise, we stop (reply to the user)
            return END

        async def call_model(state: AgentState):
            """Call the model with current state"""
            messages = state["messages"]
            
            # Add system message with context
            system_message = SystemMessage(content=SYSTEM_PROMPT)
            
            # Combine system message with conversation
            full_messages = [system_message] + messages
            
            response = await llm_with_tools.ainvoke(full_messages)
            return {"messages": [response]}

        # Build graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)
        
        # Add edges
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", should_continue)
        workflow.add_edge("tools", "agent")
        
        # Compile the graph
        self.graph = workflow.compile()
        print("📊 LangGraph workflow compiled successfully")

    async def chat(self, message: str, state: Optional[AgentState] = None) -> tuple[str, AgentState]:
        """
        Chat with the agent
        
        Args:
            message: User message
            state: Current conversation state (optional)
            
        Returns:
            Tuple of (response, updated_state)
        """
        if not self.graph:
            raise RuntimeError("Agent not properly initialized. Use async context manager.")
        
        # Initialize state if not provided
        if state is None:
            state = AgentState(
                messages=[],
                current_list_id=None,
                current_list_name=None,
                last_operation=None
            )
        
        # Add user message to state
        state["messages"].append(HumanMessage(content=message))
        
        # Run the graph
        result = await self.graph.ainvoke(state)
        
        # Extract the response
        last_message = result["messages"][-1]
        response = last_message.content
        
        return response, result

    async def run_interactive(self):
        """Run an interactive chat session"""
        print("\n🤖 Microsoft To-Do Agent (powered by LangGraph + MCP)")
        print("Type 'quit', 'exit', or 'bye' to end the conversation")
        print("=" * 60)
        
        state = None
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("\n👋 Goodbye! Have a productive day!")
                    break
                
                if not user_input:
                    continue
                
                print("🤖 To-Do Agent: Thinking...")
                response, state = await self.chat(user_input, state)
                print(f"🤖 To-Do Agent: {response}")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Have a productive day!")
                break
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                print("Please try again or type 'quit' to exit.")


async def main():
    """Main function to run the agent"""
    import os

    # Get Google API key
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("❌ Error: GOOGLE_API_KEY environment variable not set")
        return

    # Initialize and run the agent
    try:
        async with TodoMCPAgent(google_api_key=google_api_key) as agent:
            print("✅ Agent initialized successfully")
            await agent.run_interactive()
    except Exception as e:
        print(f"❌ Failed to initialize agent: {str(e)}")
        print("Make sure your MCP server is properly configured and dependencies are installed.")


if __name__ == "__main__":
    asyncio.run(main())

