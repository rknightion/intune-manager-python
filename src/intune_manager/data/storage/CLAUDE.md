# intune_manager.data.storage – AGENT Brief

## Purpose
- Manage binary attachments (application icons, exported reports, log bundles) with disk quota enforcement.
- Provide async-friendly APIs for storing/retrieving cached files with LRU eviction policy.
- Track usage metadata (file size, last accessed, content hash) for cache management.

## Module Structure
- **`manager.py`**: `StorageManager` — file I/O, quota tracking, LRU eviction
- **`models.py`**: `FileMetadata` pydantic model (path, size, last_accessed, hash)

## Conventions
- **Isolation**: Keep storage under `~/.cache/IntuneManager/storage/` (tenant-scoped if needed).
- **Quota enforcement**: Track total usage; evict LRU files when exceeding quota (default 500MB).
- **Content hashing**: Use content hash to deduplicate identical files (e.g., app icons).
- **Async I/O**: All disk operations are async; never block on large file reads/writes.
- **Metadata tracking**: Maintain manifest (JSON) of stored files for fast lookups.
- **Cleanup on app exit**: Validate manifest vs. actual files; remove orphaned files.

## Key Patterns

### Storing Files
```python
storage = StorageManager()

# Save with auto-dedup by hash
path = await storage.store_file(
    data=icon_bytes,
    category="app_icons",
    name="app_id",
    content_hash=hashlib.sha256(icon_bytes).hexdigest()
)
# Returns: ~/.cache/IntuneManager/storage/app_icons/app_id.png
```

### Retrieval with Expiry
```python
# Get file (updates last_accessed timestamp)
data = await storage.get_file("app_icons", "app_id")

# Check if expired (not accessed for >30 days)
if storage.is_expired("app_icons", "app_id", days=30):
    await storage.delete_file("app_icons", "app_id")
```

### Quota Management
```python
# Check total usage
usage_mb = storage.total_usage_mb()

# Auto-evict LRU files if over quota (500MB default)
await storage.enforce_quota(max_mb=500)

# Get manifest for bookkeeping
manifest = await storage.get_manifest()  # Returns FileMetadata list
```

## Guidelines
- **Size limits**: Consider max file size per type (e.g., icons ≤5MB, exports ≤100MB).
- **Hashing**: Use SHA-256 for dedup; store hash in metadata for validation.
- **Concurrency**: Support concurrent reads; serialize writes via lock to prevent corruption.
- **Testing**: Unit test quota enforcement, LRU eviction, dedup logic with mock fs.
- **Monitoring**: Log storage operations (store, retrieve, evict); warn on quota overages.

## Related Modules
- See `@intune_manager/config` for cache directory paths
- See `@intune_manager/services` for service-level storage usage (e.g., ApplicationService icon caching)
