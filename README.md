# DraftPilot

DraftPilot is an autonomous AI agent built using Python and FastAPI. It accepts a user's request, creates its own execution plan, completes the required tasks, and generates a professional Microsoft Word (.docx) document.

This project was developed as part of a Python AI Engineer Autonomous Agents assignment.

---

## Features

- Accepts natural language requests
- Creates its own task list automatically
- Generates business documents like proposals and project plans
- Uses Reflection/Self-Check to improve the final output
- Generates Microsoft Word (.docx) documents
- REST API built with FastAPI

---

## Tech Stack

- Python
- FastAPI
- Groq API
- python-docx
- Pydantic

---

## API Endpoints

### POST /agent

```json
{
  "request": "Create a business proposal for an AI CRM system."
}
```

### GET /health

Checks if the API is running.

### GET /agent/download

Downloads the generated Word document.

---

## How to Run

1. Clone the repository

```bash
git clone https://github.com/your-username/draftpilot.git
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. (Optional) Add your Groq API key to `.env`

```
GROQ_API_KEY=your_api_key
```

4. Start the server

```bash
uvicorn main:app --reload
```

5. Open Swagger UI

```
http://127.0.0.1:8000/docs
```

---

## Project Structure

```
draftpilot/
│── agent/
│── main.py
│── test_client.py
│── requirements.txt
│── README.md
```

---

## Engineering Improvement

I implemented **Reflection / Self-Check**.

After generating the document, the agent reviews its own output. If any section is incomplete or contains errors, it regenerates that section before creating the final Word document. This helps improve the overall quality of the generated content.

---

## Sample Documents

The agent can generate:

- Business Proposal
- Project Plan
- Meeting Minutes
- Technical Design
- Business Report
- SOP

---

## Future Improvements

- Conversation memory
- RAG integration
- Database support
- More document templates
- Multi-agent workflow

---

## Author

**Kumar Veeresh**

B.Tech CSE (2025)
