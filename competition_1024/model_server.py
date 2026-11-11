# -*- coding: utf-8 -*-
"""
比赛侧调用的生成服务（本地调试）。

- 无 MODEL_PATH：启发式解析，直接返回 JSON 字符串。
- 有 MODEL_PATH：加载 HuggingFace 因果 LM，prompt 输出接在 broadcast 后。
"""

from __future__ import annotations

import json
import os
from typing import Any

from competition_1024.heuristic_parser import parse_broadcast


def _parse_with_hf(text: str, model_path: str, max_new_tokens: int) -> str:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        raise RuntimeError("需要 pip install torch transformers 才能加载 MODEL_PATH") from e

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )
    device = next(model.parameters()).device
    prompt = text.rstrip() + "\n"
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    gen = tokenizer.decode(out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    return gen.strip()


def generate_model_output(text: str) -> str:
    """返回模型应输出的 JSON 字符串（含固定 required_cars/trip_seconds=1）。"""
    model_path = os.environ.get("COMPETITION_1024_MODEL_PATH", "").strip()
    max_tokens = int(os.environ.get("COMPETITION_1024_MAX_NEW_TOKENS", "32"))
    if model_path:
        raw = _parse_with_hf(text, model_path, max_tokens)
        # 若模型已输出 JSON，原样返回；否则包一层
        raw = raw.strip()
        if raw.startswith("{"):
            return raw
        return json.dumps({"demands": []}, ensure_ascii=False)
    result = parse_broadcast(text)
    return result["model_output"]


def create_app():
    try:
        from fastapi import FastAPI
        from pydantic import BaseModel, Field
    except ImportError as e:
        raise RuntimeError("需要 pip install fastapi uvicorn") from e

    app = FastAPI(title="competition-1024-model")

    class GenRequest(BaseModel):
        text: str = Field(..., description="广播正文")
        max_new_tokens: int = 32

    class GenResponse(BaseModel):
        model_output: str

    @app.get("/health")
    def health():
        return {"ok": True, "backend": "hf" if os.environ.get("COMPETITION_1024_MODEL_PATH") else "heuristic"}

    @app.post("/v1/generate", response_model=GenResponse)
    def generate(req: GenRequest):
        prev = os.environ.get("COMPETITION_1024_MAX_NEW_TOKENS")
        os.environ["COMPETITION_1024_MAX_NEW_TOKENS"] = str(req.max_new_tokens)
        try:
            return GenResponse(model_output=generate_model_output(req.text))
        finally:
            if prev is None:
                os.environ.pop("COMPETITION_1024_MAX_NEW_TOKENS", None)
            else:
                os.environ["COMPETITION_1024_MAX_NEW_TOKENS"] = prev

    @app.post("/v1/completions")
    def completions(body: dict[str, Any]):
        """OpenAI 风格兼容：prompt 字段即广播正文。"""
        text = body.get("prompt") or body.get("text") or ""
        return {"choices": [{"text": generate_model_output(str(text))}]}

    return app


def main():
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
