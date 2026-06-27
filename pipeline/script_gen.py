import json

from openai import OpenAI

from pipeline.config import OPENAI_API_KEY, SCRIPT_MODEL

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """你是一位资深历史纪录片编剧，专门为YouTube制作关于韩国历史的中文纪录片脚本。
你的写作风格沉稳、客观、富有画面感，旁白语气是一位冷静严谨的历史学者男声。

请严格按照以下JSON格式输出，不要输出任何多余文字：
{
  "title": "吸引人的中文视频标题（不超过60字，包含关键词以利于搜索）",
  "description": "YouTube视频简介（150-300字，包含主题概述和3-5个相关标签提示）",
  "tags": ["标签1", "标签2", "...8-15个中文/英文标签"],
  "scenes": [
    {
      "narration": "这一场景的中文旁白文本（一段话，3-6句，适合朗读，语气沉稳客观）",
      "image_prompt": "用于AI图像生成的英文提示词，描绘这一场景的历史画面，风格为cinematic historical documentary illustration, painterly, dramatic lighting, no text, no watermark"
    }
  ]
}

要求（必须严格遵守，这是硬性指标，不是建议）：
- scenes 数量必须恰好是 12 个。
- 每一个场景的 narration 字数必须在 180 到 230 个汉字之间（不含标点也基本不能低于160字），绝对不能写成简短的一两句话。
- 因此整个脚本 narration 总字数必须达到 2100 字以上（12个场景 × 约180字），这样朗读总时长才能达到5-10分钟。字数不足是不可接受的错误。
- 每个场景内部要包含具体的历史细节、人物对话或心理描写、场景描写，而不是空洞的概括句，以撑满180-230字的篇幅。
- 内容必须基于真实历史事件，叙事要有开头（背景介绍）、发展（事件经过，可拆成多个场景）、结尾（历史意义/影响）的完整结构。
- 不要使用现代政治敏感表述，保持客观中立的历史叙述视角。
- image_prompt 必须是英文，且不包含任何文字、字幕、现代元素。
"""

MIN_TOTAL_CHARS = 1800
MAX_ATTEMPTS = 3


def _total_narration_chars(data: dict) -> int:
    return sum(len(s.get("narration", "")) for s in data.get("scenes", []))


def _request_script(messages: list[dict]) -> dict:
    response = client.chat.completions.create(
        model=SCRIPT_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.8,
    )
    return json.loads(response.choices[0].message.content)


def generate_script(topic: str) -> dict:
    user_prompt = f"请围绕主题《{topic}》撰写一部中文历史纪录片脚本。"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    data = None
    for attempt in range(MAX_ATTEMPTS):
        data = _request_script(messages)
        total_chars = _total_narration_chars(data)
        if total_chars >= MIN_TOTAL_CHARS:
            break
        messages.append({"role": "assistant", "content": json.dumps(data, ensure_ascii=False)})
        messages.append({
            "role": "user",
            "content": (
                f"当前脚本旁白总字数只有{total_chars}字，远远不够，必须达到{MIN_TOTAL_CHARS}字以上。"
                f"请重新输出完整的JSON，把每个场景的narration都扩写到180-230字，"
                f"增加具体的历史细节、人物言行、场景氛围描写，不要缩短或省略场景。"
            ),
        })

    assert data is not None
    assert "scenes" in data and len(data["scenes"]) > 0, "Script generation returned no scenes"
    assert "title" in data and data["title"], "Script generation returned no title"

    return data


if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "世宗大王与韩文的创制"
    script = generate_script(topic)
    print(json.dumps(script, ensure_ascii=False, indent=2))
