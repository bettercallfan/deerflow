import time
import random

from openai import OpenAI
from openai import RateLimitError
from typing import Optional, Dict, Any


def validate_response(response: Optional[str]) -> str:
    if response is None:
        return ""
    return response.strip()


class LLMClient:
    """
    基础 LLM 调用框架
    """
    def __init__(self, api_key: str, model_name: str, url: str):
        # 验证必要参数
        if not api_key:
            raise ValueError('[Error] API key is missing')
        if not model_name:
            raise ValueError('[Error] Model name is missing')
        if not url:
            raise ValueError('[Error] URL is missing')

        self.model_name = model_name
        self.time_out = 1800.0
        self.api_key = api_key
        self.url = url

        self.client = OpenAI(
            api_key=api_key,
            base_url=url,
        )

    def invoke(self, system_prompt: str, user_prompt: str, max_retries: int = 10, **kwargs) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 提取 OpenAI 额外参数
        allowed_keys = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "stream"}
        extra_params = {key: value for key, value in kwargs.items() if key in allowed_keys and value is not None}

        timeout = kwargs.pop("timeout", self.time_out)

        for attempt in range(max_retries):
            try:
                base_delay = 1.0  # 基础延迟1秒
                jitter = random.uniform(0, 0.5)  # 随机抖动0-0.5秒
                delay = base_delay + jitter
                time.sleep(delay)

                # 调用
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    timeout=timeout,
                    **extra_params,
                )

                if response.choices and response.choices[0].message:
                    return validate_response(response.choices[0].message.content)
                return ""
                
            except RateLimitError as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5 + random.uniform(0, 2)
                    print(f"遇到速率限制，等待 {wait_time:.2f} 秒后重试 (尝试 {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    print(f"达到最大重试次数，仍然遇到速率限制错误")
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2 + random.uniform(0, 1)
                    print(f"遇到错误: {e}，等待 {wait_time:.2f} 秒后重试 (尝试 {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    raise

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.model_name,
            "model": self.model_name,
            "api_base": self.url or "default",
        }