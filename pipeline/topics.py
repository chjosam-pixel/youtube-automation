import json
import random

from pipeline.config import TOPICS_STATE_FILE

TOPIC_BANK = [
    "高句丽广开土大王的征服战争",
    "新罗与唐朝联军统一三国的过程",
    "百济的灭亡与扶余隆的悲剧",
    "高丽太祖王建统一后三国",
    "高丽与契丹的三次战争",
    "朝鲜王朝的建立与李成桂",
    "世宗大王与韩文（训民正音）的创制",
    "壬辰倭乱与李舜臣的龟船传奇",
    "丙子胡乱与朝鲜的屈辱",
    "光海君的外交与废位",
    "朝鲜燕山君的暴政",
    "东学农民运动的兴起与失败",
    "甲申政变与朝鲜近代化的尝试",
    "大韩帝国的成立与灭亡",
    "安重根刺杀伊藤博文事件",
    "三一运动与韩国独立精神",
    "大韩民国临时政府的流亡岁月",
    "韩国光复与朝鲜半岛的分裂",
    "朝鲜战争的爆发与仁川登陆",
    "板门店停战协定的签署",
    "高丽青瓷工艺的辉煌历史",
    "新罗黄金王冠与古坟文化",
    "百济金铜大香炉的发现",
    "韩国佛国寺与石窟庵的建造传奇",
    "高丽八万大藏经的雕刻奇迹",
    "朝鲜王朝实录的编纂与保存",
    "景福宫的兴建与战火重建",
    "济州岛三姓穴神话与耽罗国",
    "伽倻联盟的兴衰之谜",
    "渤海国与高句丽遗民的复国梦",
    "新罗花郎制度与花郎世纪",
    "高丽武人政权与崔忠献家族",
    "朝鲜士林派与勋旧派的政争",
    "退溪李滉与朝鲜性理学的发展",
    "许浚与东医宝鉴的医学传奇",
    "朝鲜通信使与日朝交流史",
    "金大建神父与朝鲜天主教受难史",
    "丙寅洋扰与朝鲜的锁国政策",
    "江华岛条约与朝鲜开埠",
    "明成皇后被刺事件始末",
]


def _load_used():
    if TOPICS_STATE_FILE.exists():
        return set(json.loads(TOPICS_STATE_FILE.read_text()))
    return set()


def _save_used(used):
    TOPICS_STATE_FILE.write_text(json.dumps(sorted(used), ensure_ascii=False, indent=2))


def pick_topic():
    used = _load_used()
    available = [t for t in TOPIC_BANK if t not in used]
    if not available:
        used = set()
        available = list(TOPIC_BANK)
    topic = random.choice(available)
    used.add(topic)
    _save_used(used)
    return topic
