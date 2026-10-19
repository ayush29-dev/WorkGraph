"""LLM calls. Groq (free tier) for real runs, a canned reply for mock mode."""
import asyncio
import os


def default_model() -> str:
    # Check console.groq.com for the models currently on the free tier.
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


async def call_llm(system: str, prompt: str, model: str | None, mock: bool) -> tuple[str, int]:
    """Return (reply_text, total_tokens)."""
    if mock:
        await asyncio.sleep(float(os.getenv("MOCK_DELAY", "0.4")))  # fake latency
        text = f"[mock reply] {prompt[:120]}"
        tokens = (len(system) + len(prompt)) // 4 + 20
        return text, tokens

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env or run in mock mode.")
    # The Groq client is synchronous. to_thread keeps the event loop free.
    return await asyncio.to_thread(_groq_call, system, prompt, model or default_model())


def _groq_call(system: str, prompt: str, model: str) -> tuple[str, int]:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=30)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=model, messages=messages)
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else 0
    return text, tokens
