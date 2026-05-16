# Plan: Deployment-Feedback-Loop Fix

**Datum:** 2026-05-16  
**Branch:** `fix/deployment-feedback-loop`  
**Brainstorm:** `docs/superpowers/brainstorm/2026-05-16-deployment-feedback-loop-fix.md`

---

## Ziel

Output-Commits des monatlichen Screeners lösen keine Cloud-Run-Deployments mehr aus.

---

## Aufgaben

### Task 1: `paths-ignore` in deploy.yml

**Datei:** `.github/workflows/deploy.yml`

```yaml
on:
  push:
    branches: [main]
    paths-ignore:
      - 'output/**'
```

**Akzeptanzkriterium:** Push auf `output/**` triggert keinen Workflow-Run.

---

### Task 2: `[skip ci]` in Output-Commit-Messages

**Datei:** `app/main.py:63`

Vorher:
```python
f"chore: monthly screener output {run_record.run_id[:7]}"
```

Nachher:
```python
f"chore: monthly screener output {run_record.run_id[:7]} [skip ci]"
```

**Akzeptanzkriterium:** Jeder Output-Commit enthält `[skip ci]`.

---

### Task 3: Test für Commit-Message-Konvention

**Datei:** `tests/test_main.py`

Neuer Test `test_monthly_run_commit_message_includes_skip_ci`:
- Erstellt temporäre Output-Datei via `tmp_path`
- Mockt alle Dependencies, `run_screener` gibt den tmp-Pfad zurück
- Erfasst den `push_file`-Aufruf
- Assert: `commit_message` endet mit `[skip ci]`

**Akzeptanzkriterium:** Test läuft grün, Coverage 100% für `app/main.py`.

---

### Task 4: Testsuite ausführen

```cmd
uv run python -m pytest
```

**Akzeptanzkriterium:** Alle Tests grün, kein Coverage-Drop.

---

## Out of Scope

- Firestore-Idempotenz-Lock (Phase 2, begründet in Brainstorm Frage 5)
- Output-Repo-Trennung (Phase 2)
- `attempt-deadline`-Änderung am Cloud Scheduler (manuelle GCP-Konfiguration, kein Code)
- Migration auf Cloud Run Jobs
