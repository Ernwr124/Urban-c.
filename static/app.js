let isProcessing = false;
let messageHistory = [];

const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');

// Auto-resize textarea
messageInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});

// Handle Enter key
messageInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Send button click
sendButton.addEventListener('click', sendMessage);

// Example prompts click handlers
document.addEventListener('DOMContentLoaded', function() {
    const examplePrompts = document.querySelectorAll('.example-prompt');
    examplePrompts.forEach(function(prompt) {
        prompt.addEventListener('click', function() {
            const text = this.getAttribute('data-prompt');
            useExample(text);
        });
    });
});

function useExample(text) {
    messageInput.value = text;
    messageInput.focus();
    messageInput.style.height = 'auto';
    messageInput.style.height = messageInput.scrollHeight + 'px';
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message || isProcessing) return;
    
    isProcessing = true;
    sendButton.disabled = true;
    
    // Clear input
    input.value = '';
    input.style.height = 'auto';
    
    // Remove welcome screen
    const welcome = document.querySelector('.welcome');
    if (welcome) {
        welcome.remove();
    }
    
    // Add user message
    addMessage('user', message);
    messageHistory.push({role: 'user', content: message});
    
    // Create assistant message container
    const messagesDiv = document.getElementById('messages');
    const assistantDiv = document.createElement('div');
    assistantDiv.className = 'message assistant-message';
    assistantDiv.innerHTML = 
        '<div class="message-header">' +
            '<span class="message-role assistant-role">Project-0</span>' +
        '</div>' +
        '<div class="thinking-indicator">' +
            '<span class="loading">Thinking</span>' +
        '</div>' +
        '<div class="message-content" id="currentResponse"></div>';
    messagesDiv.appendChild(assistantDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                messages: messageHistory,
                stream: true
            })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';
        
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.type === 'thinking') {
                            const thinkingDiv = assistantDiv.querySelector('.thinking-indicator');
                            if (thinkingDiv) {
                                thinkingDiv.textContent = data.content;
                            }
                        } else if (data.type === 'content') {
                            // Remove thinking indicator
                            const thinkingDiv = assistantDiv.querySelector('.thinking-indicator');
                            if (thinkingDiv) {
                                thinkingDiv.remove();
                            }
                            
                            fullResponse += data.content;
                            const responseDiv = document.getElementById('currentResponse');
                            responseDiv.innerHTML = formatMessage(fullResponse);
                            messagesDiv.scrollTop = messagesDiv.scrollHeight;
                        } else if (data.type === 'done') {
                            messageHistory.push({role: 'assistant', content: fullResponse});
                        } else if (data.type === 'error') {
                            const responseDiv = document.getElementById('currentResponse');
                            responseDiv.innerHTML = '<span style="color: #ff4444;">' + data.content + '</span>';
                        }
                    } catch (e) {
                        console.error('Parse error:', e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error:', error);
        const responseDiv = document.getElementById('currentResponse');
        responseDiv.innerHTML = '<span style="color: #ff4444;">Error: ' + error.message + '</span>';
    } finally {
        isProcessing = false;
        sendButton.disabled = false;
        input.focus();
    }
}

function addMessage(role, content) {
    const messagesDiv = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ' + role + '-message';
    
    const roleLabel = role === 'user' ? 'You' : 'Project-0';
    const roleClass = role === 'user' ? 'user-role' : 'assistant-role';
    
    messageDiv.innerHTML = 
        '<div class="message-header">' +
            '<span class="message-role ' + roleClass + '">' + roleLabel + '</span>' +
        '</div>' +
        '<div class="message-content">' + formatMessage(content) + '</div>';
    
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function formatMessage(content) {
    // Format code blocks
    content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, lang, code) {
        lang = lang || '';
        return '<pre><code>' + escapeHtml(code.trim()) + '</code></pre>';
    });
    
    // Format inline code
    content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Format bold
    content = content.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    
    // Format line breaks
    content = content.replace(/\n/g, '<br>');
    
    return content;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Focus input on load
window.addEventListener('load', function() {
    messageInput.focus();
});
