"""Small wrapper around OpenRouter's OpenAI-compatible API."""

import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def get_llm_reply(user_message: str, context: str = "", language: str = "English") -> str:
    """Send a message through OpenRouter and return its text response.

    Raises:
        RuntimeError: If OPENROUTER_API_KEY is not set in the environment or .env file.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Add it to your .env file before running the app."
        )

    system_prompt = (
        "You are a helpful robot voice assistant. Reply briefly and naturally. "
        f"The user's detected language is {language}. "
        "Reply in that same language. Do not mention the model provider."
    )
    if context:
        system_prompt += f"\n\nKnowledge-base context:\n{context}"

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    completion = client.chat.completions.create(
        # OpenRouter selects an available free model for this router.
        model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        max_tokens=500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    reply = completion.choices[0].message.content
    if not reply:
        raise RuntimeError("OpenRouter returned an empty response.")
    return reply


def get_claude_reply(user_message: str, context: str = "", language: str = "English") -> str:
    """Backward-compatible name for :func:`get_llm_reply`."""
    return get_llm_reply(user_message, context=context, language=language)
