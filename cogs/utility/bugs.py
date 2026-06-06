"""
bugs.py — AI-Powered Bug Scanner (Owner Only)
───────────────────────────────────────────────
Scans every .py file in the bot directory, sends them in
batches to the Claude API, and returns a structured bug report.

Commands:
  ;bugs              — Scan all bot files for bugs
  ;bugs file <path>  — Scan a single specific file
  ;bugs scan <dir>   — Scan a specific directory

Owner only. Uses claude-sonnet-4-20250514 via the Anthropic API.
"""

import discord
from discord.ext import commands
import aiosqlite
import asyncio
import json
import os
import re
import sys
import time
import traceback
import urllib.request
import urllib.error
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

# Directories/files to scan (relative to bot root)
SCAN_DIRS = ["cogs", "events", "automod", "antinuke"]
SCAN_ROOT_FILES = ["main.py", "emojis.py"]

# Files to always skip
SKIP_FILES = {
    "bugs.py",          # don't scan ourselves
    "debug_jsk.py",
    "__init__.py",
}

# Max chars of code to send per API call (leave room for prompt)
BATCH_SIZE_CHARS = 28_000

# Claude API model
MODEL = "claude-sonnet-4-20250514"

# Severity emoji map
SEV_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
    "info":     "ℹ️",
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _find_bot_root() -> Path:
    """Find the bot root directory (where main.py lives)."""
    # Walk up from this file's location
    p = Path(__file__).resolve().parent
    for _ in range(4):
        if (p / "main.py").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent


def _collect_files(root: Path, dirs: list[str], root_files: list[str]) -> list[Path]:
    """Collect all .py files to scan."""
    files: list[Path] = []

    for fname in root_files:
        fp = root / fname
        if fp.exists() and fp.name not in SKIP_FILES:
            files.append(fp)

    for d in dirs:
        dp = root / d
        if dp.exists():
            for fp in sorted(dp.rglob("*.py")):
                if "__pycache__" not in str(fp) and fp.name not in SKIP_FILES:
                    files.append(fp)

    return files


def _make_batches(files: list[Path], root: Path) -> list[list[tuple[str, str]]]:
    """
    Group files into batches where each batch's total code size ≤ BATCH_SIZE_CHARS.
    Returns list of batches; each batch is a list of (relative_path, code) tuples.
    """
    batches: list[list[tuple[str, str]]] = []
    current_batch: list[tuple[str, str]] = []
    current_size = 0

    for fp in files:
        try:
            code = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = str(fp.relative_to(root))
        entry_size = len(rel) + len(code) + 100  # +100 for formatting overhead

        # If a single file exceeds batch size, truncate with a note
        if entry_size > BATCH_SIZE_CHARS:
            code = code[:BATCH_SIZE_CHARS - 500] + "\n\n# ... [truncated — file too large]"
            entry_size = BATCH_SIZE_CHARS

        if current_size + entry_size > BATCH_SIZE_CHARS and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = 0

        current_batch.append((rel, code))
        current_size += entry_size

    if current_batch:
        batches.append(current_batch)

    return batches


def _build_prompt(batch: list[tuple[str, str]]) -> str:
    files_block = ""
    for rel_path, code in batch:
        files_block += f"\n\n### FILE: {rel_path}\n```python\n{code}\n```"

    return f"""You are a Python/discord.py expert performing a code review on a Discord bot.

Analyse the following bot files for bugs, errors, and issues. Focus on:
- Runtime exceptions (unhandled exceptions, wrong types, missing await, etc.)
- discord.py API misuse (deprecated methods, wrong intents, missing permissions checks)
- Logic errors (infinite loops, wrong conditions, off-by-one, etc.)
- Database issues (missing commits, SQL injection risks, wrong column names)
- Async issues (blocking calls in async context, missing await, race conditions)
- Variable scope bugs (closures in loops, nonlocal missing, etc.)
- Missing error handling on critical operations

IMPORTANT INSTRUCTIONS:
- Return ONLY valid JSON, no markdown, no preamble, no explanation outside the JSON.
- If a file has no bugs, do not include it in the output.
- Only report genuine bugs, not style issues or minor suggestions.

Return this exact JSON structure:
{{
  "bugs": [
    {{
      "file": "relative/path/to/file.py",
      "line": 42,
      "severity": "critical|high|medium|low",
      "title": "Short bug title",
      "description": "Clear explanation of the bug and why it causes a problem",
      "fix": "Concrete suggestion to fix it"
    }}
  ],
  "files_scanned": ["file1.py", "file2.py"],
  "clean_files": ["file3.py"]
}}
{files_block}"""


async def _call_claude_api(prompt: str) -> dict:
    """Call the Anthropic API and return parsed JSON result."""

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    loop = asyncio.get_event_loop()

    def _do_request():
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    raw = await loop.run_in_executor(None, _do_request)

    # Extract text content from response
    content_blocks = raw.get("content", [])
    text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

    # Strip any accidental markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    return json.loads(text)


def _severity_rank(s: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(s.lower(), 5)


def _format_bug_pages(all_bugs: list[dict], files_scanned: int, clean_count: int, elapsed: float) -> list[str]:
    """
    Turn the flat list of bugs into a list of Discord message strings,
    each ≤ 1900 chars so they fit in one message.
    """
    if not all_bugs:
        return [
            f"✅ **Bug Scan Complete** — No bugs found!\n"
            f"Scanned `{files_scanned}` files in `{elapsed:.1f}s`."
        ]

    # Sort by severity then file
    all_bugs.sort(key=lambda b: (_severity_rank(b.get("severity", "low")), b.get("file", "")))

    # Count by severity
    counts = {}
    for b in all_bugs:
        sev = b.get("severity", "low").lower()
        counts[sev] = counts.get(sev, 0) + 1

    summary_parts = []
    for sev in ("critical", "high", "medium", "low"):
        if sev in counts:
            summary_parts.append(f"{SEV_EMOJI[sev]} {counts[sev]} {sev}")

    header = (
        f"## 🐛 Bug Scan Report\n"
        f"Scanned `{files_scanned}` files · `{len(all_bugs)}` issues · `{clean_count}` clean · `{elapsed:.1f}s`\n"
        f"{' · '.join(summary_parts)}\n"
        f"{'─'*40}\n"
    )

    pages: list[str] = []
    current = header

    for bug in all_bugs:
        sev   = bug.get("severity", "low").lower()
        emoji = SEV_EMOJI.get(sev, "⚪")
        file  = bug.get("file", "unknown")
        line  = bug.get("line", "?")
        title = bug.get("title", "Untitled bug")
        desc  = bug.get("description", "")
        fix   = bug.get("fix", "")

        entry = (
            f"\n{emoji} **{title}**\n"
            f"`{file}` — line `{line}` — `{sev.upper()}`\n"
            f"{desc}\n"
        )
        if fix:
            entry += f"💡 *Fix: {fix}*\n"
        entry += f"{'─'*30}\n"

        if len(current) + len(entry) > 1900:
            pages.append(current)
            current = f"*(continued — page {len(pages)+1})*\n" + entry
        else:
            current += entry

    if current.strip():
        pages.append(current)

    return pages


# ─────────────────────────────────────────────
# COG
# ─────────────────────────────────────────────

class BugScanner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot      = bot
        self.root     = _find_bot_root()
        self._running = False   # prevent concurrent scans

    # ── Main command group ──────────────────────

    @commands.group(name="bugs", invoke_without_command=True)
    @commands.is_owner()
    async def bugs(self, ctx: commands.Context):
        """Scan all bot files for bugs using AI analysis."""
        await self._run_scan(ctx, dirs=SCAN_DIRS, root_files=SCAN_ROOT_FILES)

    @bugs.command(name="file", aliases=["f"])
    @commands.is_owner()
    async def bugs_file(self, ctx: commands.Context, *, filepath: str):
        """Scan a single file.  Example: ;bugs file cogs/welcome.py"""
        fp = self.root / filepath.strip()
        if not fp.exists():
            return await ctx.send(f"❌ File not found: `{filepath}`")
        if not fp.suffix == ".py":
            return await ctx.send(f"❌ Only `.py` files can be scanned.")
        await self._run_scan(ctx, specific_files=[fp])

    @bugs.command(name="scan", aliases=["dir", "d"])
    @commands.is_owner()
    async def bugs_dir(self, ctx: commands.Context, *, directory: str):
        """Scan a specific directory.  Example: ;bugs scan cogs"""
        dp = self.root / directory.strip()
        if not dp.exists() or not dp.is_dir():
            return await ctx.send(f"❌ Directory not found: `{directory}`")
        files = [
            fp for fp in sorted(dp.rglob("*.py"))
            if "__pycache__" not in str(fp) and fp.name not in SKIP_FILES
        ]
        if not files:
            return await ctx.send(f"❌ No `.py` files found in `{directory}`.")
        await self._run_scan(ctx, specific_files=files)

    # ── Core scan runner ───────────────────────

    async def _run_scan(
        self,
        ctx: commands.Context,
        dirs: list[str] | None = None,
        root_files: list[str] | None = None,
        specific_files: list[Path] | None = None,
    ):
        if self._running:
            return await ctx.send("⏳ A scan is already running. Please wait for it to finish.")

        self._running = True
        start = time.time()

        # ── Collect files ──
        if specific_files is not None:
            files = specific_files
        else:
            files = _collect_files(self.root, dirs or [], root_files or [])

        if not files:
            self._running = False
            return await ctx.send("❌ No files found to scan.")

        # ── Status message ──
        status = await ctx.send(
            f"🔍 **Scanning {len(files)} files for bugs...**\n"
            f"Using `{MODEL}` — this may take a moment."
        )

        # ── Batch and call API ──
        batches = _make_batches(files, self.root)
        all_bugs: list[dict]  = []
        files_scanned: set[str] = set()
        clean_files: list[str] = []
        errors: list[str]     = []

        for i, batch in enumerate(batches):
            batch_names = [rel for rel, _ in batch]
            await status.edit(
                content=(
                    f"🔍 **Scanning batch {i+1}/{len(batches)}...**\n"
                    f"Files: {', '.join(f'`{n}`' for n in batch_names[:5])}"
                    + (f" and {len(batch_names)-5} more" if len(batch_names) > 5 else "")
                )
            )

            try:
                prompt = _build_prompt(batch)
                result = await _call_claude_api(prompt)
                all_bugs.extend(result.get("bugs", []))
                for f in result.get("files_scanned", batch_names):
                    files_scanned.add(f)
                clean_files.extend(result.get("clean_files", []))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                errors.append(f"Batch {i+1} HTTP {e.code}: {body[:200]}")
            except json.JSONDecodeError as e:
                errors.append(f"Batch {i+1} JSON parse error: {e}")
            except Exception as e:
                errors.append(f"Batch {i+1} error: {type(e).__name__}: {e}")

            # Small delay between batches to avoid rate limits
            if i < len(batches) - 1:
                await asyncio.sleep(1.5)

        elapsed = time.time() - start
        await status.delete()

        # ── Format and send results ──
        pages = _format_bug_pages(all_bugs, len(files_scanned), len(clean_files), elapsed)

        for page in pages:
            await ctx.send(page)

        # Report any API errors
        if errors:
            err_text = "\n".join(f"• {e}" for e in errors)
            await ctx.send(f"⚠️ **Some batches failed:**\n```\n{err_text[:1800]}\n```")

        self._running = False

    # ── Error handler ──────────────────────────

    @bugs.error
    @bugs_file.error
    @bugs_dir.error
    async def bugs_error(self, ctx: commands.Context, error):
        self._running = False
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ This command is restricted to the bot owner.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`")
        else:
            await ctx.send(f"❌ Unexpected error: `{error}`")
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(BugScanner(bot))
