# PersonaAI Backend

A FastAPI-based backend service for PersonaAI.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment variables in `.env` file:
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/personaai
```

4. Run the development server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`
API documentation will be available at `http://localhost:8000/docs`
