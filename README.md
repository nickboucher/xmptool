# XMP Tool

This tool creates XMP sidecar files to link Live Photos (pairing image and video), expose deepy-nested/undecteable/inferred datetime metadata, and remove low-quality preview files. **All features are optional** and are enabled via flags: `-l/--live-photos` (Live Photo linking), `-t/--time` (date/time processing), and `-p/--previews` (preview file removal). While immich can now handle these cases automatically, `xmptool` provides a way to apply or audit these fixes manually; to run the tool you must specify at least one of these flags.

The motivation for this tool is [Google Photos](https://photos.google.com/) — it's intended for users importing media into [immich](https://github.com/immich-app/immich) from Google Photos. When selecting "Download All" from an album in Google Photos, the resulting zip file:
- Removes EXIF metadata from some media files, particularly videos.
- Unlinks "Live Photos" from their corresponding video files by stripping key metadata.

Recent versions of iOS save three files per photo: a full-quality image, a Live Photo video, and a low-quality preview image. When Live Photos are disabled, only two files are saved: the full-quality image and the low-quality preview. The `-p/--previews` flag identifies these groups of media files sharing the same filename (but with different extensions), determines the smallest image file in each group (the preview), and moves it to the system recycling bin so it can be recovered if needed. Specifically:
- **2 files, both images**: the smaller image is the preview — recycled with `-p`.
- **2 files, one image + one video**: this is a Live Photo pair — linked with `-l`, not treated as a preview group.
- **3 files, 2 images + 1 video**: the smaller image is the preview — recycled with `-p`; the remaining image + video form a Live Photo pair for `-l`.

`xmptool` automatically corrects these issues by creating XMP sidecar files that link Live Photos to their corresponding video files and, when requested, expose date/time metadata.

No changes are made to the original media files: all edits are stored in separate XMP sidecar files which are compatible with [immich](https://github.com/immich-app/immich). Use `--dry-run` to preview all changes before applying them.

## Usage

```
usage: xmptool [-h] [-f] [-r] [-n] [-t] [-l] [-p] [-i DATETIME] [-o] [-v] [-d] path

This tool creates XMP sidecar files to link Live Photos expose datetime metadata.

positional arguments:
  path                Directory, single file, or glob pattern containing media
                      files.

options:
  -h, --help          show this help message and exit
  -f, --force         Force the creation of XMP files even if they already exist.
  -r, --recalculate   Only regenerate XMP files for media that already has XMP
                      files.
  -n, --dry-run       Show what would be changed without making any modifications.
  -i, --iso DATETIME  Use the given ISO-format datetime instead of extracting from
                      file metadata. Requires -t/--time.
  -o, --override      Force XMP creation even if datetime is already embedded in the
                      file. Requires -t/--time.
  -v, --verbose       Enable verbose logging.
  -d, --debug         Enable debug logging.

required options:
  At least one of the following must be specified

  -t, --time          Process datetime metadata. (At least one of -l/--live-photos,
                      -t/--time, or -p/--previews is required.)
  -l, --live-photos   Process Live Photo content IDs (linking images to their
                      corresponding videos). (At least one of -l/--live-photos,
                      -t/--time, or -p/--previews is required.)
  -p, --previews      Identify and recycle low-quality preview files. When two or
                      three media files share the same filename stem and include
                      multiple images, the smallest image is sent to the system
                      recycling bin. (At least one of -l/--live-photos, -t/--time,
                      or -p/--previews is required.)

Note: At least one of -l/--live-photos, -t/--time, or -p/--previews must be specified.
```


## Installation

After cloning this repository, you can install the tool using the following command:

```bash
pip install .
```

In addition, this tool requires the `exiftool` command line utility to be installed on your system (>=13.10). You can download it from the [ExifTool website](https://exiftool.org/).

Once installed, you can run the tool using the `xmptool` command.