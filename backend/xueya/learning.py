"""Parity with browser offline rules. No model or API is used in these calculations."""
from __future__ import annotations
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

COURSE = json.loads((Path(__file__).parent / "data/course.json").read_text(encoding="utf-8"))
SOURCES, QUESTIONS = COURSE["sources"], COURSE["questions"]
SHANGHAI = ZoneInfo("Asia/Shanghai")


def today():
    return datetime.now(SHANGHAI).date().isoformat()


def valid_date(value):
    try:
        return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def add_days(value, days):
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def date_of(value, base=None):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=SHANGHAI)
        return stamp.astimezone(SHANGHAI).date().isoformat()
    except (ValueError, TypeError):
        return base


def wrong_questions(records, questions=None):
    latest = {r.get("questionId"): r for r in records}
    return [q for q in (QUESTIONS if questions is None else questions) if q["id"] in latest and not latest[q["id"]].get("correct")]


def memory_cards(records, base=None, questions=None):
    base, questions = base or today(), QUESTIONS if questions is None else questions
    cards, by_id = {}, {q["id"]: q for q in questions}
    for q in questions:
        cards[q["topic"]] = {"topic": q["topic"], "sourceId": q.get("sourceId", ""), "wrongCount": 0, "lastReviewed": None, "nextReview": None}
    for record in sorted(records, key=lambda r: str(r.get("createdAt", ""))):
        if record.get("questionId") not in by_id:
            continue
        card = cards[by_id[record["questionId"]]["topic"]]
        card["wrongCount"] = 0 if record.get("correct") else card["wrongCount"] + 1
        n = card["wrongCount"]
        interval = 7 if n == 0 else 3 if n == 1 else 2 if n == 2 else 1
        card["lastReviewed"] = date_of(record.get("createdAt"), base)
        card["nextReview"] = add_days(card["lastReviewed"], interval)
    return [{**c, "due": bool(c["lastReviewed"] and c["nextReview"] <= base)} for c in cards.values()]


def build_plan(exam_date, minutes, records, base=None, questions=None):
    base, questions = base or today(), QUESTIONS if questions is None else questions
    if not valid_date(exam_date) or exam_date < base or not questions:
        return []
    weak = [q["topic"] for q in wrong_questions(records, questions)]
    topics = list(dict.fromkeys(weak + [q["topic"] for q in questions]))
    daily = max(15, min(120, int(minutes or 30)))
    output = []
    for i in range(min(7, (date.fromisoformat(exam_date) - date.fromisoformat(base)).days + 1)):
        day, topic = add_days(base, i), topics[i % len(topics)]
        first = math.ceil(daily * .6)
        output.append({"date": day, "tasks": [
            {"id": f"{day}-{topic}-read", "title": f"{'回顾薄弱点' if topic in weak else '理解'}：{topic}", "detail": "阅读课程原文，保存一张重点卡片", "minutes": first},
            {"id": f"{day}-{topic}-practice", "title": f"练习与复述：{topic}", "detail": "完成示例练习，用自己的话解释答案", "minutes": daily-first}]})
    return output


def progress(records, questions=None, base=None):
    questions = QUESTIONS if questions is None else questions
    known = {q["id"] for q in questions}
    records = [r for r in records if r.get("questionId") in known]
    return {"total": len(records), "correct": sum(bool(r.get("correct")) for r in records),
            "weakTopics": list(dict.fromkeys(q["topic"] for q in wrong_questions(records, questions))),
            "dueTopics": [c["topic"] for c in memory_cards(records, base, questions) if c["due"]]}


def route_task(question, mode="ask"):
    if mode in ("summarize", "quiz"):
        return mode
    if re.search(r"(?:复习|学习|备考).{0,10}(?:计划|安排)|(?:计划|安排).{0,10}(?:复习|学习|备考)", question):
        return "plan"
    if re.search(r"薄弱|弱项|掌握情况|错题分析|学习情况|学习进度|复习重点", question):
        return "review"
    if re.search(r"总结|归纳|整理.{0,6}(?:重点|知识)", question):
        return "summarize"
    return "quiz" if re.search(r"(?:出|生成).{0,4}(?:练习|题目|题)|练习题|测验", question) else "ask"


def refers_previous(question):
    return bool(re.search(r"它|这个|这些|这种|这样|那个|那些|上述|刚才|上面|前面|继续|进一步|再解释|再说|展开讲|换个说法|举个例|举一个例|^(?:为什么|为何|怎么理解)[呢吗？?。！!\s]*$", question))


def local_answer(question, mode, sources):
    if not sources:
        return "当前资料中没有找到足够依据。请补充具体的课程关键词，或者上传相关 TXT / MD 资料后再试。"
    blocks = "\n\n".join(f"[{i+1}] {s['quote']}" for i, s in enumerate(sources))
    if mode == "summarize":
        return f"知识卡片：{question}\n\n" + "\n\n".join(f"重点 {i+1}｜{s['quote']}" for i, s in enumerate(sources)) + "\n\n复习时，先遮住答案，用自己的话复述这些重点。"
    if mode == "quiz":
        return f"可以先用这个问题检验理解：\n{question}\n\n请结合下列原文，写出定义、适用条件和边界情况：\n{blocks}\n\n需要选择题和判题反馈，可以进入“练习与错题”的示例题库。"
    return f"根据当前资料，可以从以下原文理解这个问题：\n\n{blocks}\n\n以上是本地检索摘录。点击引用可核对原文。"


def study_text(intent, stats, plan=None, base=None):
    summary = (f"最近 {stats['total']} 次作答中，答对 {stats['correct']} 次。\n当前待巩固：{'、'.join(stats['weakTopics']) or '暂无未解决的错题'}。\n今日到期复习：{'、'.join(stats['dueTopics']) or '暂无'}。" if stats["total"] else "目前还没有可分析的作答记录。先完成一组练习，就能根据结果识别薄弱点。")
    if intent != "plan":
        return summary
    if plan and plan["examDate"] < (base or today()):
        return summary + "\n\n考试日期已经过去，请先在复习计划中更新考试日期。当前计划未作修改。"
    if not plan or not plan["days"]:
        return summary + "\n\n暂时没有可安排的任务，请先完成练习或检查考试日期。"
    days = "\n\n".join(d["date"] + "\n" + "\n".join(f"· {t['title']}（{t['minutes']} 分钟）" for t in d["tasks"]) for d in plan["days"])
    return f"复习计划预览（每天 {plan['minutes']} 分钟，考试日期 {plan['examDate']}）：\n\n{days}\n\n{summary}\n\n这是一份预览，尚未修改你已有的复习计划。"
