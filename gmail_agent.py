"""
LangGraph Gmail Agent

This agent uses LangGraph to provide natural language interaction with Gmail
through the MCP server. It can automate email management, sending, reading,
and complex multi-step workflows.
"""

import asyncio
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

# Gmail Agent System Prompt
from prompts.gmail_prompt import GMAIL_SYSTEM_PROMPT

class AgentState(TypedDict):
    """State for the LangGraph Gmail agent"""
    messages: Annotated[List, add_messages]
    current_message_id: Optional[str]
    current_thread_id: Optional[str]
    last_operation: Optional[str]
    search_context: Optional[str]


class GmailMCPAgent:
    """LangGraph agent for Gmail automation via MCP"""
    
    def __init__(self, mcp_url: str = "http://127.0.0.1:5001/mcp", google_api_key: str = None):
        """
        Initialize the Gmail MCP Agent
        
        Args:
            mcp_url: URL of the Gmail MCP server
            google_api_key: Google API key for the LLM
        """
        self.mcp_url = mcp_url
        self.mcp_client = None
        self.connected = False
        
        # Initialize LLM
        api_key = google_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Google API key is required. Set GOOGLE_API_KEY environment variable or pass it directly.")

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            google_api_key=api_key,
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
        """Connect to the Gmail MCP server"""
        try:
            if not self.connected:
                print("🔄 Connecting to Gmail MCP server...")
                self.mcp_client = Client(self.mcp_url)
                await self.mcp_client.__aenter__()
                self.connected = True
                print("✅ Connected to Gmail MCP Server")
        except Exception as e:
            print(f"❌ Failed to connect to Gmail MCP server: {str(e)}")
            print("\nTroubleshooting:")
            print(f"1. Check if Gmail MCP server is running at: {self.mcp_url}")
            print("2. Verify your Gmail API credentials are configured")
            print("3. Make sure the MCP server dependencies are installed")
            raise RuntimeError(f"Failed to initialize Gmail MCP server: {str(e)}")

    async def disconnect_mcp(self):
        """Disconnect from the Gmail MCP server"""
        if self.connected and self.mcp_client:
            await self.mcp_client.__aexit__(None, None, None)
            self.connected = False
            print("🔌 Disconnected from Gmail MCP Server")
            
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
            
            print(f"🔧 Called Gmail MCP tool '{tool_name}' - Success: {'error' not in parsed_result}")
            return parsed_result
            
        except Exception as e:
            error_msg = f"Error calling MCP tool {tool_name}: {str(e)}"
            print(f"❌ {error_msg}")
            return {"error": error_msg}

    async def setup_tools(self):
        """Setup LangGraph tools that wrap Gmail MCP server functionality"""
        
        @tool
        async def list_messages(query: str = '', max_results: int = 10) -> str:
            """Get Gmail messages with optional search query.
            
            Args:
                query: Search query (e.g., 'from:user@example.com is:unread', 'subject:important')
                max_results: Maximum number of messages to return (default: 10)
            """
            result = await self.call_mcp_tool("list_messages", {
                "query": query,
                "max_results": max_results
            })
            
            if "error" in result:
                return f"Error listing messages: {result['error']}"
            
            messages = result.get("messages", [])
            if not messages:
                return f"No messages found{' for query: ' + query if query else ''}."
            
            output = f"Found {len(messages)} messages{' for query: ' + query if query else ''}:\n\n"
            for i, msg in enumerate(messages, 1):
                from_addr = msg.get('from', 'Unknown')[:30]
                subject = msg.get('subject', 'No Subject')[:50]
                date = msg.get('date', 'Unknown')[:20]
                labels = ', '.join(msg.get('labelIds', [])[:3])
                
                output += f"{i}. From: {from_addr}\n"
                output += f"   Subject: {subject}\n"
                output += f"   Date: {date}\n"
                output += f"   Labels: {labels}\n"
                output += f"   ID: {msg.get('id', 'Unknown')}\n\n"
            
            return output

        @tool
        async def get_message(message_id: str) -> str:
            """Get detailed information about a specific Gmail message.
            
            Args:
                message_id: The ID of the message to retrieve
            """
            result = await self.call_mcp_tool("get_message", {"message_id": message_id})
            
            if "error" in result:
                return f"Error getting message: {result['error']}"
            
            message = result.get("message", {})
            if not message:
                return "Message not found."
            
            output = "📧 Message Details:\n"
            output += f"From: {message.get('from', 'Unknown')}\n"
            output += f"To: {message.get('to', 'Unknown')}\n"
            output += f"Subject: {message.get('subject', 'No Subject')}\n"
            output += f"Date: {message.get('date', 'Unknown')}\n"
            output += f"Labels: {', '.join(message.get('labelIds', []))}\n"
            
            if message.get('cc'):
                output += f"CC: {message['cc']}\n"
            
            body = message.get('body', '')
            if body:
                output += f"\n📝 Body:\n{body[:1000]}"
                if len(body) > 1000:
                    output += "... (truncated)"
            
            attachments = message.get('attachments', [])
            if attachments:
                output += f"\n\n📎 Attachments ({len(attachments)}):\n"
                for att in attachments:
                    output += f"  • {att.get('filename', 'Unknown')} ({att.get('mimeType', 'Unknown type')})\n"
            
            return output

        @tool
        async def search_messages(query: str, max_results: int = 10) -> str:
            """Search Gmail messages with advanced query syntax.
            
            Args:
                query: Gmail search query (e.g., 'from:boss@company.com after:2023/01/01')
                max_results: Maximum number of results (default: 10)
            """
            result = await self.call_mcp_tool("search_messages", {
                "query": query,
                "max_results": max_results
            })
            
            if "error" in result:
                return f"Error searching messages: {result['error']}"
            
            messages = result.get("messages", [])
            if not messages:
                return f"No messages found for search query: {query}"
            
            output = f"🔍 Search Results ({len(messages)} messages) for: {query}\n\n"
            for i, msg in enumerate(messages, 1):
                output += f"{i}. {msg.get('subject', 'No Subject')}\n"
                output += f"   From: {msg.get('from', 'Unknown')}\n"
                output += f"   Date: {msg.get('date', 'Unknown')}\n"
                output += f"   ID: {msg.get('id', 'Unknown')}\n\n"
            
            return output

        @tool
        async def send_message(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
            """Send a new Gmail message.
            
            Args:
                to: Recipient email address
                subject: Email subject
                body: Email body content
                cc: CC recipients (optional)
                bcc: BCC recipients (optional)
            """
            params = {
                "to": to,
                "subject": subject,
                "body": body
            }
            if cc:
                params["cc"] = cc
            if bcc:
                params["bcc"] = bcc
            
            result = await self.call_mcp_tool("send_message", params)
            
            if "error" in result:
                return f"Error sending message: {result['error']}"
            
            if result.get("success"):
                message_id = result.get("messageId", "Unknown")
                return f"✅ Email sent successfully!\nTo: {to}\nSubject: {subject}\nMessage ID: {message_id}"
            
            return "Failed to send email."

        @tool
        async def reply_to_message(message_id: str, reply_body: str) -> str:
            """Reply to an existing Gmail message.
            
            Args:
                message_id: ID of the message to reply to
                reply_body: Content of the reply
            """
            result = await self.call_mcp_tool("reply_to_message", {
                "message_id": message_id,
                "reply_body": reply_body
            })
            
            if "error" in result:
                return f"Error sending reply: {result['error']}"
            
            if result.get("success"):
                reply_id = result.get("messageId", "Unknown")
                return f"✅ Reply sent successfully!\nOriginal Message ID: {message_id}\nReply ID: {reply_id}"
            
            return "Failed to send reply."

        @tool
        async def mark_message_as_read(message_id: str) -> str:
            """Mark a Gmail message as read.
            
            Args:
                message_id: ID of the message to mark as read
            """
            result = await self.call_mcp_tool("mark_message_as_read", {"message_id": message_id})
            
            if "error" in result:
                return f"Error marking message as read: {result['error']}"
            
            if result.get("success"):
                return f"✅ Message marked as read (ID: {message_id})"
            
            return "Failed to mark message as read."

        @tool
        async def mark_message_as_unread(message_id: str) -> str:
            """Mark a Gmail message as unread.
            
            Args:
                message_id: ID of the message to mark as unread
            """
            result = await self.call_mcp_tool("mark_message_as_unread", {"message_id": message_id})
            
            if "error" in result:
                return f"Error marking message as unread: {result['error']}"
            
            if result.get("success"):
                return f"✅ Message marked as unread (ID: {message_id})"
            
            return "Failed to mark message as unread."

        @tool
        async def add_label_to_message(message_id: str, label_id: str) -> str:
            """Add a label to a Gmail message.
            
            Args:
                message_id: ID of the message
                label_id: ID of the label to add (e.g., 'IMPORTANT', 'STARRED')
            """
            result = await self.call_mcp_tool("add_label_to_message", {
                "message_id": message_id,
                "label_id": label_id
            })
            
            if "error" in result:
                return f"Error adding label: {result['error']}"
            
            if result.get("success"):
                current_labels = ', '.join(result.get("labelIds", []))
                return f"✅ Label '{label_id}' added to message (ID: {message_id})\nCurrent labels: {current_labels}"
            
            return "Failed to add label."

        @tool
        async def remove_label_from_message(message_id: str, label_id: str) -> str:
            """Remove a label from a Gmail message.
            
            Args:
                message_id: ID of the message
                label_id: ID of the label to remove
            """
            result = await self.call_mcp_tool("remove_label_from_message", {
                "message_id": message_id,
                "label_id": label_id
            })
            
            if "error" in result:
                return f"Error removing label: {result['error']}"
            
            if result.get("success"):
                current_labels = ', '.join(result.get("labelIds", []))
                return f"✅ Label '{label_id}' removed from message (ID: {message_id})\nCurrent labels: {current_labels}"
            
            return "Failed to remove label."

        @tool
        async def list_labels() -> str:
            """Get all available Gmail labels."""
            result = await self.call_mcp_tool("list_labels")
            
            if "error" in result:
                return f"Error listing labels: {result['error']}"
            
            labels = result.get("labels", [])
            if not labels:
                return "No labels found."
            
            output = f"📂 Available Gmail Labels ({len(labels)}):\n\n"
            for label in labels:
                name = label.get('name', 'Unknown')
                label_id = label.get('id', 'Unknown')
                label_type = label.get('type', 'Unknown')
                total = label.get('messagesTotal', 0)
                unread = label.get('messagesUnread', 0)
                
                output += f"• {name} (ID: {label_id})\n"
                output += f"  Type: {label_type} | Total: {total} | Unread: {unread}\n\n"
            
            return output

        # Store tools for the graph
        self.tools = [
            list_messages, get_message, search_messages,
            send_message, reply_to_message,
            mark_message_as_read, mark_message_as_unread,
            add_label_to_message, remove_label_from_message,
            list_labels
        ]
        
        print(f"🛠️  Setup {len(self.tools)} Gmail LangGraph tools")

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
            system_message = SystemMessage(content=GMAIL_SYSTEM_PROMPT)
            
            # Add context if available
            context_info = ""
            if state.get("current_message_id"):
                context_info += f"Currently focused on message ID: {state['current_message_id']}\n"
            if state.get("search_context"):
                context_info += f"Recent search context: {state['search_context']}\n"
            if state.get("last_operation"):
                context_info += f"Last operation: {state['last_operation']}\n"
            
            if context_info:
                enhanced_prompt = GMAIL_SYSTEM_PROMPT + f"\n\nCurrent Context:\n{context_info}"
                system_message = SystemMessage(content=enhanced_prompt)
            
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
        print("📊 Gmail LangGraph workflow compiled successfully")

    async def chat(self, message: str, state: Optional[AgentState] = None) -> tuple[str, AgentState]:
        """
        Chat with the Gmail agent
        
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
                current_message_id=None,
                current_thread_id=None,
                last_operation=None,
                search_context=None
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
        print("\n📧 Gmail Agent (powered by LangGraph + MCP)")
        print("Type 'quit', 'exit', or 'bye' to end the conversation")
        print("=" * 60)
        print("\nExamples of what you can ask:")
        print("• 'Show me my unread emails'")
        print("• 'Send an email to john@example.com about the meeting'")
        print("• 'Search for emails from my boss this week'")
        print("• 'Mark that message as important'")
        print("• 'Reply to the latest email'")
        print("=" * 60)
        
        state = None
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("\n👋 Goodbye! Have a great day with your emails!")
                    break
                
                if not user_input:
                    continue
                
                print("📧 Gmail Agent: Processing...")
                response, state = await self.chat(user_input, state)
                print(f"📧 Gmail Agent: {response}")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Have a great day with your emails!")
                break
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                print("Please try again or type 'quit' to exit.")


async def main():
    """Main function to run the Gmail agent"""
    
    # Get Google API key
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("❌ Error: GOOGLE_API_KEY environment variable not set")
        print("Please set your Google API key in the .env file or environment variables")
        return

    # Initialize and run the agent
    try:
        async with GmailMCPAgent(google_api_key=google_api_key) as agent:
            print("✅ Gmail Agent initialized successfully")
            await agent.run_interactive()
    except Exception as e:
        print(f"❌ Failed to initialize Gmail agent: {str(e)}")
        print("Make sure your Gmail MCP server is properly configured and running.")


if __name__ == "__main__":
    asyncio.run(main())