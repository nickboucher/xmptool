# XMP Tool

This tool will create an XMP sidecar file for any media files in a specified directory that are missing date/time metadata. It will also link "Live Photos" to their corresponding video files.

This tool is designed for users of [immich](https://github.com/immich-app/immich), although it can also be used independently. The motivation for this tool is [Google Photos](https://photos.google.com/). When selecting "Download All" from an album in Google Photos, the resulting zip file:
- Removes EXIF metadata from some media files, particularly videos.
- Unlinks "Live Photos" from their corresponding video files by stripping key metadata.

`xmptool` is designed to automatically correct these issues by bulk creating XMP sidecar files for media files missing date/time metadata and linking "Live Photos" to their corresponding video files.

Date/time metadata is inferred from surrounding files in the directory containing this information. "Live Photos" without links to the corresponding video file are corrected by adding a Content Identifier to the XMP sidecar file. No changes are made to the original media files: all edits are stored a separate XMP sidecar files which are compatible with [immich](https://github.com/immich-app/immich).

## Usage

```
xmptool [-h] [-f] [-r] [-s] [-v] [-d] dir

positional arguments:
  dir                 The directory containing media files.

options:
  -h, --help          show this help message and exit
  -f, --force         Force the creation of XMP files even if they already exist.
  -r, --recalculate   Only regenerate XMP files for media that already has XMP files.
  -s, --single-files  Process single files (non-Live Photos) to make date/time more discoverable by immich.
  -v, --verbose       Enable verbose logging.
  -d, --debug         Enable debug logging.
```

## Installation

After cloning this repository, you can install the tool using the following command:

```bash
pip install .
```

In addition, this tool requires the `exiftool` command line utility to be installed on your system (>=13.10). You can download it from the [ExifTool website](https://exiftool.org/).

Once installed, you can run the tool using the `xmptool` command.