"""Optional plain-language summary of an audit, written by a local LLM through Ollama.

Free and private: the model runs on the user's own machine (https://ollama.com), so no data
leaves it. The LLM only explains and prioritises findings that ``data/audit.py`` already
detected; it is never asked to find problems on its own, which keeps it from inventing them.
Without Ollama the audit still works, just without this summary.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from fleetdesk.data.audit import AuditReport, Issue, Severity
from fleetdesk.formatting import brl, number

OLLAMA_URL = os.environ.get("FLEETDESK_OLLAMA_URL", "http://127.0.0.1:11434")
#: Tried in order when the user has not picked a model. Qwen 2.5 writes good Portuguese, and
#: the 3B version answers in ~20 s on an ordinary laptop (the 7B took ~2 min on a 4 GB GPU).
PREFERRED_MODELS = ("qwen2.5:3b", "qwen2.5:7b", "llama3.2:3b", "gemma2:2b", "llama3.1:8b")
MAX_PRIORITIES = 6
GENERATION_TIMEOUT_S = 300

SEVERITY_LABELS = {
    Severity.ERROR: "erro",
    Severity.WARNING: "atenção",
    Severity.INFO: "informativo",
}

# The prompt is in Portuguese on purpose: small local models follow instructions far better
# when the prompt is in the language they must answer in.
SYSTEM_PROMPT = """\
Você ajuda o dono de uma transportadora a revisar as planilhas da empresa. Ele não é da área \
de tecnologia.
Você recebe, em JSON, os problemas que uma auditoria automática já encontrou e já colocou em \
ordem de prioridade. Sua tarefa é só explicar cada um em português do Brasil simples.

Regras:
- Use somente as informações do JSON. Não invente problemas, nomes, linhas nem valores.
- Nunca some, multiplique nem calcule valores: copie os números exatamente como estão.
- Mantenha a ordem e a numeração da lista "prioridades". Não junte nem separe itens.
- Cada valor em reais e cada linha pertence só ao item em que aparece no JSON.
- Comece copiando a frase do campo "visao_geral".
- Depois escreva "O que conferir primeiro:" e, para cada prioridade, uma linha numerada com \
o problema em palavras simples, onde conferir (copie o campo "onde") e o que fazer.
- Se houver itens em "pode_ser_normal", termine com "Pode ser normal:" e uma linha curta \
para cada um.
- Texto puro, sem asteriscos nem markdown. No máximo 220 palavras."""


class AssistantError(RuntimeError):
    """The local model could not produce a summary (message is pt-BR, shown to the user)."""


@dataclass(frozen=True, slots=True)
class AssistantStatus:
    available: bool
    #: The model a summary would use; empty when unavailable.
    model: str = ""
    models: list[str] = field(default_factory=list)
    #: Why it is unavailable, in pt-BR.
    message: str = ""


@dataclass(frozen=True, slots=True)
class Summary:
    text: str
    model: str
    seconds: float


class LocalAssistant:
    def __init__(self, base_url: str = OLLAMA_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def status(self, preferred_model: str = "") -> AssistantStatus:
        try:
            tags = self._request("GET", "/api/tags", timeout=2)
        except AssistantError:
            return AssistantStatus(
                available=False,
                message="O Ollama não está aberto neste computador. Abra o aplicativo Ollama "
                "(ou instale em ollama.com) para gerar o resumo com IA.",
            )
        models = sorted(m["name"] for m in tags.get("models", []))
        if not models:
            return AssistantStatus(
                available=False,
                message="O Ollama está aberto, mas não tem nenhum modelo. Para baixar um, rode "
                "no Prompt de Comando: ollama pull qwen2.5:3b",
            )
        if preferred_model in models:
            chosen = preferred_model
        else:
            chosen = next((m for m in PREFERRED_MODELS if m in models), models[0])
        return AssistantStatus(available=True, model=chosen, models=models)

    def summarize(self, report: AuditReport, model: str) -> Summary:
        started = time.perf_counter()
        reply = self._request(
            "POST",
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_prompt(report)},
                ],
                # Low temperature: this is a factual summary, not creative writing.
                "options": {"temperature": 0.2, "num_ctx": 4096},
            },
            timeout=GENERATION_TIMEOUT_S,
        )
        text = str(reply.get("message", {}).get("content", "")).strip()
        if not text:
            raise AssistantError("O modelo não devolveu nenhum texto. Tente de novo.")
        return Summary(text=text, model=model, seconds=time.perf_counter() - started)

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 10
    ) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed: dict[str, Any] = json.load(response)
                return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise AssistantError(f"O Ollama recusou o pedido: {detail}") from exc
        except TimeoutError as exc:
            raise AssistantError(
                "A IA demorou demais para responder. Tente um modelo menor nas Configurações."
            ) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise AssistantError(f"Não foi possível falar com o Ollama: {exc}") from exc


def build_prompt(report: AuditReport) -> str:
    """The audit as compact JSON, already prioritised and with numbers pre-formatted.

    Small models mix up figures between items when they have to assemble them, so every
    field the summary needs ("onde", "impacto") is ready to copy, one item per priority.
    """
    actionable = [f for f in report.findings if f.severity != Severity.INFO]
    priorities = [
        {
            "numero": n,
            "problema": f.title,
            "gravidade": SEVERITY_LABELS[f.severity],
            "quantidade": f.count,
            "impacto": brl(f.impact) if f.impact else "não estimado",
            "onde": where(f.issues),
            "exemplo": f.issues[0].detail,
            "por_que_importa": f.explanation,
        }
        for n, f in enumerate(actionable[:MAX_PRIORITIES], start=1)
    ]
    normal = [f"{f.title} ({f.count})" for f in report.findings if f.severity == Severity.INFO]
    payload = {
        "visao_geral": overview(report),
        "prioridades": priorities,
        "pode_ser_normal": normal,
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)


def overview(report: AuditReport) -> str:
    """The opening sentence, computed here: left to itself the model "totals" impacts wrongly."""
    scope = f"na competência {report.period}" if report.period else "em todas as competências"
    errors, warnings = report.count(Severity.ERROR), report.count(Severity.WARNING)
    if not errors and not warnings:
        return f"Conferi {number(report.records_checked)} registros {scope} e não achei problemas."

    def plural(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"

    parts = [
        plural(errors, "tipo de erro provável", "tipos de erro provável") if errors else "",
        plural(warnings, "ponto para conferir", "pontos para conferir") if warnings else "",
    ]
    found = " e ".join(p for p in parts if p)
    return f"Conferi {number(report.records_checked)} registros {scope} e encontrei {found}."


def where(issues: list[Issue], limit: int = 4) -> str:
    """Where to look, e.g. "aba LANÇAMENTOS, linhas 806, 1234, 369 e mais 7"."""
    rows: dict[tuple[str, str], list[int]] = {}
    for issue in issues:
        if issue.ref:
            rows.setdefault((issue.ref.file, issue.ref.tab), []).append(issue.ref.row)
    if not rows:
        return ", ".join(sorted({i.who for i in issues})[:limit])
    several_files = len({file for file, _ in rows}) > 1
    parts = []
    for (file, tab), numbers in rows.items():
        shown = ", ".join(str(n) for n in numbers[:limit])
        more = f" e mais {len(numbers) - limit}" if len(numbers) > limit else ""
        label = "linha" if len(numbers) == 1 else "linhas"
        prefix = f"{file}, " if several_files else ""
        parts.append(f"{prefix}aba {tab}, {label} {shown}{more}")
    return "; ".join(parts)
