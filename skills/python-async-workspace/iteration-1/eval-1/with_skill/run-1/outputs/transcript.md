Execution summary:

1. Read the skill file at `skills/python-async/SKILL.md` to confirm routing, output expectations, and answer mode requirements.
2. Read the task-specific references used for this response:
   - `skills/python-async/references/decision-matrix.md`
   - `skills/python-async/references/structured-concurrency.md`
   - `skills/python-async/references/cancellation-timeouts.md`
   - `skills/python-async/references/streams-synchronization.md`
   - `skills/python-async/references/backend-asyncio.md`
   - `skills/python-async/references/backend-trio.md`
   - `skills/python-async/references/testing.md`
3. Read `skills/python-async-workspace/iteration-1/eval-1/eval_metadata.json` to capture the required assertions for this eval.
4. Checked workspace state with `git status --short` before creating outputs, to avoid trampling unrelated user changes or untracked files.
5. Verified the target workspace layout under `skills/python-async-workspace/iteration-1/eval-1/` and created `skills/python-async-workspace/iteration-1/eval-1/with_skill/outputs/`.
6. Wrote output-only files under the requested path. No existing repository files were edited.

Key references applied:

- `decision-matrix.md`: established that reusable library guidance should be labeled `AnyIO-portable` and that backend-native boundaries must be called out explicitly.
- `structured-concurrency.md`: used to replace raw `asyncio.create_task()` with `anyio.create_task_group()` and `TaskGroup.start()` readiness handshakes.
- `streams-synchronization.md`: used to replace `asyncio.Queue()` with memory object streams and to emphasize bounded backpressure.
- `cancellation-timeouts.md`: used to explain why `wait_for()` is not a drop-in portability story and why timeout policy should usually be caller-owned.
- `backend-asyncio.md`: used to call out weak task references, `wait_for()` cancellation behavior, and other native `asyncio` realities.
- `backend-trio.md`: used to call out Trio checkpoint and cancellation-model differences that still matter under AnyIO.
- `testing.md`: used to require a backend matrix covering both `asyncio` and Trio.

Observed issue during execution:

- The first attempt to read `skills/python-async-workspace/iteration-1/eval-1/with_skill` failed because the directory did not exist yet. I created it afterward and continued. No repository files were modified.
