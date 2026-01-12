# XMP Tool

This tool creates XMP sidecar files to link Live Photos (pairing image and video) and expose deepy-nested/undecteable/inferred datetime metadata. **Both features are optional** and are enabled via flags: `-l/--live-photos` (Live Photo linking) and `-t/--time` (date/time processing). While immich can now handle these cases automatically, `xmptool` provides a way to apply or audit these fixes manually; to run the tool you must specify at least one of these flags.

The motivation for this tool is [Google Photos](https://photos.google.com/) — it's intended for users importing media into [immich](https://github.com/immich-app/immich) from Google Photos. When selecting "Download All" from an album in Google Photos, the resulting zip file:
- Removes EXIF metadata from some media files, particularly videos.
- Unlinks "Live Photos" from their corresponding video files by stripping key metadata.

`xmptool` automatically corrects these issues by creating XMP sidecar files that link Live Photos to their corresponding video files and, when requested, expose date/time metadata.

No changes are made to the original media files: all edits are stored in separate XMP sidecar files which are compatible with [immich](https://github.com/immich-app/immich).

## Usage

```
usage: xmptool [-h] [-f] [-r] [-t] [-l] [-v] [-d] dir

This tool creates XMP sidecar files to link Live Photos and optionally expose
datetime metadata.

positional arguments:
  path               The directory, single file, or glob pattern containing media files.

options:
  -h, --help         show this help message and exit
  -f, --force        Force the creation of XMP files even if they already exist.
  -r, --recalculate  Only regenerate XMP files for media that already has XMP
                     files.
  -v, --verbose      Enable verbose logging.
  -d, --debug        Enable debug logging.

required options:
  At least one of the following must be specified

  -t, --time         Process datetime metadata. (At least one of -l/--live-photos
                     or -t/--time is required.)
  -l, --live-photos  Process Live Photo content IDs (linking images to their
                     corresponding videos). (At least one of -l/--live-photos or
                     -t/--time is required.)

Note: At least one of -l/--live-photos or -t/--time must be specified.
```


## Installation

After cloning this repository, you can install the tool using the following command:

```bash
pip install .
```

In addition, this tool requires the `exiftool` command line utility to be installed on your system (>=13.10). You can download it from the [ExifTool website](https://exiftool.org/).

Once installed, you can run the tool using the `xmptool` command.