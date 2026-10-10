"""Runtime model configuration: generator and judge families.

@implements: DEC-07
@implements: DEC-24
@grounded_by: REF-24, ADD-16

Architecture.md Section 7 (decided 2026-07-08): the generator (extraction,
alignment, runtime generation) runs on OpenAI; the three judges (extraction,
mapping, runtime grounding) run on an independent non-OpenAI family
(Anthropic Claude), because same-family judges have correlated failure modes.

All model ids and keys are config values, never hardcoded. Missing
configuration fails fast with a clear message; the pipeline must never fall
back silently to a default model (no silent degradation, Section 13).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class ModelConfigError(RuntimeError):
    """Raised when required model configuration is absent."""


class ConfigurationError(ModelConfigError):
    """A model's declared parameters are missing, malformed or refused (spec F
    D-F29). A subclass of ModelConfigError, so every caller that turns a
    missing key into a clean refusal does the same for a declaration."""


class DeclaredParameterRefused(ConfigurationError):
    """The inference backend (a 400 naming the parameter) or its SDK (a refusal before
    sending) refused a parameter the table declares: a configuration error that
    stops the run, never a fallback (spec F D-F29)."""

    def __init__(self, inference_backend: str, model: str, parameter: str, value: str, detail: str):
        # one sentence shape in both repositories (review X-M1)
        super().__init__(
            f"configuration error: {inference_backend}:{model} refused the declared {parameter} {value} "
            f"({detail}); correct its row in {MODEL_PARAMETERS_FILE}"
        )
        self.inference_backend, self.model, self.parameter, self.value = inference_backend, model, parameter, value


# OpenAI-family name markers. The judge must not be any of these (DEC-07:
# same-family generator and judge have correlated failure modes). This is a
# deny-list, so it cannot prove family disjointness for an unknown vendor
# name; the generator-is-not-judge checks below close the most dangerous
# gap (the generator grading its own output) regardless of naming.
_OPENAI_FAMILY_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt", "openai", "davinci")

# Effort is part of the instrument (spec F D-F22, 2026-09-24): a model
# name alone does not say what ran, since Opus 5.5's API default is
# medium and a run at another level is another instrument. The vocabulary
# is closed so every table names an instrument the same way; the same
# five words are the dashboard's EFFORT_LEVELS.
EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

# Spec F D-F29 (2026-09-27): temperature, effort and JSON mode are declared per
# model before the experiment, from the model developer's documentation, and sent as
# declared; nothing is probed or learned. The table is keyed by model id and
# selects nothing: .env still names the models (architecture.md Section 7).
NOT_APPLICABLE = "N/A"
TEMPERATURE_VALUES: tuple[str, ...] = ("0", NOT_APPLICABLE)
JSON_MODE_VALUES: tuple[str, ...] = ("sent", NOT_APPLICABLE)
INFERENCE_BACKENDS: tuple[str, ...] = ("openai", "anthropic")
# B158 (R1): the company that made a model, derived from the inference backend
# that serves it. Today each API serves only its own developer's models, so the
# derivation is the identity; a third backend (a cloud reseller) is one row here.
MODEL_DEVELOPER_OF: dict[str, str] = {"anthropic": "anthropic", "openai": "openai"}
MODEL_PARAMETERS_FILE = "config/model_parameters.json"
MODEL_PARAMETERS_PATH = Path(__file__).resolve().parents[3] / MODEL_PARAMETERS_FILE
MODEL_PARAMETERS_SCHEMA_VERSION = 1
# The two variables B84 introduced; since D-F29 the table holds the effort, so
# a leftover line would read as a setting that no longer applies.
RETIRED_EFFORT_VARIABLES: tuple[str, ...] = ("TERE4AI_GENERATOR_EFFORT", "TERE4AI_JUDGE_EFFORT")
_ROW_KEYS = frozenset({"inference_backend", "temperature", "effort", "json_mode", "documentation"})
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


@dataclass(frozen=True)
class ModelParameters:
    """One model's declared request parameters, a row of the table (spec F D-F29)."""

    model_id: str
    inference_backend: str
    temperature: str
    effort: str
    json_mode: str
    documentation_url: str
    documentation_read_on: str

    def as_row(self) -> dict[str, Any]:
        return {"inference_backend": self.inference_backend, "temperature": self.temperature, "effort": self.effort,
                "json_mode": self.json_mode,
                "documentation": {"url": self.documentation_url, "read_on": self.documentation_read_on}}


def model_parameters_digest(generator: ModelParameters, judge: ModelParameters) -> str:
    """SHA-256 of the two declarations in use, canonical JSON, documentation included."""
    rows = {"generator": {"model_id": generator.model_id, **generator.as_row()},
            "judge": {"model_id": judge.model_id, **judge.as_row()}}
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def model_developer_of(inference_backend: str) -> str:
    """The company that made the models an inference backend serves (B158, R1);
    refused for a backend the table does not name."""
    try:
        return MODEL_DEVELOPER_OF[inference_backend]
    except KeyError:
        raise ValueError(f"no model developer known for the inference backend {inference_backend!r}") from None


def _where(path: Path) -> str:
    """The table named in a message: its repository path, never an absolute one."""
    return MODEL_PARAMETERS_FILE if path == MODEL_PARAMETERS_PATH else path.name


def _row_problems(row: Any) -> list[str]:
    if not isinstance(row, dict):
        return ["the row is not an object"]
    problems: list[str] = []
    missing = sorted(_ROW_KEYS - set(row))
    unknown = sorted(set(row) - _ROW_KEYS - {"note"})
    if missing:
        problems.append("missing " + ", ".join(missing))
    if unknown:
        problems.append("unknown " + ", ".join(unknown))
    if row.get("inference_backend") not in INFERENCE_BACKENDS:
        problems.append(f"inference_backend must be one of {', '.join(INFERENCE_BACKENDS)}")
    if row.get("temperature") not in TEMPERATURE_VALUES:
        problems.append('temperature must be "0" or "N/A"')
    if row.get("effort") not in (*EFFORT_LEVELS, NOT_APPLICABLE):
        problems.append(f"effort must be one of {', '.join(EFFORT_LEVELS)} or \"N/A\"")
    if row.get("json_mode") not in JSON_MODE_VALUES:
        problems.append('json_mode must be "sent" or "N/A"')
    elif row.get("inference_backend") == "anthropic" and row.get("json_mode") != NOT_APPLICABLE:
        problems.append('json_mode must be "N/A" on an anthropic row: the judge client has no JSON mode parameter')
    doc = row.get("documentation")
    if not isinstance(doc, dict) or set(doc) != {"url", "read_on"} or not all(
            value is None or isinstance(value, str) for value in doc.values()):
        problems.append('documentation must be {"url": <string or null>, "read_on": <string or null>}')
    if "note" in row and not isinstance(row["note"], str):
        problems.append("note must be a string")
    return problems


def load_model_parameters(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """The table's rows keyed by model id, every row checked; raises
    ConfigurationError naming every malformed row at once."""
    path = path or MODEL_PARAMETERS_PATH
    where = _where(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigurationError(
            f"configuration error: {where} is missing; it declares each model's temperature, effort and "
            "JSON mode (spec F D-F29)") from None
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"configuration error: {where} cannot be read ({type(exc).__name__})") from None
    if (not isinstance(data, dict) or data.get("schema_version") != MODEL_PARAMETERS_SCHEMA_VERSION
            or not isinstance(data.get("models"), dict)):
        raise ConfigurationError(
            f"configuration error: {where} must hold schema_version {MODEL_PARAMETERS_SCHEMA_VERSION} and a "
            "models object keyed by model id")
    problems = [f"{model_id}: {problem}" for model_id, row in data["models"].items()
                for problem in _row_problems(row)]
    if problems:
        raise ConfigurationError(f"configuration error: {where} has malformed rows: " + "; ".join(problems))
    return data["models"]


def declaration_for(models: dict[str, dict[str, Any]], model_id: str, inference_backend: str,
                    where: str = MODEL_PARAMETERS_FILE) -> ModelParameters:
    """The declared parameters of one configured model, refused when the table has
    no row for it, the row names another inference backend, or the row does not yet name
    the documentation page and the day it was read."""
    row = models.get(model_id)
    if row is None:
        raise ConfigurationError(
            f"configuration error: {where} declares no row for model {model_id!r}; add one with its inference backend, "
            "temperature, effort, json_mode and the documentation page with the day it was read (spec F D-F29)")
    if row["inference_backend"] != inference_backend:
        raise ConfigurationError(
            f"configuration error: {where} declares {model_id!r} with inference backend "
            f"{row['inference_backend']}, but the {inference_backend} client is configured to use it")
    url, read_on = row["documentation"]["url"], row["documentation"]["read_on"]
    # the day as YYYY-MM-DD only: date.fromisoformat also reads a week date
    # ("2026-W39-1") and a basic date, which are not the day as written
    try:
        read_day = (date.fromisoformat(read_on)
                    if isinstance(read_on, str) and _ISO_DAY.fullmatch(read_on) else None)
    except ValueError:
        read_day = None
    try:
        page = urlsplit(url) if isinstance(url, str) else None
    except ValueError:  # an unparsable address ("https://[docs") is no page, refused by name below
        page = None
    if page is None or page.scheme != "https" or not page.hostname or read_day is None:
        raise ConfigurationError(
            f"configuration error: the row for {model_id!r} in {where} names no documentation page (https) or "
            "no day it was read (YYYY-MM-DD); read the model developer's documentation for this model, confirm the row "
            "and fill documentation.url and documentation.read_on (spec F D-F29)")
    return ModelParameters(model_id=model_id, inference_backend=inference_backend, temperature=row["temperature"],
                           effort=row["effort"], json_mode=row["json_mode"],
                           documentation_url=url, documentation_read_on=read_on)


def _retired_variables_error(env: Any) -> str | None:
    """The refusal sentence while a retired effort variable is set (ruling P4)."""
    retired = [name for name in RETIRED_EFFORT_VARIABLES if env.get(name)]
    if not retired:
        return None
    return (f"configuration error: {', '.join(retired)} is no longer read: each model's effort is declared in "
            f"{MODEL_PARAMETERS_FILE} (spec F D-F29); remove the line from .env and from the environment")


def runtime_judge_declaration(model_id: str | None, path: Path | None = None,
                              env: Any = None) -> dict[str, Any]:
    """The runtime judge's declared effort and temperature for the facade's
    health answer (spec F D-F29); null values with the reason when the model is
    not set, a retired effort variable is set (every paid path refuses then,
    review B101 3A-M11) or the table does not declare it, never a guess. env
    defaults to os.environ."""
    if not model_id:
        return {"model": None, "effort": None, "temperature": None,
                "declaration_error": "TERE4AI_JUDGE_MODEL is not set"}
    retired = _retired_variables_error(os.environ if env is None else env)
    if retired is not None:
        return {"model": model_id, "effort": None, "temperature": None, "declaration_error": retired}
    path = path or MODEL_PARAMETERS_PATH
    try:
        declared = declaration_for(load_model_parameters(path), model_id, "anthropic", _where(path))
    except ConfigurationError as exc:
        return {"model": model_id, "effort": None, "temperature": None, "declaration_error": str(exc)}
    return {"model": model_id, "effort": declared.effort, "temperature": declared.temperature,
            "declaration_error": None}


def assert_independent_judge(generator_model: str, judge_model: str) -> None:
    """Reject a judge that is not independent of the generator (DEC-07).

    Two failure modes: the judge is an OpenAI-family model (same family as
    the generator), or the judge is literally the same model id as the
    generator (the generator judging itself). Either collapses the control.
    """
    if judge_model.strip().lower().startswith(_OPENAI_FAMILY_PREFIXES):
        raise ModelConfigError(
            f"judge model {judge_model!r} looks like an OpenAI-family model; "
            "DEC-07 requires an independent non-OpenAI judge family."
        )
    if generator_model.strip().lower() == judge_model.strip().lower():
        raise ModelConfigError(
            f"generator and judge share the model id {generator_model!r}; "
            "DEC-07 requires an independent judge, not the generator judging "
            "its own output."
        )


def require_independent_clients(generator: object, judge: object) -> None:
    """Use-time guard against self-assessment (DEC-07).

    load_model_config enforces distinct model ids for production, but a
    programmatic caller can still pass one client object as both generator
    and judge, bypassing config. This catches that: the same object judging
    its own output is not a control. Distinct client objects that happen to
    share a model id (offline test stubs) are allowed here; production ids
    are already vetted at config load.
    """
    if generator is judge:
        raise ModelConfigError(
            "the same model client was passed as both generator and judge; "
            "DEC-07 requires an independent judge (self-assessment is not a "
            "control)."
        )


def load_dotenv_once() -> None:
    """Load the repo's .env into os.environ, never overriding an exported variable.

    Despite the name, this runs on every call, not once: there is no memo
    flag. Because it never overrides an already-exported variable, repeated
    calls are idempotent, so the health handler may call it on every poll
    and the paid path may call it on every run. Do not memoise; a cached
    "already loaded" flag would miss a .env edited between calls.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")


@dataclass(frozen=True)
class ModelConfig:
    """Pinned model configuration for one build or run."""

    generator_model: str
    judge_model: str
    generator_api_key: str
    judge_api_key: str
    generator_parameters: ModelParameters
    judge_parameters: ModelParameters

    def __post_init__(self) -> None:
        """Each model component's row is the row of its own model and inference
        backend, so a client never sends one model's id with another model's
        declaration."""
        problems = []
        for component, model_id, row, inference_backend in (
                ("generator", self.generator_model, self.generator_parameters, "openai"),
                ("judge", self.judge_model, self.judge_parameters, "anthropic")):
            if row.model_id != model_id:
                problems.append(f"the {component} model {model_id!r} is given the declared row of {row.model_id!r}")
            if row.inference_backend != inference_backend:
                problems.append(f"the {component} row for {row.model_id!r} names inference backend "
                                f"{row.inference_backend}, but the {component} client is {inference_backend}")
        if problems:
            raise ConfigurationError("configuration error: " + "; ".join(problems))

    @property
    def generator_effort(self) -> str:
        return self.generator_parameters.effort

    @property
    def judge_effort(self) -> str:
        return self.judge_parameters.effort

    @property
    def model_parameters_sha256(self) -> str:
        return model_parameters_digest(self.generator_parameters, self.judge_parameters)

    def as_public_dict(self) -> dict[str, str]:
        """Loggable form: model ids and the declared parameters, never keys. A
        resume compares this dict (graph_store/checkpoints.py), so a changed
        declaration refuses a resume by name (model_parameters_sha256)."""
        return {
            "generator_model": self.generator_model,
            "judge_model": self.judge_model,
            "generator_effort": self.generator_parameters.effort,
            "judge_effort": self.judge_parameters.effort,
            "generator_temperature": self.generator_parameters.temperature,
            "judge_temperature": self.judge_parameters.temperature,
            "generator_json_mode": self.generator_parameters.json_mode,
            "model_parameters_sha256": self.model_parameters_sha256,
        }


def load_model_config(env: dict[str, str] | None = None, parameters_path: Path | None = None) -> ModelConfig:
    """Load and validate the model configuration.

    env defaults to os.environ (after loading .env). Raises ModelConfigError
    listing every missing variable at once, so a misconfigured run stops
    before any model call. parameters_path defaults to
    config/model_parameters.json; raises ConfigurationError naming every
    model the table does not declare.
    """
    if env is None:
        load_dotenv_once()
        env = dict(os.environ)

    required = {
        "TERE4AI_GENERATOR_MODEL": "generator model id (OpenAI family)",
        "TERE4AI_JUDGE_MODEL": "judge model id (independent non-OpenAI family, DEC-07)",
        "OPENAI_API_KEY": "generator API key",
        "ANTHROPIC_API_KEY": "judge API key",
    }
    missing = [name for name in required if not env.get(name)]
    if missing:
        details = "; ".join(f"{name} ({required[name]})" for name in missing)
        raise ModelConfigError(
            f"missing model configuration: {details}. Set these in .env "
            "(see .env.example); the pipeline never falls back to defaults."
        )

    retired = _retired_variables_error(env)
    if retired is not None:
        raise ConfigurationError(retired)

    judge_model = env["TERE4AI_JUDGE_MODEL"]
    generator_model = env["TERE4AI_GENERATOR_MODEL"]
    assert_independent_judge(generator_model, judge_model)

    path = parameters_path or MODEL_PARAMETERS_PATH
    models = load_model_parameters(path)
    declared: dict[str, ModelParameters] = {}
    problems: list[str] = []
    for component, model_id, inference_backend in (("generator", generator_model, "openai"),
                                                   ("judge", judge_model, "anthropic")):
        try:
            declared[component] = declaration_for(models, model_id, inference_backend, _where(path))
        except ConfigurationError as exc:
            problems.append(str(exc).removeprefix("configuration error: "))
    if problems:
        raise ConfigurationError("configuration error: " + "; ".join(problems))

    return ModelConfig(
        generator_model=generator_model,
        judge_model=judge_model,
        generator_api_key=env["OPENAI_API_KEY"],
        judge_api_key=env["ANTHROPIC_API_KEY"],
        generator_parameters=declared["generator"],
        judge_parameters=declared["judge"],
    )


# DEC-24 (spec G D-G74 (2), (3), (5); rulings S54, S55, S67, S68): the HTTP
# facade's generator-only mode and its judge routes each load only what they
# call. The generator-only mode reads the generator's model, key and
# declared row; the judge routes read the demo judge (an OpenAI model as the
# judge, refused when it is the generator's model) and the signing
# key. Neither reads the Anthropic judge's settings or key, which only the
# inline mode and the MCP tools need. DEC-07's TERE4AI_JUDGE_MODEL and
# assert_independent_judge are untouched.
MODEL_PRICES_FILE = "config/model_prices.json"
MODEL_PRICES_PATH = Path(__file__).resolve().parents[3] / MODEL_PRICES_FILE
PRICE_KEYS: tuple[str, ...] = ("input", "output", "batch_input", "batch_output")
GENERATOR_VARIABLE = "TERE4AI_GENERATOR_MODEL"
DEMO_JUDGE_VARIABLE = "TERE4AI_DEMO_JUDGE_MODEL"
SIGNING_KEY_VARIABLE = "TERE4AI_ANSWER_SIGNING_KEY"
_SIGNING_KEY = re.compile(r"[0-9a-fA-F]{64}", re.ASCII)


def price_problem(row: Any) -> str | None:
    """What is wrong with one price row, or None. The page and the day are
    checked as declaration_for checks the declaration's own (https page,
    YYYY-MM-DD day)."""
    if not isinstance(row, dict):
        return "the row is not an object"
    if row.get("inference_backend") not in INFERENCE_BACKENDS:
        return "inference_backend must be openai or anthropic"
    for key in PRICE_KEYS:
        try:
            if float(row[key]) < 0:
                return f"{key} is negative"
        except (KeyError, TypeError, ValueError):
            return f"{key} is missing or is not a decimal string"
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        return "no pricing page (https) and no day it was read (YYYY-MM-DD)"
    url, read_on = pricing.get("url"), pricing.get("read_on")
    try:
        read_day = (date.fromisoformat(read_on)
                    if isinstance(read_on, str) and _ISO_DAY.fullmatch(read_on) else None)
    except ValueError:
        read_day = None
    try:
        page = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        page = None
    if page is None or page.scheme != "https" or not page.hostname or read_day is None:
        return "names no pricing page (https) or no day it was read (YYYY-MM-DD)"
    return None


def load_model_prices(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """The price rows of config/model_prices.json keyed by model id, every row
    checked; the four prices come back as floats (USD per million tokens).
    Raises ConfigurationError naming every refused row. (Moved here from
    scripts/estimate_benchmark_cost.py, which imports it, so the demo judge's
    configuration reads the same table, DEC-24.)"""
    path = path or MODEL_PRICES_PATH
    where = MODEL_PRICES_FILE if path == MODEL_PRICES_PATH else path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigurationError(f"configuration error: {where} is missing") from None
    except (OSError, ValueError) as exc:
        raise ConfigurationError(
            f"configuration error: {where} cannot be read ({type(exc).__name__})") from None
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or not isinstance(data.get("models"), dict)):
        raise ConfigurationError(
            f"configuration error: {where} must hold schema_version 1 and a models object keyed by model id")
    problems = [f"{model_id}: {problem}" for model_id, row in data["models"].items()
                if (problem := price_problem(row)) is not None]
    if problems:
        raise ConfigurationError(f"configuration error: {where} has refused rows: " + "; ".join(problems))
    return {model_id: {**row, **{key: float(row[key]) for key in PRICE_KEYS}}
            for model_id, row in data["models"].items()}


def _environment(env: dict[str, str] | None) -> dict[str, str]:
    if env is None:
        load_dotenv_once()
        return dict(os.environ)
    return env


@dataclass(frozen=True)
class GeneratorConfig:
    """The generator alone, for the facade's generator-only mode (DEC-24): the
    three attributes OpenAIGenerator reads, and nothing of the judge."""

    generator_model: str
    generator_api_key: str
    generator_parameters: ModelParameters


def load_generator_config(env: dict[str, str] | None = None, parameters_path: Path | None = None) -> GeneratorConfig:
    """The generator's model, key and declared row; refused (ModelConfigError,
    ConfigurationError) naming what is missing, before any model call."""
    env = _environment(env)
    missing = [name for name in (GENERATOR_VARIABLE, "OPENAI_API_KEY") if not env.get(name)]
    if missing:
        raise ModelConfigError(f"missing model configuration for the generator: {', '.join(missing)}. Set these in "
                               ".env (see .env.example); the pipeline never falls back to defaults.")
    retired = _retired_variables_error(env)
    if retired is not None:
        raise ConfigurationError(retired)
    path = parameters_path or MODEL_PARAMETERS_PATH
    model = env[GENERATOR_VARIABLE]
    return GeneratorConfig(generator_model=model, generator_api_key=env["OPENAI_API_KEY"],
                           generator_parameters=declaration_for(load_model_parameters(path), model, "openai", _where(path)))


@dataclass(frozen=True)
class DemoJudgeConfig:
    """The demo judge of DEC-24: an OpenAI model as the judge, with its
    declared row and its price row."""

    model: str
    api_key: str
    parameters: ModelParameters
    price: dict[str, Any]


def load_demo_judge_config(env: dict[str, str] | None = None, parameters_path: Path | None = None,
                           prices_path: Path | None = None) -> DemoJudgeConfig:
    """TERE4AI_DEMO_JUDGE_MODEL with its openai row in config/model_parameters.json
    and its row in config/model_prices.json; refused when it is unset, equals
    TERE4AI_GENERATOR_MODEL, or lacks either row (spec G D-G74 (5))."""
    env = _environment(env)
    missing = [name for name in (DEMO_JUDGE_VARIABLE, "OPENAI_API_KEY") if not env.get(name)]
    if missing:
        raise ModelConfigError(f"missing model configuration for the demo judge: {', '.join(missing)}. Set these in "
                               ".env (see .env.example).")
    model = env[DEMO_JUDGE_VARIABLE]
    generator = env.get(GENERATOR_VARIABLE, "")
    if generator and model.strip().lower() == generator.strip().lower():
        raise ModelConfigError(f"the demo judge {model!r} is the generator's model; the generator never judges "
                               "its own output (DEC-24, DEC-07)")
    path = parameters_path or MODEL_PARAMETERS_PATH
    parameters = declaration_for(load_model_parameters(path), model, "openai", _where(path))
    prices = load_model_prices(prices_path)
    if model not in prices:
        where = MODEL_PRICES_FILE if prices_path is None or prices_path == MODEL_PRICES_PATH else prices_path.name
        raise ConfigurationError(f"configuration error: {where} has no price row for the demo judge {model!r}")
    return DemoJudgeConfig(model=model, api_key=env["OPENAI_API_KEY"], parameters=parameters, price=prices[model])


def load_signing_key(env: dict[str, str] | None = None) -> bytes:
    """The facade's answer-signing key: 64 hexadecimal characters (32 bytes),
    any other form a configuration error; never logged, never returned."""
    env = _environment(env)
    value = env.get(SIGNING_KEY_VARIABLE, "")
    if not value:
        raise ModelConfigError(f"configuration error: {SIGNING_KEY_VARIABLE} is not set; the generator-only mode "
                               "and the judge routes need it (DEC-24)")
    if not _SIGNING_KEY.fullmatch(value):
        raise ModelConfigError(f"configuration error: {SIGNING_KEY_VARIABLE} must be 64 hexadecimal characters "
                               "(32 bytes)")
    return bytes.fromhex(value)


def route_readiness(env: dict[str, str] | None = None, parameters_path: Path | None = None,
                    prices_path: Path | None = None) -> dict[str, Any]:
    """/api/health's readiness of each route apart (spec G D-G74 (2), S68):
    the generator-only mode, the demo judge with its declaration and price,
    the signing key present or missing (never its value)."""
    env = _environment(env)
    try:
        generator = load_generator_config(env, parameters_path)
        generator_part: dict[str, Any] = {"ready": True, "model": generator.generator_model,
                                          "effort": generator.generator_parameters.effort, "error": None}
    except ModelConfigError as exc:
        generator_part = {"ready": False, "model": env.get(GENERATOR_VARIABLE) or None, "effort": None, "error": str(exc)}
    try:
        judge = load_demo_judge_config(env, parameters_path, prices_path)
        judge_part: dict[str, Any] = {"ready": True, "model": judge.model, "effort": judge.parameters.effort,
                                      "temperature": judge.parameters.temperature, "declaration_error": None}
    except ModelConfigError as exc:
        judge_part = {"ready": False, "model": env.get(DEMO_JUDGE_VARIABLE) or None, "effort": None,
                      "temperature": None, "declaration_error": str(exc)}
    try:
        load_signing_key(env)
        key_part: dict[str, Any] = {"present": True, "error": None}
    except ModelConfigError as exc:
        key_part = {"present": bool(env.get(SIGNING_KEY_VARIABLE)), "error": str(exc)}
    return {"generator_only": generator_part, "demo_judge": judge_part, "signing_key": key_part}
