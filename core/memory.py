import json
from pathlib import Path

_MEMORY_FILE = Path(__file__).parent.parent / "memory.json"
_MAX_FACTS   = 50


def load_facts() -> list[str]:
    if not _MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        return data.get("facts", [])
    except Exception:
        return []


def save_fact(fact: str) -> bool:
    """Добавляет факт если его ещё нет. Возвращает True если добавил."""
    fact = fact.strip()
    if not fact:
        return False
    facts = load_facts()
    if fact in facts:
        return False
    facts.append(fact)
    if len(facts) > _MAX_FACTS:
        facts = facts[-_MAX_FACTS:]
    _MEMORY_FILE.write_text(
        json.dumps({"facts": facts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[memory] saved: {fact}")
    return True


def build_memory_block() -> str:
    """Возвращает блок для системного промпта или пустую строку."""
    facts = load_facts()
    if not facts:
        return ""
    lines = "\n".join(f"- {f}" for f in facts)
    return f"\nЧто ты уже знаешь о пользователе (из прошлых бесед):\n{lines}"
