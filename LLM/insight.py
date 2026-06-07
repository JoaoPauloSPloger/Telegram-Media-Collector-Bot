import aiohttp
import json
import os
import logging
from src.database.db import config

async def get_llm_insight(error_message: str) -> str:
    provider = config.get('llm_provider', '').lower()
    api_key = config.get('llm_api_key', '')

    if not provider:
        return None

    try:
        with open('LLM/prompt.MD', 'r') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        prompt_template = "You are an expert system administrator. Analyze this error briefly: {error_log}"

    prompt = prompt_template.replace('{error_log}', error_message)

    try:
        async with aiohttp.ClientSession() as session:
            if provider == 'openai' or provider == 'chatgpt':
                return await _call_openai(session, api_key, prompt)
            elif provider == 'anthropic' or provider == 'claude':
                return await _call_anthropic(session, api_key, prompt)
            elif provider == 'gemini':
                return await _call_gemini(session, api_key, prompt)
            elif provider == 'groq':
                return await _call_groq(session, api_key, prompt)
            elif provider == 'local':
                return await _call_local(session, prompt)
            else:
                logging.warning(f"Unknown LLM provider: {provider}")
                return None
    except Exception as e:
        logging.error(f"LLM Insight failed: {e}")
        return None

async def _call_openai(session, api_key, prompt):
    model = config.get('llm_model') or "gpt-3.5-turbo"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data['choices'][0]['message']['content'].strip()
        return None

async def _call_anthropic(session, api_key, prompt):
    model = config.get('llm_model') or "claude-3-haiku-20240307"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }
    async with session.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data['content'][0]['text'].strip()
        return None

async def _call_gemini(session, api_key, prompt):
    model = config.get('llm_model') or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1000}
    }
    async with session.post(url, headers=headers, json=payload, timeout=120) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        return None

async def _call_groq(session, api_key, prompt):
    model = config.get('llm_model') or "llama3-8b-8192"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data['choices'][0]['message']['content'].strip()
        return None

async def _call_local(session, prompt):
    model = config.get('llm_model') or "llama3"
    local_url = config.get('llm_local_url', 'http://localhost:11434/api/generate')
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    async with session.post(local_url, json=payload, timeout=60) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get('response', '').strip()
        return None
