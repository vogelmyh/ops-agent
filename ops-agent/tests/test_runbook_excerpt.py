from app.graph.runbook_excerpt import excerpt_runbook

SAMPLE = """\
# Title

## 适用范围
- **仅适用于服务 `ecomm-order`**。

## 症状
CrashLoopBackOff

## 处置
rollback_deployment

## 勿用手段
restart only
"""


def test_excerpt_runbook_keeps_key_sections():
    text = excerpt_runbook(SAMPLE, max_chars=500)
    assert "## 适用范围" in text
    assert "## 症状" in text
    assert "## 处置" in text
    assert "rollback_deployment" in text
