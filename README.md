# Gemini UI Server

This project is a simple web server built with FastAPI that provides a user interface to interact with Google's Gemini models. It demonstrates how to use the `google-genai` Python SDK for both direct text generation and function calling.

For function calls, this server securely communicates with a separate "S2" tool execution server using short-lived JSON Web Tokens (JWTs).

## Features

- **Simple Web UI**: A clean HTML and JavaScript frontend for submitting prompts.
- **FastAPI Backend**: A robust and modern Python web framework.
- **Gemini Integration**: Uses the latest `google-genai` SDK to interact with Gemini models (e.g., `gemini-1.5-flash`).
- **Function Calling**: Capable of deciding when to call external tools based on the user's prompt.
- **Secure Tool Execution**: Generates JWTs to authorize tool execution requests to a separate microservice (the "S2" server).

## Prerequisites

- Python 3.8+
- A Google Gemini API Key. You can get one from Google AI Studio.
- A running instance of the "S2" tool execution server. This project only contains the client-side logic to call it.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd gemini-ui-server
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate

    # For Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**

    The server requires several environment variables to be set. You can export them in your shell or create a `.env` file in the project root (this file is ignored by git).

    **Example `.env` file:**
    ```
    # Your API key from Google AI Studio
    GEMINI_API_KEY="your_gemini_api_key_here"

    # The base URL of your running S2 tool execution server
    S2_BASE_URL="http://localhost:8080"

    # A secret string used to sign JWTs. This MUST match the secret used by the S2 server.
    JWT_SECRET="your-super-secret-and-long-string"

    # (Optional) The Gemini model to use. Defaults to gemini-1.5-flash.
    # GEMINI_MODEL="gemini-1.5-pro"
    ```

## Running the Server

Once the setup is complete, you can run the FastAPI server using Uvicorn. The `--reload` flag is useful for development as it automatically restarts the server when you make code changes.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## How to Use

1.  Open your web browser and navigate to `http://localhost:8000`.
2.  You will see a simple interface with a text area.
3.  Enter a prompt. For example:
    - To get a direct answer: `What is the capital of France?`
    - To trigger a tool call: `Do I have any meetings tomorrow?`
4.  Click the "Submit" button.
5.  The server will process the request. If a tool is needed, it will contact the S2 server and then use the tool's output to generate a final response. The final JSON result will be displayed on the page.