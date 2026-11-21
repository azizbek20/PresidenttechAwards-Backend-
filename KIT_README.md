# Eye Detect AI — Claude Code migration kit

Everything Claude Code needs to replace the PyTorch/ONNX inference in
`backend/` with Claude vision and make the backend deployable on Vercel.

## What is inside

| File | Purpose |
|---|---|
| `backend/CLAUDE.md` | **Replaces** the current one. Keeps the safety rules, unfreezes the files the migration must change, keeps the API contract frozen. (The old v4 version stays in git history.) |
| `backend/docs/MIGRATION_PLAN.md` | The spec Claude Code follows: design, decision rules, schema, tests, phases, done criteria, reviewer checklist. |
| `backend/docs/PROMPTS.md` | The prompts to paste, in order: start (Phase 0), then tests → implementation → review for each phase. |
| `backend/docs/NOTES.md` | Log Claude Code fills in: baseline, test impact, results. |
| `backend/app/inference/prompts/fundus_v1.md` | Draft system prompt for reading fundus images. **The ophthalmologist must review it** before the accuracy eval. |
| `backend/.env.vercel.example` | Environment variable names for Vercel (placeholders only). |

## How to use it

1. **Unzip into the repo root** so the `backend/` folders merge:
   ```bash
   cd PresidenttechAwards-Backend
   unzip -o ~/Downloads/eye-detect-claude-kit.zip
   git status        # CLAUDE.md modified; docs, prompt and env template added
   ```
2. **Put the Anthropic key in `backend/.env`** (already git-ignored):
   `ANTHROPIC_API_KEY=...`. Never paste it into a prompt. It is not needed
   until the end of Phase 2.
3. **Open Claude Code at the repo root** and paste the START prompt from
   `backend/docs/PROMPTS.md`. It creates the branch, commits the kit, runs
   the baseline tests and stops with a report. Read that report first.
4. **Run each phase in order: tests → implementation → review.** Do not move
   on until the phase's commands pass and the reviewer finds nothing serious.
   - Phase 1: delete model code
   - Phase 2: Claude engine (manual check with a few real images at the end)
   - Phase 3: Vercel (you create the Vercel project, Blob store and Postgres)
   - Phase 4: accuracy eval on labelled public fundus images
5. Delete this `KIT_README.md` from the repo root when you are done.

## Before you show results to anyone

- Demo results so far came from image brightness, not from analysing a retina.
- Claude results are decision support only until the Phase 4 eval meets the
  pass bar (sensitivity ≥ 90%, specificity ≥ 80% for referable DR) and the
  ophthalmologist signs off.
- Use public dataset images or consented images only: patient photos sent to
  the Anthropic API and Vercel leave Uzbekistan.
- The app's offline model can show a green result; see
  `backend/docs/MIGRATION_PLAN.md` §10 for the Android developer.
