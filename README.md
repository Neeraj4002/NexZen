# NextZen - AI-Powered Productivity Suite

A comprehensive AI assistant powered by LangGraph and MCP (Model Context Protocol) that orchestrates multiple specialized agents for productivity and communication management.

## 🌟 Features

### 🤖 Master Agent Orchestration
- **Intelligent Routing**: Automatically routes requests to appropriate specialized agents
- **Context Management**: Maintains conversation context across different agents
- **Multi-Agent Coordination**: Seamlessly coordinates between Todo and Gmail agents

### 📋 Todo Management (Microsoft To-Do Integration)
- View and manage task lists
- Create, update, and delete tasks
- Set due dates and reminders
- Organize tasks by priority and categories
- Natural language task creation and management

### 📧 Gmail Management
- Read and search emails with advanced queries
- Send emails and replies
- Mark messages as read/unread
- Manage email labels and organization
- View sent emails and email threads
- Handle attachments and rich email content


## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+**
2. **Google API Key** for Gemini LLM
3. **Microsoft To-Do API credentials**
4. **Gmail API credentials**

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd NextZen
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Setup environment variables**
Create a `.env` file:
```env
GOOGLE_API_KEY=your_google_api_key_here
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret
GMAIL_CREDENTIALS_PATH=path/to/gmail/credentials.json
```

4. **Setup API Credentials**

   **For Microsoft To-Do:**
   - Register app at [Azure Portal](https://portal.azure.com/)
   - Configure Microsoft Graph API permissions
   - Get client ID and secret

   **For Gmail:**
   - Enable Gmail API in [Google Cloud Console](https://console.cloud.google.com/)
   - Download credentials.json file
   - Configure OAuth consent screen

### Running the Application

1. **Start the MCP Servers**
```bash
# Terminal 1 - Todo MCP Server
python improved_mcp_server.py

# Terminal 2 - Gmail MCP Server  
python gmail_mcp_server.py
```

2. **Start the Master Agent**
```bash
# Terminal 3 - Master Agent
python main_agent.py
```

## 💬 Usage Examples

### Todo Management
```
👤 You: Show my tasks for today
👤 You: Create a task to review the quarterly budget due tomorrow
👤 You: Mark the meeting task as complete
👤 You: Open my NexZen task list
```

### Email Management
```
👤 You: Check my unread emails
👤 You: Send an email to boss@company.com about the project update
👤 You: Search for emails from john@example.com this week
👤 You: Show me my sent emails to whitebox6623@proton.me
👤 You: Reply to the latest email saying I'll review it today
```

### Smart Routing
The Master Agent automatically determines which specialized agent to use:
- **Todo keywords**: task, todo, reminder, due, deadline, schedule, list
- **Email keywords**: email, gmail, message, send, reply, inbox, unread

## 📁 Project Structure

## 🛠️ Components

### Master Agent (`main_agent.py`)
- Orchestrates multiple specialized agents
- Uses LangGraph for workflow management
- Intelligent request routing and context management

### Todo Agent (`todo.py`)
- Integrates with Microsoft To-Do via MCP
- Natural language task management
- LangGraph-powered conversation flow

### Gmail Agent (`gmail_agent.py`)
- Integrates with Gmail via MCP
- Email reading, sending, and management
- Advanced search and organization features

### MCP Servers
- **Todo MCP Server**: Bridges Microsoft To-Do API
- **Gmail MCP Server**: Bridges Gmail API
- Provides standardized MCP interface for agents

## 🔧 Configuration

### Environment Variables
```env
# Required
GOOGLE_API_KEY=your_google_gemini_api_key

# Microsoft To-Do (Optional - will prompt for OAuth)
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret

# Gmail (Optional - will prompt for OAuth)
GMAIL_CREDENTIALS_PATH=credentials.json
```

### MCP Server URLs
- Todo MCP Server: `http://127.0.0.1:8080`
- Gmail MCP Server: `http://127.0.0.1:5001`

## 🚨 Troubleshooting

### Common Issues

1. **"Failed to connect to MCP server"**
   - Ensure MCP servers are running on correct ports
   - Check firewall settings
   - Verify server logs for errors

2. **"Google API key is required"**
   - Set `GOOGLE_API_KEY` in your `.env` file
   - Ensure the API key has Gemini API access

3. **"SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC"**
   - Temporary Gmail API connection issue
   - Wait a moment and retry
   - Restart Gmail MCP server if persistent

4. **Authentication Errors**
   - Delete `token.json` files to re-authenticate
   - Check API credentials and permissions
   - Ensure OAuth consent screen is configured

### Debug Mode
Enable verbose logging by setting:
```env
DEBUG=true
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request


## 🛣️ Roadmap

- [ ] **Slack Integration**: Add Slack agent for team communication
- [ ] **Calendar Management**: Google/Outlook calendar integration
- [ ] **Document Processing**: PDF/Word document analysis and management
- [ ] **Web Search Agent**: Real-time web search and summarization
- [ ] **Database Integration**: SQL/NoSQL database query agent
- [ ] **Voice Interface**: Speech-to-text and text-to-speech capabilities
- [ ] **Mobile App**: React Native mobile companion
- [ ] **Dashboard UI**: Web-based management interface

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **LangGraph**: For the powerful agent orchestration framework
- **MCP (Model Context Protocol)**: For standardized agent communication
- **Google Gemini**: For the intelligent language model
- **Microsoft Graph API**: For To-Do integration
- **Gmail API**: For email management capabilities

**NextZen** - *Your AI-powered productivity companion* 🚀

Made with ⚡ by [S.N.K] — AI for Devs, Done Right.

