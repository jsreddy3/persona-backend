# How to Run PersonaAI Backend

## Backend Setup

1. First, clean up any existing database:
```bash
rm -f data/personaai.db
```

2. Initialize the database with test data:
```bash
# Replace /path/to/backend_persona with your actual path
PYTHONPATH=/path/to/backend_persona python init_db.py
```

3. Start the FastAPI server:
```bash
uvicorn main:app --reload
```

## Frontend Integration

To integrate with the backend, add this helper function to your frontend code:

```javascript
async function fetchWithAuth(url, options = {}) {
    // Add default options
    options = {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            // Use test credentials - these match the test user created by init_db.py
            'X-World-ID-Nullifier-Hash': 'test_nullifier_hash',
            'X-World-ID-Credential': 'test_credential',
            ...options.headers
        }
    };
    
    const response = await fetch(url, options);
    
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    return data;
}
```

Then use this helper instead of regular `fetch` for all authenticated API calls. For example:

```javascript
// Create a character
await fetchWithAuth('http://localhost:8000/characters/', {
    method: 'POST',
    body: JSON.stringify({
        name: 'Test Character',
        system_prompt: 'You are a helpful assistant',
        greeting: 'Hello! How can I help?'
    })
});

// Start a conversation
const conversationId = await fetchWithAuth('http://localhost:8000/conversations/', {
    method: 'POST',
    body: JSON.stringify({
        character_id: 1,
        language: 'en'
    })
});

// Send a message
await fetchWithAuth(`http://localhost:8000/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({
        content: 'Hello!'
    })
});
```

## API Endpoints

### Public Endpoints (No Auth Required)
- `POST /users/verify` - Verify a World ID proof and create/update user
- `GET /characters/popular` - Get popular characters (marketplace)
- `GET /characters/{id}/stats` - Get character statistics (marketplace)

### Authenticated Endpoints (Require Test Credentials)
All other endpoints require the test credentials in the headers:

#### Characters
- `POST /characters/` - Create a character
- `GET /characters/{id}` - Get character details

#### Conversations
- `POST /conversations/` - Create a new conversation
- `GET /conversations/` - List all conversations
- `GET /conversations/{id}/messages` - Get messages in a conversation
- `POST /conversations/{id}/messages` - Send a message in a conversation

#### Users
- `GET /users/me` - Get current user info
- `GET /users/stats` - Get user statistics
- `POST /users/credits` - Purchase credits

## Notes
- The test credentials are already set up in the database by `init_db.py`
- Most endpoints require auth except for initial World ID verification
- All API responses are JSON
- The server runs on `http://localhost:8000` by default
