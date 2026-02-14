#!/usr/bin/env python3
from datetime import datetime
from argparse import ArgumentParser
from sys import exit
from os import walk, remove, listdir
from os.path import isfile, splitext, join, isdir, basename, dirname, getsize
from glob import glob
from subprocess import run
from json import loads
from collections import defaultdict
from uuid import uuid4
from colorlog import getLogger, StreamHandler, ColoredFormatter
from packaging.version import Version, parse
from send2trash import send2trash

IMAGE_EXTs = ('jpg', 'jpeg', 'png', 'gif', 'tiff', 'tif', 'webp', 'heic', 'heif')
VIDEO_EXTs = ('mp4', 'mov', 'avi')
EXTs = IMAGE_EXTs + VIDEO_EXTs

logger = getLogger(__name__)

def is_image(file_path: str) -> bool:
    """Check if a file path has an image extension."""
    return file_path.lower().endswith(IMAGE_EXTs)

def is_video(file_path: str) -> bool:
    """Check if a file path has a video extension."""
    return file_path.lower().endswith(VIDEO_EXTs)

def exif_tool(file_path: str, tags: list) -> dict[str, str]:
    cmd = ['exiftool', '-json', '-d', '%Y-%m-%dT%H:%M:%S%:z']
    cmd += [f'-{tag}' for tag in tags]
    cmd += [file_path]
    result = run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'Error: Failed to extract metadata from {file_path}')
        exit(1)
    metadata = loads(result.stdout)[0]
    metadata.pop('SourceFile')
    return metadata

def get_creation_date(metadata: dict[str, str]) -> tuple[str|None, bool, str|None]:
    """Extract creation date from metadata, trying standard fields first, then track-level fields.
    Returns tuple of (date, was_found_in_track, field_name)
    """
    # Try standard EXIF/XMP dates first
    if 'DateTimeOriginal' in metadata:
        return metadata['DateTimeOriginal'], False, 'DateTimeOriginal'
    if 'CreateDate' in metadata:
        return metadata['CreateDate'], False, 'CreateDate'
    if 'DateCreated' in metadata:
        return metadata['DateCreated'], False, 'DateCreated'
    
    # Fall back to Media Create Date
    if 'MediaCreateDate' in metadata:
        return metadata['MediaCreateDate'], True, 'MediaCreateDate'
    # Fall back to Track Create Date
    if 'TrackCreateDate' in metadata:
        return metadata['TrackCreateDate'], True, 'TrackCreateDate'
    return None, False, None

def find_nearest_datetime(file_path: str) -> tuple[datetime|None, str|None]:
    """Find the nearest file in the same directory with a datetime.
    Files are sorted alphabetically; preceding files are preferred over subsequent.
    Returns (datetime, source_file_path) or (None, None).
    """
    dir_path = dirname(file_path) or '.'
    target_name = basename(file_path)

    # Collect all supported media files in the same directory (excluding the target)
    siblings = []
    for f in listdir(dir_path):
        if f.lower().endswith(EXTs) and not f.startswith('._') and f != target_name:
            siblings.append(f)
    siblings.sort()

    if not siblings:
        return None, None

    # Determine target's alphabetical position among all files
    all_names = sorted(siblings + [target_name])
    target_idx = all_names.index(target_name)

    tags = ['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated',
            'XMP:CreateDate', 'MediaCreateDate', 'TrackCreateDate']

    # Search by increasing distance, preceding preferred on each step
    for dist in range(1, len(all_names)):
        for idx in (target_idx - dist, target_idx + dist):
            if 0 <= idx < len(all_names):
                candidate = join(dir_path, all_names[idx])
                metadata = exif_tool(candidate, tags)
                creation_date, _, _ = get_creation_date(metadata)
                if creation_date:
                    try:
                        return datetime.fromisoformat(creation_date), candidate
                    except ValueError:
                        continue

    return None, None

def find_preview_files(file_paths: list[str]) -> list[str]:
    """Identify low-quality preview files from groups sharing the same filename stem.
    Handles two cases:
    - 2 files with same stem, both images: the smaller image is the preview.
    - 3 files with same stem (2 images + 1 video): the smaller image is the preview.
    Groups of 2 with one image + one video are Live Photo pairs, not previews.
    Returns the list of preview file paths to recycle.
    """
    stem_map: dict[str, list[str]] = defaultdict(list)
    for fp in file_paths:
        root, _ = splitext(fp)
        stem_map[root].append(fp)
    previews: list[str] = []
    for stem, paths in stem_map.items():
        images = [p for p in paths if is_image(p)]
        videos = [p for p in paths if is_video(p)]
        if len(paths) == 2 and len(images) == 2:
            # Two images, no video: smaller is preview
            smallest = min(images, key=lambda p: getsize(p))
            previews.append(smallest)
        elif len(paths) == 3 and len(images) == 2 and len(videos) == 1:
            # Two images + one video: smaller image is preview
            smallest = min(images, key=lambda p: getsize(p))
            previews.append(smallest)
    return previews

def recycle_previews(preview_files: list[str], dry_run: bool = False) -> list[str]:
    """Send preview files to the system recycling bin.
    Returns the list of recycled (or would-be-recycled) file paths.
    """
    recycled: list[str] = []
    for fp in preview_files:
        if dry_run:
            logger.warning(f'Would recycle low-quality preview file: {fp}')
        else:
            logger.warning(f'Recycling low-quality preview file: {fp}')
            send2trash(fp)
        recycled.append(fp)
    return recycled

def xmp(creation_date: datetime|None, content_id: str|None) -> str:
    result = "<?xpacket begin='\ufeff' id='W5M0MpCehiHzreSzNTczkc9d'?>\n" \
             "<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='Image::ExifTool 12.99'>\n" \
             "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>\n\n"
    
    if creation_date:
        result += "<rdf:Description rdf:about=''\n" \
                  " xmlns:exif='http://ns.adobe.com/exif/1.0/'>\n" \
                  f" <exif:DateTimeOriginal>{creation_date.isoformat()}</exif:DateTimeOriginal>\n" \
                  "</rdf:Description>\n\n" \
                  "<rdf:Description rdf:about=''\n" \
                  " xmlns:photoshop='http://ns.adobe.com/photoshop/1.0/'>\n" \
                  f" <photoshop:DateCreated>{creation_date.isoformat()}</photoshop:DateCreated>\n" \
                  "</rdf:Description>\n\n"
    if content_id:
        result += "<rdf:Description rdf:about=''\n" \
                  " xmlns:Apple='http://ns.exiftool.org/MakerNotes/Apple/1.0/'>\n" \
                  f" <Apple:ContentIdentifier>{content_id}</Apple:ContentIdentifier>\n" \
                  "</rdf:Description>\n\n"
    
    result += "</rdf:RDF>\n" \
              "</x:xmpmeta>\n" \
              "<?xpacket end='w'?>"

    return result

def main() -> None:

    parser = ArgumentParser(
                    description='This tool creates XMP sidecar files to link Live Photos expose datetime metadata.',
                    epilog='Note: At least one of -l/--live-photos, -t/--time, or -p/--previews must be specified.')
    parser.add_argument('path', metavar='path', type=str, help='Directory, single file, or glob pattern containing media files.')
    parser.add_argument('-f', '--force', action='store_true', help='Force the creation of XMP files even if they already exist.')
    parser.add_argument('-r', '--recalculate', action='store_true', help='Only regenerate XMP files for media that already has XMP files.')
    parser.add_argument('-n', '--dry-run', action='store_true', dest='dry_run', help='Show what would be changed without making any modifications.')

    # Group the flags that are required as "at least one must be present" so help shows them together
    req_group = parser.add_argument_group('required options', 'At least one of the following must be specified')
    req_group.add_argument('-t', '--time', action='store_true', dest='time', help='Process datetime metadata. (At least one of -l/--live-photos, -t/--time, or -p/--previews is required.)')
    req_group.add_argument('-l', '--live-photos', action='store_true', dest='live_photos', help='Process Live Photo content IDs (linking images to their corresponding videos). (At least one of -l/--live-photos, -t/--time, or -p/--previews is required.)')
    req_group.add_argument('-p', '--previews', action='store_true', dest='previews', help='Identify and recycle low-quality preview files. When three media files share the same filename stem, the smallest is sent to the system recycling bin. (At least one of -l/--live-photos, -t/--time, or -p/--previews is required.)')

    parser.add_argument('-i', '--iso', type=str, dest='iso', metavar='DATETIME', help='Use the given ISO-format datetime instead of extracting from file metadata. Requires -t/--time.')
    parser.add_argument('-o', '--override', action='store_true', dest='override', help='Force XMP creation even if datetime is already embedded in the file. Requires -t/--time.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging.')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging.')
    args = parser.parse_args()

    # Require at least one of --time, --live-photos, or --previews
    if not (args.time or args.live_photos or args.previews):
        parser.error('At least one of -l/--live-photos, -t/--time, or -p/--previews must be specified.')

    # --iso and --override require --time
    if args.iso and not args.time:
        parser.error('-i/--iso requires -t/--time.')
    if args.override and not args.time:
        parser.error('-o/--override requires -t/--time.')

    # Parse the --iso datetime upfront
    iso_date = None
    if args.iso:
        try:
            iso_date = datetime.fromisoformat(args.iso)
        except ValueError:
            parser.error(f'Invalid ISO datetime format: {args.iso}')

    handler = StreamHandler()
    handler.setFormatter(ColoredFormatter('%(log_color)s%(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel('DEBUG' if args.debug else 'INFO' if (args.verbose or args.dry_run) else 'WARNING')

    result = run(['exiftool', '-ver'], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error('exiftool is not available. Please install exiftool and try again.')
        exit(1)
    exiftool_ver = parse(result.stdout.strip())
    if exiftool_ver < Version('13.10'):
        logger.error(f'exiftool version 13.10 or newer is required ({exiftool_ver} installed). Please update exiftool and try again.')
        exit(1)
    
    # Accept a directory, a single file, or a glob pattern
    file_paths = []
    if isdir(args.path):
        for root, dirs, files in walk(args.path):
            for file in files:
                if file.lower().endswith((EXTs)) and not file.startswith('._'):
                    file_paths.append(join(root, file))
    elif isfile(args.path):
        # Single file
        if args.path.lower().endswith(EXTs) and not basename(args.path).startswith('._'):
            file_paths = [args.path]
        else:
            logger.error(f"File {args.path} is not a supported media file.")
            exit(1)
    else:
        # Treat as glob pattern
        matches = glob(args.path, recursive=True)
        for m in matches:
            if isfile(m) and m.lower().endswith(EXTs) and not basename(m).startswith('._'):
                file_paths.append(m)
        if not file_paths:
            logger.error(f'No media files found for pattern: {args.path}')
            exit(1)
    file_paths.sort()

    # Identify and handle preview files before pair/single processing
    recycled_files: list[str] = []
    if args.previews:
        if isfile(args.path):
            # Single file: discover group from directory
            dir_path = dirname(args.path) or '.'
            target_stem, _ = splitext(args.path)
            group_files = []
            for f in listdir(dir_path):
                full = join(dir_path, f)
                stem, _ = splitext(full)
                if stem == target_stem and isfile(full) and f.lower().endswith(EXTs) and not f.startswith('._'):
                    group_files.append(full)
            preview_files = find_preview_files(group_files)
        else:
            preview_files = find_preview_files(file_paths)
        recycled_files = recycle_previews(preview_files, dry_run=args.dry_run)
        # Remove recycled files from file_paths so they are not processed further
        recycled_set = set(recycled_files)
        file_paths = [fp for fp in file_paths if fp not in recycled_set]

    file_pairs = defaultdict(list)
    for file_path in file_paths:
        root, ext = splitext(file_path)
        file_pairs[root].append(ext)

    processed_files = []
    for file, exts in file_pairs.items():
        if len(exts) == 2:
            # Verify this is an image+video pair (not two images or two videos)
            pair_files = [f'{file}{ext}' for ext in exts]
            if not (any(is_image(f) for f in pair_files) and any(is_video(f) for f in pair_files)):
                logger.debug(f"Skipping non-Live-Photo pair {file} (not an image+video combination).")
                continue
            logger.debug(f"Processing file pair: {file}")
            pair_creation_date = None
            pair_content_id = None
            skip = False
            from_track = False
            date_in_exif = False
            
            # Build tag list based on flags
            tags = []
            if args.live_photos:
                tags.append('MakerNotes:ContentIdentifier')
            if args.time:
                tags.extend(['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated', 'XMP:CreateDate', 'MediaCreateDate', 'TrackCreateDate'])
            
            for ext in exts:
                file_path = f'{file}{ext}'
                metadata = exif_tool(file_path, tags)
                
                # Only process datetime if --time flag is passed
                if args.time:
                    if iso_date:
                        pair_creation_date = iso_date
                    else:
                        creation_date, from_track, field_name = get_creation_date(metadata)
                        if creation_date:
                            if field_name in ('DateTimeOriginal', 'CreateDate') and not args.override:
                                logger.debug(f'Datetime already exposed in EXIF ({field_name}) for {file_path}, skipping XMP creation for datetime.')
                                date_in_exif = True
                                pair_creation_date = None
                            else:
                                if field_name in ('DateTimeOriginal', 'CreateDate') and args.override:
                                    logger.info(f'Overriding existing EXIF datetime ({field_name}) for {file_path}.')
                                try:
                                    pair_creation_date = datetime.fromisoformat(creation_date)
                                except ValueError:
                                    logger.warning(f'Invalid creation date format "{creation_date}" in {file_path}, skipping date.')
                                    pair_creation_date = None
                        else:
                            logger.debug(f'No creation date in paired file {file_path}.')

                # Only process ContentIdentifier if live photos flag is passed
                if args.live_photos:
                    content_id = metadata.get('ContentIdentifier')
                    if content_id:
                        if pair_content_id and pair_content_id != content_id:
                            logger.warning(f'Content ID mismatch in {file_path}.')
                            skip = True
                            break
                        pair_content_id = content_id
                    else:
                        if not pair_content_id:
                            logger.info(f'Creating Missing Content ID for {file_path}.')
                            pair_content_id = str(uuid4())
            
            if not skip:
                has_xmp = isfile(f'{file}{exts[0]}.xmp') or isfile(f'{file}{exts[1]}.xmp')
                should_process = args.force or (args.recalculate and has_xmp) or not has_xmp
                
                # Determine if we would write an XMP file (consider both live-photo content ID and datetime flags)
                would_write_xmp = (args.live_photos and pair_content_id is not None) or (args.time and pair_creation_date is not None)
                
                # If in force or recalculate mode and we wouldn't write an XMP, delete existing ones
                if (args.force or args.recalculate) and has_xmp and not would_write_xmp:
                    for ext in exts:
                        xmp_path = f'{file}{ext}.xmp'
                        if isfile(xmp_path):
                            if args.dry_run:
                                logger.info(f'Would delete XMP file that would not be recreated: {xmp_path}')
                            else:
                                logger.info(f'Deleting XMP file that would not be recreated: {xmp_path}')
                                remove(xmp_path)
                elif not should_process:
                    logger.warning(f'XMP file already exists for pair {file}, skipping.')
                elif args.recalculate and not has_xmp:
                    logger.debug(f'Skipping pair {file} (no existing XMP file in recalculate mode).')
                elif would_write_xmp:
                    if from_track and args.time:
                        logger.info(f"Recovered creation date from track metadata for {file}")
                    for ext in exts:
                        if args.dry_run:
                            logger.info(f"Would write XMP Content ID {'& Date' if pair_creation_date else ''} file: {file}{ext}.xmp")
                        else:
                            with open(f'{file}{ext}.xmp', 'w') as f:
                                logger.info(f"Writing XMP Content ID {'& Date' if pair_creation_date else ''} file: {file}{ext}.xmp")
                                f.write(xmp(pair_creation_date, pair_content_id if args.live_photos else None))
                        processed_files.append(f'{file}{ext}')

    # Process single files (non-Live Photos) if --time flag is passed
    if args.time:
        for file_path in file_paths:
            if file_path not in processed_files:
                # If --iso is given, use that datetime directly
                if iso_date:
                    file_creation_date = iso_date
                    from_track = False
                else:
                    metadata = exif_tool(file_path, ['EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'XMP:DateCreated', 'XMP:CreateDate', 'MediaCreateDate', 'TrackCreateDate'])
                    creation_date, from_track, field_name = get_creation_date(metadata)
                    file_creation_date = None
                    
                    if creation_date:
                        # Skip if datetime is already exposed in EXIF (unless --override)
                        if field_name in ('DateTimeOriginal', 'CreateDate') and not args.override:
                            logger.debug(f'Datetime already exposed in EXIF ({field_name}) for {file_path}, skipping XMP creation.')
                            continue
                        if field_name in ('DateTimeOriginal', 'CreateDate') and args.override:
                            logger.info(f'Overriding existing EXIF datetime ({field_name}) for {file_path}.')
                        
                        try:
                            file_creation_date = datetime.fromisoformat(creation_date)
                        except ValueError:
                            logger.warning(f'Invalid creation date format "{creation_date}" in {file_path}, skipping.')
                            continue
                    else:
                        # No creation date found - try to infer from nearest file in the same directory
                        inferred_date, source_file = find_nearest_datetime(file_path)
                        if inferred_date:
                            logger.info(f'Inferred creation date from {source_file} for {file_path}.')
                            file_creation_date = inferred_date
                        else:
                            has_xmp = isfile(f'{file_path}.xmp')
                            if (args.force or args.recalculate) and has_xmp:
                                if args.dry_run:
                                    logger.info(f'Would delete XMP file for file with no creation date: {file_path}.xmp')
                                else:
                                    logger.info(f'Deleting XMP file for file with no creation date: {file_path}.xmp')
                                    remove(f'{file_path}.xmp')
                            else:
                                logger.warning(f'No creation date could be inferred for {file_path}, skipping.')
                            continue

                root, ext = splitext(file_path)
                has_xmp = isfile(f'{file_path}.xmp')
                should_process = args.force or (args.recalculate and has_xmp) or not has_xmp
                
                if not should_process:
                    logger.warning(f'XMP file already exists for file {file_path}, skipping.')
                elif args.recalculate and not has_xmp:
                    logger.debug(f'Skipping {file_path} (no existing XMP file in recalculate mode).')
                else:
                    if from_track:
                        logger.info(f"Recovered creation date from track metadata for {file_path}")
                    if args.dry_run:
                        logger.info(f"Would write XMP Date file: {file_path}.xmp")
                    else:
                        with open(f'{file_path}.xmp', 'w') as f:
                            logger.info(f"Writing XMP Date file: {file_path}.xmp")
                            f.write(xmp(file_creation_date, None))
                    processed_files.append(file_path)
    else:
        # If --time is NOT passed, delete XMP files for single files in force/recalculate mode
        # since single files would not be processed without --time
        if args.force or args.recalculate:
            for file_path in file_paths:
                if file_path not in processed_files:
                    xmp_path = f'{file_path}.xmp'
                    if isfile(xmp_path):
                        if args.dry_run:
                            logger.info(f'Would delete XMP file for single file (--time not passed): {xmp_path}')
                        else:
                            logger.info(f'Deleting XMP file for single file (--time not passed): {xmp_path}')
                            remove(xmp_path)
    
    prefix = "Dry run complete" if args.dry_run else "Complete"
    wrote_verb = "Would write" if args.dry_run else "Wrote"
    recycled_verb = "Would recycle" if args.dry_run else "Recycled"
    print(f"{prefix}.\n{wrote_verb} {len(processed_files)} XMP files for {args.path}.")
    if recycled_files:
        print(f"{recycled_verb} {len(recycled_files)} low-quality preview files.")

if __name__ == "__main__":
    main()