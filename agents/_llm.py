"""
agents/_llm.py
==============
Minimal, dependency-light LLM client supporting:
  * D-A-I spine (default) -- the dai-assistant model router on 127.0.0.1:11435
  * Ollama (local, free, last-resort fallback)
  * Groq    (opt-in via GROQ_API_KEY in vault)
  * HuggingFace Inference API (opt-in via HF_TOKEN in vault)

The spine is the only inference path by default. It owns free-tier rotation, 429
cooling, secret redaction and policy/sovereign.json -- routing through it is what
applies those to agent prompts. Direct cloud backends are used only if the spine
is explicitly selected out via `default_backend`.

No paid backends. No telemetry. No phone-home.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
MODELS_CFG = ROOT / "config" / "models.yaml"
AGENTS_CFG = ROOT / "config" / "agents.yaml"


@dataclass
class LLMResponse:
    text: str
    backend: str
    model: str


def _load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text())


def _ollama_chat(model: str, system: str, user: str, temperature: float) -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    num_predict = int(os.environ.get("OLLAMA_NUM_PREDICT", "256"))
    r = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _dai_router_chat(
    base_url: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> str:
    """
    Chat through the D-A-I spine -- the dai-assistant OpenAI-compatible model router.

    Model ids: `dai/auto` (text-optimised rotation) and `dai/vision-auto` (vision).
    The router, not this client, decides which free provider serves the request.
    """
    r = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _groq_chat(
    model: str,
    system: str,
    user: str,
    temperature: float,
    token: str,
) -> str:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _hf_chat(model: str, system: str, user: str, token: str) -> str:
    r = requests.post(
        f"https://api-inference.huggingface.co/models/{model}",
        headers={"Authorization": f"Bearer {token}"},
        json={"inputs": f"<|system|>\n{system}\n<|user|>\n{user}\n<|assistant|>\n"},
        timeout=300,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"]
    return json.dumps(data)


def _gemini_chat(
    model: str,
    system: str,
    user: str,
    temperature: float,
    token: str,
) -> str:
    """Google AI Studio (Gemini) free tier."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={token}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature},
    }
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return json.dumps(data)


def chat(role: str, user: str, vault_env: Optional[dict] = None) -> LLMResponse:
    """
    `role` is a key in agents.yaml.
    `vault_env` is an optional dict of decrypted env values (e.g. GROQ_API_KEY).
    """
    models = _load_yaml(MODELS_CFG)
    agents = _load_yaml(AGENTS_CFG)

    if role == "genie":
        cfg = agents["genie"]
    else:
        cfg = agents["agents"].get(role) or {
            "model_key": "sidekick",
            "system_prompt": "You are a Genie Sidekick.",
        }

    model_key = cfg["model_key"]
    system_prompt = cfg["system_prompt"]

    vault_env = vault_env or {}
    backend = models.get("default_backend", "ollama")
    fallback = models.get("fallback_backend", "ollama")

    if backend == "dai_router":
        # The spine is the only inference path. A cloud token in the vault does NOT
        # override it: routing through the router is what applies secret redaction and
        # policy/sovereign.json. If the spine is unreachable we fail down to local
        # Ollama -- never sideways to a direct, unredacted cloud call.
        router = models.get("dai_router", {})
        base_url = os.environ.get(
            "DAI_ROUTER_URL", router.get("base_url", "http://127.0.0.1:11435/v1")
        )
        m = router.get("models", {}).get(model_key, "dai/auto")
        temperature = models.get(fallback, {}).get(model_key, {}).get("temperature", 0.3)
        try:
            text = _dai_router_chat(base_url, m, system_prompt, user, temperature)
        except requests.RequestException as exc:
            if fallback != "ollama":
                raise RuntimeError(
                    f"D-A-I spine unreachable at {base_url} and "
                    f"fallback_backend={fallback!r}."
                ) from exc
            local = models["ollama"][model_key]
            text = _ollama_chat(
                local["model"], system_prompt, user, local["temperature"]
            )
            return LLMResponse(
                text=text, backend="ollama-fallback", model=local["model"]
            )
        return LLMResponse(text=text, backend="dai_router", model=m)

    # Legacy direct backends -- reached only when default_backend names one of them.
    # Gemini first (best free reasoning), then Groq (fastest), then HF.
    if vault_env.get("GEMINI_API_KEY"):
        backend = "gemini"
    elif vault_env.get("GROQ_API_KEY"):
        backend = "groq"
    elif vault_env.get("HF_TOKEN"):
        backend = "huggingface"

    if backend == "ollama":
        entry = models["ollama"][model_key]
        try:
            text = _ollama_chat(
                entry["model"],
                system_prompt,
                user,
                entry["temperature"],
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                "Ollama is the default backend, but it is not reachable at "
                f"{os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')}. "
                "Start Ollama and pull the configured models, or store a free "
                "cloud token with scripts/set_token.py."
            ) from exc
        return LLMResponse(text=text, backend="ollama", model=entry["model"])
    if backend == "gemini":
        m = models["gemini"]["models"]["fast"]
        return LLMResponse(
            text=_gemini_chat(m, system_prompt, user, 0.3, vault_env["GEMINI_API_KEY"]),
            backend="gemini",
            model=m,
        )
    if backend == "groq":
        m = models["groq"]["models"]["fast"]
        return LLMResponse(
            text=_groq_chat(m, system_prompt, user, 0.3, vault_env["GROQ_API_KEY"]),
            backend="groq",
            model=m,
        )
    if backend == "huggingface":
        m = models["huggingface"]["models"]["fast"]
        return LLMResponse(
            text=_hf_chat(m, system_prompt, user, vault_env["HF_TOKEN"]),
            backend="huggingface",
            model=m,
        )

    raise RuntimeError(f"Unknown backend: {backend}")
