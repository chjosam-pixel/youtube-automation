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

要求：
- 整个脚本旁白总长度需要能够朗读5到10分钟（中文朗读速度约每分钟220-260字），因此 narration 总字数应在1200-2400字之间。
- scenes 数量应在8到14个之间，每个场景旁白控制在100-220字。
- 内容必须基于真实历史事件，叙事要有开头（背景介绍）、发展（事件经过）、结尾（历史意义/影响）的完整结构。
- 不要使用现代政治敏感表述，保持客观中立的历史叙述视角。
- image_prompt 必须是英文，且不包含任何文字、字幕、现代元素。
"""


def generate_script(topic: str) -> dict:
    user_prompt = f"请围绕主题《{topic}》撰写一部中文历史纪录片脚本。"
    response = client.chat.completions.create(
        model=SCRIPT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )
    content = response.choices[0].message.content
    data = json.loads(content)

    assert "scenes" in data and len(data["scenes"]) > 0, "Script generation returned no scenes"
    assert "title" in data and data["title"], "Script generation returned no title"

    return data


if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "世宗大王与韩文的创制"
    script = generate_script(topic)
    print(json.dumps(script, ensure_ascii=False, indent=2))
