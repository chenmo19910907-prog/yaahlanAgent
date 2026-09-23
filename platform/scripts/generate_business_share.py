#!/usr/bin/env python3
"""从 content.json 或钉钉文档缓存生成业务分享标准文档 HTML。"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_PATH = REPO_ROOT / "platform" / "exports" / "business-share" / "content.json"
OUTPUT_DIR = REPO_ROOT / "platform" / "exports" / "business-share"
STANDARD_HTML = OUTPUT_DIR / "index.html"
SHOWCASE_UI_CSS = REPO_ROOT / "platform" / "family_pk_report" / "assets" / "showcase.ui.css"
SHOWCASE_EXTRA_CSS = REPO_ROOT / "platform" / "family_pk_report" / "assets" / "showcase.extra.css"
BUSINESS_SHARE_OVERRIDES_CSS = OUTPUT_DIR / "business-share.overrides.css"

DEFAULT_DINGTALK_CACHE = (
    Path.home() / "Documents/cursor-mcp/dingDoc/智能工具平台搭建与测试应用的探索过程"
)
DINGTALK_CONTENT_FILE = "KGZLxjv9VG349wRwhZ4qkvrkV6EDybno_content.json"
DINGTALK_SOURCE_HTML = "KGZLxjv9VG349wRwhZ4qkvrkV6EDybno.html"
SOURCE_DOC_URL = (
    "https://alidocs.dingtalk.com/i/nodes/KGZLxjv9VG349wRwhZ4qkvrkV6EDybno"
)
IMAGE_URL_PREFIX = "/business-share/images"
DEFAULT_AGENT_URL = "http://172.18.124.255:18766"
WORKFLOW_REFERENCE_URL = f"{DEFAULT_AGENT_URL}/family-pk-showcase/"
DEFAULT_TAB_ID = "overview"
OVERVIEW_TAB = {
    "id": "overview",
    "index": "概",
    "title": "概况",
    "intro": (
        "我们使用 Cursor 已有的能力，以相对简单高效的方式搭建了智能工具平台，"
        "但智能工具的方案并不是最初就规划好的，而是在日常工作解决问题的过程中"
        "逐步迭代探索出来的。\n\n"
        "作为从事产品业务方向的测试，本次分享零门槛智能工具平台搭建与测试应用的探索过程，"
        "主要是一起进行思路上的交流。"
    ),
}
CONCLUSION_TAB = {
    "id": "conclusion",
    "index": "结",
    "title": "结语",
    "intro": (
        "智能工具平台不是一次性项目，而是在真实测试与研发工作中"
        "不断生长、人人可维护的一套能力体系。"
    ),
}
DEFAULT_PLATFORM_METRICS = {
    "cards": [
        {"label": "工具台登记的能力数量", "value": "333"},
        {"label": "平台处理过的请求总量", "value": "2,546"},
        {"label": "知识库规模", "value": "6,017"},
        {"label": "工作流数量", "value": "25"},
    ],
    "summary": [
        {"title": "能力沉淀", "text": "知识库、MOA、工作流。"},
        {"title": "对话交付", "text": "钉钉、Web Agent。"},
        {"title": "全员共建", "text": "人人可用、人人可维护。"},
        {"title": "安全可控", "text": "鉴权、审计、隔离。"},
    ],
}
SKIP_CHAPTER_IDS = {"intro"}
SKIP_CHAPTER_TITLES = {"个人介绍"}
# 以下章节保留钉钉原文，不走 TEXT_POLISH 改写
SKIP_POLISH_CHAPTER_IDS = {"security"}
CHAPTER_SKIP_PARAGRAPHS: dict[str, set[str]] = {
    "tunnel": {
        "抓包、Mock 协助测试，生成式 MOA 能力再翻倍。",
    },
}
LINK_OVERRIDES: dict[str, str] = {
    "http://172.18.124.255:18766/keynote#20": "http://172.18.124.255:18766/keynote#1",
}

# 钉钉原文未收录、但分享页需展示的补充条目：(小节标题, [(序号, 正文), ...])
EXTRA_STEPS: dict[str, list[tuple[str, str]]] = {
    "二、功能介绍": [
        (
            "10",
            "虽然 Web Agent 有着诸多优势，但是业务逻辑更重，相同问题的处理时间会比钉钉机器人慢 "
            "15 秒左右，所以简单的 MOA 数值操作更推荐使用机器人进行请求。",
        ),
    ],
    "三、外部agent拓展能力": [
        (
            "5",
            "当前 MOA 无法满足操作需求时，自动通过服务端 Agent 查实现方法、验证并登记——"
            "新能力落库即全员可用，能力可无限生长",
        ),
    ],
}

HERO_CONSOLE_HTML = """
      <div class="hero-console" aria-hidden="true">
        <span class="signal-line one"></span><span class="signal-line two"></span>
        <div class="signal-card signal-a">
          <svg class="signal-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19h16M6 17V7m6 10V5m6 12V9"/></svg>
          <strong>知识库演化</strong><small>KNOWLEDGE BASE</small>
          <span class="signal-dots"><i></i><i></i><i></i><i></i><i></i></span>
        </div>
        <div class="signal-card signal-b">
          <svg class="signal-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="9" y="14" width="6" height="6" rx="1"/><path d="M7 10v2h10v-2M12 12v2"/></svg>
          <strong>MOA · Tunnel</strong><small>TOOL CAPABILITIES</small>
          <span class="signal-dots"><i></i><i></i><i></i><i></i><i></i></span>
        </div>
        <div class="signal-card signal-c">
          <svg class="signal-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 20h8M12 18v2"/></svg>
          <strong>Web Agent</strong><small>PLATFORM DELIVERY</small>
          <span class="signal-dots"><i></i><i></i><i></i><i></i><i></i></span>
        </div>
      </div>"""

CHAPTER_PHASE_CLASS: dict[str, dict[str, str]] = {
    "evolution": {
        "一、": "phase-kb",
        "二、": "phase-record",
        "三、": "phase-capability",
        "四、": "phase-auth",
    },
    "tunnel": {
        "一、": "phase-capture",
        "二、": "phase-mock",
        "三、": "phase-gen-moa",
        "四、": "phase-workflow",
    },
    "dingtalk-bot": {
        "一、": "phase-flow",
        "二、": "phase-benefit",
    },
    "platform": {
        "一、": "phase-layout",
        "二、": "phase-features",
        "三、": "phase-external",
    },
    "security": {
        "一、": "phase-entry",
        "二、": "phase-audit",
        "三、": "phase-admin",
    },
}

CHAPTER_CALLOUT_PREFIX: dict[str, set[str]] = {
    "evolution": {"四、"},
    "tunnel": {"四、"},
    "platform": {"三、"},
}

CHAPTER_ROADMAPS: dict[str, str] = {}

TEXT_POLISH: dict[str, str] = {
    "一开始我们尝试用Cursor编写测试用例，需要录入项目相关的知识库": (
        "起初尝试用 Cursor 生成测试用例，前提是先把项目相关知识录入知识库。"
    ),
    "进行手动操作录入知识库": "手动整理并录入知识库",
    "读取需求文档生成知识库，由历史测试用例直接生成知识库": (
        "从需求文档或历史用例自动生成知识库"
    ),
    "最终自动读取需求和用例目录，做到知识库的持续更新": (
        "自动同步需求与用例目录，知识库持续更新"
    ),
    "万物皆可知识库多多益善，历史bug、团队测试机信息、常用手机号管理、测试账号池子等": (
        "万物皆可入库：历史 Bug、测试机信息、常用手机号、测试账号池等"
    ),
    "如果文档可以录入知识库，那MOA能力是否也能录入知识库": (
        "MOA 列表每个人只能独立维护，新增 MOA 无法触达全员。"
        "文档能入库，MOA 能力是否也能以同样方式沉淀？"
    ),
    "粘贴完整的MOA请求并描述其功能供Cursor学习，效果超出预期": (
        "粘贴完整 MOA 请求并描述功能，供 Cursor 学习——效果超出预期"
    ),
    "既然Cursor已经学习了MOA请求方式，那后续直接截图能否也实现MOA的录制": (
        "Cursor 学会 MOA 请求后，能否通过截图完成 MOA 录制？"
    ),
    "如果MOA可以录制，管理后台的功能应该也可以录制，可实现能力逐渐增多": (
        "MOA 能录，Admin 后台功能也应能录——能力面逐步扩大"
    ),
    "万物皆可录制，所有常用MOA、风控解除、常用后台功能、Tunnel抓包、盘古配置等": (
        "万物皆可录制：常用 MOA、风控解除、后台操作、Tunnel 抓包、盘古配置等"
    ),
    "使用自然语言完成造数操作，结合知识库自动分析需要的数值计算": (
        "自然语言完成造数，结合知识库自动推算所需数值"
    ),
    "多MOA协同操作，批量造数，一次完成需要人工多步才能完成的操作": (
        "多 MOA 协同、批量造数，一次完成原先需人工多步的操作"
    ),
    "根据诉求，自动分析前置条件进行账号准备工作": (
        "按诉求自动分析前置条件，完成账号准备"
    ),
    "任何人都是工具平台的使用人，任何人也都是工具平台的维护者": (
        "人人可用、人人可维护——使用与沉淀在同一套流程里"
    ),
    "Q：功能使用依赖录制账号的cookie和token，如果避免鉴权过期中断操作？": (
        "Q：功能使用依赖录制账号的cookie和token，如何避免鉴权过期中断操作？"
    ),
    "我们增加了Aegis SSO 重新登录能力，使用工具时检测到鉴权失败，会使用配置的账号密码重新登录更新凭证，用新凭证自动重试原请求。": (
        "接入 Aegis SSO 自动续期：鉴权失败时用配置账号重新登录、更新凭证，并自动重试原请求。"
    ),
    "历史Tunnel记录直接查找，先操作后提取，准确又高效": (
        "历史 Tunnel 记录直接查找——先操作、后提取，准确高效"
    ),
    "复制Tunnel实时请求和历史请求方式给Cursor进行学习": (
        "将 Tunnel 实时/历史请求交给 Cursor 学习"
    ),
    "实现操作后提取Tunnel请求的操作": "实现「操作后自动提取 Tunnel 请求」",
    "如果只是对UI进行测试，需要造数1000条，使用MOA的操作效率大打折扣。将Tunnel的mock请求方法和描述交给Cursor，经过多次mock操作的学习后实现智能mock工具": (
        "纯 UI 测试需造数上千条时，MOA 效率不足。"
        "将 Tunnel Mock 方法与描述交给 Cursor，经多次学习后沉淀为智能 Mock 工具"
    ),
    "已有的MOA能力有限，如何把任意功能都用MOA操作": (
        "已有 MOA 能力有限——如何把任意后台功能都变成 MOA 操作？"
    ),
    "使用Tunnel已有的MOA能力，经过多次录制学习，实现把用户操作变成MOA入库": (
        "借助 Tunnel 已有 MOA，经多次录制学习，将用户操作自动入库"
    ),
    "学习完成后任意操作即可生成相关MOA": "学习完成后，任意操作即可生成对应 MOA",
    "使用生成式MOA还可以实现多设备联动操作，两用户发起接受CP关系，两房间匹配跨房PK等": (
        "生成式 MOA 还支持多设备联动：双用户组 CP、双房间跨房 PK 等"
    ),
    "通过以上方式，目前我们的智能工具已经支持了300多个操作，所有操作还可以进行组合搭配完成更加复杂的工作流": (
        "目前智能工具已支持 300+ 操作，可组合编排更复杂的工作流"
    ),
    "CP宝箱活动，CP之间赠送指定礼物增加亲密值，达标亲密值解锁宝箱，开启宝箱获得不同奖励": (
        "以 CP 宝箱活动为例：送礼增亲密值 → 达标解锁宝箱 → 领取奖励"
    ),
    "从MSE读取盘古配置，获取CP宝箱的礼物支持、达标数值、奖励配置等所有信息": (
        "从 MSE 读取盘古配置，获取礼物、达标数值、奖励等全量信息"
    ),
    "通过生成式MOA，指定用户组成CP，并获取活动页面的数据返回验证CP亲密值和达标进程": (
        "生成式 MOA 组 CP，拉取活动页数据验证亲密值与达标进度"
    ),
    "送礼前对两个账号的钻石余额/明细、背包礼物（数量/钻价/有效期）、个人装扮（类型/名称/数量/有效期）、CP 勋章、用户铭牌进行记录，以上能力也是通过生成式MOA实现": (
        "送礼前快照双方资产（钻石、背包、装扮、CP 勋章、铭牌等）——均由生成式 MOA 实现"
    ),
    "CP双方送礼增加亲密值升级宝箱等级，领取宝箱奖励": (
        "CP 双方送礼升级宝箱，领取奖励"
    ),
    "验证领取奖励后账号资产变更，确认达标数值和奖励下发与盘古配置一致，符合产品需求": (
        "验证领奖后资产变更，确认达标数值与奖励下发与盘古配置一致"
    ),
    "目前在活动测试中搭建并应用的工作流还有，家族PK测试、周年砸金蛋、PK提款机、家族基金造数等。": (
        "已落地的工作流还包括：家族 PK、周年砸金蛋、PK 提款机、家族基金造数等"
    ),
    "智能工具平台搭建完成后面临一个问题，如何保证每个人都可以安全快捷的使用起来，于是又提出了如下方案": (
        "平台搭建完成后，如何让每个人都能安全、快捷地使用？钉钉机器人成为自然选择"
    ),
    "创建钉钉机器人Stream模式": "创建钉钉机器人（Stream 模式）",
    "通过Python + dingtalk_stream将Cursor接入钉钉": (
        "Python + dingtalk_stream 将 Cursor 接入钉钉"
    ),
    "流程是@机器人-gateway排队-Cursor_runner调Cursor SDK-结果回钉钉": (
        "流程：@机器人 → Gateway 排队 → Cursor Runner 调 SDK → 结果回钉钉"
    ),
    "调整机器人回复等待状态卡片和回复结果卡片样式，增加中断操作": (
        "优化等待/结果卡片样式，支持中断操作"
    ),
    "批量操作展示进度，预估执行时间": "批量操作展示进度与预估耗时",
    "不同用户上下文隔离，相同用户按队列顺序执行": (
        "用户上下文隔离，同用户请求按队列顺序执行"
    ),
    "零门槛入口，群里@机器人或和机器人私聊即用，无需装 Cursor": (
        "零门槛：群里 @ 或私聊即用，无需安装 Cursor"
    ),
    "执行结果有钉钉提醒，无需原地发呆": "执行结果钉钉推送，无需原地等待",
    "移动随时问，手机钉钉发指令，想到即刻执行": (
        "移动随时问：手机钉钉发指令，想到即执行"
    ),
    "附件直传，截图、Excel、链接随问随带": "附件直传：截图、Excel、链接随问随带",
    "权限可控，没有添加权限的用户使用机器人会被拦截": (
        "权限可控：未授权用户将被拦截"
    ),
    "提问信息和用户钉钉账号做绑定，操作可以归属到人": (
        "提问与钉钉账号绑定，操作可归属到人"
    ),
    "钉钉机器人可以作为网页版agent登录验证和用户身份获取": (
        "钉钉机器人兼作 Web Agent 登录验证与身份来源"
    ),
    "随着使用增加，机器人已经不足以承载复杂操作，我们需要更多的功能和更多的拓展性，智能工具平台agent成为必然趋势": (
        "随使用加深，机器人已不足以承载复杂操作——Web Agent 成为必然"
    ),
    "新对话布局": "新对话布局（默认态）",
    "展开布局": "展开布局（侧边栏 + 对话区）",
    "折叠布局": "折叠布局（聚焦对话）",
    "使用验证码方式接入钉钉，保证用户真实，操作可审计，敏感行为可溯源": (
        "钉钉验证码登录：用户真实、操作可审计、敏感行为可溯源"
    ),
    "工具台能力展示，不熟悉的操作可以一键执行": (
        "工具台展示全部能力，不熟悉的一键执行"
    ),
    "钉钉对话可以在网页同步，带【钉钉】标识，按发起人进行归档": (
        "钉钉对话网页同步，带【钉钉】标识，按发起人归档"
    ),
    "支持附件传输和下载，中断任务可以自动回填": (
        "支持附件传输/下载，中断任务自动回填"
    ),
    "会话归属创建者，他人默认可读，并且支持邀请同事共创会话": (
        "会话归属创建者，默认可读，支持邀请同事共创"
    ),
    "执行结果可以选择发送到钉钉，提问后不比原地等待，钉钉自会提示，也可以将执行结果直接通过钉钉转发给他人或群聊。": (
        "执行结果可以选择发送到钉钉，提问后不必原地等待，钉钉自会提示，也可以将执行结果直接通过钉钉转发给他人或群聊。"
    ),
    "执行结果可以选择发送到钉钉，也可以将执行结果直接通过钉钉转发给他人或群聊": (
        "执行结果可发钉钉，也可一键转发给他人或群聊"
    ),
    "常用会话置顶，特殊会话修改标题，历史会话全局搜索，长对话分页拉取": (
        "会话置顶、改标题、全局搜索、长对话分页"
    ),
    "回复详略自由调整，简洁回复、标准回复、详细回复": (
        "回复详略可调：简洁 / 标准 / 详细"
    ),
    "常用工具直达，token用量统计等关于Yaahlan智能工具agent的详细介绍见文档：http://172.18.124.255:18766/keynote#1。": (
        "常用工具直达，token用量统计等，更多关于yaahlan智能工具agent的详细介绍见文档 "
        "http://172.18.124.255:18766/keynote#1"
    ),
    "常用工具直达，token用量统计等，更多关于Yaahlan智能工具agent的详细介绍见文档：http://172.18.124.255:18766/keynote#1。": (
        "常用工具直达，token用量统计等，更多关于yaahlan智能工具agent的详细介绍见文档 "
        "http://172.18.124.255:18766/keynote#1"
    ),
    "支持接入服务端已有agent，相同的功能不再重复部署，有效避免资源浪费": (
        "接入服务端已有 Agent，避免重复部署与资源浪费"
    ),
    "通过勾选可以自由决定是否启用外部agent": "勾选即可自由启用/关闭外部 Agent",
    "调用外部agent具有强提示，执行结果保留外部agent问答记录": (
        "调用外部 Agent 强提示，保留完整问答记录"
    ),
    "使用服务端agent查代码接口，可以直接登记MOA": (
        "服务端 Agent 查代码接口，可直接登记 MOA"
    ),
    "使用钉钉机器人需先被邀请加入群聊，且后台可以配置钉钉机器人的使用权限": (
        "钉钉机器人须先入群，后台可配置使用权限"
    ),
    "网页版agent必须登录后才能使用，登录agent必须先获得机器人使用权限": (
        "Web Agent 须登录使用，登录前提为机器人使用权限"
    ),
    "网关日志脱敏 token/cookie/密码，重要信息不回泄露": (
        "网关日志脱敏 token/cookie/密码，敏感信息不外泄"
    ),
    "工具平台所有操作根据用户隔离，会话记录都有保存数据全员可见，可以随时对操作人进行溯源": (
        "操作按用户隔离，会话全员可见、可随时溯源操作人"
    ),
    "所有工具的使用都要通过Aegis配置的账号，账号在MSE及开发者后台的权限做限制，会对平台的所有操作生效": (
        "全部工具经 Aegis 配置账号执行，MSE/开发者后台权限限制对所有操作生效"
    ),
    "智能工具平台增加管理员系统，三种权限可调，没有权限的用户无法进行敏感操作": (
        "管理员系统三种权限可调，无权限用户无法执行敏感操作"
    ),
    "有权限的用户进行线上环境查询操作时，只有入库的能力可以被使用，其他能力无权操作": (
        "线上环境查询仅开放已入库能力，其余能力无权操作"
    ),
}

OVERVIEW_QA_INTRO = (
    "接下来将用Q&A的方式，在抛出问题和解决问题的过程中介绍智能工具平台的搭建过程。"
)
EVOLUTION_SHARE_TOPIC_INTRO = (
    "从知识库沉淀、MOA 能力录制到自然语言造数——智能工具的四段演进路径。"
)
# 仅用于「分享内容概览」列表，不写入各 tab 页 section-intro
SHARE_TOPIC_OVERVIEW_INTROS: dict[str, str] = {
    "dingtalk-bot": (
        "钉钉 Stream 机器人接入 Cursor SDK——团队零门槛在群里调用，移动随时问、权限可管控。"
    ),
    "platform": (
        "Web Agent 承载复杂操作与能力目录——统一交互、工具台一键直达、可接外部 Agent。"
    ),
    "security": (
        "入口鉴权、操作审计与用户隔离——敏感行为可溯源、线上能力分级管控。"
    ),
}

CHAPTER_META: dict[str, dict[str, str]] = {
    "智能工具演化": {
        "id": "evolution",
        "index": "一",
        "title": "智能工具演化",
        "intro": EVOLUTION_SHARE_TOPIC_INTRO,
    },
    "Tunnel能力应用": {
        "id": "tunnel",
        "index": "二",
        "title": "Tunnel 能力应用",
        "intro": "抓包、Mock 协助测试，生成式 MOA 能力再翻倍。",
    },
    "智能工具机器人": {
        "id": "dingtalk-bot",
        "index": "三",
        "title": "智能工具机器人",
        "intro": "",
    },
    "智能工具平台Agent": {
        "id": "platform",
        "index": "四",
        "title": "智能工具平台 Agent",
        "intro": "",
    },
    "安全性": {
        "id": "security",
        "index": "五",
        "title": "安全性",
        "intro": "",
    },
}

def _shared_css() -> str:
    parts: list[str] = []
    for path in (SHOWCASE_UI_CSS, SHOWCASE_EXTRA_CSS, BUSINESS_SHARE_OVERRIDES_CSS):
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    if not parts:
        raise SystemExit(f"缺少 showcase 样式：{SHOWCASE_UI_CSS}")
    return "\n".join(parts)


SUBSECTION_RE = re.compile(r"^[一二三四五六七八九十]+、")
STEP_RE = re.compile(r"^(\d+)[、.]")
QA_Q_RE = re.compile(r"^Q[：:]\s*")
QA_A_RE = re.compile(r"^A[：:]\s*")
TRAILING_URL_RE = re.compile(r"\s*https?://\S+\s*$")
TRAILING_EMPTY_PAREN_RE = re.compile(r"[（(]\s*[）)]?\s*$")
INLINE_URL_RE = re.compile(r"https?://[^\s<>\"']+")
DOC_LINK_HINTS = (
    "关于用 Cursor 搭建智能工具平台有更详细的文档",
    "关于工作流的搭建和使用有更详细的文档",
)


def _load_content() -> dict:
    data = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("content.json must be an object")
    return data


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def collect_text(nodes: list) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, list):
            parts.append(collect_text(node[2:] if len(node) > 2 else node[1:]))
    return "".join(parts)


def walk(node: object, out: list[dict[str, str]]) -> None:
    if isinstance(node, list) and node:
        tag = node[0]
        attrs = node[1] if len(node) > 1 and isinstance(node[1], dict) else {}
        children = node[2:] if len(node) > 2 else []
        if tag in ("h1", "h2", "h3", "h4", "h5", "p"):
            text = collect_text(children).strip()
            if text:
                out.append({"kind": "text", "tag": tag, "text": text})
            for child in children:
                walk(child, out)
        elif tag == "img":
            out.append(
                {
                    "kind": "img",
                    "src": str(attrs.get("src") or ""),
                    "name": str(attrs.get("name") or "image.png"),
                }
            )
        else:
            for child in children:
                walk(child, out)
    elif isinstance(node, list):
        for child in node:
            walk(child, out)


def load_dingtalk_items(cache_dir: Path) -> list[dict[str, str]]:
    content_path = cache_dir / DINGTALK_CONTENT_FILE
    if not content_path.is_file():
        raise SystemExit(f"缺少缓存：{content_path}\n请先 parse_document 或提供 --from-dingtalk 目录")
    data = json.loads(content_path.read_text(encoding="utf-8"))
    body = data["parts"]["00000000-0000-0000-0000-000000000001"]["data"]["body"]
    items: list[dict[str, str]] = []
    for node in body[2:]:
        walk(node, items)
    return items


def load_local_images(cache_dir: Path) -> list[str]:
    html_path = cache_dir / DINGTALK_SOURCE_HTML
    if not html_path.is_file():
        return []
    text = html_path.read_text(encoding="utf-8")
    return re.findall(r'src="(images/[^"]+)"', text)


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").strip()
    if not text:
        return ""
    text = text.replace("cursor", "Cursor").replace("yaahlan", "Yaahlan")
    text = text.replace("tunnel", "Tunnel").replace("moa", "MOA")
    return text


def _polish_text(text: str, *, chapter_id: str = "") -> str:
    normalized = _normalize_text(text)
    if chapter_id in SKIP_POLISH_CHAPTER_IDS:
        return normalized
    return TEXT_POLISH.get(normalized, normalized)


def _is_subsection_title(text: str) -> bool:
    return bool(SUBSECTION_RE.match(text))


def _subsection_prefix(text: str) -> str:
    match = SUBSECTION_RE.match(text)
    return match.group(0) if match else ""


def _display_subsection_title(text: str) -> str:
    """去掉「一、」等前缀，编号由 CSS ::before 图标展示。"""
    return SUBSECTION_RE.sub("", text, count=1)


def _block_class_for(chapter_id: str, subsection_title: str) -> str:
    prefix = _subsection_prefix(subsection_title)
    phase_map = CHAPTER_PHASE_CLASS.get(chapter_id, {})
    phase = phase_map.get(prefix, "")
    block_class = "demo-block"
    if phase:
        block_class = f"demo-block {phase}"
    callout_prefixes = CHAPTER_CALLOUT_PREFIX.get(chapter_id, set())
    if prefix in callout_prefixes:
        block_class += " callout"
    return block_class


def _open_demo_block(out: list[str], chapter_id: str, title: str) -> None:
    out.append(f'  <div class="{_block_class_for(chapter_id, title)}">')
    out.append('    <div class="demo-title-row">')
    out.append(f'      <h3 class="demo-title">{_esc(_display_subsection_title(title))}</h3>')
    out.append("    </div>")


CHAPTER_TITLE_ALIASES = {
    "工具智能演化": "智能工具演化",
    "Yaahlan智能工具平台Agent": "智能工具平台Agent",
}


def _should_skip_chapter(h1_text: str, sid: str) -> bool:
    if sid in SKIP_CHAPTER_IDS or h1_text in SKIP_CHAPTER_TITLES:
        return True
    if h1_text.startswith("个人介绍"):
        return True
    # 钉钉文档常把「概况」与导语合并为一个 h1，概况 tab 已由 _render_overview_panel 单独渲染
    if h1_text.startswith("概况"):
        return True
    # 结语 tab 由 _render_conclusion_panel 单独渲染
    if h1_text == "结语" or sid == "conclusion":
        return True
    return False


def _chapter_meta(h1_text: str) -> dict[str, str]:
    h1_text = CHAPTER_TITLE_ALIASES.get(h1_text, h1_text)
    if h1_text in CHAPTER_META:
        return CHAPTER_META[h1_text]
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", h1_text).strip("-").lower()[:48] or "section"
    return {
        "id": slug,
        "index": "",
        "title": h1_text,
        "intro": "",
    }


def _read_agent_url() -> str:
    if not CONTENT_PATH.is_file():
        return DEFAULT_AGENT_URL
    try:
        existing = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_AGENT_URL
    return str(existing.get("agentUrl") or DEFAULT_AGENT_URL)


def _sync_content_json() -> dict:
    chapters = [
        {
            "id": OVERVIEW_TAB["id"],
            "index": OVERVIEW_TAB["index"],
            "title": OVERVIEW_TAB["title"],
            "intro": OVERVIEW_TAB["intro"],
            "status": "done",
        }
    ]
    for h1, meta in CHAPTER_META.items():
        chapters.append(
            {
                "id": meta["id"],
                "index": meta["index"] if meta["index"] != "0" else "",
                "title": meta["title"],
                "intro": meta["intro"],
                "status": "done",
            }
        )
    chapters.append(
        {
            "id": CONCLUSION_TAB["id"],
            "index": CONCLUSION_TAB["index"],
            "title": CONCLUSION_TAB["title"],
            "intro": CONCLUSION_TAB["intro"],
            "status": "done",
        }
    )
    data = {
        "title": "智能工具平台搭建与测试应用的探索过程",
        "lead": "",
        "author": {
            "name": "陈墨",
            "role": "产品业务向测试",
            "department": "Yaahlan 项目测试",
        },
        "shareFocus": OVERVIEW_TAB["intro"],
        "sourceDocUrl": SOURCE_DOC_URL,
        "agentUrl": _read_agent_url(),
        "platformMetrics": DEFAULT_PLATFORM_METRICS,
        "chapters": chapters,
    }
    if CONTENT_PATH.is_file():
        try:
            existing = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        if existing.get("platformMetrics"):
            data["platformMetrics"] = existing["platformMetrics"]
    CONTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTENT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def _strip_trailing_url(text: str) -> str:
    return TRAILING_URL_RE.sub("", text).strip()


def _normalize_url(raw: str) -> str:
    url = raw.rstrip(".,;:)。")
    return LINK_OVERRIDES.get(url, url)


def _doc_link_label(url: str) -> str:
    if "keynote" in url:
        return "Keynote 介绍"
    agent_url = _read_agent_url().rstrip("/")
    if url.rstrip("/") == agent_url:
        return "智能工具 Agent"
    if "family-pk-showcase" in url:
        return "工作流参考"
    if "platform-guide" in url:
        return "平台搭建参考"
    return "打开链接"


def _format_see_detail_link(text: str, *, link_text: str | None = None) -> str:
    match = INLINE_URL_RE.search(text)
    if not match:
        return _esc(text)
    url = _normalize_url(match.group(0))
    prefix = text[: match.start()].strip()
    prefix = re.sub(r"[：:]\s*$", "", prefix).strip()
    label = link_text or _doc_link_label(url)
    link = f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(label)}</a>'
    return f"{_esc(prefix)}（详见 {link}）"


def _should_use_see_detail_link(text: str) -> bool:
    if _is_agent_access_paragraph(text):
        return True
    if "见文档" not in text:
        return False
    return bool(INLINE_URL_RE.search(text))


def _link_label(prefix: str, url: str) -> str:
    if prefix.endswith("报告"):
        return "查看报告"
    if prefix.endswith(("介绍", "详情", "文档")):
        return "查看详情"
    if len(url) > 48:
        return "打开链接"
    return url


def _linkify(text: str) -> str:
    parts: list[str] = []
    last = 0
    for match in INLINE_URL_RE.finditer(text):
        prefix = text[last : match.start()]
        parts.append(_esc(prefix))
        url = _normalize_url(match.group(0))
        label = _link_label(prefix, url)
        parts.append(
            f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(label)}</a>'
        )
        last = match.end()
    parts.append(_esc(text[last:]))
    return "".join(parts)


def _is_step_paragraph(text: str) -> bool:
    return bool(STEP_RE.match(text))


def _step_number(text: str) -> str:
    match = STEP_RE.match(text)
    return match.group(1) if match else ""


def _step_body(text: str) -> str:
    return STEP_RE.sub("", text, count=1).strip()


def _is_q_text(text: str) -> bool:
    return bool(QA_Q_RE.match(text.strip()))


def _is_a_text(text: str) -> bool:
    return bool(QA_A_RE.match(text.strip()))


def _qa_body(text: str) -> str:
    stripped = text.strip()
    for pattern in (QA_Q_RE, QA_A_RE):
        if pattern.match(stripped):
            return pattern.sub("", stripped, count=1).strip()
    return stripped


def _render_qa_block(num: str | None, q_text: str, a_text: str | None = None) -> str:
    extra = " has-no" if not num else ""
    num_cell = (
        f'      <span class="qa-no">{_esc(num)}.</span>'
        if num
        else ""
    )
    a_row = ""
    if a_text:
        a_content = _linkify(_qa_body(a_text))
        a_row = (
            "        <div class=\"qa-row qa-a\">\n"
            "          <span class=\"qa-label\">A:</span>\n"
            f"          <div class=\"qa-text\">{a_content}</div>\n"
            "        </div>"
        )
    q_content = _linkify(_qa_body(q_text))
    return (
        f"    <div class=\"qa-block{extra}\">\n"
        f"{num_cell}\n"
        "      <div class=\"qa-lines\">\n"
        "        <div class=\"qa-row qa-q\">\n"
        "          <span class=\"qa-label\">Q:</span>\n"
        f"          <div class=\"qa-text\">{q_content}</div>\n"
        "        </div>\n"
        f"{a_row}\n"
        "      </div>\n"
        "    </div>"
    )


def _render_shot_html(filename: str, *, single: bool = False) -> str:
    src = f"{IMAGE_URL_PREFIX}/{_esc(filename)}"
    single_class = " is-single" if single else ""
    return (
        f'<div class="demo-wf-media-only{single_class}">'
        f'<div class="media-box">'
        f'<button type="button" class="demo-zoom-trigger" data-zoom-src="{src}" data-zoom-caption="配图">'
        f'<img src="{src}" alt="配图" loading="lazy" />'
        f"</button>"
        f'<div class="media-caption">附图 · 点击查看大图</div>'
        f"</div></div>"
    )


def _render_shot_placeholder() -> str:
    return (
        '<div class="demo-wf-media-only is-single">'
        '<div class="media-box demo-placeholder">配图 · 见钉钉原文档</div></div>'
    )


LIGHTBOX_HTML = """
  <div id="demo-image-lightbox" class="demo-lightbox" hidden aria-hidden="true">
    <div class="demo-lightbox-backdrop" data-lightbox-close></div>
    <figure class="demo-lightbox-panel">
      <img src="" alt="大图预览" />
      <figcaption class="demo-lightbox-caption"></figcaption>
    </figure>
    <button type="button" class="demo-lightbox-close" data-lightbox-close aria-label="关闭预览">&times;</button>
  </div>
  <script>
    (function () {
      var lightbox = document.getElementById("demo-image-lightbox");
      if (!lightbox) return;
      var lightboxImg = lightbox.querySelector(".demo-lightbox-panel img");
      var lightboxCaption = lightbox.querySelector(".demo-lightbox-caption");
      function openLightbox(src, caption) {
        if (!lightboxImg || !src) return;
        lightboxImg.src = src;
        lightboxImg.alt = caption || "大图预览";
        if (lightboxCaption) {
          lightboxCaption.textContent = caption || "";
          lightboxCaption.hidden = !caption;
        }
        lightbox.hidden = false;
        lightbox.classList.add("open");
        lightbox.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
      }
      function closeLightbox() {
        if (!lightboxImg) return;
        lightbox.classList.remove("open");
        lightbox.hidden = true;
        lightbox.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        lightboxImg.removeAttribute("src");
      }
      document.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof Element)) return;
        var zoomBtn = target.closest(".demo-zoom-trigger");
        if (zoomBtn) {
          event.preventDefault();
          openLightbox(
            zoomBtn.getAttribute("data-zoom-src") || "",
            zoomBtn.getAttribute("data-zoom-caption") || ""
          );
          return;
        }
        if (target.closest("[data-lightbox-close]")) closeLightbox();
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeLightbox();
      });
      var links = document.querySelectorAll(".tab-link");
      var panels = document.querySelectorAll(".tab-panel");
      var known = new Set(
        Array.from(panels).map(function (p) { return p.getAttribute("data-tab"); })
      );
      var defaultTab = "__DEFAULT_TAB__";
      var activeTabId = null;
      function scrollActivePanelToTop() {
        var panel = document.querySelector(".tab-panel.active");
        if (!panel) return;
        var target = panel.querySelector(".section") || panel;
        target.scrollIntoView({ behavior: "smooth", block: "start", inline: "nearest" });
      }
      function activate(tabId, options) {
        options = options || {};
        if (tabId === "top") tabId = defaultTab;
        if (!known.has(tabId)) tabId = defaultTab;
        var tabChanged = activeTabId !== null && activeTabId !== tabId;
        panels.forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-tab") === tabId);
        });
        links.forEach(function (a) {
          a.classList.toggle("active", a.getAttribute("data-tab") === tabId);
        });
        if (tabChanged || options.scroll) scrollActivePanelToTop();
        activeTabId = tabId;
      }
      links.forEach(function (a) {
        a.addEventListener("click", function (e) {
          e.preventDefault();
          var tabId = a.getAttribute("data-tab") || defaultTab;
          activate(tabId);
          history.replaceState(null, "", "#" + tabId);
        });
      });
      window.addEventListener("hashchange", function () {
        activate((location.hash || "#__DEFAULT_TAB__").slice(1), { scroll: true });
      });
      activate((location.hash || "#__DEFAULT_TAB__").slice(1));
    })();
  </script>"""


def _flush_shots(filenames: list[str | None]) -> list[str]:
    if not filenames:
        return []
    single = len(filenames) == 1
    shots = [
        _render_shot_html(name, single=single) if name else _render_shot_placeholder()
        for name in filenames
    ]
    if single:
        return [f"    {shots[0]}"]
    inner = "\n".join(f"      {line}" for line in shots)
    return [
        '    <div class="media-gallery">',
        inner,
        "    </div>",
    ]


def _render_step_item(num: str, body: str) -> str:
    content = (
        _format_see_detail_link(body)
        if _should_use_see_detail_link(body)
        else _linkify(body)
    )
    content = content.replace("\n", "<br>")
    return (
        f'      <li><strong class="step-no">{_esc(num)}.</strong>{content}</li>'
    )


def _is_agent_access_paragraph(text: str) -> bool:
    return "Agent地址" in text or "Agent 地址" in text


def _render_share_topics_list(data: dict) -> str:
    items: list[str] = []
    num = 1
    skip_ids = {OVERVIEW_TAB["id"], CONCLUSION_TAB["id"]}
    for chapter in data.get("chapters") or []:
        if chapter.get("id") in skip_ids:
            continue
        title = str(chapter.get("title") or "").strip()
        if not title:
            continue
        cid = str(chapter.get("id") or "")
        intro = str(chapter.get("intro") or "").strip()
        if cid == "evolution":
            intro = EVOLUTION_SHARE_TOPIC_INTRO
        elif not intro:
            intro = SHARE_TOPIC_OVERVIEW_INTROS.get(cid, "")
        body = f"<strong>{_esc(title)}</strong>"
        if intro:
            body += f"——{_esc(intro)}"
        items.append(
            f'      <li><strong class="step-no">{num}.</strong>{body}</li>'
        )
        num += 1
    if not items:
        return ""
    return "    <ul class=\"summary-cards\">\n" + "\n".join(items) + "\n    </ul>"


def _render_lead_paragraphs(text: str) -> str:
    parts = [part.strip() for part in str(text).split("\n\n") if part.strip()]
    if not parts:
        return "    <p></p>"
    return "\n".join(f"    <p>{_esc(part)}</p>" for part in parts)


def _render_overview_panel(data: dict, *, active: bool = True) -> str:
    intro = str(data.get("shareFocus") or OVERVIEW_TAB["intro"])
    active_class = " active" if active else ""
    share_topics = _render_share_topics_list(data)
    intro_html = _render_lead_paragraphs(intro)

    return f"""<div class="tab-panel{active_class}" data-tab="overview" role="tabpanel">
<section class="section" id="overview">
  <div class="demo-title-row">
    <h2 class="demo-title">{_esc(OVERVIEW_TAB["title"])}</h2>
  </div>
  <div class="section-intro lead-block">
{intro_html}
  </div>
  <div class="demo-block phase-kb">
    <div class="demo-title-row">
      <h3 class="demo-title">分享内容概览</h3>
    </div>
    <p>{_esc(OVERVIEW_QA_INTRO)}</p>
{share_topics}
  </div>
  <div class="demo-block phase-record">
    <div class="demo-title-row">
      <h3 class="demo-title">技术选型与构建思路</h3>
    </div>
    <p>构建思路：<strong>不另起技术栈，以 Cursor 的对话、Agent、Rules、Skills 作为平台底座</strong>——用户以自然语言描述诉求，Agent 调用既有能力或探索新路径，验证通过后完成沉淀，供团队复用。</p>
    <ul class="summary-cards">
      <li><strong class="step-no">1.</strong><strong>低门槛</strong>——以业务语言描述目标，无需预先掌握框架与命令。</li>
      <li><strong class="step-no">2.</strong><strong>高效率</strong>——探索与交付在同一对话链路中完成，减少重复脚本开发。</li>
      <li><strong class="step-no">3.</strong><strong>轻架构</strong>——不追求大而全的中台，将每次有效操作转化为团队能力资产。</li>
    </ul>
  </div>
</section>
</div>"""


def _platform_metrics(data: dict | None = None) -> dict:
    metrics = (data or {}).get("platformMetrics") or DEFAULT_PLATFORM_METRICS
    cards = metrics.get("cards") or DEFAULT_PLATFORM_METRICS["cards"]
    summary = metrics.get("summary") or DEFAULT_PLATFORM_METRICS["summary"]
    return {"cards": cards, "summary": summary}


def _render_platform_metrics_html(data: dict | None = None) -> str:
    metrics = _platform_metrics(data)
    cards_html = "".join(
        f'<div class="metric"><div class="label">{_esc(card["label"])}</div>'
        f'<div class="value">{_esc(card["value"])}</div></div>'
        for card in metrics["cards"]
    )
    summary_html = "".join(
        f'<li><strong class="step-no">{index}.</strong>'
        f'<strong>{_esc(item["title"])}</strong>——{_esc(item["text"])}</li>'
        for index, item in enumerate(metrics["summary"], start=1)
    )
    return f"""    <div class="metric-grid">
{cards_html}
    </div>
    <ul class="summary-cards">
{summary_html}
    </ul>"""


def _render_conclusion_panel(data: dict | None = None, *, active: bool = False) -> str:
    active_class = " active" if active else ""
    intro = CONCLUSION_TAB["intro"]
    metrics_html = _render_platform_metrics_html(data)
    return f"""<div class="tab-panel{active_class}" data-tab="conclusion" role="tabpanel">
<section class="section" id="conclusion">
  <div class="demo-title-row">
    <h2 class="demo-title">{_esc(CONCLUSION_TAB["title"])}</h2>
  </div>
  <p class="conclusion-lead">{_esc(intro)}</p>
  <div class="demo-block phase-summary">
    <div class="demo-title-row">
      <h3 class="demo-title">平台建设概况</h3>
    </div>
{metrics_html}
  </div>
  <div class="demo-block phase-outlook callout">
    <div class="demo-title-row">
      <h3 class="demo-title">接下来</h3>
    </div>
    <p>此外智能工具平台把人工操作的流程转化成了机器操作的语言，为将来的真自动化测试做好了铺垫准备。</p>
    <p>平台仍在日常工作中持续迭代。前面涉及的所有文档，包括当前的分享文档，都可以在 Web Agent <strong>设置 → 关于</strong> 中找到。</p>
    {_render_shot_html("web-agent-about-modal.png", single=True)}
  </div>
</section>
</div>"""


def _render_doc_link_paragraph(
    text: str, hint: str, link_html: str, *, chapter_id: str = ""
) -> str:
    normalized = _strip_trailing_url(_polish_text(text, chapter_id=chapter_id))
    normalized = TRAILING_EMPTY_PAREN_RE.sub("", normalized).strip()
    body = normalized.replace(hint, f"{hint}（详见 {link_html}）")
    return f'    <div class="section-intro doc-link"><p>{body}</p></div>'


def _render_paragraph(text: str, *, chapter_id: str = "") -> str | None:
    normalized = _polish_text(text, chapter_id=chapter_id)
    if not normalized:
        return None
    if _is_step_paragraph(normalized):
        return None
    for hint in DOC_LINK_HINTS:
        if hint in normalized:
            if "Cursor 搭建" in hint:
                link = '<a href="/platform-guide/" target="_blank" rel="noopener">平台搭建参考</a>'
            else:
                link = f'<a href="{WORKFLOW_REFERENCE_URL}" target="_blank" rel="noopener">工作流参考</a>'
            return _render_doc_link_paragraph(text, hint, link, chapter_id=chapter_id)
    if _is_agent_access_paragraph(normalized):
        body = _format_see_detail_link(normalized)
        return f'    <div class="section-intro doc-link"><p>{body}</p></div>'
    return f"    <p>{_linkify(normalized)}</p>"


def _render_hero(title: str) -> str:
    return (
        f'<header class="hero" id="top">\n'
        f'  <div class="hero-copy">\n'
        f'    <p class="eyebrow">业务分享</p>\n'
        f'    <h1>{_esc(title)}</h1>\n'
        f"  </div>\n"
        f"{HERO_CONSOLE_HTML}\n"
        f"</header>"
    )


def _render_tab_link(title: str, sid: str, *, active: bool = False) -> str:
    active_class = " active" if active else ""
    return (
        f'      <a href="#{_esc(sid)}" class="tab-link{active_class}" '
        f'data-tab="{_esc(sid)}">{_esc(title)}</a>\n'
    )


def _render_page_shell(
    title: str,
    toc_lines: str,
    hero_html: str,
    body: str,
    footer_html: str,
    *,
    default_tab: str = DEFAULT_TAB_ID,
) -> str:
    css = _shared_css()
    lightbox_html = LIGHTBOX_HTML.replace("__DEFAULT_TAB__", default_tab)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
  <title>{_esc(title)}</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
{hero_html}
    <div class="tab-bar"><nav class="nav tab-nav">
{toc_lines}    </nav></div>
    <div class="tab-panels">
{body}
    </div>
    {footer_html}
  </div>{lightbox_html}
</body>
</html>
"""


def _build_from_dingtalk(cache_dir: Path) -> tuple[str, dict]:
    items = load_dingtalk_items(cache_dir)
    local_images = load_local_images(cache_dir)
    data = _sync_content_json()

    out: list[str] = []
    toc: list[tuple[str, str]] = []
    first_panel = True
    img_idx = 0
    in_chapter = False
    in_block = False
    current_block_title = ""
    current_chapter_id = ""
    current_chapter_intro = ""
    skip_duplicate_intro = False
    skip_chapter = False
    in_prose = False
    in_step_list = False
    pending_shots: list[str | None] = []
    injected_extra_blocks: set[str] = set()
    pending_q: tuple[str | None, str] | None = None

    def flush_pending_q() -> None:
        nonlocal pending_q
        if pending_q is None:
            return
        num, q_text = pending_q
        pending_q = None
        out.append(_render_qa_block(num, q_text))

    def flush_shots() -> None:
        out.extend(_flush_shots(pending_shots))
        pending_shots.clear()

    def close_step_list() -> None:
        nonlocal in_step_list
        if in_step_list:
            out.append("    </ul>")
            in_step_list = False

    def begin_q(num: str | None, q_text: str) -> None:
        nonlocal pending_q
        close_step_list()
        flush_shots()
        flush_pending_q()
        pending_q = (num, q_text)

    def complete_qa(a_text: str) -> None:
        nonlocal pending_q
        if pending_q is None:
            return
        num, q_text = pending_q
        pending_q = None
        out.append(_render_qa_block(num, q_text, a_text))

    def open_prose(*, extra_class: str = "") -> None:
        nonlocal in_prose
        if not in_prose:
            klass = "section-intro"
            if extra_class:
                klass = f"{klass} {extra_class}"
            out.append(f'  <div class="{klass}">')
            in_prose = True

    def close_prose() -> None:
        nonlocal in_prose
        if in_prose:
            out.append("  </div>")
            in_prose = False

    def inject_extra_steps(block_title: str) -> None:
        if block_title in injected_extra_blocks:
            return
        extra = EXTRA_STEPS.get(block_title)
        if not extra:
            return
        injected_extra_blocks.add(block_title)
        close_step_list()
        flush_shots()
        out.append('    <ul class="summary-cards">')
        for num, body in extra:
            out.append(_render_step_item(num, body))
        out.append("    </ul>")

    def close_block() -> None:
        nonlocal in_block, current_block_title
        close_step_list()
        flush_shots()
        flush_pending_q()
        if in_block:
            inject_extra_steps(current_block_title)
            out.append("  </div>")
            in_block = False
            current_block_title = ""

    def close_chapter() -> None:
        nonlocal in_chapter, current_chapter_id, current_chapter_intro, skip_duplicate_intro
        close_block()
        close_prose()
        close_step_list()
        if in_chapter:
            out.append("</section>")
            out.append("</div>")
            in_chapter = False
            current_chapter_id = ""
            current_chapter_intro = ""
            skip_duplicate_intro = False

    def append_shot(filename: str | None) -> None:
        pending_shots.append(filename)

    hero_html = _render_hero(data["title"])

    out.append(_render_overview_panel(data, active=True))
    toc.append((OVERVIEW_TAB["title"], OVERVIEW_TAB["id"]))
    first_panel = False

    for item in items:
        if item["kind"] == "img":
            if skip_chapter:
                img_idx += 1
                continue
            src = local_images[img_idx] if img_idx < len(local_images) else ""
            img_idx += 1
            img_path = cache_dir / src if src else None
            filename: str | None = None
            if src and img_path and img_path.is_file():
                dest_dir = OUTPUT_DIR / "images"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / Path(src).name
                if not dest.is_file() or dest.stat().st_size != img_path.stat().st_size:
                    dest.write_bytes(img_path.read_bytes())
                filename = dest.name
            append_shot(filename)
            continue

        tag = item["tag"]
        text = _normalize_text(item["text"])
        if not text:
            continue

        if tag == "h1":
            close_chapter()
            meta = _chapter_meta(text)
            sid = meta["id"]
            if _should_skip_chapter(text, sid):
                skip_chapter = True
                current_chapter_id = ""
                current_chapter_intro = ""
                skip_duplicate_intro = False
                continue
            skip_chapter = False
            current_chapter_id = sid
            current_chapter_intro = str(meta.get("intro") or "").strip()
            skip_duplicate_intro = bool(current_chapter_intro)
            toc.append((meta["title"], sid))
            active = " active" if first_panel else ""
            first_panel = False
            out.append(
                f'<div class="tab-panel{active}" data-tab="{sid}" role="tabpanel">'
            )
            out.append(f'<section class="section" id="{sid}">')
            out.append('  <div class="demo-title-row">')
            out.append(f'    <h2 class="demo-title">{_esc(meta["title"])}</h2>')
            out.append("  </div>")
            if meta.get("intro"):
                out.append(
                    f'  <div class="section-intro"><p>{_esc(meta["intro"])}</p></div>'
                )
            roadmap = CHAPTER_ROADMAPS.get(sid)
            if roadmap:
                out.append(roadmap)
            in_chapter = True
            continue

        if skip_chapter:
            continue

        if _is_subsection_title(text):
            close_prose()
            close_block()
            current_block_title = text
            _open_demo_block(out, current_chapter_id, text)
            in_block = True
            continue

        if _is_a_text(text) and pending_q is not None:
            complete_qa(_polish_text(text, chapter_id=current_chapter_id))
            continue

        if _is_step_paragraph(text):
            step_num = _step_number(text)
            step_body = _polish_text(
                _step_body(text), chapter_id=current_chapter_id
            )
            if _is_q_text(step_body):
                begin_q(step_num, step_body)
                continue
            if pending_shots and in_step_list:
                out.append("    </ul>")
                in_step_list = False
            flush_shots()
            if not in_step_list:
                out.append('    <ul class="summary-cards">')
                in_step_list = True
            out.append(
                _render_step_item(
                    step_num,
                    step_body,
                )
            )
            continue

        close_step_list()
        flush_shots()
        normalized = _polish_text(text, chapter_id=current_chapter_id)
        if not normalized or _is_step_paragraph(normalized):
            continue
        if _is_q_text(normalized):
            begin_q(None, normalized)
            continue
        if (
            skip_duplicate_intro
            and current_chapter_intro
            and normalized == current_chapter_intro
        ):
            skip_duplicate_intro = False
            continue
        if normalized in CHAPTER_SKIP_PARAGRAPHS.get(current_chapter_id, set()):
            continue
        if in_block:
            paragraph = _render_paragraph(text, chapter_id=current_chapter_id)
            if paragraph:
                out.append(paragraph)
            continue
        for hint in DOC_LINK_HINTS:
            if hint in normalized:
                close_prose()
                if "Cursor 搭建" in hint:
                    link = '<a href="/platform-guide/" target="_blank" rel="noopener">平台搭建参考</a>'
                else:
                    link = f'<a href="{WORKFLOW_REFERENCE_URL}" target="_blank" rel="noopener">工作流参考</a>'
                out.append(
                    _render_doc_link_paragraph(
                        text, hint, link, chapter_id=current_chapter_id
                    )
                )
                break
        else:
            extra = (
                "lead-block"
                if current_chapter_id in ("dingtalk-bot", "platform") and not in_block
                else ""
            )
            open_prose(extra_class=extra)
            out.append(f"    <p>{_linkify(normalized)}</p>")

    close_chapter()

    toc.append((CONCLUSION_TAB["title"], CONCLUSION_TAB["id"]))
    out.append(_render_conclusion_panel(data, active=False))

    default_tab = OVERVIEW_TAB["id"]
    toc_lines = "".join(
        _render_tab_link(title, sid, active=(sid == default_tab))
        for title, sid in toc
    )
    body = "\n".join(out)
    footer = ""
    page = _render_page_shell(
        data["title"], toc_lines, hero_html, body, footer, default_tab=default_tab
    )
    return page, data


def _build_standard(data: dict) -> str:
    toc_lines: list[str] = []
    body_parts: list[str] = []
    chapters = [
        chapter
        for chapter in data["chapters"]
        if chapter["id"] not in SKIP_CHAPTER_IDS
    ]
    default_tab = OVERVIEW_TAB["id"]

    toc_lines.append(
        _render_tab_link(OVERVIEW_TAB["title"], OVERVIEW_TAB["id"], active=True)
    )
    body_parts.append(_render_overview_panel(data, active=True))

    for index, chapter in enumerate(chapters):
        if chapter["id"] in {OVERVIEW_TAB["id"], CONCLUSION_TAB["id"]}:
            continue
        cid = chapter["id"]
        toc_lines.append(_render_tab_link(chapter["title"], cid, active=False))
        todo = (
            '<span class="todo-badge">待补充</span>'
            if chapter.get("status") != "done"
            else ""
        )
        body_parts.append(
            f"""<div class="tab-panel" data-tab="{cid}" role="tabpanel">
<section class="section" id="{cid}">
  <div class="demo-title-row"><h2 class="demo-title">{_esc(chapter["title"])}</h2></div>
  {todo}
</section>
</div>"""
        )

    toc_lines.append(
        _render_tab_link(CONCLUSION_TAB["title"], CONCLUSION_TAB["id"], active=False)
    )
    body_parts.append(_render_conclusion_panel(data, active=False))

    hero_html = _render_hero(data["title"])

    body = "\n".join(body_parts)
    toc_html = "".join(toc_lines)
    footer = ""
    return _render_page_shell(
        data["title"], toc_html, hero_html, body, footer, default_tab=default_tab
    )


def main() -> int:
    cache_dir = DEFAULT_DINGTALK_CACHE
    use_dingtalk = False
    args = sys.argv[1:]
    if args and args[0] == "--from-dingtalk":
        use_dingtalk = True
        if len(args) > 1:
            cache_dir = Path(args[1]).expanduser().resolve()
    elif (cache_dir / DINGTALK_CONTENT_FILE).is_file() and "--placeholder-only" not in args:
        use_dingtalk = True

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if use_dingtalk:
        page, data = _build_from_dingtalk(cache_dir)
        STANDARD_HTML.write_text(page, encoding="utf-8")
    else:
        data = _load_content()
        STANDARD_HTML.write_text(_build_standard(data), encoding="utf-8")

    print(f"generated {STANDARD_HTML}")
    if use_dingtalk:
        print(f"synced {CONTENT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
