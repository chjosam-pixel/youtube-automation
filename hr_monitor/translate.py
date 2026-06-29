"""Best-effort English -> Korean translation for digest text.

Uses the OpenAI API (same key as the YouTube pipeline) when available.
Falls back to the original text untranslated if no key is configured or the
request fails, so a translation hiccup never blocks an alert from going out.
"""

import os

import requests

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
TRANSLATE_MODEL = os.environ.get("HR_MONITOR_TRANSLATE_MODEL", "gpt-4o-mini")


def translate_to_korean(text: str) -> str:
    if not OPENAI_API_KEY or not text.strip():
        return text
    try:
        resp = requests.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": TRANSLATE_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Translate the given English news text to natural Korean. "
                            "Keep proper nouns (company/place names) recognizable. "
                            "Keep the same number of lines as the input. "
                            "Return only the translated text, no extra commentary."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0.2,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        print(f"[hr_monitor] translation failed, sending original text: {exc}")
        return text
