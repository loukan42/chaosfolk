"""Report archives. Each audit stores one .zip: one upload on Vercel Blob instead of one per file,
which keeps the free plan's 2,000 monthly uploads for audits. Report pages are read from the archive."""
from pathlib import Path
import tempfile
import threading
import zipfile


class LocalReports:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def path(self, audit_id):
        return self.folder / f"{audit_id}.zip"

    def save(self, audit_id, data):
        partial = self.path(audit_id).with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(self.path(audit_id))

    def load(self, audit_id):
        path = self.path(audit_id)
        return path.read_bytes() if path.is_file() else None

    def local_path(self, audit_id):
        path = self.path(audit_id)
        return path if path.is_file() else None

    def delete(self, audit_ids):
        for audit_id in audit_ids:
            self.path(audit_id).unlink(missing_ok=True)


class BlobReports:
    """Private Vercel Blob store: the archive is only reachable through this API, by its audit id."""

    def __init__(self, blob=None, cache_dir=None):
        if blob is None:
            from vercel.blob import sync as blob
        self.blob = blob
        self.cache = Path(cache_dir or Path(tempfile.gettempdir()) / "chaosfolk-reports")
        self.cache.mkdir(parents=True, exist_ok=True)
        self.guard = threading.Lock()

    @staticmethod
    def name(audit_id):
        return f"reports/{audit_id}.zip"

    def save(self, audit_id, data):
        self.blob.put_blob(self.name(audit_id), data, access="private", content_type="application/zip",
                           allow_overwrite=True)

    def load(self, audit_id):
        path = self.local_path(audit_id)
        return path.read_bytes() if path else None

    def local_path(self, audit_id):
        """Download once per function instance; later page and image requests read the cached copy."""
        cached = self.cache / f"{audit_id}.zip"
        if cached.is_file():
            return cached
        with self.guard:
            if cached.is_file():
                return cached
            try:
                body = self.blob.get_blob(self.name(audit_id), access="private").body
            except FileNotFoundError:
                return None
            partial = cached.with_suffix(".part")
            partial.write_bytes(body)
            partial.replace(cached)
        return cached

    def delete(self, audit_ids):
        names = [self.name(audit_id) for audit_id in audit_ids]
        if names:
            self.blob.delete_blob(names)
        for audit_id in audit_ids:
            (self.cache / f"{audit_id}.zip").unlink(missing_ok=True)


def read_member(zip_path, path):
    """Return the bytes of `path` inside the archive's top folder, or None. No path can leave the folder."""
    with zipfile.ZipFile(zip_path) as bundle:
        names = bundle.namelist()
        if not names:
            return None
        top = names[0].split("/", 1)[0]
        parts = [part for part in path.split("/") if part]
        if any(part in {".", ".."} or "\\" in part for part in parts):
            return None
        member = "/".join([top, *parts])
        if member not in names:
            return None
        return bundle.read(member)
