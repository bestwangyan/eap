"""Phase 4: 安全围栏链

接入点：
  - chat.py chat_stream()   输入首道拦截（持久化前）+ 输出检查（持久化前）
  - orchestrator.stream_chat()  输入防御纵深（兜底其他调用路径）

设计约定：
  - 同步方法：orchestrator 是同步生成器（gevent worker），围栏全部为
    纯正则/关键词检查，无 IO，不需要 async
  - 拦截语义：check 返回 passed=False 时 fail-closed（阻断）；围栏自身
    抛异常时由调用方 fail-open（可用性优先），调用方需包 try/except
"""
import re
import logging

logger = logging.getLogger(__name__)


class GuardrailResult:
    def __init__(self, passed: bool, reason: str = "", modified_text: str = "", details: dict = None):
        self.passed = passed
        self.reason = reason
        self.modified_text = modified_text
        self.details = details or {}


class BaseGuardrail:
    def check(self, text: str, context: dict | None = None) -> GuardrailResult:
        raise NotImplementedError


class PIIGuardrail(BaseGuardrail):
    """PII 检测与脱敏"""
    PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        "PHONE_CN": r'1[3-9]\d{9}',
        "ID_CARD_CN": r'\d{17}[\dXx]',
        "CREDIT_CARD": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
        "IP_ADDRESS": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    }

    def __init__(self, mode: str = "redact"):
        self.mode = mode

    def check(self, text: str, context: dict | None = None) -> GuardrailResult:
        findings = []
        for pii_type, pattern in self.PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                findings.append({"type": pii_type, "value": match.group()})
        if findings:
            if self.mode == "block":
                return GuardrailResult(False, f"检测到敏感信息: {[f['type'] for f in findings]}")
            sanitized = text
            for f in findings:
                if self.mode == "redact":
                    sanitized = sanitized.replace(f["value"], f"[REDACTED_{f['type']}]")
                elif self.mode == "mask":
                    v = f["value"]
                    sanitized = sanitized.replace(v, v[:3] + "****" + v[-3:] if len(v) > 6 else "****")
            return GuardrailResult(True, modified_text=sanitized, details={"findings": findings})
        return GuardrailResult(True)


class ContentSafetyGuardrail(BaseGuardrail):
    """内容安全审核"""
    BLOCKED = ["DROP TABLE", "DROP DATABASE", "<script", "rm -rf /", "curl", "| bash", "eval(", "__import__"]
    FORBIDDEN = [
        (r'(?i)drop\s+table', "SQL DROP"),
        (r'(?i)<script.*?>', "XSS"),
        (r'(?i)rm\s+-rf\s+/', "危险命令"),
    ]

    def check(self, text: str, context: dict | None = None) -> GuardrailResult:
        for kw in self.BLOCKED:
            if kw.lower() in text.lower():
                return GuardrailResult(False, f"检测到危险关键词: {kw}")
        for pattern, label in self.FORBIDDEN:
            if re.search(pattern, text):
                return GuardrailResult(False, f"检测到危险模式: {label}")
        return GuardrailResult(True)


class GuardrailChain:
    def __init__(self):
        self.guardrails: list[BaseGuardrail] = [
            PIIGuardrail(mode="redact"),
            ContentSafetyGuardrail(),
        ]

    def check_input(self, text: str, context: dict | None = None) -> GuardrailResult:
        """输入检查：逐围栏执行；被拦截立即返回，脱敏文本透传给下一个围栏"""
        for g in self.guardrails:
            result = g.check(text, context)
            if not result.passed:
                return result
            if result.modified_text:
                text = result.modified_text
        return GuardrailResult(True, modified_text=text)

    def check_output(self, text: str, context: dict | None = None) -> GuardrailResult:
        """输出检查：被拦截立即返回；脱敏文本在最后统一返回（调用方可替换持久化内容）"""
        for g in self.guardrails:
            result = g.check(text, context)
            if not result.passed:
                return result
            if result.modified_text:
                text = result.modified_text
        return GuardrailResult(True, modified_text=text)
