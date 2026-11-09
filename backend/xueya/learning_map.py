"""Read-only mind-map export for the personalized learning workbench.

The export is a study-route tree derived from data that already exists for the
signed-in account: the stored plan (optionally with its projected learning route
and knowledge framework). Nothing is written and no model is called.

Two archive formats are produced from the same tree:

* ``.xmind`` - XMind Zen / XMind 2020+ workbook (``content.json`` +
  ``metadata.json`` + ``manifest.json`` + an XMind 8 compatibility
  ``content.xml`` stub). The ZIP layout follows the JSON workbook format
  written by XMind itself and by community writers; it is validated by tests but
  cannot be opened by an XMind client in this environment.
* ``.mm`` - FreeMind XML fallback for clients that cannot read the JSON format.

Paths are mounted by :mod:`backend.xueya.workbench_api` under
``/api/learning/space/workbench/map/*``; ``rest`` is the operation name.
"""
from __future__ import annotations

import datetime
import io
import json
import re
import zipfile
from urllib.parse import quote

from fastapi import Response

from .common import AppError, digest, require, utc_now
from .learning_route import view as project_route
from .study_space_service import StudySpaceService

MAX_TITLE = 200
MAX_DETAIL = 500
MAX_GOAL = 1000
MAX_NODES = 600
MAX_PHASES = 24
MAX_STAGES = 60
MAX_TASKS_PER_DAY = 40
MAX_ROUTE_NODES = 300
MAX_FRAMEWORK_NODES = 80
MAX_FRAMEWORK_DEPTH = 5
MAX_DAYS = 366
MAX_ANSWER_CHARS = 200

XMindMediaType = "application/vnd.xmind.workbook"
FreeMindMediaType = "application/x-freemind"


# ---------------------------------------------------------------------------
# Small normalization helpers. Client-supplied values are always bounded here;
# the server never trusts a draft body beyond the fields it actually renders.
# ---------------------------------------------------------------------------

def _clean(value, limit=MAX_TITLE):
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    text = " ".join(text.split())
    return text[:limit]


def _clean_multiline(value, limit=MAX_GOAL):
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    return text.strip()[:limit]


def _iso_date(value):
    text = _clean(value, 10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return ""
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return ""
    return text


def _minutes(value):
    return value if type(value) is int and 0 <= value <= 480 else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 10000 else 0


def _account_key(request, host):
    """Resolve the learning account the same way the study-space API does."""
    account = getattr(getattr(host, "app", None), "state", None)
    account = getattr(account, "account", None) if account is not None else None
    if account is not None and account.record():
        require(account.authorized(request), "AUTH_REQUIRED")
        record = account.current(request) or {}
        return record.get("learningOwner") or record.get("username") or "local"
    return "local"


class _Budget:
    def __init__(self, limit=MAX_NODES):
        self.remaining = limit
        self.truncated = False

    def take(self):
        if self.remaining <= 0:
            self.truncated = True
            return False
        self.remaining -= 1
        return True


def _node(title, *, kind="topic", detail="", completed=None, fields=None, node_id=None):
    value = {"id": node_id or "n-" + digest([kind, title])[:20], "kind": kind,
             "title": _clean(title) or "未命名", "subtitle": _clean(detail, MAX_DETAIL), "children": []}
    if completed is not None:
        value["completed"] = bool(completed)
    if fields:
        value["fields"] = fields
    return value


def _subtitle(*parts):
    return " · ".join(str(part) for part in parts if part not in (None, "", False))


def _difficulty_label(value):
    # Plan drafts use 基础/进阶/挑战; projected route nodes use 简单/中等/困难.
    return value if value in ("基础", "进阶", "挑战", "简单", "中等", "困难") else ""


def _date_range(start, end):
    left, right = _iso_date(start), _iso_date(end)
    if left and right:
        return f"{left} 至 {right}"
    return left or right


def _weekday_label(value):
    return {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}.get(value, "")


def _rest_days_label(value):
    days = sorted({day for day in value if type(day) is int and 1 <= day <= 7}) if isinstance(value, list) else []
    return "、".join(_weekday_label(day) for day in days) or "无"


def _plan_summary(plan, budget):
    """The first branch under the root: facts the program actually knows."""
    info = _node("计划信息", kind="fact", detail="由程序从计划字段直接整理，不含模型推断")
    if not budget.take():
        return info
    facts = []
    goal = _clean_multiline(plan.get("goal"), MAX_GOAL)
    if goal:
        facts.append(("学习目标", goal, "fact"))
    difficulty = _difficulty_label(plan.get("difficulty"))
    if difficulty:
        facts.append(("难度", difficulty, "fact"))
    start, end = _iso_date(plan.get("startDate")), _iso_date(plan.get("endDate"))
    if start or end:
        days = plan.get("daysCount")
        span = (f"{start or '未提供'} 至 {end or '未提供'}")
        if type(days) is int and days > 0:
            span += f"（{days} 天）"
        facts.append(("计划周期", span, "fact"))
    minutes = _minutes(plan.get("dailyMinutes"))
    if minutes:
        facts.append(("每日可用时间", f"{minutes} 分钟", "fact"))
    facts.append(("固定休息日", _rest_days_label(plan.get("restDays")), "fact"))
    subjects = plan.get("subjects") if isinstance(plan.get("subjects"), list) else []
    subjects = [subject for subject in (_clean(item, 40) for item in subjects) if subject][:12]
    if subjects:
        facts.append(("学科与专题", "、".join(subjects), "fact"))
    explanation = _clean_multiline(plan.get("explanation"), MAX_DETAIL)
    if explanation:
        facts.append(("排程说明", explanation, "fact"))
    for title, detail, kind in facts:
        if not budget.take():
            break
        info["children"].append(_node(title, kind=kind, detail=detail))
    return info


def _task_fields(plan, task, date):
    resource = task.get("resource") if isinstance(task.get("resource"), dict) else {}
    if "boundCount" in task:
        bound = _count(task.get("boundCount"))
        required = _count(task.get("requiredCount")) or bound
    else:
        bound = 1 if resource.get("type") == "question" else 0
        required = bound
    submitted = min(_count(task.get("submittedCount")), bound) if bound else 0
    return {"date": _iso_date(date), "minutes": _minutes(task.get("minutes")),
            "difficulty": _difficulty_label(task.get("difficulty")) or _difficulty_label(plan.get("difficulty")),
            "questions": bound, "required": required, "submitted": submitted,
            "unbound": bound == 0, "phase": _clean(task.get("phase"), 60)}


def _task_node(plan, task, date, *, kind="task", budget=None, stats=None, title=None):
    """One task / knowledge point with only fields that exist in the plan."""
    fields = _task_fields(plan, task, date)
    completed = bool(task.get("completed"))
    if fields["questions"]:
        binding = f"关联题目 {fields['submitted']}/{fields['questions']}"
    elif fields["required"]:
        binding = f"未绑定本地题目（需 {fields['required']} 道）"
    else:
        binding = "未绑定本地题目"
    detail = _subtitle(fields["date"], f"{fields['minutes']} 分钟" if fields["minutes"] is not None else "",
                       fields["difficulty"],
                       "已完成" if completed else "未完成", binding)
    node = _node(title or task.get("title") or "学习任务", kind=kind, detail=detail,
                 completed=completed, fields=fields)
    if stats is not None:
        stats["tasks"] += 1
        stats["completed"] += int(completed)
        stats["questionRefs"] += fields["questions"]
        stats["unboundTasks"] += int(fields["unbound"])
    return node


def _phases_from_route(plan, route, budget, stats):
    phases = route.get("phases") if isinstance(route, dict) else None
    if not isinstance(phases, list) or not phases:
        return None
    output = []
    stage_total = 0
    for phase in phases:
        if not isinstance(phase, dict) or not budget.take():
            budget.truncated = True
            break
        if len(output) >= MAX_PHASES:
            budget.truncated = True
            break
        completed = bool(phase.get("completed"))
        node = _node(phase.get("title") or "学习阶段", kind="phase", completed=completed,
                     detail=_subtitle(_date_range(phase.get("startDate"), phase.get("endDate")),
                                      "阶段已完成" if completed else "阶段未完成"))
        stats["phases"] += 1
        stages = phase.get("stages") if isinstance(phase.get("stages"), list) else []
        for stage in stages:
            if not isinstance(stage, dict) or stage_total >= MAX_STAGES or not budget.take():
                budget.truncated = True
                break
            stage_total += 1
            stage_completed = bool(stage.get("completed"))
            stage_node = _node(stage.get("title") or "学习任务", kind="stage", completed=stage_completed,
                               detail=_subtitle(_date_range(stage.get("startDate"), stage.get("endDate")),
                                                "已完成" if stage_completed else "未完成",
                                                f"{_minutes(stage.get('minutes'))} 分钟" if _minutes(stage.get("minutes")) else "",
                                                f"题目 {_count(stage.get('questionCount'))} 道" if _count(stage.get("questionCount")) else ""))
            stats["stages"] += 1
            nodes = [raw for raw in (stage.get("nodes") if isinstance(stage.get("nodes"), list) else [])[:MAX_ROUTE_NODES]
                     if isinstance(raw, dict)]
            stage_title = _clean(stage.get("title"))
            groups = _group_route_nodes(nodes)
            if len(groups) == 1 and groups[0][0] == stage_title:
                # A planned task without a separate knowledge point would repeat
                # the same title twice; keep a single node for it.
                item = _group_node(plan, groups[0], stage_title, node["title"],
                                   stage.get("startDate"), kind="stage", stats=stats)
                node["children"].append(item)
            else:
                for group in groups:
                    if not budget.take():
                        budget.truncated = True
                        break
                    item = _group_node(plan, group, stage_title, node["title"],
                                       stage.get("startDate"), kind="task", stats=stats)
                    stage_node["children"].append(item)
                node["children"].append(stage_node)
        output.append(node)
    return output


def _group_route_nodes(nodes):
    """One planned task split across days keeps one tree node per task title."""
    groups = []
    for raw in nodes:
        title = _clean(raw.get("title")) or "学习任务"
        if groups and groups[-1][0] == title:
            groups[-1][1].append(raw)
        else:
            groups.append([title, [raw]])
    return groups


def _group_node(plan, group, level_title, phase_title, fallback_date, *, kind, stats):
    title, raws = group
    if len(raws) == 1:
        item = _task_node(plan, _route_task(raws[0], level_title, phase_title),
                          raws[0].get("date") or fallback_date, kind=kind, stats=stats)
        _annotate_readiness(item, raws[0])
        return item
    dates = [date for date in (_iso_date(raw.get("date")) for raw in raws) if date]
    minutes = sum(_minutes(raw.get("minutes")) or 0 for raw in raws) or None
    bound = sum(len(raw.get("questions")) for raw in raws if isinstance(raw.get("questions"), list))
    required = sum((_count(raw.get("requiredCount")) or len(raw.get("questions") or [])) for raw in raws)
    merged = {"title": title, "minutes": minutes,
              "completed": all(bool(raw.get("completed")) for raw in raws),
              "difficulty": next((_difficulty_label(raw.get("difficulty")) for raw in raws
                                  if _difficulty_label(raw.get("difficulty"))), ""),
              "boundCount": bound, "requiredCount": required,
              "submittedCount": sum(_count(raw.get("submittedCount")) for raw in raws),
              "phase": phase_title}
    item = _task_node(plan, merged, dates[0] if dates else fallback_date, kind=kind, stats=stats)
    fields = item["fields"]
    binding = (f"关联题目 {fields['submitted']}/{fields['questions']}" if fields["questions"]
               else f"未绑定本地题目（需 {fields['required']} 道）" if fields["required"]
               else "未绑定本地题目")
    span = f"{dates[0]} 至 {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else "")
    item["subtitle"] = _subtitle(span, f"共 {minutes} 分钟（{len(raws)} 次）" if minutes else "",
                                 fields["difficulty"],
                                 "已完成" if merged["completed"] else "未完成", binding)
    readiness = next((raw.get("readiness") for raw in raws
                      if raw.get("readiness") and raw.get("readiness") != "ready"), "")
    if readiness:
        item["subtitle"] = _subtitle(item["subtitle"],
                                     {"materials-needed": "待补充资料题目",
                                      "questions-needed": "题目不足"}.get(readiness, ""))
    return item


def _route_task(raw, stage_title, phase_title):
    questions = raw.get("questions") if isinstance(raw.get("questions"), list) else []
    required = _count(raw.get("requiredCount")) or len(questions)
    return {"title": raw.get("title") or stage_title or "学习任务",
            "minutes": raw.get("minutes"), "completed": raw.get("completed"),
            "difficulty": raw.get("difficulty"), "boundCount": len(questions),
            "requiredCount": required, "submittedCount": _count(raw.get("submittedCount")),
            "phase": phase_title}


def _annotate_readiness(item, raw):
    readiness = raw.get("readiness")
    if readiness and readiness != "ready":
        item["subtitle"] = _subtitle(item["subtitle"],
                                     {"materials-needed": "待补充资料题目",
                                      "questions-needed": "题目不足"}.get(readiness, ""))


def _phases_from_days(plan, budget, stats):
    """Fallback for plans saved before route projection existed (real days/tasks)."""
    days = plan.get("days") if isinstance(plan.get("days"), list) else []
    phases = {}
    order = []
    for day in days:
        if not isinstance(day, dict):
            continue
        for task in (day.get("tasks") if isinstance(day.get("tasks"), list) else [])[:MAX_TASKS_PER_DAY]:
            if not isinstance(task, dict):
                continue
            label = _clean(task.get("phase"), 60) or "学习与巩固"
            if label not in phases:
                phases[label] = []
                order.append(label)
            phases[label].append((task, day.get("date")))
    output = []
    for label in order[:MAX_PHASES]:
        if not budget.take():
            budget.truncated = True
            break
        node = _node(label, kind="phase", detail="按计划任务所属阶段归纳")
        stats["phases"] += 1
        for task, date in phases[label]:
            if not budget.take():
                budget.truncated = True
                break
            node["children"].append(_task_node(plan, task, date, budget=budget, stats=stats))
        output.append(node)
    if len(order) > MAX_PHASES:
        budget.truncated = True
    return output or None


def _framework_nodes(value):
    """Validate a framework artifact / client payload down to label+parentId."""
    nodes = value.get("nodes") if isinstance(value, dict) else None
    if not isinstance(nodes, list) or not nodes:
        return None
    kept, seen = [], set()
    for raw in nodes[:MAX_FRAMEWORK_NODES]:
        if not isinstance(raw, dict):
            continue
        node_id = _clean(raw.get("id"), 64)
        label = _clean(raw.get("label") or raw.get("title"))
        if not node_id or not label or node_id in seen:
            continue
        seen.add(node_id)
        kept.append({"id": node_id, "label": label, "parentId": _clean(raw.get("parentId"), 64) or None,
                     "description": _clean(raw.get("description"), MAX_DETAIL)})
    if not kept:
        return None
    ids = {item["id"] for item in kept}
    for item in kept:
        if item["parentId"] and item["parentId"] not in ids:
            item["parentId"] = None
    title = _clean(value.get("title")) or "关联知识框架"
    return {"title": title, "nodes": kept}


def _framework_branch(plan, framework, budget, stats):
    children_by_parent = {}
    for item in framework["nodes"]:
        children_by_parent.setdefault(item["parentId"], []).append(item)
    if not children_by_parent.get(None):
        # Defensive: a malformed parent chain must still produce one visible root.
        framework["nodes"][0]["parentId"] = None
        children_by_parent = {}
        for item in framework["nodes"]:
            children_by_parent.setdefault(item["parentId"], []).append(item)
    if not budget.take():
        return None
    coverage = plan.get("frameworkCoverage") if isinstance(plan.get("frameworkCoverage"), dict) else None
    detail = ""
    if coverage:
        detail = _subtitle(f"资料关联覆盖 {coverage.get('representedPhases', '?')}/{coverage.get('totalPhases', '?')} 阶段",
                           f"{coverage.get('representedTasks', '?')}/{coverage.get('totalTasks', '?')} 项任务",
                           "部分覆盖" if coverage.get("partial") else "全阶段覆盖")
    branch = _node(framework["title"], kind="framework", detail=detail or "账号内已保存的知识框架")
    stats["frameworks"] = 1

    def attach(parent_node, parent_id, depth):
        if depth > MAX_FRAMEWORK_DEPTH:
            budget.truncated = True
            return
        for item in children_by_parent.get(parent_id, [])[:MAX_FRAMEWORK_NODES]:
            if not budget.take():
                budget.truncated = True
                return
            node = _node(item["label"], kind="topic", detail=item["description"])
            stats["knowledgePoints"] += 1
            parent_node["children"].append(node)
            attach(node, item["id"], depth + 1)

    roots = children_by_parent.get(None, [])
    for root in roots[:MAX_FRAMEWORK_NODES]:
        if not budget.take():
            budget.truncated = True
            break
        node = _node(root["label"], kind="topic", detail=root["description"])
        stats["knowledgePoints"] += 1
        branch["children"].append(node)
        attach(node, root["id"], 1)
    if len(roots) > 1:
        branch["subtitle"] = _subtitle(branch["subtitle"], f"{len(roots)} 个顶层主题")
    return branch


def build_tree(plan, *, source="plan", framework=None):
    """Build the 计划→阶段→任务/知识点 tree from stored (or sanitized) data."""
    plan = plan if isinstance(plan, dict) else {}
    budget = _Budget()
    stats = {"phases": 0, "stages": 0, "tasks": 0, "completed": 0, "questionRefs": 0,
             "unboundTasks": 0, "knowledgePoints": 0, "frameworks": 0}
    title = _clean(plan.get("title")) or "我的学习计划"
    root = _node(title, kind="plan", detail=_clean_multiline(plan.get("goal"), MAX_GOAL))
    root["children"].append(_plan_summary(plan, budget))

    route = plan.get("learningRoute") if isinstance(plan.get("learningRoute"), dict) else None
    phases = _phases_from_route(plan, route, budget, stats) if route else None
    if phases is None:
        phases = _phases_from_days(plan, budget, stats)
    if phases:
        root["children"].extend(phases)
    else:
        fallback = _node("学习路线", kind="phase",
                         detail="该计划还没有可读取的阶段或每日任务数据；请先生成或整理计划路线")
        root["children"].append(fallback)

    branch = _framework_branch(plan, framework, budget, stats) if framework else None
    if branch:
        root["children"].append(branch)

    total = stats["tasks"]
    progress = _subtitle(f"{stats['completed']}/{total} 项任务已完成" if total else "暂无排程任务",
                         f"{stats['questionRefs']} 道本地题目已绑定" if stats["questionRefs"] else "未绑定本地题目")
    root["subtitle"] = _subtitle(progress,
                                 "部分节点因大小限制未导出" if budget.truncated else "")
    tree = {
        "id": "map-" + digest([source, plan.get("id") or title, plan.get("updatedAt") or ""])[:24],
        "kind": "study-plan-mindmap",
        "source": source if source in ("plan", "draft") else "plan",
        "planId": _clean(plan.get("id"), 64) or None,
        "title": title,
        "generatedAt": utc_now(),
        "limits": {"maxNodes": MAX_NODES, "maxTitleChars": MAX_TITLE, "maxDetailChars": MAX_DETAIL,
                   "maxPhases": MAX_PHASES, "maxStages": MAX_STAGES},
        "truncated": bool(budget.truncated) or stats["tasks"] >= MAX_NODES,
        "stats": stats,
        "root": root,
    }
    return tree


# ---------------------------------------------------------------------------
# XMind Zen workbook. The ZIP entry set below is the JSON workbook layout that
# XMind 2020+ reads: content.json (array of sheets), metadata.json, manifest.json
# and an XMind 8 compatibility content.xml stub. Entries are stored (not
# deflated) like XMind's own writer, and JSON is UTF-8 without a BOM.
# ---------------------------------------------------------------------------

def _topic(node, used):
    """Convert one tree node to an XMind topic with a workspace-unique id."""
    topic_id = "t" + digest([node.get("id"), node.get("title")])[:24]
    suffix = 1
    while topic_id in used:
        suffix += 1
        topic_id = "t" + digest([node.get("id"), node.get("title"), suffix])[:24]
    used.add(topic_id)
    topic = {"id": topic_id, "class": "topic", "title": _clean(node.get("title")) or "未命名"}
    detail = node.get("subtitle") or ""
    if detail:
        topic["notes"] = {"plain": {"content": detail + "\n"}}
    if node.get("completed") is True:
        topic["labels"] = ["已完成"]
    children = node.get("children") if isinstance(node.get("children"), list) else []
    converted = [_topic(child, used) for child in children if isinstance(child, dict)]
    if converted:
        topic["children"] = {"attached": converted}
    return topic


def xmind_bytes(tree):
    root = tree.get("root") if isinstance(tree.get("root"), dict) else _node(tree.get("title") or "学习计划")
    used = set()
    root_topic = _topic(root, used)
    root_topic["structureClass"] = "org.xmind.ui.logic.right"
    sheet_id = "sheet-" + digest([tree.get("id"), tree.get("title")])[:24]
    content = [{
        "id": sheet_id,
        "class": "sheet",
        "title": _clean(tree.get("title")) or "学习计划",
        "topicPositioning": "fixed",
        "rootTopic": root_topic,
    }]
    metadata = {
        "creator": {"name": "学涯 Copilot", "version": "1.0"},
        "dataStructureVersion": "2",
        "layoutEngineVersion": "3",
    }
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}, "content.xml": {}}}
    stub = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" '
        'xmlns:fo="http://www.w3.org/1999/XSL/Format" xmlns:svg="http://www.w3.org/2000/svg" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'version="2.0"><sheet id="' + sheet_id + '">'
        '<topic id="legacy-warning" structure-class="org.xmind.ui.logic.right">'
        '<title>This workbook uses the XMind Zen (XMind 2020+) JSON format</title>'
        '<children><topics type="attached"><topic id="legacy-warning-detail">'
        '<title>Open it with XMind 2020 or newer; XMind 8 cannot read content.json. '
        '此文件为 XMind Zen（XMind 2020 及更新版本）格式，请使用 XMind 2020 或更新版本打开。</title>'
        '</topic></topics></children></topic><title>Compatibility</title></sheet></xmap-content>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("content.json", json.dumps(content, ensure_ascii=False))
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        archive.writestr("content.xml", stub.encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# FreeMind fallback.
# ---------------------------------------------------------------------------

def _xml_attr(value):
    text = str(value if value is not None else "")
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def _mm_node(node, used=None):
    used = set() if used is None else used
    base = str(node.get("id") or "node")
    node_id, suffix = base, 1
    while node_id in used:
        suffix += 1
        node_id = f"{base}-{suffix}"
    used.add(node_id)
    lines = [f'<node TEXT="{_xml_attr(_clean(node.get("title")) or "未命名")}" '
             f'ID="{_xml_attr(node_id)}">']
    detail = _clean(node.get("subtitle"), MAX_DETAIL)
    if detail:
        lines.append('<richcontent TYPE="NOTE"><html><body><p>' + _xml_attr(detail) + "</p></body></html></richcontent>")
    for child in node.get("children") or []:
        if isinstance(child, dict):
            lines.append(_mm_node(child, used))
    lines.append("</node>")
    return "".join(lines)


def mm_bytes(tree):
    root = tree.get("root") if isinstance(tree.get("root"), dict) else {"title": tree.get("title")}
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n<map version="1.0.1">\n'
            + _mm_node(root) + "\n</map>\n")
    return body.encode("utf-8")


# ---------------------------------------------------------------------------
# Data loading (read-only) and request handling.
# ---------------------------------------------------------------------------

def _learn_scope(host, account):
    """Read-only scope for the account's learning space.

    StudySpaceService._scope is the same helper the plan endpoints use; the
    service course already exists whenever a plan exists, so a missing plan is
    an empty read rather than a write here.
    """
    service = StudySpaceService(host.p)
    scope = service._scope(account)
    return service, scope


def _read_entity(host, scope, kind, entity_id):
    if not isinstance(entity_id, str) or not re.fullmatch(r"[\w.:-]{1,150}", entity_id):
        return None
    try:
        row = host.p.repo.read(scope, kind, entity_id)
    except AppError as error:
        if error.code == "COURSE_NOT_FOUND":
            return None
        raise
    return row


def _load_plan(host, account, plan_id):
    service, scope = _learn_scope(host, account)
    row = _read_entity(host, scope, "plan", plan_id)
    return (service, row["value"]) if row else None


def _load_framework(host, scope, plan, payload):
    candidate = None
    if isinstance(payload.get("frameworkId"), str):
        candidate = payload.get("frameworkId")
    elif isinstance(payload.get("framework"), str):
        candidate = payload.get("framework")
    elif isinstance(payload.get("framework"), dict):
        # An explicit client body may describe the tree; it is sanitized and
        # bounded exactly like a stored framework before being rendered.
        return _framework_nodes(payload["framework"])
    if not candidate:
        candidate = plan.get("frameworkId")
    if not candidate:
        return None
    row = _read_entity(host, scope, "concept", candidate)
    return _framework_nodes(row["value"]) if row else None


def sanitize_draft(value):
    """Bound a client-posted draft to the fields the tree actually renders."""
    if not isinstance(value, dict):
        raise AppError("INVALID_MAP_REQUEST")
    plan = {key: _clean(value.get(key), limit) for key, limit in (
        ("id", 64), ("title", MAX_TITLE), ("difficulty", 8), ("status", 20),
        ("startDate", 10), ("endDate", 10),
    )}
    plan["goal"] = _clean_multiline(value.get("goal"), MAX_GOAL)
    plan["explanation"] = _clean_multiline(value.get("explanation"), MAX_DETAIL)
    plan["difficulty"] = _difficulty_label(plan["difficulty"])
    plan["startDate"] = _iso_date(plan["startDate"])
    plan["endDate"] = _iso_date(plan["endDate"])
    plan["dailyMinutes"] = _minutes(value.get("dailyMinutes"))
    plan["daysCount"] = value.get("daysCount") if type(value.get("daysCount")) is int and 1 <= value["daysCount"] <= MAX_DAYS else None
    rest = value.get("restDays")
    plan["restDays"] = sorted({day for day in rest if type(day) is int and 1 <= day <= 7}) if isinstance(rest, list) else []
    subjects = value.get("subjects")
    plan["subjects"] = [item for item in (_clean(subject, 40) for subject in subjects[:12]) if item] if isinstance(subjects, list) else []
    days = []
    for day in (value.get("days") if isinstance(value.get("days"), list) else [])[:MAX_DAYS]:
        if not isinstance(day, dict):
            continue
        tasks = []
        for task in (day.get("tasks") if isinstance(day.get("tasks"), list) else [])[:MAX_TASKS_PER_DAY]:
            if not isinstance(task, dict):
                continue
            resource = task.get("resource") if isinstance(task.get("resource"), dict) else {}
            bound = _count(task.get("boundCount"))
            if not bound and resource.get("type") == "question":
                bound = 1
            tasks.append({
                "id": _clean(task.get("id"), 64),
                "title": _clean(task.get("title")),
                "phase": _clean(task.get("phase"), 60),
                "minutes": _minutes(task.get("minutes")),
                "completed": task.get("completed") is True,
                "difficulty": _difficulty_label(task.get("difficulty")),
                "resource": {"type": _clean(resource.get("type"), 20)},
                "boundCount": bound,
                "requiredCount": _count(task.get("requiredCount")) or bound,
                "submittedCount": _count(task.get("submittedCount")),
            })
        days.append({"date": _iso_date(day.get("date")), "isRestDay": day.get("isRestDay") is True,
                     "budgetMinutes": _minutes(day.get("budgetMinutes")), "tasks": tasks})
    plan["days"] = days
    route = value.get("learningRoute")
    if isinstance(route, dict) and isinstance(route.get("phases"), list):
        plan["learningRoute"] = {"phases": [phase for phase in route["phases"][:MAX_PHASES] if isinstance(phase, dict)]}
    if not (plan["title"] or plan["goal"] or plan["days"]):
        raise AppError("INVALID_MAP_REQUEST")
    return plan


def _tree_for_request(host, account, payload):
    plan_id = payload.get("planId")
    if isinstance(plan_id, str) and plan_id.strip():
        loaded = _load_plan(host, account, plan_id.strip())
        require(loaded is not None, "PLAN_NOT_FOUND")
        service, plan = loaded
        framework = _load_framework(host, service._scope(account), plan, payload)
        return build_tree(plan, source="plan", framework=framework)
    draft = payload.get("draft")
    require(draft is not None, "INVALID_MAP_REQUEST")
    plan = sanitize_draft(draft)
    framework = _load_framework(host, _learn_scope(host, account)[1], plan, payload)
    return build_tree(plan, source="draft", framework=framework)


def _download_name(tree, extension):
    base = _clean(tree.get("title"), 60) or "学习计划"
    base = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", base).strip() or "学习计划"
    return f"学涯-{base}.{extension}"


def _attachment(content, media_type, filename, ascii_name):
    headers = {
        "Content-Disposition": "attachment; filename=\"" + ascii_name + "\"; filename*=UTF-8''" + quote(filename, safe=""),
        "Content-Length": str(len(content)),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=content, media_type=media_type, headers=headers)


async def dispatch(rest, request, course, host):
    operation = (rest or "").strip("/")
    if operation not in ("tree", "export", "xmind", "mm"):
        return None
    require(host is not None and getattr(host, "p", None) is not None, "PLATFORM_DISABLED")
    account = _account_key(request, host)
    if operation == "tree":
        payload = {}
        if request.method == "POST":
            from .app import json_body
            payload = await json_body(request, 65536)
        else:
            require(request.method == "GET", "METHOD_NOT_ALLOWED")
            plan_id = request.query_params.get("planId")
            if plan_id:
                payload = {"planId": plan_id}
        tree = _tree_for_request(host, account, payload)
        return {"ok": True, "tree": tree}
    require(request.method == "POST", "METHOD_NOT_ALLOWED")
    from .app import json_body
    payload = await json_body(request, 65536)
    tree = _tree_for_request(host, account, payload)
    if operation == "mm":
        return _attachment(mm_bytes(tree), FreeMindMediaType,
                           _download_name(tree, "mm"), "study-plan.mm")
    return _attachment(xmind_bytes(tree), XMindMediaType,
                       _download_name(tree, "xmind"), "study-plan.xmind")
