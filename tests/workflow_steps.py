"""Run one step of a workflow in this repo, as the workflow ships it.

The reusable workflows keep their logic inline in `run:` blocks. `run_step`
takes one step's script and `env:` out of the workflow file by step name, fills
in the `${{ }}` expressions they use, and runs the script with bash the way a
GitHub-hosted Linux runner does (`bash -e`, no `shell:` set). A test then
checks the script itself, not a copy of it.

Only plain context references are filled in: `inputs.*`, `github.*` and
`steps.<id>.outputs.<name>`. Anything else raises, so an expression this
module cannot evaluate fails the test instead of turning into an empty string.
"""
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
STEP_OUTPUT = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")


@dataclass
class StepResult:
    rc: int
    log: str
    outputs: dict
    summary: str


def find_step(workflow, name):
    doc = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    found = [s for job in doc["jobs"].values() for s in job.get("steps", [])
             if s.get("name") == name]
    if len(found) != 1:
        raise LookupError(f"{workflow}: {len(found)} steps named {name!r}, want 1")
    return found[0]


def render(text, values, outputs):
    """Replace each `${{ expr }}` in text.

    `values` maps an expression such as `inputs.run` to its value. `outputs`
    maps a step id to the outputs it wrote; an output a known step did not
    write renders empty, as it does in Actions.
    """
    def sub(m):
        expr = m.group(1)
        if expr in values:
            return str(values[expr])
        ref = STEP_OUTPUT.fullmatch(expr)
        if ref and ref.group(1) in outputs:
            return str(outputs[ref.group(1)].get(ref.group(2), ""))
        raise KeyError(f"no value for ${{{{ {expr} }}}}")
    return EXPR.sub(sub, str(text))


def parse_outputs(text):
    out = {}
    for line in text.splitlines():
        if line:
            key, sep, value = line.partition("=")
            if not sep:
                raise ValueError(f"unsupported GITHUB_OUTPUT line: {line!r}")
            out[key] = value
    return out


def run_step(workflow, name, cwd, values=None, outputs=None, env=None):
    """Run the step named `name` in `cwd` and return what it did."""
    values, outputs = values or {}, outputs or {}
    step = find_step(workflow, name)
    script = render(step["run"], values, outputs)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "step.sh").write_text(script, encoding="utf-8")
        (tmp / "output").touch()
        (tmp / "summary").touch()
        full_env = dict(os.environ)
        full_env.update(env or {})
        full_env.update({k: render(v, values, outputs) for k, v in step.get("env", {}).items()})
        full_env["GITHUB_OUTPUT"] = str(tmp / "output")
        full_env["GITHUB_STEP_SUMMARY"] = str(tmp / "summary")
        p = subprocess.run(["bash", "--noprofile", "--norc", "-e", str(tmp / "step.sh")],
                           cwd=cwd, env=full_env, capture_output=True, text=True)
        return StepResult(p.returncode, p.stdout + p.stderr,
                          parse_outputs((tmp / "output").read_text(encoding="utf-8")),
                          (tmp / "summary").read_text(encoding="utf-8"))
