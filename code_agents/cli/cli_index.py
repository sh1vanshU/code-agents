"""CLI index command — build and query the RAG vector store."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger("code_agents.cli.cli_index")


def cmd_index():
    """Build or inspect the RAG code index for the current repo.

    Usage:
      code-agents index              # build/update the index
      code-agents index --force      # force full rebuild
      code-agents index --stats      # show index statistics
    """
    from .cli_helpers import _colors
    bold, green, yellow, red, cyan, dim = _colors()

    args = sys.argv[2:]

    if "--help" in args or "-h" in args:
        print(cmd_index.__doc__)
        return

    repo_path = _get_repo_path()
    if not repo_path:
        print(red("  Not in a git repo or target repo not configured."))
        return

    from code_agents.knowledge.rag_context import VectorStore

    store = VectorStore(repo_path)

    if "--stats" in args:
        st = store.stats()
        print()
        print(f"  {bold('RAG Vector Store Stats')}")
        print(f"  {'─' * 36}")
        print(f"  {bold('Repo:')}          {st.get('repo_path', '—')}")
        print(f"  {bold('Chunks:')}        {st.get('chunk_count', 0)}")
        print(f"  {bold('Files:')}         {st.get('file_count', 0)}")
        print(f"  {bold('Vocab size:')}    {st.get('vocab_size', 0)}")
        print(f"  {bold('Embeddings:')}    {'yes' if st.get('has_embeddings') else 'no (TF-IDF only)'}")
        print(f"  {bold('Last updated:')}  {st.get('last_updated', '—')}")
        print(f"  {bold('Git commit:')}    {st.get('git_commit', '—')}")
        print()
        return

    force = "--force" in args
    print(f"  {'Rebuilding' if force else 'Building'} RAG index for: {cyan(repo_path)}")

    chunk_count = store.build(force=force)
    st = store.stats()
    print(f"  {green('✓')} Indexed {bold(str(chunk_count))} chunks from {st.get('file_count', '?')} files")
    print(f"  {dim('Vocab:')} {st.get('vocab_size', 0)} terms  {dim('Embeddings:')} {'yes' if st.get('has_embeddings') else 'TF-IDF only'}")
    print()


def _get_repo_path() -> str:
    """Resolve the target repo path."""
    import os

    # Check env var first
    repo = os.environ.get("TARGET_REPO_PATH", "")
    if repo and os.path.isdir(repo):
        return repo

    # Fall back to cwd
    cwd = os.getcwd()
    if os.path.isdir(os.path.join(cwd, ".git")):
        return cwd

    return ""
