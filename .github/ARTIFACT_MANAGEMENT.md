# Artifact Management Strategy

This document describes how build artifacts and packages are managed across the CI/CD pipeline.

## Overview

The project uses a tiered artifact storage strategy:

1. **GitHub Releases** - Official versioned releases (kept indefinitely)
2. **GitHub Pre-releases** - Rolling CI builds (automated cleanup)
3. **Workflow Artifacts** - Short-term build artifacts (7-90 day retention)

## CI Builds (`ci.yml`)

**Triggers:** Push to `main`, pull requests, manual dispatch

**Artifact Publishing:**

### Main Branch Builds
- **Pre-release Tags:** `ci-main-{os}-{arch}` (e.g., `ci-main-linux-x64`)
- **Retention:** Last 5 builds per platform
- **Updates:** Each build overwrites the previous release for that platform
- **Access:** Available as GitHub pre-releases

### Pull Request Builds
- **Pre-release Tags:** `ci-pr-{number}-{os}-{arch}` (e.g., `ci-pr-123-windows-x64`)
- **Retention:** 7 days after creation
- **Updates:** Each PR push overwrites the previous build for that PR and platform
- **Cleanup:** Automatically deleted 7 days after creation

### Workflow Artifacts
- **Retention:** 7 days
- **Purpose:** Quick access during build, backup storage
- **Cleanup:** Automatically deleted after 7 days

## Release Builds (`release.yml`)

**Triggers:** GitHub release publication, manual dispatch with tag

**Artifact Publishing:**

### GitHub Releases
- **Tags:** Semantic version tags (e.g., `v0.1.0`, `v1.2.3`)
- **Retention:** Indefinite (standard releases)
- **Assets:** Platform-specific binaries attached to the release
- **Access:** Public release page

### Workflow Artifacts
- **Retention:** 90 days
- **Purpose:** Quick download during release testing
- **Cleanup:** Automatically deleted after 90 days

## Cleanup Workflow (`cleanup.yml`)

**Schedule:** Daily at 2 AM UTC

**Jobs:**

### 1. Workflow Artifacts Cleanup
Deletes workflow artifacts older than 7 days across all workflows.

### 2. PR Pre-release Cleanup
Deletes PR pre-releases (tagged `ci-pr-*`) older than 7 days.

### 3. Main Pre-release Cleanup
Keeps only the latest 5 main pre-releases per platform (tagged `ci-main-*`).

### Manual Execution
Run the cleanup workflow manually with dry-run mode:
```bash
# Via GitHub UI: Actions → Cleanup Artifacts and Pre-releases → Run workflow
# Enable "Dry run" to preview what would be deleted
```

## Accessing Artifacts

### Latest CI Builds (Main Branch)
1. Go to [Releases](../../releases)
2. Find pre-releases tagged `ci-main-{os}-{arch}`
3. Download the binary for your platform

### PR Builds
1. Go to [Releases](../../releases)
2. Find pre-releases tagged `ci-pr-{number}-{os}-{arch}`
3. Download the binary for your platform

### Official Releases
1. Go to [Releases](../../releases)
2. Find the version-tagged release (e.g., `v0.1.0`)
3. Download the binary for your platform

### Recent Workflow Artifacts
1. Go to [Actions](../../actions)
2. Select the workflow run
3. Download artifacts from the "Artifacts" section

## Storage Budget

| Type | Retention | Estimated Size | Notes |
|------|-----------|----------------|-------|
| Release builds | Indefinite | ~30 MB × 6 platforms × N releases | Official releases only |
| Main pre-releases | Latest 5 per platform | ~30 MB × 6 platforms × 5 = ~900 MB | Rolling builds |
| PR pre-releases | 7 days | ~30 MB × 6 platforms × active PRs | Typically 1-3 PRs |
| Workflow artifacts (CI) | 7 days | ~30 MB × 6 platforms × daily builds | ~1.26 GB per week |
| Workflow artifacts (Release) | 90 days | ~30 MB × 6 platforms × releases | Minimal, releases are infrequent |

**Total Estimated Usage:** ~2-3 GB for active development

## Configuration

### Adjusting Retention Policies

**Main pre-releases (keep latest N per platform):**
Edit `.github/workflows/cleanup.yml`:
```yaml
const keepCount = 5;  # Change to desired number
```

**PR pre-release age (days before deletion):**
Edit `.github/workflows/cleanup.yml`:
```yaml
const retentionDays = 7;  # Change to desired number of days
```

**Workflow artifact retention:**
Edit `.github/workflows/ci.yml`:
```yaml
retention-days: 7  # Change to desired number of days
```

Edit `.github/workflows/release.yml`:
```yaml
retention-days: 90  # Change to desired number of days
```

## Benefits

1. **Fast CI builds:** Latest builds always available as pre-releases
2. **PR testing:** Every PR build published automatically
3. **Storage efficiency:** Automatic cleanup prevents storage bloat
4. **Cost control:** Limited retention keeps storage costs manageable
5. **Easy access:** All artifacts available through GitHub UI
6. **Historical releases:** Official releases preserved indefinitely
