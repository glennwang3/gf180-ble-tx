# Your files

Everything you change in this lab is in two files in this folder. A third is
complete and only to be read:

| File | What it decides | You |
| --- | --- | --- |
| `views.py` | the context each agent is given | edit it |
| `prompts.py` | what each agent is told | edit it |
| `policy.py` | which results may become the answer, when to stop, which model each agent uses | read it |

The rest of the project (the flow in `pd/`, the agent workflow in `agents/`, the
designs) is the framework. Read it as much as you like, but do not change it: your
two files are graded inside an unmodified copy of the project.

## How the TODOs work

Every TODO is a few lines to fill in, with a comment above each line that says
what goes there:

- in `views.py`, replace each `None` with the expression its comment gives;
- in `prompts.py`, write two to five sentences inside each empty `"""` string.

Until a function or a prompt is filled in, it keeps the behaviour you received,
so the loop runs at every stage of your work. Search the two files for `TODO step`.

## The steps

Six steps, in the order the loop runs: first the navigator, then the stage agent,
then the stop agent, and finally what happens when a run fails.

| Step | Where | What you fill in | How you know it worked |
| --- | --- | --- | --- |
| 0 | none | Run the loop as you received it (`--runs 20`), open `run.html`, read `report.json` | You can say what each agent did in one iteration |
| 1 | `views.py` `navigator_view` | 1.1 to 1.5: five one-line expressions | The navigator's input tokens fall (`python -m pd.ledger WORK`) |
| 2 | `prompts.py` `NAVIGATOR_*` | 2.1 to 2.5: the two moves, the score, candidates, when to evaluate, how to answer | At least one evaluation during the search |
| 3 | `views.py` `stage_view` | 3.1 to 3.5: five one-line expressions | The stage agent's input tokens fall |
| 4 | `prompts.py` `STAGE_AGENT_*` | 4.1 to 4.4: its context, its goal, no repeated tries, the order of calls | Its reasons mention what was already tried |
| 5 | `views.py` `stop_view` | 5.1 to 5.3: three one-line expressions | The stop agent's input tokens fall |
| 6 | `prompts.py` `DIAGNOSTICIAN_*` | 6.1 to 6.3: how to read a failed run | `python -m agents.diagnose_cases` finds most causes |
| optional | `prompts.py` `STOP_AGENT` | the stop agent's prompt | Compare it with the stopping rule in `stop_decisions` |

After a step or two, make a short run and compare it with the previous one:

```bash
./venv/bin/python -m agents.graph --runs 8 --usd 1.00 --work runs/stepN
./venv/bin/python tools/compare_runs.py runs/stepM runs/stepN
./venv/bin/python tools/agent_actions.py runs/stepN > runs/stepN/actions.md
```

A run with `--runs 8` takes under half an hour. Make full 20-run searches only once
the steps are done. The assignment handout explains every term the steps use.
