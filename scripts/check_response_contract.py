#!/usr/bin/env python3
"""Check whether a Bazi response satisfies the skill's output contract.

This is a lightweight regression helper. It checks for required structural
signals and banned phrases; it does not judge whether the Bazi reasoning is
correct.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


BANNED_PHRASES = (
    "某大师说",
    "命中注定",
    "一定会破产",
    "必死",
    "绝症",
    "袁天罡断你命中注定",
    "李淳风预言",
    "只因五行缺",
    "所以必须补",
)

RELATIVE_TIME_TOKENS = (
    "今年",
    "明年",
    "后年",
    "近两年",
    "现在",
    "当前",
    "接下来",
    "上半年",
    "下半年",
    "这个月",
    "本月",
    "下个月",
)

REPORT_STAGE_TOKENS = (
    "分析报告",
    "画像报告",
    "命主报告",
    "完整报告",
    "完整画像",
    "做一份报告",
)

MONTHLY_STAGE_TOKENS = (
    "本月",
    "这个月",
    "下个月",
    "按月",
    "月度",
    "每月",
)

MONTHLY_ADVICE_TOKENS = (
    "月度建议",
    "按月建议",
    "本月建议",
    "下个月建议",
    "每月提醒",
)

GENDER_TOKENS = ("男", "女", "男性", "女性")

ADVICE_REQUEST_TOKENS = (
    "建议",
    "怎么做",
    "如何应对",
    "应对",
    "破局",
    "该不该",
    "怎么办",
)

ADVICE_SIGNAL_TOKENS = (
    "建议：",
    "建议如下",
    "应对：",
    "策略：",
    "做法：",
    "打法",
    "怎么做",
    "如何应对",
    "你该",
    "最该",
    "优先",
)

SCOPE_KEYWORDS = {
    "career": ("事业", "工作", "职业", "升职", "岗位"),
    "wealth": ("财运", "赚钱", "收入", "投资", "破财"),
    "relationship": ("婚姻", "感情", "夫妻", "正缘", "对象"),
    "health": ("健康", "身体", "睡眠", "焦虑", "体质"),
}

UNMARRIED_HINTS = ("未婚", "单身", "没结婚")
MARRIED_HINTS = ("已婚", "结婚", "老婆", "老公", "夫妻")
SPOUSE_SIDEVIEW_HINTS = ("我老婆", "我老公", "配偶", "妻子", "丈夫")

UNMARRIED_BANNED = ("已婚来看", "夫妻关系", "婚姻还能不能继续")
MARRIED_BANNED = ("正缘", "对象类型", "长相", "恋爱窗口")

ABSOLUTE_YEAR_RE = re.compile(r"(19|20)\d{2}年")
ABSOLUTE_RANGE_RE = re.compile(r"(19|20)\d{2}\s*[-~到至]\s*(19|20)\d{2}年?")
PILLAR_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
CONFIDENCE_A_RE = re.compile(r"置信度[^。\n]*A|A级置信度")


COMMON_REQUIRED = {
    "general": (
        ("direct_judgement", ("铁口", "判断", "结论", "断语")),
        ("evidence", ("依据", "命局", "月令", "日主", "十神", "格局")),
        ("method", ("名家方法", "按", "徐子平", "沈孝瞻", "张楠", "任铁樵", "韦千里", "袁树珊", "徐乐吾")),
        ("real_world", ("现实", "落点", "表现", "职业", "关系", "资产", "现金流")),
        ("calibration", ("置信度", "校准", "待确认", "反馈")),
    ),
    "wealth": (
        ("income_model", ("收入能力", "收入结构", "经营模式")),
        ("liquidity", ("现金流", "流动性", "周转")),
        ("asset_actions", ("资产动作", "项目投入", "负债", "配置")),
        ("felt_security", ("财富安全感", "安全感", "体感")),
        ("wealth_methods", ("李虚中", "徐子平", "张楠", "韦千里")),
    ),
    "classical": (
        ("classical_boundary", ("四柱", "命局", "依据", "证据")),
        ("role_boundary", ("李淳风", "袁天罡", "古法", "口吻", "象法")),
        ("legend_boundary", ("传说", "预言", "不作", "不当作", "边界")),
    ),
    "dayun": (
        ("dayun", ("大运", "流年")),
        ("trigger", ("触发", "冲", "合", "刑", "害", "伏吟", "反吟")),
        ("confidence", ("置信度", "A", "B", "C")),
    ),
    "health": (
        ("constitution", ("体质", "寒暖", "燥湿", "五行")),
        ("medical_boundary", ("医学", "检查", "诊断", "医生")),
    ),
    "report": (
        ("report_core", ("核心画像", "人物画像", "性格画像")),
        ("report_breakdown", ("分项画像", "事业画像", "财富画像", "婚恋画像")),
        ("report_stage", ("当前阶段", "所处阶段")),
        ("report_calibration", ("校准问题", "校准点", "待确认")),
    ),
    "monthly": (
        ("monthly_conclusion", ("本月结论", "结论")),
        ("monthly_trigger", ("触发机制", "触发")),
        ("monthly_real_world", ("现实表现", "现实落点", "现实表现")),
        ("monthly_risk", ("风险点", "本月风险")),
    ),
}


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def check_required(text: str, mode: str) -> list[str]:
    missing: list[str] = []
    required = list(COMMON_REQUIRED["general"])
    if mode != "general":
        required.extend(COMMON_REQUIRED[mode])

    for key, words in required:
        if not contains_any(text, words):
            missing.append(f"{key}: expected one of {', '.join(words)}")
    return missing


def check_banned(text: str) -> list[str]:
    return [phrase for phrase in BANNED_PHRASES if phrase in text]


def infer_relation_context(question: str) -> str:
    if contains_any(question, SPOUSE_SIDEVIEW_HINTS):
        return "spouse_sideview"
    if contains_any(question, MARRIED_HINTS):
        return "married"
    if contains_any(question, UNMARRIED_HINTS):
        return "unmarried"
    return "general"


def infer_question_flags(question: str) -> dict[str, bool | str]:
    return {
        "has_relative_time": contains_any(question, RELATIVE_TIME_TOKENS),
        "asks_advice": contains_any(question, ADVICE_REQUEST_TOKENS),
        "relation_context": infer_relation_context(question),
    }


def infer_experience_stage(question: str) -> str:
    if contains_any(question, MONTHLY_STAGE_TOKENS):
        return "monthly"
    if contains_any(question, REPORT_STAGE_TOKENS):
        return "report"
    if contains_any(question, GENDER_TOKENS) and len(PILLAR_RE.findall(question)) >= 3:
        return "report"
    return "general"


def check_relative_time_anchor(question: str, response: str) -> list[str]:
    if not contains_any(question, RELATIVE_TIME_TOKENS):
        return []

    first_line = first_nonempty_line(response)
    if ABSOLUTE_YEAR_RE.search(first_line) or ABSOLUTE_RANGE_RE.search(first_line):
        return []
    return [
        "relative_date_resolved: question uses relative time, but the first non-empty response line does not anchor to an absolute year/range"
    ]


def check_advice_layering(question: str, response: str) -> list[str]:
    if contains_any(question, ADVICE_REQUEST_TOKENS):
        return []

    hits = [token for token in ADVICE_SIGNAL_TOKENS if token in response]
    if not hits:
        return []
    return [f"advice_only_when_requested: response contains advice/strategy signals without the user explicitly asking for advice ({', '.join(hits)})"]


def infer_domain_scope(text: str) -> set[str]:
    scopes: set[str] = set()
    for name, keywords in SCOPE_KEYWORDS.items():
        if contains_any(text, keywords):
            scopes.add(name)
    return scopes


def check_scope_only(question: str, response: str) -> list[str]:
    question_scopes = infer_domain_scope(question)
    if len(question_scopes) != 1:
        return []

    response_scopes = infer_domain_scope(response)
    extra_scopes = sorted(scope for scope in response_scopes if scope not in question_scopes)
    if len(extra_scopes) >= 2:
        return [
            f"asked_scope_only: question scope is {', '.join(sorted(question_scopes))}, but response expands into multiple additional scopes ({', '.join(extra_scopes)})"
        ]
    return []


def check_relation_context(relation_context: str, response: str) -> list[str]:
    issues: list[str] = []

    if relation_context == "unmarried":
        hits = [token for token in UNMARRIED_BANNED if token in response]
        if hits:
            issues.append(
                f"married_mode_consistent: unmarried question contains married-only phrasing ({', '.join(hits)})"
            )

    if relation_context == "married":
        hits = [token for token in MARRIED_BANNED if token in response]
        if hits:
            issues.append(
                f"married_mode_consistent: married question contains unmarried/zhengyuan phrasing ({', '.join(hits)})"
            )

    if relation_context == "spouse_sideview":
        if "侧看" not in response and "命主盘" not in response:
            issues.append(
                "married_mode_consistent: spouse side-view response should explicitly state this is a side-view inference from the chart owner"
            )
        if "校准" not in response and "出生" not in response:
            issues.append(
                "sideview_confidence_lowered: spouse side-view response should offer calibration via the spouse's birth information"
            )
        if CONFIDENCE_A_RE.search(response):
            issues.append(
                "sideview_confidence_lowered: spouse side-view responses should not use A-level confidence"
            )

    return issues


def check_report_stage(response: str) -> list[str]:
    issues: list[str] = []
    if "核心画像" not in response and "人物画像" not in response and "性格画像" not in response:
        issues.append("report_mode_consistent: report responses should explicitly contain a core portrait section")
    if "分项画像" not in response and "事业画像" not in response and "财富画像" not in response and "婚恋画像" not in response:
        issues.append("report_mode_consistent: report responses should contain a breakdown portrait section")
    if "当前阶段" not in response and "所处阶段" not in response:
        issues.append("report_mode_consistent: report responses should position the chart owner's current stage")
    return issues


def check_monthly_stage(question: str, response: str) -> list[str]:
    issues: list[str] = []
    first_line = first_nonempty_line(response)
    if not ABSOLUTE_YEAR_RE.search(first_line) or ("月" not in first_line and "节气" not in first_line):
        issues.append("monthly_anchor_resolved: monthly responses should anchor the first line to an absolute year/month or solar-month range")

    if contains_any(question, MONTHLY_ADVICE_TOKENS):
        advice_hits = [token for token in ADVICE_SIGNAL_TOKENS if token in response]
        if not advice_hits and "建议" not in response:
            issues.append("monthly_advice_present: monthly advice questions should produce explicit monthly advice")
    return issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Response text/markdown file to check.")
    parser.add_argument(
        "--mode",
        choices=sorted(COMMON_REQUIRED.keys()),
        default="general",
        help="Contract mode to check.",
    )
    parser.add_argument(
        "--question",
        help="Optional user question/prompt used to validate relative-time anchoring, judgement-vs-advice layering, and relation context.",
    )
    parser.add_argument(
        "--relation-context",
        choices=("auto", "general", "unmarried", "married", "spouse_sideview"),
        default="auto",
        help="Override relation context checks. Default auto-infers from --question when provided.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    text = Path(args.path).read_text(encoding="utf-8")
    missing = check_required(text, args.mode)
    banned = check_banned(text)
    extra_issues: list[str] = []

    if args.question:
        flags = infer_question_flags(args.question)
        experience_stage = infer_experience_stage(args.question)
        extra_issues.extend(check_relative_time_anchor(args.question, text))
        extra_issues.extend(check_advice_layering(args.question, text))
        extra_issues.extend(check_scope_only(args.question, text))
        relation_context = args.relation_context
        if relation_context == "auto":
            relation_context = str(flags["relation_context"])
        if relation_context != "general":
            extra_issues.extend(check_relation_context(relation_context, text))
        if args.mode == "report" or experience_stage == "report":
            extra_issues.extend(check_report_stage(text))
        if args.mode == "monthly" or experience_stage == "monthly":
            extra_issues.extend(check_monthly_stage(args.question, text))
    elif args.relation_context != "auto":
        extra_issues.extend(check_relation_context(args.relation_context, text))
    elif args.mode == "report":
        extra_issues.extend(check_report_stage(text))
    elif args.mode == "monthly":
        extra_issues.extend(check_monthly_stage("", text))

    if not missing and not banned and not extra_issues:
        print(f"PASS: {args.path} satisfies {args.mode} contract.")
        return 0

    if missing:
        print("Missing required signals:")
        for item in missing:
            print(f"- {item}")
    if banned:
        print("Banned phrases found:")
        for phrase in banned:
            print(f"- {phrase}")
    if extra_issues:
        print("Additional contract issues:")
        for item in extra_issues:
            print(f"- {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
