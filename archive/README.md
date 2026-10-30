# Archive

Retired 30 October 2026: the Windows download (the `.exe` app) is no longer built or published. Learners use
Club Coders in the browser.

- `release/build_windows.py` and `release/clubcoders.spec`: the PyInstaller build of `ClubCoders-windows.zip`.
- `github-workflows/release.yml`: the GitHub Actions workflow that built and published it on a `v*` tag. It is out
  of `.github/workflows/`, so it no longer runs.

The tag `archive/public-release-2026-10-30` marks the last commit with the flow in place. Existing GitHub releases
are left as they were. `make_public_repo.py`, which generated this repo, lives in the ClubCodersAI repo.
