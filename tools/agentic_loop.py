# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Agentic test loop: diagnose failures, propose fixes, await human approval."""
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic
import ollama

from tools.baseline_monitor import check_run
from tools.diagnosis_log import log_diagnosis
from tools.telemetry_logger import DB_PATH as FLEET_DB
# Canonical map lives in the nav_fleet package (Session 15) — the workspace overlay
# (auto-sourced by .bashrc) normally makes it importable here. Fall back to importing
# from source when the overlay isn't inherited (e.g. a non-interactive shell — see
# CLAUDE.md's ANTHROPIC_API_KEY gotcha for why .bashrc sourcing can't be relied on there).
try:
    from nav_fleet.semantic_map import SEMANTIC_MAP
except ModuleNotFoundError:  # no colcon overlay (non-interactive shell) — import from source
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src' / 'nav_fleet'))
    from nav_fleet.semantic_map import SEMANTIC_MAP

client = anthropic.Anthropic()

NAV2_PARAMS_PATH = Path(__file__).resolve().parent.parent / 'src' / 'nav_fleet' / 'config' / 'nav2_params.yaml'

OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:14b-instruct')


def load_nav2_params_text(path=NAV2_PARAMS_PATH):
    """Raw text of the real nav2_params.yaml — injected into diagnose()'s prompt so
    the model reads actual current values instead of inferring them from memory (the
    bug: Claude once claimed 0.55 for inflation_radius when the real value is 0.25).
    Direct context injection, no RAG — matches this project's standing decision."""
    return Path(path).read_text()


TOOLS = [
    {
        'name': 'propose_nav_param_change',
        'description': 'Propose a change to nav2_params.yaml to address a navigation failure.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'param_path': {'type': 'string', 'description': 'Dot-separated param key'},
                'current_value': {'type': 'string'},
                'proposed_value': {'type': 'string'},
                'rationale': {'type': 'string'},
            },
            'required': ['param_path', 'proposed_value', 'rationale'],
        },
    },
    {
        'name': 'generate_world_variant',
        'description': (
            'Generate a new SDF world file with different obstacle positions '
            'for broader test coverage.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'variant_name': {'type': 'string'},
                'obstacle_layout': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'name': {'type': 'string'},
                            'x': {'type': 'number'},
                            'y': {'type': 'number'},
                            'size_x': {'type': 'number'},
                            'size_y': {'type': 'number'},
                        },
                    },
                },
                'rationale': {'type': 'string'},
            },
            'required': ['variant_name', 'obstacle_layout', 'rationale'],
        },
    },
    {
        'name': 'propose_mission_plan',
        'description': (
            'Generate a sequence of Nav2 goal poses from a natural language mission description. '
            'Prefer named locations from SEMANTIC_MAP over raw coordinates.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'mission_description': {'type': 'string'},
                'goals': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'location': {
                                'type': 'string',
                                'description': 'Named location from SEMANTIC_MAP, or "custom"',
                            },
                            'label': {
                                'type': 'string',
                                'description': 'Human-readable step label',
                            },
                            'x': {'type': 'number', 'description': 'Only if location is "custom"'},
                            'y': {'type': 'number', 'description': 'Only if location is "custom"'},
                        },
                        'required': ['location', 'label'],
                    },
                },
                'rationale': {'type': 'string'},
            },
            'required': ['mission_description', 'goals', 'rationale'],
        },
    },
]


def _to_ollama_tools(tools):
    """Anthropic-shaped TOOLS -> Ollama/OpenAI function-calling shape. Does not
    mutate the input list."""
    return [
        {
            'type': 'function',
            'function': {
                'name': t['name'],
                'description': t['description'],
                'parameters': t['input_schema'],
            },
        }
        for t in tools
    ]


@dataclass
class _TextBlock:
    text: str
    type: str = 'text'


@dataclass
class _ToolUseBlock:
    name: str
    input: dict
    type: str = 'tool_use'


@dataclass
class _DiagnosisResponse:
    content: list


def _validate_ollama_tool_proposal(name, args, tools_by_name):
    """Shared validation for a (tool name, args) pair proposed by Ollama, used by
    the JSON-prompted fallback below. Raises RuntimeError with an actionable message
    on any mismatch; returns None on success."""
    if name not in tools_by_name:
        raise RuntimeError(
            f'Ollama model {OLLAMA_MODEL!r} proposed an unknown tool '
            f'{name!r} — expected one of {sorted(tools_by_name)}.'
        )
    if not isinstance(args, dict):
        raise RuntimeError(
            f'Ollama model {OLLAMA_MODEL!r} returned non-object tool-call '
            f'arguments for {name!r}: {args!r}'
        )
    required = tools_by_name[name]['input_schema'].get('required', [])
    missing = [key for key in required if key not in args]
    if missing:
        raise RuntimeError(
            f'Ollama model {OLLAMA_MODEL!r} omitted required argument(s) '
            f'{missing} for tool {name!r}: got {args!r}'
        )


def _diagnose_ollama_json_fallback(prompt, tools_by_name):
    """Root cause (confirmed 2026-07-29 by direct reproduction against the live
    model): qwen2.5:14b-instruct reliably invokes a tool via Ollama's native
    tool-calling for short prompts, but silently degrades to free-text-only analysis
    once the real diagnose() prompt's full nav2_params.yaml injection (~16K chars) is
    included — no error, just no tool_calls. Native tool-calling and structured JSON
    output are two different code paths in Ollama/llama.cpp; the JSON-constrained
    decoder (format='json') holds up where native tool-calling silently drops. This
    is the 'Approach C' fallback parked in the 2026-07-28 design spec, built now that
    the validation harness (indirectly) and this live failure have shown native
    tool-calling is unreliable for this model/prompt combination."""
    schema_text = json.dumps(
        {name: t['input_schema'] for name, t in tools_by_name.items()}, indent=2
    )
    fallback_prompt = f"""{prompt}

Respond with ONLY a single JSON object (no other text, no markdown fences) in this
exact shape:
{{"tool": "<one of {sorted(tools_by_name)}>", "input": {{...fields matching that tool's schema below...}}}}

Tool schemas:
{schema_text}"""

    try:
        result = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': fallback_prompt}],
            format='json',
        )
    except Exception as exc:
        raise RuntimeError(
            f'Ollama model {OLLAMA_MODEL!r} did not propose a tool call for this '
            f'prompt (native tool-calling returned no proposal, and the JSON-prompted '
            f'fallback failed to reach Ollama: {exc}).'
        ) from exc

    try:
        parsed = json.loads(result.message.content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f'Ollama model {OLLAMA_MODEL!r} did not propose a tool call for this '
            f'prompt (native tool-calling returned no proposal, and the JSON-prompted '
            f'fallback returned non-JSON content: {result.message.content!r}).'
        ) from exc

    name = parsed.get('tool') if isinstance(parsed, dict) else None
    args = parsed.get('input') if isinstance(parsed, dict) else None
    if name is None:
        raise RuntimeError(
            f'Ollama model {OLLAMA_MODEL!r} did not propose a tool call for this '
            f'prompt (JSON-prompted fallback response had no "tool" key: {parsed!r}).'
        )
    _validate_ollama_tool_proposal(name, args, tools_by_name)
    return _ToolUseBlock(name=name, input=dict(args))


def _diagnose_ollama(prompt):
    ollama_tools = _to_ollama_tools(TOOLS)
    tools_by_name = {t['name']: t for t in TOOLS}
    try:
        result = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            tools=ollama_tools,
        )
    except Exception as exc:
        if 'not found' in str(exc).lower():
            raise RuntimeError(
                f"Model {OLLAMA_MODEL!r} isn't pulled locally — run "
                f"`ollama pull {OLLAMA_MODEL}`."
            ) from exc
        raise RuntimeError(
            "Couldn't reach Ollama — is it running? Start it with `ollama serve` "
            "(or check `systemctl status ollama`), then retry."
        ) from exc

    blocks = []
    if result.message.content:
        blocks.append(_TextBlock(text=result.message.content))
    for call in (result.message.tool_calls or []):
        name = call.function.name
        if name not in tools_by_name:
            raise RuntimeError(
                f'Ollama model {OLLAMA_MODEL!r} proposed an unknown tool '
                f'{name!r} — expected one of {sorted(tools_by_name)}.'
            )
        args = call.function.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f'Ollama model {OLLAMA_MODEL!r} returned malformed tool-call '
                    f'arguments for {name!r}: {args!r}'
                ) from exc
        if not isinstance(args, dict):
            raise RuntimeError(
                f'Ollama model {OLLAMA_MODEL!r} returned non-object tool-call '
                f'arguments for {name!r}: {args!r}'
            )
        required = tools_by_name[name]['input_schema'].get('required', [])
        missing = [key for key in required if key not in args]
        if missing:
            raise RuntimeError(
                f'Ollama model {OLLAMA_MODEL!r} omitted required argument(s) '
                f'{missing} for tool {name!r}: got {args!r}'
            )
        blocks.append(_ToolUseBlock(name=name, input=dict(args)))

    if not any(isinstance(b, _ToolUseBlock) for b in blocks):
        blocks.append(_diagnose_ollama_json_fallback(prompt, tools_by_name))
    return _DiagnosisResponse(content=blocks)


def load_latest_run(db_path=FLEET_DB):
    """Load the most recent row from the `runs` table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    if row is None:
        raise FileNotFoundError(f'No runs found in {db_path}')
    return dict(row)


def resolve_goals(goals):
    """Resolve named locations to (x, y) coordinates."""
    resolved = []
    for g in goals:
        loc = g.get('location', 'custom')
        if loc in SEMANTIC_MAP:
            x, y = SEMANTIC_MAP[loc]
        else:
            x, y = g.get('x', 0.0), g.get('y', 0.0)
        resolved.append({'x': x, 'y': y, 'label': g.get('label', loc)})
    return resolved


def evaluate_diagnosis_items(response, nav2_params_text=None):
    """Turns a diagnose() response into a display-ready, UNIFIED list of
    recommendation items — both formally submitted tool calls AND best-effort
    extracted from the free-text narrative (2026-07-29 third-round rebuild: Mike's
    first review of the two-source split caught that a real submitted item and
    several prose-only recommendations looked like two disconnected things with no
    way to tell how they related — now every recommendation the model produced
    lands in ONE list, each tagged with where it came from).

    Returns one dict per recommendation, in order (submitted items first, then
    extracted ones): {'tool_name', 'input', 'auto_verdict', 'auto_notes', 'source',
    'title'}. `source` is `'submitted'` (a real tool_use block) or `'extracted'`
    (parsed from prose by extract_prose_recommendations — best-effort, may be
    incomplete). `title` is a human-readable label: the model's own nearby heading
    for extracted items, None for submitted items (callers derive their own display
    title from the real structured fields).

    auto_verdict is one of, computed identically regardless of source — extracted
    items get the SAME fact-check as real ones, which is the whole point (checking
    existence works even without a current_value claim, which is the common case for
    prose-written recommendations — see _evaluate_one_item):
      'good'       — propose_nav_param_change whose param exists in the real
                     nav2_params.yaml, and whose current_value claim (if any) matches
                     it; no conflicting sibling item.
      'bad'        — propose_nav_param_change whose param isn't found in the real
                     file at all, or whose current_value claim doesn't match it.
                     Takes priority over 'conflict' when both apply — a fact-check
                     failure is the more objective, more important finding.
      'conflict'   — two or more propose_nav_param_change items (matched by leaf
                     param name, regardless of source) propose different values for
                     what's effectively the same parameter.
      'unverified' — any other tool (propose_mission_plan, generate_world_variant) —
                     nothing in the real config to fact-check a mission plan or world
                     layout against.

    Deliberately does not raise, retry, or hide anything — pure computation, nothing
    persisted here (see tools.diagnosis_log for the separate, system-driven auto-log).
    Works via duck typing (block.type/.name/.input) so it covers response.content
    from either backend — Anthropic SDK's ToolUseBlock and this module's own
    _ToolUseBlock both satisfy that shape.
    """
    if nav2_params_text is None:
        nav2_params_text = load_nav2_params_text()

    items = []
    for block in getattr(response, 'content', []):
        if getattr(block, 'type', None) != 'tool_use':
            continue
        evaluated = _evaluate_one_item(block.name, block.input, nav2_params_text)
        evaluated['source'] = 'submitted'
        evaluated['title'] = None
        items.append(evaluated)

    analysis_text = '\n'.join(
        block.text for block in getattr(response, 'content', [])
        if getattr(block, 'type', None) == 'text'
    ) or None
    for extracted in extract_prose_recommendations(analysis_text):
        evaluated = _evaluate_one_item(extracted['tool_name'], extracted['input'], nav2_params_text)
        evaluated['source'] = 'extracted'
        evaluated['title'] = extracted['title']
        items.append(evaluated)

    _detect_cross_item_conflicts(items)
    return items


def _evaluate_one_item(name, inputs, nav2_params_text):
    if name != 'propose_nav_param_change':
        return {'tool_name': name, 'input': inputs, 'auto_verdict': 'unverified',
                'auto_notes': None}

    param_path = inputs.get('param_path', '')
    leaf = param_path.rsplit('.', 1)[-1] if param_path else ''
    if not leaf:
        return {'tool_name': name, 'input': inputs, 'auto_verdict': 'good', 'auto_notes': None}

    # Existence check runs regardless of whether current_value was claimed — most
    # real-world prose recommendations never state one, so gating this behind
    # current_value (the old behavior) silently disabled the check almost every time.
    match = re.search(rf'(?<![\w.]){re.escape(leaf)}\s*:\s*(\S+)', nav2_params_text)
    if match is None:
        return {
            'tool_name': name, 'input': inputs, 'auto_verdict': 'bad',
            'auto_notes': (
                f'⚠ param {leaf!r} (from param_path {param_path!r}) was not '
                f'found anywhere in the real nav2_params.yaml — the model may have '
                f'fabricated this parameter.'
            ),
        }

    current_value = inputs.get('current_value')
    if current_value is None:
        return {'tool_name': name, 'input': inputs, 'auto_verdict': 'good', 'auto_notes': None}

    real_value = match.group(1).rstrip(',')
    if not _nav_param_values_match(current_value, real_value):
        return {
            'tool_name': name, 'input': inputs, 'auto_verdict': 'bad',
            'auto_notes': (
                f'⚠ claimed current_value {current_value!r} for {leaf!r} does '
                f'not match the real nav2_params.yaml value {real_value!r} — '
                f'verify before applying.'
            ),
        }

    return {'tool_name': name, 'input': inputs, 'auto_verdict': 'good', 'auto_notes': None}


def _detect_cross_item_conflicts(items):
    """Mutates items in place: groups propose_nav_param_change items by leaf param
    name, flags any group with more than one distinct proposed_value as 'conflict' —
    unless an item already failed its own fact check ('bad' takes priority, see
    evaluate_diagnosis_items's docstring)."""
    by_leaf = {}
    for idx, item in enumerate(items):
        if item['tool_name'] != 'propose_nav_param_change':
            continue
        param_path = item['input'].get('param_path', '')
        leaf = param_path.rsplit('.', 1)[-1] if param_path else ''
        if not leaf:
            continue
        by_leaf.setdefault(leaf, []).append(idx)

    for leaf, indices in by_leaf.items():
        proposed_values = {items[i]['input'].get('proposed_value') for i in indices}
        if len(proposed_values) <= 1:
            continue  # they agree — not a conflict
        for i in indices:
            if items[i]['auto_verdict'] == 'bad':
                continue  # fact-check failure takes priority over conflict
            others = [j for j in indices if j != i]
            items[i]['auto_verdict'] = 'conflict'
            items[i]['auto_notes'] = (
                f'⚠ disagrees with recommendation(s) {others} for the same '
                f'parameter ({leaf!r}) — proposed values: '
                f'{sorted(proposed_values)}.'
            )


_EXTRACT_FIELD_ALIASES = {
    'propose_nav_param_change': {
        'param_path': ['param_path', 'parameter', 'param', 'parameter_name'],
        'current_value': ['current_value'],
        'proposed_value': ['proposed_value', 'new_value', 'value'],
        'rationale': ['rationale', 'reason', 'explanation'],
    },
    'propose_mission_plan': {
        'mission_description': ['mission_description', 'description', 'mission',
                                 'mission_name'],
        'rationale': ['rationale', 'reason', 'explanation'],
    },
    'generate_world_variant': {
        'variant_name': ['variant_name', 'name'],
        'rationale': ['rationale', 'reason', 'explanation'],
    },
}


def extract_prose_recommendations(analysis_text):
    """Best-effort parser (2026-07-29, third-round fix): the model consistently
    writes UNSUBMITTED recommendations inside its own free text — observed live in
    THREE distinct formats so far: kwargs-style (`tool_name(key=value, ...)`),
    colon-style positional (`tool_name(a:b:c)`), and a flat JSON object
    (`{"tool": "tool_name", ...}`). Extracts each into the same {'tool_name',
    'input'} shape evaluate_diagnosis_items already knows how to fact-check, plus a
    best-effort 'title' from the nearby text — callers tag these 'source':
    'extracted' to distinguish them from real submitted tool calls.

    Explicitly tied to this model's CURRENT writing habits — a differently-formatted
    response may not be caught, and this is not claimed as a general-purpose code
    parser. Never raises and never silently drops a found call: an unparseable body
    still produces an item (title + tool_name, input falls back to {'raw_text': ...})
    so its EXISTENCE stays visible even when its details can't be extracted.
    """
    if not analysis_text:
        return []

    tool_names = [t['name'] for t in TOOLS]
    tool_alternation = '|'.join(re.escape(n) for n in tool_names)
    matches = []  # (start_pos, item_dict) — sorted into text order before returning

    call_start = re.compile(r'\b(' + tool_alternation + r')\s*\(')
    for m in call_start.finditer(analysis_text):
        tool_name = m.group(1)
        open_idx = m.end() - 1
        close_idx = _find_balanced_close_paren(analysis_text, open_idx)
        body = analysis_text[open_idx + 1:close_idx - 1]
        title = _extract_nearby_title(analysis_text, m.start())
        raw_pairs = _parse_kwargs_body(body)
        parsed_input = _normalize_extracted_fields(tool_name, raw_pairs, body)
        matches.append((m.start(), {'tool_name': tool_name, 'input': parsed_input, 'title': title}))

    # Balanced-brace scan (not a flat regex) — 2026-07-29, 4th real format found
    # live: the model sometimes wraps args in a NESTED "parameters" sub-object
    # ({"tool": "...", "parameters": {...}}), which a regex assuming a flat object
    # (no nested {}) silently matches zero of. Try every '{' as a candidate open;
    # cheap to do (a handful of braces in a short response) and correctly handles
    # arbitrary nesting depth via real brace-balance tracking, not regex lookahead.
    for idx, ch in enumerate(analysis_text):
        if ch != '{':
            continue
        close_idx = _find_balanced_close_brace(analysis_text, idx)
        span = analysis_text[idx:close_idx]
        try:
            parsed = json.loads(span)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        tool_name = parsed.get('tool')
        if tool_name not in tool_names:
            continue
        fields = {k: v for k, v in parsed.items() if k != 'tool'}
        for wrapper_key in ('parameters', 'input', 'args'):
            nested = fields.pop(wrapper_key, None)
            if isinstance(nested, dict):
                fields.update(nested)
        title = _extract_nearby_title(analysis_text, idx)
        raw_pairs = {k: (v if isinstance(v, str) else str(v)) for k, v in fields.items()}
        parsed_input = _normalize_extracted_fields(tool_name, raw_pairs, '')
        matches.append((idx, {'tool_name': tool_name, 'input': parsed_input, 'title': title}))

    matches.sort(key=lambda pair: pair[0])
    return [item for _, item in matches]


def _find_balanced_close_paren(text, open_idx):
    depth = 0
    i = open_idx
    while i < len(text):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)  # unbalanced (shouldn't normally happen) — take the rest


def _find_balanced_close_brace(text, open_idx):
    """Same as _find_balanced_close_paren but for {}. A separate function, not a
    shared parameterized one — string literals inside JSON can legally contain '('
    or ')' without needing balance tracking, but this scan is specifically for JSON
    object nesting, a different concern from the paren-call scan above."""
    depth = 0
    i = open_idx
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


_CODE_FENCE_LINE = re.compile(r'^```\s*\w*\s*$')       # ``` or ```python etc.
_PUNCTUATION_ONLY_LINE = re.compile(r'^[`)\](}>\-*#\s]*$')  # stray brackets, rules
# Generic structural headings the model reuses across items — not item-specific,
# so grabbing one as "the title" is worse than no title (live bug, 2026-07-29:
# 'GOOD — Recommendations' on the real page, meaningless to a reader).
_GENERIC_SECTION_HEADINGS = {
    'recommendations', 'metrics analysis', 'analysis', 'summary', "model's written analysis",
}


def _is_title_junk_line(line):
    if _CODE_FENCE_LINE.match(line) or _PUNCTUATION_ONLY_LINE.match(line):
        return True
    normalized = line.strip('#*: ').strip().lower()
    return normalized in _GENERIC_SECTION_HEADINGS


def _extract_nearby_title(text, call_start_idx, lookback=5):
    """Best-effort: scans backward through up to `lookback` non-blank lines before
    the call, skipping "junk" lines (markdown code fences like ```python, and
    stray leftover punctuation like a lone ')' from a PRIOR multi-line call) that
    aren't real titles, and returns the first line that looks like a heading rather
    than a sentence fragment. Returns None if nothing suitable is found within the
    lookback window — a missing title is honest; a junk one (2026-07-29 live bugs:
    '```python', ')') is worse than none."""
    preceding = text[:call_start_idx]
    lines = [l.strip() for l in preceding.splitlines() if l.strip()]
    for line in reversed(lines[-lookback:]):
        if _is_title_junk_line(line):
            continue
        candidate = line.strip('#*: ').strip()
        if candidate and len(candidate) <= 80 and not candidate.endswith('.'):
            return candidate
        return None  # nearest real line exists but doesn't look like a title
    return None


def _parse_kwargs_body(body):
    """Parses key=value pairs from a call body (handles quoted strings and simple
    bracketed lists as single opaque values). Returns {} if the body isn't
    kwargs-shaped at all (e.g. colon-style positional args) — that's expected and
    handled by _normalize_extracted_fields's fallback, not an error here."""
    pairs = {}
    for m in re.finditer(
        r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\[[^\]]*\]|[-\w./]+)',
        body,
    ):
        key, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        pairs[key] = value
    return pairs


def _normalize_extracted_fields(tool_name, raw_pairs, body):
    aliases = _EXTRACT_FIELD_ALIASES.get(tool_name, {})
    normalized = {}
    for field, alias_list in aliases.items():
        for alias in alias_list:
            if alias in raw_pairs:
                normalized[field] = raw_pairs[alias]
                break

    if tool_name == 'propose_nav_param_change':
        if 'component' in raw_pairs and 'param_path' in normalized:
            normalized['param_path'] = f"{raw_pairs['component']}.{normalized['param_path']}"
        elif not normalized.get('param_path') and '=' not in body:
            # Colon-style positional: component[:subcomponent...]:param:value
            segments = [s.strip() for s in body.split(':') if s.strip()]
            if len(segments) >= 3:
                *path_parts, value = segments
                normalized['param_path'] = '.'.join(path_parts)
                normalized['proposed_value'] = value

    if not normalized and body.strip():
        normalized['raw_text'] = body.strip()
    return normalized


def _nav_param_values_match(claimed, real):
    try:
        return float(claimed) == float(real)
    except (TypeError, ValueError):
        return str(claimed) == str(real)


def diagnose(run_data, db_path=FLEET_DB, trend_context=None, backend=None, source='cli'):
    """Call the configured backend (Ollama by default, or Claude — see backend=/
    AGENTIC_BACKEND) with telemetry + drift context; get structured diagnosis and
    proposed action.

    Auto-logs the call to tools.diagnosis_log (2026-07-29 design) — system-driven,
    happens every time, no separate save action, same lifecycle as
    tools.telemetry_logger.log_run(). `source` ('cli' default, dashboard/app.py passes
    'dashboard') is the only thing a caller needs to say about itself; everything else
    logged (backend, model, prompt, evaluated items, conflicts) is derived here.

    trend_context (Piece 5, optional): a plain-text summary from
    tools.baseline_monitor.build_trend_summary() — the dashboard's "Diagnose with AI"
    button feeds the currently-filtered view's big-picture trend here, not just this
    one run. None (the default) matches the original single-run CLI behavior exactly.
    """
    locations_str = '\n'.join(f'  {k}: {v}' for k, v in SEMANTIC_MAP.items())

    # Reuse the real drift detector (Session 12) instead of re-deriving pass/fail from
    # hardcoded thresholds — it compares against a rolling baseline of past PASS runs.
    drift_reports = check_run(run_data['id'], db_path=db_path)
    if drift_reports:
        drift_str = '\n'.join(
            f'  {r.metric}: current={r.current:.2f} baseline_mean={r.mean:.2f} '
            f'sigma={r.sigma:.1f} '
            + (f'FLAGGED ({r.severity})' if r.flagged else 'ok')
            for r in drift_reports
        )
    else:
        drift_str = '  Not enough baseline history yet (need 3+ prior PASS runs).'

    nav2_params_text = load_nav2_params_text()

    prompt = f"""You are an autonomous robotics test engineer.

The latest nav test run (id={run_data['id']}, scenario={run_data['scenario']},
result={run_data['result']}, sim_engine={run_data.get('sim_engine')}):
{json.dumps(run_data, indent=2)}

Drift report against the rolling baseline (config/drift_config.yaml sigma thresholds):
{drift_str}

The REAL current contents of src/nav_fleet/config/nav2_params.yaml — use these exact
values for `current_value` if proposing a param change. Do not guess or infer a
current value from memory or training data; read it from this text:
{nav2_params_text}
"""

    if trend_context:
        prompt += f"""
Big-picture trend context across the currently-filtered dashboard view (not just this
one run):
{trend_context}
"""

    prompt += f"""
Available named locations in this environment (use these in mission plans):
{locations_str}

Respond in two clearly separate parts:

1. Metrics Analysis (prose): briefly explain what's flagged and why, in plain language.
This text is shown to a human for context only — it is never programmatically trusted or
acted on, so do not put anything here that needs to be applied.

2. Recommendations (structured, one tool call per recommendation): for every concrete
action you recommend, submit it as its own tool call — call propose_nav_param_change once
per parameter you want changed, propose_mission_plan for a mission suggestion, or
generate_world_variant for a harder world. Call as many tools as you have recommendations
for — do not describe an actionable recommendation only in the Metrics Analysis prose; if
it isn't submitted as its own tool call, it will not be reviewed. If nothing is flagged,
use propose_mission_plan with semantic location names to create a more challenging
multi-waypoint mission (e.g. "visit the bedroom goal, then the desk, then return to
home_base") or use generate_world_variant to propose a harder obstacle layout."""

    backend = backend or os.environ.get('AGENTIC_BACKEND', 'ollama')
    if backend == 'claude':
        response = _diagnose_claude(prompt)
        model_name = 'claude-sonnet-5'
    elif backend == 'ollama':
        response = _diagnose_ollama(prompt)
        model_name = OLLAMA_MODEL
    else:
        raise ValueError(f"unknown AGENTIC_BACKEND {backend!r} — expected 'claude' or 'ollama'")

    items = evaluate_diagnosis_items(response, nav2_params_text)
    analysis_text = '\n'.join(
        block.text for block in getattr(response, 'content', [])
        if getattr(block, 'type', None) == 'text'
    ) or None
    conflict_notes = [i['auto_notes'] for i in items if i['auto_verdict'] == 'conflict']
    log_diagnosis(
        backend=backend, model_name=model_name, source=source, prompt_text=prompt,
        analysis_text=analysis_text, items=items, conflict_notes=conflict_notes or None,
        run_id=run_data.get('id'), db_path=db_path,
    )
    return response


def summarize_diagnosis(items):
    """Code-generated Summary content (2026-07-29, third-round rebuild) — a real
    tally instead of a single terse audit line. Supersedes build_conflict_notes /
    detect_narrative_item_mismatch: now that extract_prose_recommendations turns
    every prose mention into a real, fact-checked item, "mentioned vs. submitted" is
    just the 'source' field on each item rather than a separate count to compute.

    Returns a list of human-readable lines, always non-empty — callers print/render
    each line, then append their own fixed closing sentence."""
    if not items:
        return ['No recommendations were found in this response — nothing to review.']

    submitted = [i for i in items if i['source'] == 'submitted']
    extracted = [i for i in items if i['source'] == 'extracted']
    counts = {'good': 0, 'bad': 0, 'conflict': 0, 'unverified': 0}
    for i in items:
        counts[i['auto_verdict']] += 1

    lines = [
        f"{len(items)} recommendation(s) found — {len(submitted)} formally submitted, "
        f"{len(extracted)} found only in the written text above (best-effort extraction, "
        f"not formally submitted).",
        f"✅ {counts['good']} good · ❌ {counts['bad']} bad · "
        f"⚠ {counts['conflict']} conflicting · ➖ {counts['unverified']} unverified.",
    ]

    for item in items:
        if item['auto_verdict'] == 'conflict':
            lines.append(item['auto_notes'])

    if extracted:
        titles = [i['title'] or i['tool_name'] for i in extracted]
        lines.append(
            f"⚠ {len(extracted)} of the above were only written in the text, never "
            f"formally submitted for review: {', '.join(titles)}."
        )

    return lines


def _diagnose_claude(prompt):
    return client.messages.create(
        model='claude-sonnet-5',
        max_tokens=2048,
        tools=TOOLS,
        messages=[{'role': 'user', 'content': prompt}],
    )


def apply_world_variant(layout, name):
    """Write a new SDF world file from the proposed obstacle layout."""
    obstacles_sdf = ''
    for obs in layout:
        obstacles_sdf += f"""
    <model name="{obs['name']}">
      <static>true</static>
      <pose>{obs['x']} {obs['y']} 0.25 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>{obs['size_x']} {obs['size_y']} 0.5</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>{obs['size_x']} {obs['size_y']} 0.5</size></box></geometry>
          <material><diffuse>0.5 0.3 0.1 1</diffuse></material>
        </visual>
      </link>
    </model>"""

    world_path = Path(f'src/nav_fleet/worlds/{name}.sdf')
    # Read the base world template and inject obstacles
    base = Path('src/nav_fleet/worlds/bedroom_simple.sdf').read_text()
    # Insert before </world>
    new_world = base.replace('  </world>', obstacles_sdf + '\n  </world>')
    world_path.write_text(new_world)
    print(f'[agentic] Created world variant: {world_path}')
    return world_path


def human_approval(action_type, details):
    """Print the proposed action and ask for human approval."""
    separator = '=' * 60
    print(f'\n{separator}')
    print(f'PROPOSED ACTION: {action_type}')
    print(json.dumps(details, indent=2))
    print(separator)
    answer = input('\nApprove? [y/N]: ').strip().lower()
    return answer == 'y'


_VERDICT_BADGE = {'good': '✅', 'bad': '❌', 'conflict': '⚠', 'unverified': '➖'}


def run_loop():
    run_data = load_latest_run()
    print(f"[agentic] Loaded run {run_data['id']}: "
          f"{run_data['scenario']} ({run_data['result']})")

    response = diagnose(run_data)  # auto-logs internally (tools.diagnosis_log)

    analysis_text = '\n'.join(
        block.text for block in response.content if block.type == 'text') or None
    if analysis_text:
        print(f'\n[Metrics Analysis]\n{analysis_text}')

    items = evaluate_diagnosis_items(response)

    print('\n[Recommendations]')
    for i, item in enumerate(items):
        badge = _VERDICT_BADGE[item['auto_verdict']]
        tag = 'submitted' if item['source'] == 'submitted' else 'TEXT ONLY, not submitted'
        title = item['title'] or item['tool_name']
        print(f'  [{i}] {badge} {title} — {item["auto_verdict"]} ({tag})')
        why = item['input'].get('rationale')
        if why:
            print(f'      Why: {why}')
        print(f'      {json.dumps(item["input"])}')
        if item['auto_notes']:
            print(f'      {item["auto_notes"]}')

    print('\n[Summary]')
    for line in summarize_diagnosis(items):
        print(f'  {line}')
    print('  Please review proposed actions and provide feedback to project owner.')

    # Only formally SUBMITTED items are safe to approve/apply — extracted items are
    # a best-effort text parse, not schema-validated, and shouldn't be actioned as if
    # they went through the real tool-calling path.
    submitted_items = [item for item in items if item['source'] == 'submitted']
    for i, item in enumerate(submitted_items):
        tool = item['tool_name']
        inputs = item['input']
        print(f"\n[agentic] Recommendation [{i}] ({item['auto_verdict']}): {tool}")

        if not human_approval(tool, inputs):
            print('[agentic] Proposal rejected by human. Skipping.')
            continue

        if tool == 'generate_world_variant':
            path = apply_world_variant(inputs['obstacle_layout'], inputs['variant_name'])
            # Honest instruction (S17 review CR-11a): the launch files hardcode
            # bedroom_simple.sdf — there is no world:= argument yet (a `world` launch
            # arg is R2 NL->world territory). Until then, running a variant means
            # pointing the launch at it by hand.
            print(f'[agentic] World variant created at {path}. To run it, edit '
                  f'src/nav_fleet/launch/sim_only_launch.py world_path to point at '
                  f'this file (no world:= launch argument exists yet).')

        elif tool == 'propose_nav_param_change':
            print('[agentic] Apply this change to src/nav_fleet/config/nav2_params.yaml:')
            print(f'  {inputs["param_path"]}: {inputs["proposed_value"]}')
            print(f'  Rationale: {inputs["rationale"]}')

        elif tool == 'propose_mission_plan':
            resolved = resolve_goals(inputs['goals'])
            plan = {**inputs, 'goals_resolved': resolved}
            plan_path = Path('reports/mission_plan.json')
            plan_path.write_text(json.dumps(plan, indent=2))
            print(f'[agentic] Mission plan saved to {plan_path}')
            print(f'  Mission: {inputs["mission_description"]}')
            for step in resolved:
                print(f'    → {step["label"]}: ({step["x"]}, {step["y"]})')


if __name__ == '__main__':
    run_loop()
