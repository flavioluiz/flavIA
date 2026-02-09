# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Changed

- **Converted PDF directory changed from `converted/` to `.converted/`**: PDF files converted to text are now stored in a hidden directory `.converted/` instead of `converted/`. This prevents converted files from being indexed as separate entries in the content catalog, avoiding duplicates. The catalog now links the original PDF to its converted text version.

### Added

- **Configurable timeouts for LLM summarization**: The `summarize_file()` and `summarize_directory()` functions now accept `timeout` and `connect_timeout` parameters (defaults: 30s and 10s respectively).
- **Improved error handling and logging**: LLM summarization now has specific exception handling for timeout, HTTP errors, and import errors, with appropriate logging at different levels.
- **Enhanced compatibility fallback**: More robust detection of OpenAI SDK/httpx version mismatches with better fallback behavior.

### Fixed

- **Duplicate catalog entries**: Converted PDF files no longer appear as separate entries in the content catalog alongside their original PDFs.
- **Better error diagnostics**: Failed LLM calls are now properly logged with context, making debugging easier.

### Removed

- **Legacy `converted/` directory support**: The system no longer checks for or migrates files from the old `converted/` directory. Users should reconvert their PDFs or manually move files to `.converted/` if needed.

## Migration Guide

If you have existing converted PDFs in a `converted/` directory:

1. **Option 1 - Reconvert** (recommended): Delete the `converted/` directory and run the PDF conversion again. Files will be created in `.converted/`.

2. **Option 2 - Manual migration**:
   ```bash
   mv converted .converted
   ```

3. **Option 3 - Keep as is**: The old `converted/` directory will be ignored by the scanner, so it won't cause issues, but links in the catalog won't work until you reconvert or migrate.

After migration, run `flavia` and use the `refresh_catalog` tool to rebuild the content catalog with correct links.
