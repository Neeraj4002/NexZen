"""
Master Agent - Orchestrates Multiple Specialized Agents

This master agent uses LangGraph to coordinate multiple specialized agents.
It intelligently routes user requests to the appropriate sub-agents and manages
the overall conversation flow.

Current Sub-Agents:
- Todo Agent: Microsoft To-Do management via MCP
- Gmail Agent: Gmail management via MCP
"""

import asyncio
import json
import os
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional, Annotated, Literal
import importlib.util
import sys

# LangGraph imports
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

# Import the sub-agents
from todo import TodoMCPAgent
from gmail_agent import GmailMCPAgent
from prompts.main_prompt import MASTER_SYSTEM_PROMPT

load_dotenv()

class MasterAgentState(TypedDict):
    """State for the Master Agent"""
    messages: Annotated[List, add_messages]
    current_context: Optional[str]  # Which sub-agent is currently active
    sub_agent_states: Dict[str, Any]  # States for different sub-agents
    conversation_summary: Optional[str]


class MasterAgent:
    """Master Agent that orchestrates multiple specialized agents"""
    MASTER_SYSTEM_PROMPT = MASTER_SYSTEM_PROMPT
    def __init__(self, google_api_key: str = None):
        """Initialize the Master Agent"""
        self.google_api_key = google_api_key or os.getenv("GOOGLE_API_KEY")
        if not self.google_api_key:
            raise ValueError("Google API key is required")
        
        # Initialize LLM
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            google_api_key=self.google_api_key,
        )
        
        # Sub-agents
        self.todo_agent = None
        self.gmail_agent = None
        self.sub_agents_initialized = False
        
        # Tools and graph
        self.tools = []
        self.graph = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize_sub_agents()
        await self.setup_tools()
        self.setup_graph()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup_sub_agents()
        
    async def initialize_sub_agents(self):
        """Initialize all sub-agents"""
        try:
            print("🚀 Initializing Master Agent and sub-agents...")
            
            # Initialize Todo Agent
            print("📋 Initializing Todo Agent...")
            self.todo_agent = TodoMCPAgent(google_api_key=self.google_api_key)
            await self.todo_agent.__aenter__()
            
            # Initialize Gmail Agent
            print("📧 Initializing Gmail Agent...")
            self.gmail_agent = GmailMCPAgent(google_api_key=self.google_api_key)
            await self.gmail_agent.__aenter__()
            
            self.sub_agents_initialized = True
            print("✅ All sub-agents initialized successfully")
            
        except Exception as e:
            print(f"❌ Error initializing sub-agents: {str(e)}")
            raise
            
    async def cleanup_sub_agents(self):
        """Cleanup all sub-agents"""
        try:
            if self.todo_agent:
                await self.todo_agent.__aexit__(None, None, None)
            if self.gmail_agent:
                await self.gmail_agent.__aexit__(None, None, None)
            print("🧹 Sub-agents cleaned up")
        except Exception as e:
            print(f"⚠️  Error during cleanup: {str(e)}")

    async def setup_tools(self):
        """Setup tools that interface with sub-agents"""
        
        @tool
        async def todo_agent(user_request: str) -> str:
            """
            REQUIRED: Use this tool for ALL todo, task, and productivity requests.
            
            This tool handles:
            - Viewing/listing tasks (e.g., "show tasks", "open NexZen", "list my todos")
            - Creating/updating/deleting tasks and task lists
            - Managing Microsoft To-Do workflows
            - Any mention of task lists by name (like "NexZen")
            - Task organization and productivity planning
            
            ALWAYS use this tool when users ask about tasks, lists, or todos.
            
            Args:
                user_request: The complete user request about todos/tasks
            """
            try:
                if not self.todo_agent:
                    return "❌ Todo Agent is not available. Please try again later."
                
                print(f"🔄 Delegating to Todo Agent: {user_request}")
                
                # Get or initialize todo agent state
                current_state = getattr(self.todo_agent, '_current_state', None)
                
                # Send request to todo agent
                response, updated_state = await self.todo_agent.chat(user_request, current_state)
                
                # Store updated state
                self.todo_agent._current_state = updated_state
                
                return response
                
            except Exception as e:
                return f"❌ Error with Todo Agent: {str(e)}"

        @tool
        async def gmail_agent(user_request: str) -> str:
            """
            REQUIRED: Use this tool for ALL email and Gmail requests.
            
            This tool handles:
            - Reading emails (e.g., "show my emails", "read unread messages", "check inbox")
            - Sending emails (e.g., "send email to", "compose message")
            - Searching emails (e.g., "find emails from", "search for emails about")
            - Managing emails (e.g., "mark as read", "add label", "reply to")
            - Email organization and workflows
            - Any mention of specific email addresses or Gmail operations
            
            ALWAYS use this tool when users ask about emails, Gmail, messages, or communication.
            
            Args:
                user_request: The complete user request about emails/Gmail
            """
            try:
                if not self.gmail_agent:
                    return "❌ Gmail Agent is not available. Please try again later."
                
                print(f"🔄 Delegating to Gmail Agent: {user_request}")
                
                # Get or initialize gmail agent state
                current_state = getattr(self.gmail_agent, '_current_state', None)
                
                # Send request to gmail agent
                response, updated_state = await self.gmail_agent.chat(user_request, current_state)
                
                # Store updated state
                self.gmail_agent._current_state = updated_state
                
                return response
                
            except Exception as e:
                return f"❌ Error with Gmail Agent: {str(e)}"

        # Store tools
        self.tools = [todo_agent, gmail_agent]
        print(f"🛠️  Master Agent tools setup complete ({len(self.tools)} tools)")

    def setup_graph(self):
        """Setup the LangGraph workflow for the master agent"""
        
        # Bind tools to LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Create tool node
        tool_node = ToolNode(self.tools)
        
        def should_continue(state: MasterAgentState) -> Literal["tools", "__end__"]:
            """Determine whether to continue to tools or end"""
            messages = state["messages"]
            last_message = messages[-1]
            
            if last_message.tool_calls:
                return "tools"
            return END

        async def call_model(state: MasterAgentState):
            """Call the model with current state"""
            messages = state["messages"]
            
            # Add system message
            system_message = SystemMessage(content=self.MASTER_SYSTEM_PROMPT)
            
            # Add context if available
            context_info = ""
            if state.get("current_context"):
                context_info = f"\nCurrent context: Working with {state['current_context']}"
            
            if state.get("conversation_summary"):
                context_info += f"\nConversation summary: {state['conversation_summary']}"
            
            if context_info:
                system_message.content += context_info
            
            # Combine system message with conversation
            full_messages = [system_message] + messages
            
            response = await llm_with_tools.ainvoke(full_messages)
            
            # Update context based on tool calls
            updated_context = state.get("current_context")
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    if tool_call["name"] == "todo_agent":
                        updated_context = "Todo Agent"
                    elif tool_call["name"] == "gmail_agent":
                        updated_context = "Gmail Agent"
            
            return {
                "messages": [response],
                "current_context": updated_context
            }

        # Build graph
        workflow = StateGraph(MasterAgentState)
        
        # Add nodes
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)
        
        # Add edges
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", should_continue)
        workflow.add_edge("tools", END)
        
        # Compile the graph
        self.graph = workflow.compile()
        print("📊 Master Agent workflow compiled successfully")

    async def chat(self, message: str, state: Optional[MasterAgentState] = None) -> tuple[str, MasterAgentState]:
        """
        Chat with the master agent
        
        Args:
            message: User message
            state: Current conversation state
            
        Returns:
            Tuple of (response, updated_state)
        """
        if not self.graph:
            raise RuntimeError("Master Agent not properly initialized")
        
        # Initialize state if not provided
        if state is None:
            state = MasterAgentState(
                messages=[],
                current_context=None,
                sub_agent_states={},
                conversation_summary=None
            )
        
        # Add user message
        state["messages"].append(HumanMessage(content=message))
        
        # Run the graph
        result = await self.graph.ainvoke(state)
        
        # Extract response
        last_message = result["messages"][-1]
        response = last_message.content
        
        return response, result

    def is_todo_related(self, message: str) -> bool:
        """Helper method to determine if a message is todo-related"""
        todo_keywords = [
            'task', 'todo', 'reminder', 'due', 'deadline', 'schedule',
            'productivity', 'organize', 'list', 'complete', 'finish',
            'create task', 'add task', 'microsoft to-do', 'to-do'
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in todo_keywords)

    def is_email_related(self, message: str) -> bool:
        """Helper method to determine if a message is email-related"""
        email_keywords = [
            'email', 'gmail', 'message', 'mail', 'send', 'reply', 'inbox',
            'compose', 'unread', 'read', 'search', 'find emails', 'check mail',
            'sent', 'received', 'label', 'star', 'important', '@', 'subject'
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in email_keywords)

    async def run_interactive(self):
        """Run an interactive chat session"""
        print("\n🤖 Master AI Assistant")
        print("I can help you with:")
        print("  📋 Todo and task management (Microsoft To-Do)")
        print("  📧 Email management (Gmail)")
        print("  💬 General questions and conversation")
        print("  🔄 And more specialized agents coming soon!")
        print("\nType 'quit', 'exit', or 'bye' to end the conversation")
        print("=" * 60)
        print("\nExample requests:")
        print("  📋 'Show my tasks for today'")
        print("  📧 'Check my unread emails'")
        print("  📧 'Send an email to john@example.com'")
        print("  📋 'Create a task to review the budget'")
        print("=" * 60)
        
        state = None
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("\n👋 Goodbye! Thanks for using the Master AI Assistant!")
                    break
                
                if not user_input:
                    continue
                
                # Show thinking indicator with routing hint
                context_hint = ""
                if self.is_todo_related(user_input):
                    context_hint = " (routing to Todo Agent)"
                elif self.is_email_related(user_input):
                    context_hint = " (routing to Gmail Agent)"
                
                print(f"🤖 Master Agent: Thinking{context_hint}...")
                
                # Get response
                response, state = await self.chat(user_input, state)
                print(f"🤖 Master Agent: {response}")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Thanks for using the Master AI Assistant!")
                break
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                print("Please try again or type 'quit' to exit.")

    async def handle_batch_requests(self, requests: List[str]) -> List[str]:
        """Handle multiple requests in batch"""
        responses = []
        state = None
        
        for i, request in enumerate(requests):
            print(f"Processing request {i+1}/{len(requests)}: {request[:50]}...")
            response, state = await self.chat(request, state)
            responses.append(response)
            
        return responses


async def main():
    """Main function to run the master agent"""
    
    # Get Google API key
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("❌ Error: GOOGLE_API_KEY environment variable not set")
        print("Please set your Google API key in the .env file or environment variables")
        return

    # Initialize and run the master agent
    try:
        async with MasterAgent(google_api_key=google_api_key) as master_agent:
            print("✅ Master Agent initialized successfully")
            await master_agent.run_interactive()
            
    except Exception as e:
        print(f"❌ Failed to initialize Master Agent: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Make sure your .env file contains GOOGLE_API_KEY")
        print("2. Ensure the todo.py and gmail_agent.py files are in the same directory")
        print("3. Check that all dependencies are installed")
        print("4. Verify that both MCP servers (Todo and Gmail) are running")
        

if __name__ == "__main__":
    asyncio.run(main())